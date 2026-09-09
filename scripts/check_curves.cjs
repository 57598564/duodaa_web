const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../f.js'), 'utf8'), context);
for (const name of context.f_names) {
  context.plot_parac_conf(name);
  assert.equal(context.x.length, context.y.length, name);
  assert(context.x.length > 100, name);
  assert(context.x.every(value => value === null || Number.isFinite(value)), name);
  assert(context.y.every(value => value === null || Number.isFinite(value)), name);
  context.x.forEach((x, i) => {
    const y = context.y[i];
    if (['logarithm', 'power'].includes(name) && x < 0) assert.equal(y, null);
    if (x === null || y === null) return;
    if (name === 'circle') assert(Math.abs(x * x + y * y - 1) < 1e-10);
    if (name === 'lemniscate') assert(Math.abs((x * x + y * y) ** 2 - 2 * (x * x - y * y)) < 1e-10);
  });
  assert(fs.existsSync(path.join(__dirname, '../assets/curves', `${name}.svg`)));
}
context.plot_parac_conf('power');
context.plot_parac_conf('sin');
assert.equal(context.x.length, 321);
console.log('16 curves: domains, finite coordinates, equations, switching and SVG assets passed.');
