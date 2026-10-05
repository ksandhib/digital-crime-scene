/* ui.js - shared helpers, API client, side panels (case overview, live feed, NEXUS) */
const DCS = {
  caseId: null, ov: null, view: 'graph', views: {}, base: 0, t0: 0, ticker: null, beat: 0,
  analysis: null, lastFeed: 0, feedSeeded: false, nexusMode: 'deterministic',
};
const TYPE_META = {
  person: ['\u{1F464}', '#7ab8ea', 'Person'], device: ['\u{1F4BB}', '#b39df0', 'Device'], email: ['\u{1F4E7}', '#e8b44c', 'Email'],
  message: ['\u{1F4F1}', '#de93b6', 'Message'], file: ['\u{1F4C4}', '#5fbb8c', 'File'], image: ['\u{1F4F7}', '#7fcfc5', 'Image'],
  location: ['\u{1F4CD}', '#cba983', 'Location'], event: ['\u{1F552}', '#e5645e', 'Event'], org: ['\u{1F3E2}', '#9aa7b6', 'Organization'],
};

function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec));
  return [sec / 3600, (sec / 60) % 60, sec % 60].map(n => String(Math.floor(n)).padStart(2, '0')).join(':');
}
function minToStr(m) { return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(Math.round(m % 60)).padStart(2, '0'); }

