"""Convert optimized static exports to AMP. Requires BeautifulSoup and Pillow."""
from pathlib import Path
import re
import json
import html
from bs4 import BeautifulSoup, Comment, NavigableString
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BOILERPLATE = 'body{-webkit-animation:-amp-start 8s steps(1,end) 0s 1 normal both;-moz-animation:-amp-start 8s steps(1,end) 0s 1 normal both;-ms-animation:-amp-start 8s steps(1,end) 0s 1 normal both;animation:-amp-start 8s steps(1,end) 0s 1 normal both}@-webkit-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}@-moz-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}@-ms-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}@-o-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}@keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}'
GLOBAL = {'id', 'class', 'title', 'lang', 'dir', 'role', 'tabindex', 'hidden', 'itemscope', 'itemtype', 'itemprop', 'itemid', 'itemref'}
ATTRS = {
    'a': {'href', 'target', 'rel', 'download', 'hreflang', 'type'},
    'time': {'datetime'}, 'ol': {'start', 'reversed', 'type'}, 'li': {'value'},
    'td': {'colspan', 'rowspan', 'headers'}, 'th': {'colspan', 'rowspan', 'headers', 'scope'},
    'col': {'span'}, 'colgroup': {'span'},
    'amp-img': {'src', 'alt', 'width', 'height', 'layout', 'srcset'},
    'amp-anim': {'src', 'alt', 'width', 'height', 'layout'},
    'amp-mathml': {'layout', 'inline'},
    'amp-carousel': {'width', 'height', 'layout', 'type', 'controls', 'loop', 'aria-label'},
}
ALLOWED = set('a abbr article aside b bdi bdo blockquote br caption cite code col colgroup dd del details dfn div dl dt em figcaption figure footer h1 h2 h3 h4 h5 h6 header hgroup hr i ins kbd li main mark nav ol p pre q rp rt ruby s samp section small span strong sub summary sup table tbody td tfoot th thead time tr u ul var wbr'.split()) | set(ATTRS)


def clean_css(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'!\s*important', '', css, flags=re.I)
    css = re.sub(r'(?<![\w-])(?:-ms-)?behavior\s*:[^;}]+;?', '', css, flags=re.I)
    css = css.replace('.content img', '.content amp-img, .content amp-anim').replace('.post-content img', '.post-content amp-img, .post-content amp-anim')
    css = re.sub(r'(?<![\w-])img\s*\{', 'amp-img, amp-anim {', css)
    return re.sub(r'\s+', ' ', css).strip()


