/* Plain browser code: the server owns secrets, model access and report permissions. */
const $ = id => document.getElementById(id);
const project = document.body.dataset.project;
let config = null;
let currentReport = null;
let chatMessages = [];
let reports = [];
let working = false;
let toastTimer;
// Remove the previous version's browser-stored token. New sessions use HttpOnly cookies.
sessionStorage.removeItem(project + '-token');

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notify(text, error=false) {
  clearTimeout(toastTimer);
  $('message').textContent = text;
  $('message').className = 'toast' + (error ? ' error' : '');
  $('message').hidden = !text;
  if (text) toastTimer = setTimeout(() => { $('message').hidden = true; }, error ? 12000 : 5000);
}
async function api(path, options={}) {
  const response = await fetch(path, {credentials:'same-origin', ...options});
  let data;
  try { data = await response.json(); } catch (_) { throw new Error('The server did not return a readable response. Please try again.'); }
  if (!response.ok) throw new Error(data.error?.message || data.detail?.[0]?.msg || 'The request could not be completed.');
  return data;
}
function jsonOptions(body) {
  return {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
}
async function run(button, action, modelWork=false) {
  if (working) return notify('A request is already running. Please wait before starting another.');
  working = true;
  const children = Array.from(button.childNodes);
  button.replaceChildren(node('span', modelWork ? 'Working?' : 'Saving?'));
  document.querySelectorAll('[data-inference], #new-chat').forEach(el => { el.disabled = true; });
  button.disabled = true;
  $('generation-status').hidden = !modelWork;
  if (modelWork) $('generation-text').textContent = 'Working locally. CPU processing can take a few minutes.';
  try { await action(); }
  catch (error) { notify(error.message, true); }
  finally {
    working = false;
    button.replaceChildren(...children);
    document.querySelectorAll('[data-inference], #new-chat').forEach(el => { el.disabled = false; });
    button.disabled = false;
    $('generation-status').hidden = true;
  }
}

// Appearance is saved without contacting the model.
function appearance() { try { return localStorage.getItem('commerce-appearance') || 'system'; } catch (_) { return 'system'; } }
function setTheme(preference, save=true) {
  if (save) { try { localStorage.setItem('commerce-appearance', preference); } catch (_) {} }
  const dark = preference === 'dark' || (preference === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $('theme-select').value = preference;
  $('theme-toggle').setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
  $('theme-toggle').setAttribute('aria-pressed', String(dark));
  document.querySelectorAll('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === (dark ? 'dark' : 'light'))));
}
$('theme-toggle').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
$('theme-select').onchange = e => setTheme(e.target.value);
document.querySelectorAll('[data-theme-choice]').forEach(button => { button.onclick = () => setTheme(button.dataset.themeChoice); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (appearance() === 'system') setTheme('system', false); });
setTheme(appearance(), false);

function view(name) {
  document.querySelectorAll('.view').forEach(section => { section.hidden = section.id !== 'view-' + name; });
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === name;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  const labels = {assistant:'Assistant', library:project === 'COA' ? 'Knowledge' : 'Documents', reports:'Reports', settings:'Settings'};
  const titles = {assistant:'Your commerce assistant', library:project === 'COA' ? 'Knowledge library' : 'Source documents', reports:'Reports & reviews', settings:'Workspace settings'};
  $('breadcrumb').textContent = labels[name];
  $('page-title').replaceChildren(node('span', titles[name]), node('span', '?', 'title-spark'));
  $('page-subtitle').textContent = name === 'assistant' ? 'A conversation backed by your store?s evidence.' : 'Everything you need, in one workspace.';
  $('sidebar').classList.remove('open');
  $('menu-toggle').setAttribute('aria-expanded', 'false');
}
document.querySelectorAll('[data-view]').forEach(button => { button.onclick = () => view(button.dataset.view); });
$('menu-toggle').onclick = () => { const opened = $('sidebar').classList.toggle('open'); $('menu-toggle').setAttribute('aria-expanded', String(opened)); };

function newConversation() {
  if (working) return;
  currentReport = null;
  chatMessages = [];
  document.querySelectorAll('.chat-message').forEach(el => el.remove());
  $('welcome').hidden = false;
  $('result').hidden = true;
  $('context-label').textContent = 'No report selected';
  $('chat-input').value = '';
  view('assistant');
}
$('new-chat').onclick = () => { newConversation(); $('chat-input').focus(); };
function bubble(role, text, label, citations=[]) {
  $('welcome').hidden = true;
  const row = node('div', undefined, 'chat-message ' + role);
  row.append(node('span', role === 'user' ? 'You' : '?', 'message-avatar'));
  const body = node('div', undefined, 'message-content');
  body.append(node('span', label || (role === 'user' ? 'You' : project + ' Assistant'), 'message-name'));
  body.append(node('div', text, 'message-text'));
  if (citations.length) {
    const list = node('div', undefined, 'source-pills');
    citations.forEach(id => list.append(node('span', id)));
    body.append(list);
  }
  row.append(body);
  $('conversation').append(row);
  $('conversation').scrollTop = $('conversation').scrollHeight;
  return row;
}
async function sendChat() {
  const text = $('chat-input').value.trim();
  if (!text || !config || working) return;
  $('chat-input').value = '';
  bubble('user', text);
  await run($('send'), async () => {
    const next = [...chatMessages.slice(-6), {role:'user', content:text}];
    try {
      const answer = await api('/v1/chat', jsonOptions({messages:next, report_id:currentReport?.id || null}));
      chatMessages = [...next, {role:'assistant', content:answer.answer}];
      bubble('assistant', answer.answer, undefined, answer.evidence_ids);
    } catch (error) {
      bubble('failed', error.message, 'Could not complete this request');
      throw error;
    }
  }, true);
}
$('chat-form').onsubmit = e => { e.preventDefault(); sendChat(); };
$('chat-input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } });
document.querySelectorAll('[data-prompt]').forEach(button => { button.onclick = () => { view('assistant'); $('chat-input').value = button.dataset.prompt; $('chat-input').focus(); }; });

function table(headers, rows) {
  const wrap = node('div', undefined, 'table-wrap');
  const el = node('table');
  const head = node('tr');
  headers.forEach(value => head.append(node('th', value)));
  const thead = node('thead'); thead.append(head); el.append(thead);
  const tbody = node('tbody');
  rows.forEach(values => { const row = node('tr'); values.forEach(value => { const cell = node('td'); cell.append(value instanceof Node ? value : node('span', String(value ?? 'Not recorded'))); row.append(cell); }); tbody.append(row); });
  el.append(tbody); wrap.append(el); return wrap;
}
function disclosure(title, value) {
  const el = node('details'); el.append(node('summary', title), node('pre', JSON.stringify(value, null, 2))); return el;
}
function empty(root, title, description) {
  const el = node('div', undefined, 'empty'); el.append(node('strong', title), node('span', description)); root.append(el);
}
function statusBadge(value) { return node('span', value.replaceAll('_',' '), 'badge' + (value === 'failed' ? ' warning' : '')); }
function renderReport(report, scroll=false) {
  currentReport = report;
  $('context-label').textContent = 'Report context ? ' + (report.result?.order_reference || report.id.slice(0,8));
  const root = $('result'); root.hidden = false; root.replaceChildren();
  const title = node('div', undefined, 'section-line');
  title.append(node('h2', project === 'COA' ? 'Investigation & evidence' : 'Comparison & evidence'), statusBadge(report.status));
  root.append(title, node('p', `Run ${report.id} ? ${report.source_mode} ? ${new Date(report.created_at).toLocaleString()}`, 'meta'));
  if (report.error) { root.append(node('p', report.error.message, 'notice')); return; }
  const result = report.result;
  if (!result) { root.append(node('p', 'This run is still processing. Refresh reports to check its status.')); return; }
  if (project === 'COA') {
    const order = result.observed_facts;
    root.append(node('h3', 'Observed order facts'), table(['Order','Status','Payment','Fulfilment','Total'], [[order.number,order.status,order.payment_status,order.fulfillment_status,`${order.currency} ${order.total}`]]));
    root.append(node('h3','Recommended next step'), node('p',result.recommended_action), node('h3','Response draft'), node('div',result.draft_response,'draft'));
    const sources = node('details'); sources.append(node('summary','Policy sources & citations'));
    result.evidence.forEach(item => { const box = node('div',undefined,'evidence'); box.append(node('strong',item.source_type === 'policy' ? `${item.title} ? v${item.version} ? page ${item.page}` : `Spree record ${item.record_id}`), node('p',item.text || `Retrieved ${item.retrieved_at}`), node('div',item.id,'meta')); sources.append(box); });
    root.append(sources, disclosure('Read-only tool trace',result.tool_trace));
    if (result.unresolved_questions?.length) root.append(node('p', 'Open questions: ' + result.unresolved_questions.join(' '),'notice'));
  } else {
    root.append(node('h3',result.order_reference + ' ? ' + result.outcome.replaceAll('_',' ')));
    root.append(table(['SKU','Ordered','Invoice','Packed','Difference','Result'],result.rows.map(row => [row.sku,row.ordered,row.invoiced,row.packed,row.difference,row.status])));
    result.discrepancies.forEach(issue => root.append(node('p',issue.message,'notice')));
    const sources = node('details'); sources.append(node('summary','Original document pages'));
    result.sources.forEach(source => source.pages.forEach(page => { const box = node('div',undefined,'evidence'); box.append(node('strong',`${source.filename} ? page ${page.page}`),node('p',page.text)); sources.append(box); }));
    root.append(sources, disclosure('Extracted fields & page evidence',{invoice:result.invoice,packing_slip:result.packing_slip}),disclosure('Matched Spree record',result.order));
  }
  (result.warnings || []).forEach(warning => root.append(node('p',warning,'notice')));
  root.append(node('p',result.review_notice,'fine'));
  if (report.status === 'needs_review') {
    const label = node('label','Review note'); label.htmlFor = 'review-note';
    const note = node('textarea'); note.id = 'review-note'; note.rows = 2; note.maxLength = 1000;
    root.append(label,note);
    const actions = node('div',undefined,'report-actions');
    ['approve','reject'].forEach(decision => {
      const button = node('button',decision === 'approve' ? 'Approve internal report' : 'Reject report', decision === 'approve' ? 'primary' : 'secondary');
      button.onclick = () => run(button,async () => {
        const reviewed = await api(`/v1/reports/${report.id}/review`,jsonOptions({decision,note:note.value,version:report.version}));
        renderReport(reviewed); await loadReports(); notify('Your review has been saved.');
      });
      actions.append(button);
    });
    root.append(actions);
  } else if (report.review) root.append(node('p',`${report.review.decision} ? ${report.review.reviewer} ? ${report.review.note}`,'meta'));
  const download = node('button','Download report','secondary');
  download.onclick = () => {
    const blob = new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
    const link = node('a'); link.href = URL.createObjectURL(blob); link.download = `${project}-${report.id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href),1000);
  };
  const actions = node('div',undefined,'report-actions'); actions.append(download); root.append(actions);
  if (scroll) root.scrollIntoView({behavior:'smooth',block:'start'});
}
function openReport(report) {
  if (working) return notify('Wait for your current request to finish before changing report context.');
  newConversation(); renderReport(report);
  const text = report.error ? report.error.message : `Report ${report.result?.order_reference || report.id.slice(0,8)} is selected. Ask a question about its evidence, or inspect the report below.`;
  bubble('assistant',text,'Report selected');
}
async function loadReports() {
  reports = await api('/v1/reports');
  $('stat-total').textContent = String(reports.length);
  $('nav-count').textContent = String(reports.length);
  $('stat-review').textContent = String(reports.filter(report => report.status === 'needs_review').length);
  $('history').replaceChildren();
  if (!reports.length) empty($('history'),'Your reports will appear here','Start an investigation or document comparison to create your first report.');
  else $('history').append(table(['Reference','Type','Status','Created',''], reports.map(report => {
    const button = node('button','Open report ?','text-button'); button.onclick = () => openReport(report);
    return [report.result?.order_reference || report.id.slice(0,8), report.kind,statusBadge(report.status),new Date(report.created_at).toLocaleDateString(),button];
  })));
  if (project === 'BDA') {
    $('document-library').replaceChildren();
    const documents = reports.flatMap(report => (report.result?.sources || []).map(source => {
      const button = node('button','View evidence ?','text-button'); button.onclick = () => openReport(report);
      return [source.filename,source.pages.length,report.result.order_reference,button];
    }));
    if (documents.length) $('document-library').append(table(['Document','Pages','Order',''],documents));
    else empty($('document-library'),'No processed documents yet','Your source documents will stay linked to their comparison report.');
  }
}
$('refresh').onclick = () => loadReports().catch(error => notify(error.message,true));
async function example(filename) {
  const response = await fetch('/v1/examples/' + filename,{credentials:'same-origin'});
  if (!response.ok) throw new Error('The demo document is unavailable.');
  return response.blob();
}
async function loadPolicies() {
  const list = await api('/v1/policies');
  $('policies').replaceChildren();
  if (!list.length) empty($('policies'),'Add your first policy','A policy gives the assistant evidence for its store-specific advice.');
  list.forEach(policy => {
    const row = node('div',undefined,'policy-row');
    const label = node('div'); label.append(node('strong',policy.title),node('span','Version ' + policy.version));
    const remove = node('button','Remove','text-button');
    remove.onclick = () => run(remove,async () => { await api('/v1/policies/' + policy.id,{method:'DELETE'}); await loadPolicies(); notify('Policy removed from retrieval.'); });
    row.append(label,remove); $('policies').append(row);
  });
}
if (project === 'COA') {
  $('reference').onchange = () => { if (currentReport && $('reference').value.trim() !== currentReport.result?.order_reference) newConversation(); };
  $('investigate').onclick = () => {
    const reference = $('reference').value.trim();
    if (!reference) { $('reference').focus(); return notify('Choose an order reference first.'); }
    if (!config || working) return;
    const question = $('chat-input').value.trim() || 'Investigate fulfilment and prepare a response consistent with the delivery policy. Identify any missing evidence.';
    $('chat-input').value = ''; bubble('user',`${reference}: ${question}`);
    run($('investigate'),async () => {
      const report = await api('/v1/tasks',jsonOptions({order_reference:reference,question}));
      renderReport(report);
      if (report.error) bubble('failed',report.error.message,'Investigation needs attention');
      else {
        const text = report.result.draft_response;
        chatMessages = [{role:'user',content:question},{role:'assistant',content:text}];
        bubble('assistant',text,'Investigation draft',report.result.evidence_ids);
      }
      await loadReports();
    },true);
  };
  $('policy-form').onsubmit = e => { e.preventDefault(); run(e.submitter,async () => {
    const form = new FormData(); form.append('title',$('policy-title').value); form.append('file',$('policy-file').files[0]);
    await api('/v1/policies',{method:'POST',body:form}); await loadPolicies(); notify('Policy indexed and ready for retrieval.');
  },true); };
  $('sample-policy').onclick = () => run($('sample-policy'),async () => {
    const form = new FormData(); form.append('title','Demo delivery policy'); form.append('file',await example('delivery-policy.md'),'delivery-policy.md');
    await api('/v1/policies',{method:'POST',body:form}); await loadPolicies(); notify('Demo delivery policy is ready.');
  },true);
} else {
  ['invoice','packing'].forEach(id => { $(id).onchange = () => { $(id + '-name').textContent = $(id).files[0]?.name || 'Choose a PDF or text file'; }; });
  async function compare(form) {
    view('assistant');
    const report = await api('/v1/jobs',{method:'POST',body:form});
    renderReport(report);
    if (report.error) bubble('failed',report.error.message,'Comparison needs attention');
    else if (report.result) {
      const result = report.result;
      const text = `${result.order_reference}: ${result.discrepancies.length} review item(s) found. ` + result.rows.map(row => `${row.sku}: ${row.ordered} ordered, ${row.invoiced} invoiced, ${row.packed} packed.`).join(' ') + ' You can inspect the evidence below or ask a follow-up question.';
      bubble('assistant',text,'Comparison result');
      chatMessages = [];
    }
    await loadReports();
  }
  $('job-form').onsubmit = e => { e.preventDefault(); run($('compare'),async () => {
    bubble('user','Compare the invoice and packing slip with their Spree order.');
    const form = new FormData(); form.append('invoice',$('invoice').files[0]); form.append('packing_slip',$('packing').files[0]); await compare(form);
  },true); };
  $('sample-pair').onclick = () => run($('sample-pair'),async () => {
    const prefix = config?.source_mode === 'live' ? 'live-' : '';
    const form = new FormData(); form.append('invoice',await example(prefix + 'invoice.txt'),prefix + 'invoice.txt'); form.append('packing_slip',await example(prefix + 'packing-slip.txt'),prefix + 'packing-slip.txt');
    bubble('user','Compare the demo invoice and packing slip.'); await compare(form);
  },true);
  $('add-documents').onclick = () => { view('assistant'); $('invoice').focus(); };
}
$('check-connections').onclick = async () => {
  const button = $('check-connections'); button.disabled = true; $('connection-status').textContent = 'Checking configured services?';
  try {
    const response = await fetch('/ready',{credentials:'same-origin'}); const data = await response.json();
    if (!data.dependencies) throw new Error(data.error?.message || 'Connection check could not finish.');
    $('connection-status').textContent = `Spree: ${data.dependencies.spree ? 'available' : 'unavailable'} ? Local model: ${data.dependencies.ollama_models ? 'installed' : 'unavailable'}. No inference was started.`;
  } catch (error) { $('connection-status').textContent = error.message; }
  finally { button.disabled = false; }
};
async function openWorkspace() {
  $('connection-error').hidden = true;
  try {
    await api('/v1/session',{method:'POST'});
    config = await api('/v1/config');
    $('mode').textContent = config.source_mode === 'live' ? 'Live Spree ? Read only' : 'Fixture mode ? Demo records';
    $('mode').className = 'badge' + (config.source_mode === 'fixture' ? ' warning' : '');
    $('model-label').textContent = config.model;
    $('setting-model').textContent = config.model;
    $('setting-source').textContent = config.source_mode === 'live' ? 'Live Spree' : 'Demo fixtures';
    if (project === 'COA') { $('reference').value = config.default_order_reference; await loadPolicies(); }
    await loadReports();
  } catch (error) {
    config = null;
    $('mode').textContent = 'Not connected';
    $('connection-error-text').textContent = error.message;
    $('connection-error').hidden = false;
  }
}
$('reconnect').onclick = openWorkspace;
openWorkspace();