async function api(method, path, body) {
  const res = await fetch('/api' + path, {
    method, headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* html report etc. */ }
  if (!res.ok) throw new Error((data && data.detail) || res.statusText);
  return data;
}
const GET = p => api('GET', p), POST = (p, b) => api('POST', p, b === undefined ? {} : b);
const CP = p => `/case/${DCS.caseId}${p}`;

function toast(msg, kind = '') {
  const t = h('div', { class: 'toast ' + kind }, msg);
  const box = $('#toasts');
  while (box.children.length >= 3) box.firstChild.remove();
  box.append(t);
  setTimeout(() => t.remove(), 5200);
}
function modal(content, wide) {
  const m = $('#modal');
  m.innerHTML = '';
  const box = h('div', { class: 'modal-box' + (wide ? ' wide' : '') }, content);
  m.append(box);
  m.classList.remove('hidden');
  m.onclick = e => { if (e.target === m) closeModal(); };
  return box;
}
function closeModal() { $('#modal').classList.add('hidden'); $('#modal').innerHTML = ''; }

/* ---- evidence tags and badges ---- */
function evTag(id) { return h('span', { class: 'tag', title: 'Open ' + id, onclick: e => { e.stopPropagation(); Evidence.open(id); } }, id); }
function relPill(r) { return h('span', { class: 'rel ' + r, title: 'Reliability' }, r); }
function linkify(text) {
  const frag = document.createDocumentFragment();
  String(text).split(/(E-\d{3})/).forEach(p => frag.append(/^E-\d{3}$/.test(p) ? evTag(p) : document.createTextNode(p)));
  return frag;
}
function evTags(ids) { return h('span', { class: 'row wrap', style: 'display:inline-flex;gap:4px' }, (ids || []).map(evTag)); }

/* ---- case panel (left) ---- */
const UI = {
  async renderLeft() {
    const ov = DCS.ov, left = $('#left');
    const sus = (DCS.analysis && DCS.analysis.suspicion) || {};
    const prev = $('.feed', left);
    const scroll = prev ? prev.scrollTop : 0;
    left.innerHTML = '';
    left.append(
      h('div', { class: 'case-head' },
        h('div', { class: 'faint', style: 'font-size:11.5px' }, `Case #${ov.case_number} \u00b7 ${ov.difficulty.toLowerCase()} \u00b7 seed ${ov.seed}`),
        h('div', { class: 'case-title' }, ov.title.split(' - ')[0]),
        h('dl', { class: 'kv', style: 'margin-top:10px' },
          h('dt', {}, 'Victim'), h('dd', {}, `${ov.victim.name}, ${ov.victim.role}`),
          h('dt', {}, 'Incident'), h('dd', {}, `Alert raised ${ov.incident_time}`),
          h('dt', {}, 'Company'), h('dd', {}, ov.company),
          h('dt', {}, 'Location'), h('dd', {}, ov.location),
          h('dt', {}, 'Severity'), h('dd', { style: 'color:var(--coral)' }, ov.severity.toLowerCase()))),
      h('div', { class: 'section-title' }, 'Suspects ', h('span', { class: 'faint', style: 'font-size:12px;font-family:var(--sans)' }, `(${ov.suspects.length})`)),
      h('div', { class: 'people-list' }, ov.suspects.map((s, i) => {
        const sc = sus[s.ref] ? sus[s.ref].score : 0;
        return h('div', { class: 'person-row', title: 'Open profile', onclick: () => Suspects.openPerson(s.ref) },
          h('span', { class: 'avatar' }, s.name.split(' ').map(x => x[0]).join('')),
          h('div', {}, h('div', { style: 'font-size:13px' }, s.name), h('div', { class: 'faint', style: 'font-size:11.5px' }, s.role)),
          h('span', { class: 'sus-bar', title: `Suspicion ${sc}%` }, h('i', { style: `width:${sc}%` })));
      })),
      h('div', { class: 'section-title' }, 'Live investigation feed'),
      h('div', { class: 'feed', id: 'feed' }));
    $('.feed', left).scrollTop = scroll;
    await UI.renderFeed();
  },
  async renderFeed() {
    const rows = await GET(CP('/feed'));
    const box = $('#feed');
    if (!box) return;
    box.innerHTML = '';
    const icons = { evidence: '\u{1F50E} Evidence discovered', contradiction: '\u26A0 Contradiction detected', correlation: '\u{1F9E0} NEXUS correlation', system: 'System', achievement: '\u{1F3C6} Achievement', hypothesis: 'Hypothesis' };
    rows.forEach(r => {
      const fresh = DCS.feedSeeded && r.id > DCS.lastFeed;
      if (fresh && ['contradiction', 'correlation', 'achievement'].includes(r.kind)) toast(r.text, r.kind);
      box.append(h('div', { class: `feed-item ${r.kind}${fresh ? ' new' : ''}` },
        h('div', { class: 't' }, r.ts),
        h('div', {}, h('div', { class: 'kind' }, icons[r.kind] || r.kind), h('div', {}, linkify(r.evidence_id ? `${r.evidence_id} ${r.text}` : r.text)))));
    });
    if (rows.length) DCS.lastFeed = Math.max(DCS.lastFeed, rows[0].id);
    DCS.feedSeeded = true;
  },

  /* ---- NEXUS (right) ---- */
  async renderNexus() {
    const right = $('#right');
    right.innerHTML = '';
    const st = (await GET('/settings')).ollama;
    DCS.nexusMode = st.online && st.model && st.use_llm ? 'llm' : 'deterministic';
    right.append(
      h('div', { class: 'nx-head' }, h('span', { class: 'nx-orb' + (DCS.nexusMode === 'llm' ? '' : ' det') }),
        h('div', {}, h('div', { style: 'font-family:var(--serif);font-size:16px' }, 'NEXUS'),
          h('div', { class: 'faint', style: 'font-size:11.5px' }, DCS.nexusMode === 'llm' ? `Local model: ${st.model}` : 'Evidence engine (offline mode)'))),
      h('div', { class: 'nx-log', id: 'nx-log' }),
      h('div', { class: 'nx-sugg', id: 'nx-sugg' }),
      h('form', { class: 'nx-form', id: 'nx-form', onsubmit: e => { e.preventDefault(); UI.ask($('#nx-in').value); } },
        h('input', { type: 'text', id: 'nx-in', placeholder: 'Ask about the evidence\u2026', autocomplete: 'off' }),
        h('button', { class: 'btn primary', type: 'submit' }, 'Ask')));
    const hist = await GET(CP('/nexus/history'));
    const log = $('#nx-log');
    if (!hist.length) UI.botMsg({ text: 'I can only answer from evidence you have discovered. Examine devices, people and locations to widen what I can see. What would you like to check?', evidence: [], confidence: null, mode: 'intro' });
    hist.forEach(q => { UI.userMsg(q.question); UI.botMsg({ text: q.answer, evidence: q.evidence || [], confidence: null, mode: q.mode }); });
    UI.suggestions();
    log.scrollTop = log.scrollHeight;
  },
  suggestions() {
    const ov = DCS.ov, a = DCS.analysis;
    const lead = a && a.lead && a.lead.name ? a.lead.name.split(' ')[0] : ov.suspects[0].name.split(' ')[0];
    const other = ov.suspects[ov.suspects.length > 1 ? 1 : 0].name.split(' ')[0];
    const qs = ['Who had access to the stolen file?', `Show me everything connected to ${lead}`, 'What happened between 23:00 and 23:30?',
      `Which evidence contradicts ${other}'s statement?`, 'What evidence is missing?', 'Which suspects had opportunity?', 'Show me the strongest evidence'];
    const box = $('#nx-sugg');
    if (!box) return;
    box.innerHTML = '';
    qs.forEach(q => box.append(h('button', { class: 'chip', onclick: () => UI.ask(q) }, q)));
  },
  userMsg(t) { const l = $('#nx-log'); l.append(h('div', { class: 'msg user' }, t)); l.scrollTop = l.scrollHeight; },
  botMsg(r) {
    const l = $('#nx-log');
    const body = h('div', { class: 'body' });
    String(r.text).split('\n').forEach((line, i) => { if (i) body.append(document.createElement('br')); body.append(linkify(line)); });
    const meta = h('div', { class: 'meta' });
    if (r.confidence != null) meta.append(h('span', {}, `Confidence ${r.confidence}%`));
    if (r.evidence && r.evidence.length) meta.append(h('span', {}, 'Evidence:'), evTags(r.evidence));
    if (r.mode === 'llm') meta.append(h('span', { class: 'faint' }, '\u00b7 local model'));
    l.append(h('div', { class: 'msg bot' }, body, meta.childNodes.length ? meta : null));
    l.scrollTop = l.scrollHeight;
  },
  async ask(q) {
    q = (q || '').trim();
    if (!q) return;
    $('#nx-in').value = '';
    UI.userMsg(q);
    const l = $('#nx-log');
    const typing = h('div', { class: 'msg bot' }, h('span', { class: 'typing' }, h('i'), h('i'), h('i')));
    l.append(typing); l.scrollTop = l.scrollHeight;
    try { const r = await POST(CP('/nexus'), { question: q }); typing.remove(); UI.botMsg(r); }
    catch (e) { typing.remove(); UI.botMsg({ text: 'NEXUS could not answer: ' + e.message, evidence: [] }); }
  },
};

/* ---- the shared "examine" action ---- */
async function examine(ref, btn) {
  if (btn) btn.disabled = true;
  try {
    const r = await POST(CP('/examine'), { ref });
    toast(r.new.length ? `${r.name}: ${r.new.length} new item(s) recovered` : `${r.name}: nothing further recoverable`, r.new.length ? 'evidence' : '');
    await App.refreshData();
    return r;
  } catch (e) { toast(e.message); }
  finally { if (btn) btn.disabled = false; }
}

/* ---- settings + tools view ---- */
DCS.views.settings = async function (root) {
  const s = await GET('/settings');
  const ach = await GET('/achievements');
  const o = s.ollama;
  root.innerHTML = '';
  const model = h('select', { onchange: async e => { await POST('/settings', { model: e.target.value }); toast('Model saved'); UI.renderNexus(); } },
    h('option', { value: '' }, 'Auto (first available)'), o.models.map(m => h('option', { value: m, selected: m === s.settings.model }, m)));
  root.append(h('div', { class: 'pad', style: 'max-width:860px' },
    h('h2', {}, 'Settings'),
    h('div', { class: 'card', style: 'margin-top:16px' },
      h('h3', {}, 'NEXUS language model'),
      h('p', { class: 'dim' }, o.online ? `Ollama is running with ${o.models.length} model(s). NEXUS uses it to phrase answers; every fact still comes from the case database.` : 'Ollama was not detected. NEXUS answers with the built-in evidence engine, which is fully playable. Start Ollama and reload to enable local model phrasing.'),
      h('label', { class: 'f' }, 'Model'), model,
      h('label', { class: 'row', style: 'margin-top:12px;gap:8px' },
        h('input', { type: 'checkbox', checked: s.settings.use_llm, onchange: async e => { await POST('/settings', { use_llm: e.target.checked }); UI.renderNexus(); } }), 'Use the local model when available')),
    h('div', { class: 'card', style: 'margin-top:14px' },
      h('h3', {}, 'This case'),
      h('p', { class: 'dim' }, `Seed ${DCS.ov.seed} (${DCS.ov.difficulty.toLowerCase()}). Enter the same seed and difficulty on the new-case screen to recreate it.`),
      h('div', { class: 'row wrap' },
        h('button', { class: 'btn', onclick: () => { location.href = `/api/case/${DCS.caseId}/export`; } }, 'Export case'),
        h('button', { class: 'btn', onclick: async () => { const r = await POST(CP('/save')); toast('Saved to saves/' + r.name); } }, 'Save snapshot'),
        h('button', { class: 'btn', onclick: () => App.confirmRetry() }, 'Retry case'),
        h('button', { class: 'btn danger', onclick: () => App.confirmSolution() }, 'View solution'))),
    h('div', { class: 'card', style: 'margin-top:14px' },
      h('h3', {}, 'Achievements'),
      h('div', { class: 'grid', style: 'grid-template-columns:repeat(auto-fill,minmax(250px,1fr));margin-top:10px' },
        ach.map(a => h('div', { style: 'display:flex;gap:10px;opacity:' + (a.unlocked ? 1 : .45) },
          h('div', { style: 'font-size:24px' }, a.icon),
          h('div', {}, h('div', { style: 'font-weight:600' }, a.name), h('div', { class: 'dim', style: 'font-size:12.5px' }, a.description + (a.progress != null && !a.unlocked ? ` (${a.progress}/5)` : ''))))))
    )));
};
