importScripts('/vendor/amp-validator.js');
const ready = amp.validator.init();
self.onmessage = async event => {
  try {
    await ready;
    const results = [];
    for (const [path, html] of Object.entries(event.data.html)) {
      const result = amp.validator.validateString(html);
      results.push({ path, status: result.status, errors: result.errors.map(error => ({
        line: error.line, message: amp.validator.renderErrorMessage(error), severity: error.severity
      })) });
    }
    self.postMessage({ id: event.data.id, results });
  } catch (error) {
    self.postMessage({ id: event.data.id, error: error.message });
  }
};
