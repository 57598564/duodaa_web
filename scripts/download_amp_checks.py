"""Download official AMP validator and reference docs for local verification."""
from pathlib import Path
from urllib.request import urlopen

target = Path(__file__).resolve().parents[1] / '.tmp'
target.mkdir(exist_ok=True)
for name, url in {
    'validator.js': 'https://cdn.ampproject.org/v0/validator_wasm.js',
    'mathml.html': 'https://amp.dev/documentation/components/amp-mathml/',
    'carousel.html': 'https://amp.dev/documentation/components/amp-carousel/',
    'v0.js': 'https://cdn.ampproject.org/v0.js',
    'amp-carousel-0.1.js': 'https://cdn.ampproject.org/v0/amp-carousel-0.1.js',
    'amp-auto-ads-0.1.js': 'https://cdn.ampproject.org/v0/amp-auto-ads-0.1.js',
    'amp-mathml-0.1.js': 'https://cdn.ampproject.org/v0/amp-mathml-0.1.js',
    'amp-anim-0.1.js': 'https://cdn.ampproject.org/v0/amp-anim-0.1.js',
    'amp-ad-0.1.js': 'https://cdn.ampproject.org/v0/amp-ad-0.1.js',
}.items():
    if (target / name).exists():
        continue
    with urlopen(url, timeout=30) as response:
        data = response.read()
    (target / name).write_bytes(data)
    print(name, len(data), flush=True)
