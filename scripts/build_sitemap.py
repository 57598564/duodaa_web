"""Generate canonical URLs for static hosting at https://duodaa.com/."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ET.register_namespace('', 'http://www.sitemaps.org/schemas/sitemap/0.9')
urlset = ET.Element('{http://www.sitemaps.org/schemas/sitemap/0.9}urlset')
pages = [ROOT / 'index.html', *sorted((ROOT / 'blog').rglob('*.html'))]
for page in pages:
    path = '/' + page.relative_to(ROOT).as_posix()
    if path.endswith('index.html'):
        path = path[:-10]
    url = ET.SubElement(urlset, 'url')
    ET.SubElement(url, 'loc').text = 'https://duodaa.com' + path
ET.indent(urlset)
ET.ElementTree(urlset).write(ROOT / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
(ROOT / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: https://duodaa.com/sitemap.xml\n', encoding='utf-8')
print(f'Sitemap contains {len(pages)} canonical URLs.')
