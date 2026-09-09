import base64
import hashlib
import io
import ipaddress
import re
import socket
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler

from bs4 import BeautifulSoup, Comment
from PIL import Image, UnidentifiedImageError
import tinycss2

from .storage import AppError, atomic_write, inside

TAGS = set('p div span section article h1 h2 h3 h4 h5 h6 br hr strong b em i u s strike blockquote pre code ul ol li a img figure figcaption table thead tbody tfoot tr th td colgroup col sup sub mark small font'.split())
CSS = set('color background-color background font-size font-family font-weight font-style text-decoration text-align line-height letter-spacing white-space word-break overflow-wrap margin margin-top margin-bottom margin-left margin-right padding padding-top padding-bottom padding-left padding-right border border-top border-bottom border-left border-right border-color border-style border-width border-radius width height max-width min-width display vertical-align list-style-type'.split())
MEDIA_ID = re.compile(r'^[a-f0-9]{64}\.(?:jpg|png|gif|webp)$')


def sanitize_css(value):
    declarations = []
    for part in tinycss2.parse_declaration_list(value, skip_comments=True, skip_whitespace=True):
        if part.type != 'declaration' or part.lower_name not in CSS:
            continue
        value = tinycss2.serialize(part.value).strip()
        lower = value.lower()
        if any(token in lower for token in ('url(', 'expression', 'javascript:', '@import', '\\', 'var(')):
            continue
        if part.lower_name == 'display' and lower not in ('block', 'inline', 'inline-block', 'table', 'table-cell'):
            continue
        declarations.append(f'{part.lower_name}:{value}')
    return ';'.join(declarations)


def sanitize_html(value):
    if not isinstance(value, str) or len(value.encode()) > 5 * 1024 * 1024:
        raise AppError('文章正文过大，请将图片通过图片按钮插入。')
    soup = BeautifulSoup(value, 'html.parser')
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()
    for tag in list(soup.find_all()):
        if tag.name is None:
            continue
        if tag.name in ('script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'svg', 'math'):
            tag.decompose()
            continue
        if tag.name not in TAGS:
            tag.unwrap()
            continue
        if tag.name == 'font':
            extra = ';'.join(f'{prop}:{tag[attr]}' for attr, prop in [('color', 'color'), ('face', 'font-family')] if tag.has_attr(attr))
            tag['style'] = tag.get('style', '') + ';' + extra
            tag.name = 'span'
        attrs = {}
        style = sanitize_css(tag.get('style', ''))
        if style:
            attrs['style'] = style
        if tag.name == 'a':
            href = tag.get('href', '').strip()
            if urlsplit(href).scheme.lower() in ('http', 'https', 'mailto') or href.startswith(('#', '/')) and not href.startswith('//'):
                attrs.update(href=href, target='_blank', rel='noopener noreferrer')
        if tag.name == 'img':
            source = tag.get('data-src') or tag.get('src', '')
            source = source.strip()
            if source.startswith(('/media/', '/assets/')):
                source = urlsplit(source).path
            if not source.startswith(('/media/', '/assets/', 'https://', 'http://', 'data:image/')):
                tag.decompose()
                continue
            attrs.update(src=source, alt=tag.get('alt', '')[:500])
            for dimension in ['width', 'height']:
                if re.fullmatch(r'\d{1,5}', str(tag.get(dimension, ''))):
                    attrs[dimension] = str(tag[dimension])
        for attr in ('colspan', 'rowspan', 'span', 'start'):
            if re.fullmatch(r'\d{1,3}', str(tag.get(attr, ''))):
                attrs[attr] = tag[attr]
        tag.attrs = attrs
    return str(soup)


def check_remote_url(url, article=False):
    parsed = urlsplit(url)
    allowed = ('mp.weixin.qq.com',) if article else ('mp.weixin.qq.com', 'qpic.cn', 'qlogo.cn')
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise AppError('链接格式不正确，请使用微信文章的 HTTP/HTTPS 链接。')
    if not any(host == domain or host.endswith('.' + domain) for domain in allowed):
        raise AppError('仅支持微信公众号文章及其微信图片地址。')
    if article and not (parsed.path == '/s' or parsed.path.startswith('/s/')):
        raise AppError('请输入 mp.weixin.qq.com/s 开头的文章链接。')
    for result in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise AppError('不允许访问本机或内网地址。')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_wechat(url, limit=8 * 1024 * 1024, article=False):
    opener = build_opener(NoRedirect)
    for _ in range(6):
        check_remote_url(url, article)
        request = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36',
            'Referer': 'https://mp.weixin.qq.com/', 'Accept-Encoding': 'identity'})
        try:
            response = opener.open(request, timeout=25)
        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308) and error.headers.get('Location'):
                url = urljoin(url, error.headers['Location'])
                continue
            raise AppError(f'微信返回 HTTP {error.code}，请在浏览器中确认链接可访问。') from error
        with response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise AppError('远程文件超过大小限制。')
            return data
    raise AppError('微信链接重定向次数过多。')


