const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const validatorModule = require(path.join(root, '.tmp/amp-check/node_modules/amphtml-validator'));
function pages(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? pages(full) : entry.name.endsWith('.html') ? [full] : [];
  });
}
(async () => {
  const validator = await validatorModule.getInstance(path.join(root, '.tmp/validator.js'));
  const results = [];
  const files = [...fs.readdirSync(root).filter(file => file.endsWith('.html')).map(file => path.join(root, file)), ...pages(path.join(root, 'blog'))];
  for (const file of files) {
    const result = validator.validateString(fs.readFileSync(file, 'utf8'));
    if (result.status !== 'PASS') results.push({ file: path.relative(root, file), errors: result.errors });
  }
  fs.writeFileSync(path.join(root, '.tmp/amp-results.json'), JSON.stringify(results, null, 2));
  console.log(`${files.length - results.length}/${files.length} AMP pages passed.`);
  const messages = new Map();
  for (const result of results) for (const error of result.errors) {
    const key = error.message;
    const record = messages.get(key) || { count: 0, example: result.file, line: error.line };
    record.count++; messages.set(key, record);
  }
  console.log(JSON.stringify(Object.fromEntries(messages), null, 2));
  process.exitCode = results.length ? 1 : 0;
})();
