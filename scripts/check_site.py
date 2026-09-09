"""Check static assets, AMP/SEO metadata, sitemap coverage and lossless image extraction."""
from pathlib import Path
from collections import Counter
import base64
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
pages = [ROOT / 'index.html', *sorted((ROOT / 'blog').rglob('*.html'))]
urls = set()
references = 0
for page in pages:
    soup = BeautifulSoup(page.read_text(encoding='utf-8'), 'html.parser')
    assert soup.html.has_attr('amp'), page
    assert len(soup.select('amp-auto-ads')) == 1, page
    assert soup.select_one('amp-auto-ads')['data-ad-client'] == 'ca-pub-9319230211682138', page
    assert len(soup.select('script[custom-element="amp-auto-ads"]')) == 1, page
    assert not soup.select('script[src*="adsbygoogle"]'), page
    assert soup.title and soup.title.get_text(strip=True), page
    assert soup.select_one('meta[name="description"]')['content'].strip(), page
    canonical = soup.select_one('link[rel="canonical"]')['href']
    assert canonical not in urls, page
    urls.add(canonical)
    assert json.loads(soup.select_one('script[type="application/ld+json"]').string)['url'] == canonical, page
    for tag in soup.select('[src], a[href]'):
        value = tag.get('src', tag.get('href', ''))
        assert not value.startswith('/blog\\'), (page, value)
        if value.startswith('/') and not value.startswith('//'):
            target = ROOT / value.split('?')[0].split('#')[0].lstrip('/')
            assert target.is_file() or (target / 'index.html').is_file(), (page, value)
            references += 1
sitemap = ET.parse(ROOT / 'sitemap.xml')
assert urls == {node.text for node in sitemap.findall('.//{*}loc')}
for image in (ROOT / 'assets/images').iterdir():
    assert hashlib.sha256(image.read_bytes()).hexdigest() == image.stem, image
print(f'{len(pages)} pages: AMP integration, SEO, unique canonical URLs, sitemap and {references} local references passed.', flush=True)

# Compare embedded image bytes against the pre-optimization Git revision.
import sys
if '--original' in sys.argv:
    revision = sys.argv[sys.argv.index('--original') + 1]
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=ROOT)
    count = 0
    for page in pages:
        proc.stdin.write(f'{revision}:{page.relative_to(ROOT).as_posix()}\n'.encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        assert header[-1] != 'missing', page
        size = int(header[-1])
        original = proc.stdout.read(size).decode('utf-8')
        proc.stdout.read(1)
        for mime, encoded in re.findall(r'src=[\"\x27]data:image/(png|jpe?g|gif|webp);base64,([^\"\x27]+)', original, re.I):
            data = base64.b64decode(encoded, validate=True)
            ext = 'jpg' if mime.lower() in ('jpg', 'jpeg') else mime.lower()
            target = ROOT / 'assets/images' / (hashlib.sha256(data).hexdigest() + '.' + ext)
            assert target.read_bytes() == data, (page, target)
            count += 1
    proc.stdin.close()
    proc.wait()
    print(f'{count} original embedded images verified byte-for-byte.')