def convert(page):
    soup = BeautifulSoup(page.read_text(encoding='utf-8'), 'html.parser')
    if soup.html.has_attr('amp'):
        repair(soup)
        page.write_text(str(soup).rstrip() + '\n', encoding='utf-8')
        return False
    title = soup.title.get_text() if soup.title else '哆嗒数学网'
    relative = page.relative_to(ROOT).as_posix()
    titles = {'blog/index.html': '数学趣闻与故事 - 哆嗒数学网·博客',
              'blog/archive.html': '近期文章归档 - 哆嗒数学网',
              'blog/about.html': '关于我们 - 哆嗒数学网'}
    title = titles.get(relative, title)
    description = soup.find('meta', attrs={'name': 'description'})
    description = description.get('content', '') if description else title
    if description == title:
        paragraphs = soup.select('.content p, .post-content p')
        description = next((p.get_text(' ', strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40), title)
    description = re.sub(r'\s+', ' ', html.unescape(description)).strip()[:160]
    published = soup.find('time', datetime=True)
    published = published['datetime'] if published else None
    first_image = soup.find('img', src=True)
    image_url = first_image['src'] if first_image else None
    if image_url and image_url.startswith('/'):
        image_url = 'https://duodaa.com' + image_url
    css_parts = []
    for link in soup.head.find_all('link', rel='stylesheet'):
        path = ROOT / link['href'].lstrip('/')
        if path.exists():
            css_parts.append(path.read_text(encoding='utf-8'))
    css_parts += [tag.get_text() for tag in soup.head.find_all('style')]
    soup.head.clear()
    soup.html.attrs = {'amp': '', 'lang': 'zh-CN'}
    soup.body.attrs = {}
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in soup.body.find_all(['script', 'style', 'noscript']):
        tag.decompose()

    components = {'amp-auto-ads': '0.1'}
    # Preserve legacy video access when an obsolete Flash player cannot run in modern browsers.
    for tag in soup.body.find_all(['embed', 'iframe']):
        source = tag.get('src', '')
        link = soup.new_tag('a', href=source, target='_blank', rel='noopener noreferrer')
        link.string = '查看原视频'
        if source.startswith(('http://', 'https://')):
            tag.replace_with(link)
        else:
            tag.unwrap()

    for tag in soup.body.find_all('img'):
        source = tag.get('src', '')
        width, height = tag.get('width'), tag.get('height')
        local = ROOT / source.lstrip('/')
        if source.startswith('/') and local.is_file():
            try:
                with Image.open(local) as image:
                    width, height = image.size
            except OSError:
                pass
        width = float(width) if width and re.fullmatch(r'\d+(?:\.\d+)?', str(width)) else 640
        height = float(height) if height and re.fullmatch(r'\d+(?:\.\d+)?', str(height)) else 480
        style = tag.get('style', '')
        display_width = re.search(r'(?:^|;)\s*width\s*:\s*([\d.]+)px', style)
        if display_width and float(display_width[1]) > 0:
            height *= float(display_width[1]) / width
            width = float(display_width[1])
        tag['style'] = re.sub(r'(?:^|;)\s*(?:width|height)\s*:[^;]*', '', style)
        tag.name = 'amp-anim' if source.lower().endswith('.gif') else 'amp-img'
        tag['width'], tag['height'] = str(max(1, round(width))), str(max(1, round(height)))
        tag['layout'] = 'intrinsic'
        tag['alt'] = tag.get('alt', '')
        if tag.name == 'amp-anim':
            components['amp-anim'] = '0.1'

    # Keep TeX math with the official AMP MathML component; skip code examples.
    pattern = re.compile(r'\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\$])\$(?!\$)([^$\n]+?)(?<!\\)\$(?!\$)', re.S)
    for node in list(soup.body.find_all(string=True)):
        if any(parent.name in ('code', 'pre', 'amp-mathml') or 'ql-code-block' in parent.get('class', []) for parent in node.parents):
            continue
        text = str(node)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        position = 0
        for match in matches:
            node.insert_before(NavigableString(text[position:match.start()]))
            formula = next(group for group in match.groups() if group is not None)
            block = match[1] is not None or match[2] is not None
            math = soup.new_tag('amp-mathml', layout='container')
            math['data-formula'] = ('\\[' if block else '\\(') + formula + ('\\]' if block else '\\)')
            if not block:
                math['inline'] = ''
            node.insert_before(math)
            position = match.end()
        node.insert_before(NavigableString(text[position:]))
        node.extract()
        components['amp-mathml'] = '0.1'

    inline_styles = {}
    for tag in list(soup.body.find_all()):
        if tag.name == 'font':
            declarations = tag.get('style', '')
            for attr, prop in [('color', 'color'), ('face', 'font-family')]:
                if tag.has_attr(attr):
                    declarations += f';{prop}:{tag[attr]}'
            tag['style'] = declarations
            tag.name = 'span'
        if tag.name not in ALLOWED:
            tag.unwrap()
            continue
        style = clean_css(tag.get('style', '')).strip('; ')
        if style:
            name = inline_styles.setdefault(style, f'export-style-{len(inline_styles)}')
            tag['class'] = tag.get('class', []) + [name]
        for attr in list(tag.attrs):
            if attr not in GLOBAL | ATTRS.get(tag.name, set()) and not attr.startswith(('aria-', 'data-')):
                del tag[attr]
        if tag.name == 'a':
            if tag.get('href', '').startswith('javascript:'):
                del tag['href']
            if tag.get('target') == '_blank':
                tag['rel'] = 'noopener noreferrer'
        if tag.name == 'amp-carousel':
            components['amp-carousel'] = '0.1'
    css_parts.append('\n'.join(f'.{name}{{{style}}}' for style, name in inline_styles.items()))
    css_parts.append('amp-img,amp-anim{max-width:100%;vertical-align:middle}amp-mathml{max-width:100%;overflow-x:auto}amp-mathml[inline]{display:inline-block;vertical-align:middle}body{overflow-wrap:anywhere}')
    css = clean_css('\n'.join(css_parts))
    if len(css.encode()) > 75000:
        raise ValueError(f'{page}: AMP CSS exceeds 75 KB: {len(css.encode())}')

    def add(tag_name, **attrs):
        tag = soup.new_tag(tag_name, attrs=attrs)
        soup.head.append(tag)
        return tag

    add('meta', charset='utf-8')
    add('meta', name='viewport', content='width=device-width,minimum-scale=1,initial-scale=1')
    add('title').string = title
    add('meta', name='description', content=description)
    if relative == '404.html':
        add('meta', name='robots', content='noindex, follow')
    path = '/' + page.relative_to(ROOT).as_posix()
    if path.endswith('index.html'):
        path = path[:-10]
    add('link', rel='canonical', href='https://duodaa.com' + path)
    url = 'https://duodaa.com' + path
    is_article = bool(re.match(r'blog/(?:old_articles/\d+|articles/[^/]+)/index\.html$', relative))
    for prop, value in {'og:title': title, 'og:description': description, 'og:url': url,
                        'og:type': 'article' if is_article else 'website',
                        'og:site_name': '哆嗒数学网', 'og:locale': 'zh_CN'}.items():
        add('meta', property=prop, content=value)
    add('meta', name='twitter:card', content='summary_large_image' if image_url else 'summary')
    if image_url:
        add('meta', property='og:image', content=image_url)
    schema = {'@context': 'https://schema.org', '@type': 'BlogPosting' if is_article else 'WebPage',
              'name': title, 'description': description, 'url': url, 'inLanguage': 'zh-CN'}
    if is_article:
        schema.update({'headline': title, 'mainEntityOfPage': url,
                       'publisher': {'@type': 'Organization', 'name': '哆嗒数学网', 'url': 'https://duodaa.com/'}})
        if published:
            schema['datePublished'] = published
        if image_url:
            schema['image'] = image_url
    elif relative == 'index.html':
        schema['@type'] = 'WebSite'
    elif relative.endswith('archive.html') or relative == 'blog/old_articles/index.html':
        schema['@type'] = 'CollectionPage'
    elif relative == 'blog/about.html':
        schema['@type'] = 'AboutPage'
    add('script', type='application/ld+json').string = json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c')
    add('link', rel='icon', href='/favicon.ico')
    add('script', **{'async': '', 'src': 'https://cdn.ampproject.org/v0.js'})
    for component, version in sorted(components.items()):
        add('script', **{'async': '', 'custom-element': component, 'src': f'https://cdn.ampproject.org/v0/{component}-{version}.js'})
    add('style', **{'amp-boilerplate': ''}).string = BOILERPLATE
    noscript = add('noscript')
    fallback = soup.new_tag('style', attrs={'amp-boilerplate': ''})
    fallback.string = 'body{-webkit-animation:none;-moz-animation:none;-ms-animation:none;animation:none}'
    noscript.append(fallback)
    add('style', **{'amp-custom': ''}).string = css
    ads = soup.new_tag('amp-auto-ads', attrs={'type': 'adsense', 'data-ad-client': 'ca-pub-9319230211682138'})
    soup.body.insert(0, ads)
    repair(soup)
    page.write_text(str(soup).rstrip() + '\n', encoding='utf-8')
    return True


def repair(soup):
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get('href') == 'https://duodaa.com/blog/' and not soup.body.find('h1'):
        heading = soup.new_tag('h1')
        heading.string = '数学趣闻与故事'
        soup.body.find('main').insert(0, heading)
    for style in soup.select('style[amp-custom]'):
        style.string = style.string.replace('scroll- }', 'scroll-behavior:auto }')
    for tag in soup.select('amp-img, amp-anim'):
        if tag.get('src', '').startswith(('file:', '//:')):
            fallback = soup.new_tag('span', attrs={'class': 'missing-image'})
            fallback.string = tag.get('alt') or '原文图片暂不可用'
            tag.replace_with(fallback)
    for link in soup.select('a[target]'):
        if link['target'] not in ('_blank', '_self', '_top'):
            link['target'] = '_blank'
            link['rel'] = 'noopener noreferrer'


if __name__ == '__main__':
    count = sum(convert(page) for page in [*sorted(ROOT.glob('*.html')), *sorted((ROOT / 'blog').rglob('*.html'))])
    print(f'Converted {count} pages to AMP.')
