"""Idempotent optimization for exported static pages (Python 3 + Pillow)."""
from pathlib import Path
import base64
import hashlib
import html
import io
import re
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)


def optimize():
    styles = {}
    for source, name in [('blog/index.html', 'blog.css'), ('blog/old_articles/1118/index.html', 'legacy.css')]:
        text = (ROOT / source).read_text(encoding='utf-8')
        match = re.search(r'<style>(.*?)</style>', text, re.S)
        if match:
            styles[match[0]] = name
            (ASSETS / name).write_text(match[1] + '\n', encoding='utf-8')

    footer_source = (ROOT / 'blog/index.html').read_text(encoding='utf-8')
    footer = re.search(r'<footer\b.*?</footer>', footer_source, re.S)[0]
    image_count = 0
    for page in sorted((ROOT / 'blog').rglob('*.html')):
        original = page.read_text(encoding='utf-8')
        if re.search(r'<html\b[^>]*\bamp(?:\s|=|>)', original):
            continue
        text = original
        if '<head>' not in text:
            links = re.findall(r'<a\b[^>]*>.*?</a>', text, re.S)
            text = ('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                    '<title>经典文章归档 - 哆嗒数学网</title>\n'
                    '<link rel="stylesheet" href="/assets/blog.css">\n</head>\n<body>\n'
                    '<header><nav class="nav" aria-label="网站导航"><a class="logo" href="/blog/">哆嗒数学网·博客</a>'
                    '<a href="/blog/archive.html">近期归档</a></nav></header>\n'
                    '<main class="legacy-archive"><h1>经典文章归档</h1><ul class="list">\n'
                    + '\n'.join('<li>' + link + '</li>' for link in links)
                    + '\n</ul></main>\n' + footer + '\n</body>\n</html>\n')
        for style, name in styles.items():
            text = text.replace(style, f'<link rel="stylesheet" href="/assets/{name}">')
        if '/assets/site.css' not in text:
            text = text.replace('</head>', '<link rel="stylesheet" href="/assets/site.css">\n</head>', 1)
        text = re.sub(r'<html class="no-js">', '<html lang="zh-CN" class="no-js">', text)
        text = text.replace('width=device-width, initial-scale=1, maximum-scale=1', 'width=device-width, initial-scale=1')
        text = re.sub(r'<link\b[^>]*href="(?:\./|../../)css\.css"[^>]*>\s*', '', text)
        # These exports only use jQuery for obsolete template code; preserve it if any inline code uses it.
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', text, re.S)
        if not any(re.search(r'\bjQuery\b|\$\s*[.(]', script) for script in scripts):
            text = text.replace('<script src="https://code.jquery.com/jquery-1.11.0.min.js"></script>', '')
        text = text.replace('<script async="" id="MathJax-script"', '<script defer id="MathJax-script"')
        text = text.replace('{footer_html}', footer)

        def fix_link(match):
            value = match[2]
            if value.startswith('/blog'):
                value = value.replace('\\', '/')
                if value == '/blog/articles/':
                    value = '/blog/archive.html'
                local = ROOT / value.lstrip('/')
                if local.is_dir() and (local / 'index.html').exists() and not value.endswith('/'):
                    value += '/'
            return 'href=' + match[1] + value + match[1]

        text = re.sub(r'href=([\"\x27])(.*?)(?:\1)', fix_link, text)
        image_index = 0

        def image_tag(match):
            nonlocal image_count, image_index
            tag = match[0]
            image_index += 1
            source = re.search(r'src=([\"\x27])data:image/(png|jpe?g|gif|webp);base64,([^\"\x27]+)\1', tag, re.I)
            if source:
                data = base64.b64decode(source[3], validate=True)
                ext = 'jpg' if source[2].lower() in ('jpeg', 'jpg') else source[2].lower()
                name = hashlib.sha256(data).hexdigest() + '.' + ext
                dest = ASSETS / 'images' / name
                dest.parent.mkdir(exist_ok=True)
                if not dest.exists():
                    dest.write_bytes(data)
                tag = tag[:source.start()] + f'src="/assets/images/{name}"' + tag[source.end():]
                image_count += 1
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        width, height = image.size
                    if not re.search(r'\swidth=', tag) and not re.search(r'\sheight=', tag):
                        tag = tag.replace('<img', f'<img width="{width}" height="{height}"', 1)
                except (OSError, ValueError):
                    pass
            if not re.search(r'\sdecoding=', tag):
                tag = tag.replace('<img', '<img decoding="async"', 1)
            if image_index > 1 and not re.search(r'\sloading=', tag):
                tag = tag.replace('<img', '<img loading="lazy"', 1)
            return tag

        text = re.sub(r'<img\b[^>]*>', image_tag, text, flags=re.I)
        text = re.sub(r'(?m)^[ \t]+$', '', text)
        if text != original:
            page.write_text(text, encoding='utf-8')
    print(f'Extracted {image_count} inline image references.')


if __name__ == '__main__':
    optimize()
