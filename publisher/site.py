"""Build a reviewable publication plan without changing the selected website."""
import hashlib
import html
import importlib.util
import json
import re
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import tinycss2

from .content import Media, MEDIA_ID, sanitize_html, sanitize_css
from .storage import AppError, inside, atomic_write, write_json


def digest(data):
    return hashlib.sha256(data).hexdigest()


def soup_of(value):
    return BeautifulSoup(value, 'html.parser')


def valid_id(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,120}', value or ''):
        raise AppError('文章编号不正确。')
    return value


def article_file(root, key):
    return inside(root, 'blog/articles/' + valid_id(key) + '/index.html')


def date_value(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise AppError('发布日期格式不正确。')
    return result.astimezone() if result.tzinfo is None else result


def metadata(page):
    soup = soup_of(page.read_text(encoding='utf-8'))
    heading = soup.select_one('article h1, h1')
    date = soup.select_one('time[datetime]')
    value = date.get('datetime') if date else ''
    if not value:
        date = soup.select_one('.meta')
        match = re.search(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?', date.get_text() if date else '')
        value = match[0] if match else '1970-01-01T00:00:00+00:00'
    description = soup.select_one('meta[name="description"]')
    return {'article_id': page.parent.name, 'title': heading.get_text(' ', strip=True) if heading else soup.title.get_text(),
            'published_at': date_value(value).isoformat(timespec='seconds'),
            'description': description.get('content', '') if description else '',
            'url': '/blog/articles/' + page.parent.name + '/', 'revision': digest(page.read_bytes())}


def articles(root):
    result = [metadata(page) for page in (root / 'blog/articles').glob('*/index.html')]
    return sorted(result, key=lambda row: (date_value(row['published_at']), row['article_id']), reverse=True)


def load_article(root, key):
    page = article_file(root, key)
    if not page.is_file():
        raise AppError('文章不存在。')
    result = metadata(page)
    source = inside(root, 'content/articles/' + key + '.json')
    if source.exists():
        saved = json.loads(source.read_text(encoding='utf-8'))
        if saved.get('rendered_sha256') == result['revision']:
            saved.update(result)
            return saved
    soup = soup_of(page.read_text(encoding='utf-8'))
    content = soup.select_one('article .content, .post-content')
    if content is None:
        raise AppError('文章格式无法识别。')
    styles = {}
    style = soup.select_one('style[amp-custom]')
    for rule in tinycss2.parse_stylesheet(style.string if style else '', skip_comments=True, skip_whitespace=True):
        if rule.type == 'qualified-rule':
            selector = tinycss2.serialize(rule.prelude).strip()
            if re.fullmatch(r'\.export-style-\d+', selector):
                styles[selector[1:]] = tinycss2.serialize(rule.content)
    for node in content.find_all():
        node['style'] = ';'.join([styles.get(name, '') for name in node.get('class', [])] + [node.get('style', '')])
        if node.name in ('amp-img', 'amp-anim'):
            node.name = 'img'
            node['style'] += ';width:' + str(node.get('width', '640')) + 'px;height:auto'
        elif node.name == 'amp-mathml':
            node.replace_with(node.get('data-formula', ''))
    author = soup.select_one('meta[name="author"]')
    source_link = soup.select_one('.source-note a')
    result.update(content_html=sanitize_html(content.decode_contents()), author=author.get('content', '') if author else '',
                  source_url=source_link.get('href', '') if source_link else '')
    return result


def amp_engine():
    if getattr(sys, 'frozen', False):
        source = Path(sys._MEIPASS) / 'engine/convert_amp.py'
    else:
        source = Path(__file__).resolve().parents[1] / 'scripts/convert_amp.py'
    spec = importlib.util.spec_from_file_location('publisher_amp_engine', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fragment(target, value):
    target.clear()
    for child in list(soup_of(value).contents):
        target.append(child)


def render_recent(rows):
    return ''.join(f'<li><a href="{row["url"]}">{html.escape(row["title"])}</a></li>' for row in rows)


def serialize(soup):
    return (str(soup).rstrip() + '\n').encode('utf-8')


class Plan:
    def __init__(self, store, document, progress=lambda value: None):
        self.store, self.root, self.config = store, store.root(), store.config()
        self.id = uuid.uuid4().hex
        self.folder = store.directory / 'previews' / self.id
        self.folder.mkdir(parents=True)
        self.files, self.before = {}, {}
        self.document = dict(document)
        self.build(progress)

    def put(self, relative, data):
        target = inside(self.root, relative)
        current = target.read_bytes() if target.exists() else None
        if current == data:
            self.files.pop(relative, None)
            self.before.pop(relative, None)
            return
        self.files[relative] = data
        self.before[relative] = digest(current) if current is not None else None
        atomic_write(inside(self.folder, relative), data)

    def build(self, progress):
        config, root, doc = self.config, self.root, self.document
        doc['title'] = str(doc.get('title', '')).strip()
        if not doc['title'] or len(doc['title']) > 200:
            raise AppError('请填写 1–200 字的文章标题。')
        doc['author'] = str(doc.get('author', '')).strip()[:100]
        content = Media(self.store).localize(doc.get('content_html', ''), progress)
        body = soup_of(content)
        if not body.get_text(strip=True) and not body.find('img'):
            raise AppError('文章正文不能为空。')
        key = doc.get('article_id')
        if key:
            existing = article_file(root, key)
            if not existing.exists() or digest(existing.read_bytes()) != doc.get('revision'):
                raise AppError('这篇文章已被其他操作更新，请重新打开文章后再编辑。')
        else:
            key = datetime.now().strftime('%Y-%m-%d-%H-%M-%S-') + uuid.uuid4().hex[:8]
        doc['article_id'] = valid_id(key)
        self.article_path = 'blog/articles/' + key + '/index.html'
        for image in body.find_all('img'):
            source = image['src']
            if source.startswith('/media/'):
                name = source[7:]
                if not MEDIA_ID.fullmatch(name):
                    raise AppError('图片标识无效。')
                data = (self.store.directory / 'media' / name).read_bytes()
                relative = 'assets/images/' + name
                self.put(relative, data)
                image['src'] = '/' + relative
            elif not source.startswith('/assets/'):
                raise AppError('正文中仍有未保存到本地的图片。')
            asset = inside(root, image['src'].lstrip('/'))
            staged = inside(self.folder, image['src'].lstrip('/'))
            if not staged.exists() and asset.is_file():
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(asset, staged)
        doc['content_html'] = str(body)
        description = str(doc.get('description', '')).strip() or body.get_text(' ', strip=True)[:160]
        doc['description'] = description[:300]
        published = date_value(doc.get('published_at') or datetime.now().astimezone().isoformat()).astimezone()
        doc['published_at'] = published.isoformat(timespec='seconds')
        source = str(doc.get('source_url', '')).strip()
        if source and not re.match(r'^https?://', source):
            raise AppError('原文链接必须使用 HTTP 或 HTTPS。')
        progress('正在生成 AMP 文章和 SEO 信息')
        for name in ['blog.css', 'site.css']:
            path = root / 'assets' / name
            if not path.is_file():
                raise AppError(f'网站缺少 assets/{name}，请选择正确的网站主文件夹。')
            target = self.folder / 'assets' / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, target)
        footer = soup_of((root / 'blog/index.html').read_text(encoding='utf-8')).find('footer')
        source_html = f'<p class="source-note">原文链接：<a href="{html.escape(source, quote=True)}" target="_blank" rel="noopener noreferrer">阅读原文</a></p>' if source else ''
        e = html.escape
        page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(doc['title'])} - {e(config['site_name'])}</title><meta name="description" content="{e(doc['description'], quote=True)}"><link rel="stylesheet" href="/assets/blog.css"><link rel="stylesheet" href="/assets/site.css"></head><body>
<header><nav class="nav"><a class="logo" href="/blog/">{e(config['site_name'])}·博客</a><div><a href="/">网站首页</a><a href="/blog/">博客</a><a href="/blog/archive.html">归档</a><a href="/blog/old_articles/">经典文章</a><a href="/blog/about.html">关于</a></div></nav></header>
<main class="container"><article class="article"><h1>{e(doc['title'])}</h1><div class="meta"><time datetime="{doc['published_at']}">{published.strftime('%Y-%m-%d %H:%M')}</time> · {e(doc['author'])}</div><div class="content">{doc['content_html']}</div>{source_html}<a class="back" href="/blog/">← 返回博客</a><nav class="nav-posts" aria-label="文章导航"></nav></article><aside class="sidebar"><div class="box"><h3>近期文章</h3><ul class="list"></ul></div></aside></main>{str(footer) if footer else ''}</body></html>'''
        staged_article = inside(self.folder, self.article_path)
        atomic_write(staged_article, page.encode('utf-8'))
        amp_engine().convert(staged_article, root=self.folder, site_url=config['site_url'], site_name=config['site_name'], ad_client=config['ad_client'])
        generated = soup_of(staged_article.read_text(encoding='utf-8'))
        author_meta = generated.new_tag('meta', attrs={'name': 'author', 'content': doc['author']})
        generated.head.append(author_meta)
        schema_tag = generated.select_one('script[type="application/ld+json"]')
        schema = json.loads(schema_tag.string)
        if doc['author']:
            schema['author'] = {'@type': 'Person', 'name': doc['author']}
        if doc.get('revision'):
            schema['dateModified'] = datetime.now().astimezone().isoformat(timespec='seconds')
        schema_tag.string = json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c')
        self.put(self.article_path, serialize(generated))
        rows = [row for row in articles(root) if row['article_id'] != key]
        rows.append({'article_id': key, 'title': doc['title'], 'published_at': doc['published_at'],
                     'description': doc['description'], 'url': '/blog/articles/' + key + '/'})
        rows.sort(key=lambda row: (date_value(row['published_at']), row['article_id']), reverse=True)
        recent = rows[:config['recent_count']]
        progress('正在同步近期文章、前后篇导航和归档')
        # Modern pages have a sidebar; legacy pages without it are left intact.
        candidates = set(path.relative_to(root).as_posix() for path in (root / 'blog').rglob('*.html')) | {self.article_path}
        for relative in sorted(candidates):
            data = self.files.get(relative)
            if data is None:
                data = inside(root, relative).read_bytes()
            text = data.decode('utf-8')
            if '<aside' not in text and relative not in ('blog/index.html', 'blog/archive.html') and not relative.startswith('blog/articles/'):
                continue
            soup = soup_of(text)
            changed = False
            for listing in soup.select('.sidebar .list'):
                fragment(listing, render_recent(recent))
                changed = True
            if relative.startswith('blog/articles/'):
                row_key = relative.split('/')[2]
                index = next((i for i, row in enumerate(rows) if row['article_id'] == row_key), None)
                nav = soup.select_one('.nav-posts')
                if nav is None and soup.select_one('article'):
                    nav = soup.new_tag('nav', attrs={'class': 'nav-posts', 'aria-label': '文章导航'})
                    soup.select_one('article').append(nav)
                if nav is not None and index is not None:
                    links = []
                    if index > 0:
                        row = rows[index - 1]
                        links.append(f'<a class="prev" href="{row["url"]}">← 上一篇：{e(row["title"])}</a>')
                    if index + 1 < len(rows):
                        row = rows[index + 1]
                        links.append(f'<a class="next" href="{row["url"]}">下一篇：{e(row["title"])} →</a>')
                    fragment(nav, ''.join(links))
                    changed = True
            if relative == 'blog/index.html':
                cards = '<h1>数学趣闻与故事</h1>' + ''.join(f'<article class="post"><div class="meta">{e(row["published_at"][:10])}</div><h2><a href="{row["url"]}">{e(row["title"])}</a></h2><p>{e(row["description"])}</p><p><a href="{row["url"]}">阅读全文 →</a></p></article>' for row in recent)
                fragment(soup.find('main'), cards)
                changed = True
            if relative == 'blog/archive.html':
                listing = soup.select_one('.archive-list')
                if listing is None:
                    raise AppError('归档页面缺少文章列表，请检查网站结构。')
                fragment(listing, ''.join(f'<div class="archive-item"><time class="archive-date" datetime="{row["published_at"]}">{row["published_at"][:10]}</time><a class="archive-link" href="{row["url"]}">{e(row["title"])}</a></div>' for row in rows))
                changed = True
            if changed:
                self.put(relative, serialize(soup))
        doc.pop('draft_id', None)
        doc.pop('site_root', None)
        doc['rendered_sha256'] = digest(self.files[self.article_path])
        self.put('content/articles/' + key + '.json', json.dumps(doc, ensure_ascii=False, indent=2).encode('utf-8'))
        ET.register_namespace('', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset = ET.Element('{http://www.sitemaps.org/schemas/sitemap/0.9}urlset')
        paths = {'index.html'} | {p.relative_to(root).as_posix() for p in (root / 'blog').rglob('*.html')} | {self.article_path}
        for path in sorted(paths):
            url = '/' + path
            if url.endswith('index.html'):
                url = url[:-10]
            node = ET.SubElement(urlset, 'url')
            ET.SubElement(node, 'loc').text = config['site_url'] + url
        ET.indent(urlset)
        self.put('sitemap.xml', ET.tostring(urlset, encoding='utf-8', xml_declaration=True))
        self.html_files = [name for name in self.files if name.endswith('.html')]
        for path in self.html_files:
            self.check_page(path)
        self.digest = digest(b''.join(name.encode() + b'\0' + self.files[name] for name in sorted(self.files)))

    def check_page(self, path):
        soup = soup_of(self.files[path].decode('utf-8'))
        if not soup.html.has_attr('amp') or not soup.select_one('link[rel="canonical"]'):
            raise AppError(f'{path} 缺少 AMP 或 SEO 基础信息。')
        css = soup.select_one('style[amp-custom]')
        if not css or len(css.get_text().encode()) > 75000:
            raise AppError(f'{path} 的样式超过 AMP 限制，请精简正文样式。')
        for script in soup.select('script[src]'):
            if not script['src'].startswith('https://cdn.ampproject.org/'):
                raise AppError('生成的页面包含 AMP 不支持的脚本。')
        for image in soup.select('amp-img, amp-anim'):
            value = image.get('src', '')
            if value.startswith('/media/') or value.startswith('data:'):
                raise AppError('生成页面中的图片未正确保存。')
            if value.startswith('/'):
                relative = value.lstrip('/')
                if relative not in self.files and not inside(self.root, relative).is_file():
                    raise AppError('生成页面引用的图片不存在。')

    def summary(self):
        return {'plan_id': self.id, 'digest': self.digest, 'article_id': self.document['article_id'],
                'article_path': self.article_path, 'files': [{'path': name, 'bytes': len(data)} for name, data in self.files.items()],
                'html': {name: self.files[name].decode('utf-8') for name in self.html_files}}