class Media:
    def __init__(self, store, fetch=fetch_wechat):
        self.store = store
        self.fetch = fetch

    def add(self, data):
        if len(data) > 20 * 1024 * 1024:
            raise AppError('单张图片不能超过 20 MB。')
        try:
            with Image.open(io.BytesIO(data)) as picture:
                width, height = picture.size
                kind = picture.format
                if kind not in ('PNG', 'JPEG', 'GIF', 'WEBP') or width * height > 40_000_000:
                    raise AppError('支持 PNG、JPEG、GIF、WebP，图片不能超过 4000 万像素。')
                picture.verify()
        except (OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise AppError('无法识别图片，请使用有效的 PNG、JPEG、GIF 或 WebP 文件。') from error
        ext = {'JPEG': 'jpg', 'PNG': 'png', 'GIF': 'gif', 'WEBP': 'webp'}[kind]
        key = hashlib.sha256(data).hexdigest() + '.' + ext
        file = self.store.directory / 'media' / key
        if not file.exists():
            atomic_write(file, data)
        return {'src': '/media/' + key, 'width': width, 'height': height, 'id': key}

    def upload(self, data_url):
        try:
            header, encoded = data_url.split(',', 1)
            if not header.startswith('data:image/') or ';base64' not in header:
                raise ValueError()
            return self.add(base64.b64decode(encoded, validate=True))
        except (ValueError, TypeError) as error:
            raise AppError('图片数据无效。') from error

    def localize(self, content, progress=lambda message: None):
        soup = BeautifulSoup(sanitize_html(content), 'html.parser')
        images = soup.find_all('img')
        if len(images) > 150:
            raise AppError('单篇文章最多支持 150 张图片。')
        cache, total = {}, 0
        for i, image in enumerate(images):
            source = image['src']
            if source.startswith('/media/'):
                if not MEDIA_ID.fullmatch(source[7:]) or not (self.store.directory / source.lstrip('/')).is_file():
                    raise AppError('草稿图片已丢失，请重新插入该图片。')
            elif source.startswith('/assets/'):
                if not inside(self.store.root(), source.lstrip('/')).is_file():
                    raise AppError('网站中的原图片不存在，请重新插入。')
            else:
                progress(f'正在保存图片 {i + 1}/{len(images)}')
                if source not in cache:
                    if source.startswith('data:image/'):
                        cache[source] = self.upload(source)
                    else:
                        data = self.fetch(source, limit=20 * 1024 * 1024)
                        total += len(data)
                        if total > 100 * 1024 * 1024:
                            raise AppError('本次导入的图片总量超过 100 MB。')
                        cache[source] = self.add(data)
                image['src'] = cache[source]['src']
                image['width'] = str(cache[source]['width'])
                image['height'] = str(cache[source]['height'])
        return str(soup)

    def import_article(self, url, progress=lambda message: None):
        parsed = urlsplit(url.strip())
        if parsed.hostname != 'mp.weixin.qq.com' or not parsed.path.startswith('/s'):
            raise AppError('请输入完整的微信公众号文章链接。')
        progress('正在获取微信正文')
        data = self.fetch(url, article=True)
        text = data.decode('utf-8', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')
        body = soup.select_one('#js_content')
        if not body or not body.get_text(strip=True) and not body.find('img'):
            raise AppError('微信未返回可导入的正文，可能需要验证或文章已失效。请在浏览器打开原文后复制正文到编辑区。')
        title = soup.select_one('#activity-name, .rich_media_title')
        meta_title = soup.find('meta', property='og:title')
        author = soup.select_one('#js_name, #js_author_name, .rich_media_meta_text')
        content = self.localize(str(body), progress)
        description = BeautifulSoup(content, 'html.parser').get_text(' ', strip=True)[:160]
        return {'title': title.get_text(strip=True) if title else (meta_title.get('content', '') if meta_title else ''),
                'author': author.get_text(strip=True) if author else '', 'description': description,
                'source_url': url, 'content_html': content,
                'published_at': datetime.now().astimezone().isoformat(timespec='minutes')}
