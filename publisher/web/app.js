'use strict';

const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('publisher-token');
if (token) sessionStorage.setItem('publisher-token', token);
history.replaceState(null, '', '/');
const editor = $('editor');
const state = { config: {}, rootValid: false, articles: [], drafts: [], history: [], library: 'articles', document: {}, dirty: false, version: 0, session: 0, busy: false, range: null, image: null, plan: null };
let saveTimer;
let draftSaveQueue = Promise.resolve();

async function api(path, body) {
  const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers: { 'X-App-Token': token || '', 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `请求失败 (${response.status})`);
  return result;
}
function report(title, message = '', type = 'running') {
  $('status-panel').hidden = false;
  $('status-panel').className = 'status-panel ' + type;
  $('status-title').textContent = title;
  $('status-message').textContent = message;
  $('status-close').hidden = type === 'running';
}
function error(error) { report('未完成操作', error.message || String(error), 'error'); }
function busy(value) {
  state.busy = value;
  for (const id of ['publish-button', 'preview-button', 'publish-preview', 'import-button', 'settings-button', 'new-article', 'exit-button']) $(id).disabled = value;
}
async function runJob(path, body, label) {
  busy(true);
  report(label);
  try {
    const task = await api(path, body);
    while (true) {
      const job = await api('/api/job/' + task.job_id);
      report(label, job.message);
      if (job.status === 'error') throw new Error(job.error);
      if (job.status === 'done') return job.result;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  } finally { busy(false); }
}
function localDate(value = new Date()) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function toEditorHTML(html) {
  const template = document.createElement('template');
  template.innerHTML = html || '';
  for (const image of template.content.querySelectorAll('img')) {
    const source = image.getAttribute('src') || '';
    if (source.startsWith('/media/')) image.src = source + '?token=' + token;
    else if (source.startsWith('/assets/')) image.src = '/site-asset' + source + '?token=' + token;
  }
  return template.innerHTML;
}
function fromEditorHTML() {
  const template = document.createElement('template');
  template.innerHTML = editor.innerHTML;
  const clone = template.content;
  for (const image of clone.querySelectorAll('img')) {
    let source = image.getAttribute('src') || '';
    source = source.split('?')[0];
    if (source.startsWith('/site-asset/')) source = source.slice('/site-asset'.length);
    image.setAttribute('src', source);
    image.classList.remove('selected-image');
    if (!image.className) image.removeAttribute('class');
  }
  return template.innerHTML;
}
function documentValue() {
  return { ...state.document, title: $('title').value.trim(), author: $('author').value.trim(), description: $('description').value.trim(),
    published_at: $('published-at').value ? new Date($('published-at').value).toISOString() : new Date().toISOString(), source_url: $('source-url').value.trim(), content_html: fromEditorHTML() };
}
function wordCount() { $('word-count').textContent = editor.innerText.replace(/\s/g, '').length.toLocaleString() + ' 字'; }
function changed() {
  state.dirty = true; state.version++; state.plan = null;
  $('save-state').textContent = '尚有未保存的修改';
  wordCount();
  clearTimeout(saveTimer);
  if (state.rootValid) saveTimer = setTimeout(() => saveDraft(false).catch(error), 2500);
}
function setDocument(document = {}) {
  clearTimeout(saveTimer); selectImage(null); state.range = null; state.session++;
  state.document = document; state.dirty = false; state.version = 0; state.plan = null;
  $('title').value = document.title || '';
  $('author').value = document.author || state.config.author || '';
  $('description').value = document.description || '';
  $('source-url').value = document.source_url || '';
  $('published-at').value = localDate(document.published_at || new Date());
  editor.innerHTML = toEditorHTML(document.content_html || '');
  $('document-state').textContent = document.article_id ? '编辑已发布文章' : document.draft_id ? '本地草稿' : '新文章';
  $('save-state').textContent = document.article_id ? '已载入文章，可继续修改' : '内容仅保存在本机';
  wordCount(); renderLibrary();
}
async function saveDraft(show = true) {
  if (!state.rootValid) { if (show) openSettings(); return; }
  clearTimeout(saveTimer);
  const version = state.version, session = state.session;
  const snapshot = documentValue();
  draftSaveQueue = draftSaveQueue.catch(() => {}).then(async () => {
    if (session !== state.session) return;
    if (state.document.draft_id) snapshot.draft_id = state.document.draft_id;
    const saved = await api('/api/drafts', snapshot);
    if (session !== state.session) return;
    state.document.draft_id = saved.draft_id;
    if (version === state.version) { state.dirty = false; $('save-state').textContent = '已保存到本机 · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
    if (show) report('草稿已保存', '草稿不会上传到 Git。', 'done');
    const current = await api('/api/state'); state.drafts = current.drafts; renderLibrary();
  });
  return draftSaveQueue;
}
async function preserveCurrent() {
  if (!state.dirty) return true;
  return new Promise(resolve => {
    const dialog = $('replace-dialog'); dialog.showModal();
    const finish = value => { dialog.close(); resolve(value); };
    $('replace-cancel').onclick = () => finish(false);
    $('replace-discard').onclick = () => { clearTimeout(saveTimer); finish(true); };
    $('replace-save').onclick = async () => { try { await saveDraft(false); if (state.rootValid) finish(true); } catch (reason) { error(reason); } };
    dialog.oncancel = () => resolve(false);
  });
}
async function refresh() {
  const data = await api('/api/state');
  state.config = data.config; state.rootValid = data.root_valid; state.drafts = data.drafts; state.history = data.history;
  $('site-label').textContent = state.rootValid ? state.config.site_root : state.config.site_root ? '原目录不可用，请重新选择网站主文件夹' : '尚未选择网站目录';
  $('site-label').title = state.config.site_root;
  if (state.rootValid) state.articles = await api('/api/articles'); else state.articles = [];
  let repo = data.repo;
  $('repo-status').textContent = !state.rootValid ? '请先选择网站目录。' : !repo.ok ? repo.error : `当前分支：${repo.branch} · ${repo.dirty ? '存在未提交的改动，发布前需处理' : '工作区干净'}${!repo.remote_configured ? '\n尚未配置 Git 远程' : ''}`;
  renderLibrary(); renderHistory();
  return data;
}
function renderLibrary() {
  const query = $('search').value.trim().toLowerCase();
  const rows = (state.library === 'articles' ? state.articles : state.drafts).filter(row => row.title.toLowerCase().includes(query));
  const list = $('library'); list.replaceChildren();
  if (!rows.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = query ? '没有找到匹配的文章' : state.library === 'drafts' ? '草稿会自动保存在这里' : '暂无文章，开始写第一篇吧'; list.append(empty); }
  for (const row of rows) {
    const button = document.createElement('button'); button.className = 'library-item';
    if (state.library === 'articles' ? row.article_id === state.document.article_id : row.draft_id === state.document.draft_id) button.classList.add('current');
    const title = document.createElement('strong'); title.textContent = row.title;
    const date = document.createElement('small'); date.textContent = row.published_at ? row.published_at.slice(0, 10) : '草稿 · ' + new Date(row.updated * 1000).toLocaleDateString();
    button.append(title, date); list.append(button);
    button.onclick = async () => {
      if (state.busy || !await preserveCurrent()) return;
      try { setDocument(await api(state.library === 'articles' ? '/api/article/' + row.article_id : '/api/draft/' + row.draft_id)); }
      catch (reason) { error(reason); }
    };
  }
}
function openSettings() {
  const form = $('settings-form');
  for (const [name, value] of Object.entries(state.config)) if (form.elements[name]) form.elements[name].value = value;
  $('settings-dialog').showModal();
}
function renderHistory() {
  const target = $('history-list'); target.replaceChildren();
  if (!state.history.length) { target.textContent = '还没有发布记录。'; return; }
  for (const row of state.history) {
    const card = document.createElement('section'); card.className = 'history-row';
    const title = document.createElement('h3'); title.textContent = row.title;
    const status = document.createElement('p'); status.textContent = ({ published: '已成功上传', push_failed: '已本地提交 · 推送失败', rolled_back: '提交失败，生成文件已恢复', preparing: '上次任务未完成，请检查仓库及备份', committed: '已本地提交', needs_review: '需要检查仓库状态' })[row.status] || row.status;
    const code = document.createElement('code'); code.textContent = row.commit ? row.commit.slice(0, 10) : '';
    card.append(title, status, code);
    if (row.error) { const message = document.createElement('p'); message.textContent = row.error; card.append(message); }
    if (row.status === 'push_failed') {
      const retry = document.createElement('button'); retry.textContent = '重试推送'; retry.className = 'primary';
      retry.onclick = async () => {
        $('history-dialog').close();
        try { const result = await runJob('/api/retry', { job_id: row.job_id }, '正在重试推送'); publicationResult(result); await refresh(); } catch (reason) { error(reason); }
      }; card.append(retry);
    }
    target.append(card);
  }
}
function saveSelection() {
  const selection = window.getSelection();
  if (selection.rangeCount && editor.contains(selection.getRangeAt(0).commonAncestorContainer)) state.range = selection.getRangeAt(0).cloneRange();
}
function restoreSelection() {
  editor.focus();
  const selection = window.getSelection(); selection.removeAllRanges();
  if (state.range && editor.contains(state.range.commonAncestorContainer)) selection.addRange(state.range);
  else { const range = document.createRange(); range.selectNodeContents(editor); range.collapse(false); selection.addRange(range); }
}
function command(name, value) { restoreSelection(); document.execCommand(name, false, value); saveSelection(); changed(); }
function selectedBlock() {
  restoreSelection();
  let element = window.getSelection().anchorNode;
  if (element && element.nodeType === Node.TEXT_NODE) element = element.parentElement;
  const block = element?.closest('p,h1,h2,h3,h4,div,blockquote,li,pre');
  return block && block !== editor ? block : null;
}
function selectImage(image) {
  if (state.image) state.image.classList.remove('selected-image');
  state.image = image;
  $('image-panel').hidden = !image; $('resize-handle').hidden = !image;
  if (!image) return;
  image.classList.add('selected-image');
  $('image-width').value = Math.round(parseFloat(image.style.width) || image.getBoundingClientRect().width);
  $('image-alt').value = image.alt;
  $('image-align').value = image.style.marginLeft === 'auto' ? image.style.marginRight === 'auto' ? 'center' : 'right' : 'left';
  positionHandle();
}
function positionHandle() {
  if (!state.image || !editor.contains(state.image)) { $('resize-handle').hidden = true; return; }
  const rect = state.image.getBoundingClientRect();
  const visible = rect.bottom > 80 && rect.top < innerHeight - 60;
  $('resize-handle').hidden = !visible;
  $('resize-handle').style.left = rect.right - 6 + 'px'; $('resize-handle').style.top = rect.bottom - 6 + 'px';
}
function setImageWidth(value) {
  if (!state.image) return;
  const width = Math.max(24, Math.min(2400, Number(value) || 24));
  state.image.style.width = width + 'px'; state.image.style.height = 'auto';
  $('image-width').value = Math.round(width); positionHandle(); changed();
}
async function insertImages(files) {
  if (!files.length) return;
  saveSelection();
  try {
    for (const file of files) {
      const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
      const image = await api('/api/media', { data_url: dataUrl });
      const tag = document.createElement('img'); tag.src = image.src + '?token=' + token; tag.width = image.width; tag.height = image.height; tag.alt = '';
      tag.style.width = Math.min(image.width, 720) + 'px'; tag.style.height = 'auto';
      command('insertHTML', '<p>' + tag.outerHTML + '</p><p><br></p>');
    }
  } catch (reason) { error(reason); }
}
async function validatePlan(plan) {
  report('正在检查待发布页面', '使用离线 AMP 校验器检查文章、列表和导航。');
  return new Promise((resolve, reject) => {
    const worker = new Worker('/validator-worker.js');
    const timer = setTimeout(() => { worker.terminate(); reject(new Error('页面校验超时，请重试。')); }, 90000);
    worker.onerror = event => { clearTimeout(timer); worker.terminate(); reject(new Error('无法启动离线页面校验：' + event.message)); };
    worker.onmessage = event => {
      clearTimeout(timer); worker.terminate();
      if (event.data.error) { reject(new Error(event.data.error)); return; }
      const failures = event.data.results.filter(result => result.status !== 'PASS');
      if (failures.length) {
        reject(new Error('页面尚未通过 AMP 校验，请调整样式后重试。\n' + failures.slice(0, 3).map(result => result.path + '\n' + result.errors.slice(0, 3).map(item => item.message).join('\n')).join('\n'))); return;
      }
      resolve(event.data.results.map(result => result.path));
    };
    worker.postMessage({ id: plan.plan_id, html: plan.html });
  });
}
async function prepare() {
  if (!state.rootValid) { openSettings(); throw new Error('请先设置网站内容主文件夹。'); }
  await saveDraft(false);
  const version = state.version, session = state.session;
  const plan = await runJob('/api/prepare', documentValue(), '正在生成发布内容');
  busy(true);
  try { plan.validated_files = await validatePlan(plan); }
  finally { busy(false); }
  if (version !== state.version || session !== state.session) throw new Error('正文在预览过程中发生了修改，请重新预览。');
  plan.editor_version = version; plan.editor_session = session; state.plan = plan;
  return plan;
}
async function publishCurrent(prepared = false) {
  try {
    clearTimeout(saveTimer);
    const plan = prepared && state.plan ? state.plan : await prepare();
    if (plan.editor_version !== state.version || plan.editor_session !== state.session) throw new Error('内容已有修改，请重新生成预览。');
    $('preview-dialog').close();
    const result = await runJob('/api/publish', { plan_id: plan.plan_id, digest: plan.digest, validated_files: plan.validated_files }, '正在上传文章');
    publicationResult(result);
    await refresh();
    if (['published', 'push_failed'].includes(result.status)) {
      const originalDraft = state.document.draft_id;
      setDocument(await api('/api/article/' + result.article_id));
      if (originalDraft) { state.document.draft_id = originalDraft; await saveDraft(false); }
    }
  } catch (reason) { error(reason); }
}
function publicationResult(result) {
  if (result.status === 'published') report('文章已上传', '本地文件、文章导航和站点地图已更新。提交：' + result.commit.slice(0, 10), 'done');
  else report('本地提交已保存，推送未成功', (result.error || '') + '\n请在“发布记录”中重试推送。', 'error');
}

document.addEventListener('selectionchange', saveSelection);
document.querySelector('.editor-toolbar').addEventListener('mousedown', event => { saveSelection(); if (event.target.closest('button')) event.preventDefault(); });
document.querySelectorAll('[data-command]').forEach(button => button.onclick = () => command(button.dataset.command));
$('block-format').onchange = event => command('formatBlock', event.target.value);
$('font-family').onchange = event => command('fontName', event.target.value || 'Microsoft YaHei');
$('font-size').onchange = event => {
  command('fontSize', '7');
  for (const font of editor.querySelectorAll('font[size="7"]')) { font.removeAttribute('size'); font.style.fontSize = event.target.value + 'px'; }
  changed();
};
$('text-color').oninput = event => command('foreColor', event.target.value);
$('highlight-color').oninput = event => command('hiliteColor', event.target.value);
$('line-height').onchange = event => { const block = selectedBlock(); if (block) { block.style.lineHeight = event.target.value; changed(); } };
editor.addEventListener('input', changed);
for (const id of ['title', 'author', 'description', 'published-at', 'source-url']) $(id).addEventListener('input', changed);
editor.addEventListener('click', event => selectImage(event.target.closest('img')));
editor.addEventListener('paste', async event => {
  event.preventDefault(); saveSelection();
  const images = [...event.clipboardData.files].filter(file => file.type.startsWith('image/'));
  if (images.length) { await insertImages(images); return; }
  const html = event.clipboardData.getData('text/html');
  if (html) {
    try { const result = await runJob('/api/localize', { content_html: html }, '正在整理粘贴内容'); command('insertHTML', toEditorHTML(result.content_html)); report('内容已粘贴', '', 'done'); } catch (reason) { error(reason); }
  } else command('insertText', event.clipboardData.getData('text/plain'));
});
editor.addEventListener('dragover', event => event.preventDefault());
editor.addEventListener('drop', event => { event.preventDefault(); insertImages([...event.dataTransfer.files].filter(file => file.type.startsWith('image/'))); });
$('image-button').onclick = () => { saveSelection(); $('image-file').click(); };
$('image-file').onchange = async event => { await insertImages([...event.target.files]); event.target.value = ''; };
$('image-width').onchange = event => setImageWidth(event.target.value);
$('image-original').onclick = () => setImageWidth(state.image?.naturalWidth || state.image?.width || 640);
$('image-fit').onclick = () => setImageWidth(editor.clientWidth - 72);
$('image-alt').oninput = event => { if (state.image) { state.image.alt = event.target.value; changed(); } };
$('image-align').onchange = event => {
  if (!state.image) return;
  state.image.style.display = 'block'; state.image.style.marginLeft = event.target.value === 'left' ? '0' : 'auto'; state.image.style.marginRight = event.target.value === 'right' ? '0' : 'auto'; positionHandle(); changed();
};
$('image-delete').onclick = () => { if (state.image) state.image.remove(); selectImage(null); changed(); };
$('resize-handle').onpointerdown = event => {
  event.preventDefault(); const target = event.currentTarget; target.setPointerCapture(event.pointerId);
  const start = event.clientX, width = state.image.getBoundingClientRect().width;
  target.onpointermove = move => setImageWidth(width + move.clientX - start);
  target.onpointerup = () => { target.onpointermove = null; target.onpointerup = null; };
};
document.querySelector('.work-scroll').addEventListener('scroll', positionHandle);
window.addEventListener('resize', positionHandle);
let insertMode = 'link';
function insertDialog(mode) {
  saveSelection(); insertMode = mode;
  $('insert-title').textContent = mode === 'link' ? '插入链接' : '插入数学公式';
  $('insert-value').value = ''; $('insert-value').placeholder = mode === 'link' ? 'https://…' : '例如 x^2 + y^2 = 1';
  $('insert-help').textContent = mode === 'link' ? '输入链接地址；先选中文字可为文字添加链接。' : '使用 LaTeX 语法。编辑区显示公式源码，发布后自动排版。';
  $('insert-dialog').showModal(); $('insert-value').focus();
}
$('link-button').onclick = () => insertDialog('link'); $('formula-button').onclick = () => insertDialog('formula');
$('insert-form').onsubmit = event => {
  event.preventDefault(); const value = $('insert-value').value.trim();
  if (insertMode === 'link' && !/^https?:\/\//i.test(value)) { $('insert-value').setCustomValidity('请使用 HTTP 或 HTTPS 链接'); $('insert-value').reportValidity(); return; }
  $('insert-value').setCustomValidity(''); $('insert-dialog').close();
  if (insertMode === 'formula') command('insertText', '$$' + value + '$$');
  else { restoreSelection(); if (window.getSelection().isCollapsed) command('insertText', value); command('createLink', value); }
};
$('insert-value').oninput = () => $('insert-value').setCustomValidity('');
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close());
$('manual-mode').onclick = () => { $('wechat-panel').hidden = true; $('manual-mode').classList.add('active'); $('wechat-mode').classList.remove('active'); };
$('wechat-mode').onclick = () => { $('wechat-panel').hidden = false; $('wechat-mode').classList.add('active'); $('manual-mode').classList.remove('active'); $('wechat-url').focus(); };
$('import-button').onclick = async () => {
  if (!await preserveCurrent()) return;
  try { const document = await runJob('/api/import', { url: $('wechat-url').value.trim() }, '正在导入微信文章'); setDocument(document); changed(); report('微信文章已导入', '可继续修改内容、样式和图片尺寸。', 'done'); } catch (reason) { error(reason); }
};
$('new-article').onclick = async () => { if (await preserveCurrent()) { setDocument(); $('title').focus(); } };
$('save-draft').onclick = () => saveDraft().catch(error);
$('preview-button').onclick = async () => {
  try { const plan = await prepare(); $('preview-summary').textContent = `${plan.validated_files.length} 个页面通过校验 · 将更新 ${plan.files.length} 个文件`; $('preview-frame').src = '/preview/' + plan.plan_id + '?token=' + token; $('preview-dialog').showModal(); report('发布内容已准备好', '尚未修改网站文件。', 'done'); } catch (reason) { error(reason); }
};
$('publish-button').onclick = () => publishCurrent(false);
$('publish-preview').onclick = () => publishCurrent(true);
$('desktop-preview').onclick = () => { $('preview-frame').style.width = '100%'; $('desktop-preview').classList.add('active'); $('mobile-preview').classList.remove('active'); };
$('mobile-preview').onclick = () => { $('preview-frame').style.width = '390px'; $('mobile-preview').classList.add('active'); $('desktop-preview').classList.remove('active'); };
$('settings-button').onclick = openSettings;
$('settings-form').onsubmit = async event => {
  event.preventDefault();
  try {
    const previousRoot = state.config.site_root;
    const nextRoot = $('setting-root').value.trim();
    if (state.dirty && state.rootValid && nextRoot !== previousRoot) await saveDraft(false);
    await api('/api/settings', Object.fromEntries(new FormData(event.currentTarget)));
    $('settings-dialog').close(); await refresh();
    if (previousRoot && previousRoot !== state.config.site_root) setDocument();
    report('网站目录已配置', state.config.site_root, 'done');
  } catch (reason) { $('repo-status').textContent = reason.message; }
};
$('browse-root').onclick = async () => { try { const result = await runJob('/api/browse', {}, '请选择网站主文件夹'); if (result.path) $('setting-root').value = result.path; $('status-panel').hidden = true; } catch (reason) { $('repo-status').textContent = reason.message; } };
$('history-button').onclick = async () => { try { await refresh(); $('history-dialog').showModal(); } catch (reason) { error(reason); } };
$('search').oninput = renderLibrary;
document.querySelectorAll('[data-library]').forEach(button => button.onclick = () => { state.library = button.dataset.library; document.querySelectorAll('[data-library]').forEach(other => other.classList.toggle('active', other === button)); renderLibrary(); });
$('status-close').onclick = () => $('status-panel').hidden = true;
$('exit-button').onclick = async () => { if (!await preserveCurrent()) return; try { await api('/api/shutdown', {}); state.dirty = false; report('工具已退出', '可以关闭此窗口。', 'done'); } catch (reason) { error(reason); } };
window.addEventListener('beforeunload', event => { if (state.dirty || state.busy) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveDraft().catch(error); } });
setInterval(() => api('/api/heartbeat').catch(() => {}), 20000);
(async () => { try { await refresh(); setDocument(); if (!state.rootValid) openSettings(); } catch (reason) { error(reason); } })();
