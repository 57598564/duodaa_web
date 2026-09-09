// Render the existing functions once at build time; AMP serves lightweight SVG images.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(root, 'f.js'), 'utf8'), context);
const escape = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
fs.mkdirSync(path.join(root, 'assets/curves'), { recursive: true });
const slides = [];
for (const name of context.f_names) {
  context.plot_parac_conf(name);
  let grid = '', d = '', connected = false;
  const px = x => 40 + (x + 4) * 65;
  const py = y => 560 - (y + 4) * 65;
  for (let i = -4; i <= 4; i++) {
    grid += `<path d="M${px(i)},40 V560 M40,${py(i)} H560" stroke="${i === 0 ? '#a0aec0' : '#e6ecf5'}"/>`;
    if (i !== 0) grid += `<text x="${px(i)}" y="582" text-anchor="middle">${i}</text><text x="26" y="${py(i) + 5}" text-anchor="end">${i}</text>`;
  }
  context.x.forEach((x, i) => {
    const y = context.y[i];
    if (x === null || y === null) { connected = false; return; }
    d += `${connected ? 'L' : 'M'}${px(x).toFixed(2)},${py(y).toFixed(2)} `;
    connected = true;
  });
  const label = context.f_display.replace('~', ' · ');
  const origin = name === 'sign' ? '<circle cx="300" cy="300" r="3" fill="#2b6fff"/>' : '';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" role="img" aria-label="${escape(label)}"><title>${escape(label)}</title><defs><clipPath id="plot"><rect x="40" y="40" width="520" height="520"/></clipPath></defs><g fill="#52647c" font-family="sans-serif" font-size="14">${grid}</g><g clip-path="url(#plot)"><path d="${d}" fill="none" stroke="#2b6fff" stroke-width="3" stroke-linejoin="round"/>${origin}</g></svg>`;
  fs.writeFileSync(path.join(root, 'assets/curves', `${name}.svg`), svg);
  slides.push(`<figure class="curve-slide"><amp-img src="/assets/curves/${name}.svg" width="600" height="600" layout="responsive" alt="${escape(label)}"></amp-img><figcaption>${escape(label)}</figcaption></figure>`);
}
const template = fs.readFileSync(path.join(__dirname, 'home.template'), 'utf8');
fs.writeFileSync(path.join(root, 'index.html'), template.replace('{{SLIDES}}', slides.join('\n')));
console.log('Rendered 16 SVG curves and the homepage. Run convert_amp.py next.');
