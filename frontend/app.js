/* app.js - boot, home screen, case loading, navigation */
const NAV = [['case', 'Case'], ['evidence', 'Evidence'], ['timeline', 'Timeline'], ['people', 'People'], ['devices', 'Devices'], ['locations', 'Locations'],
  ['graph', 'Graph'], ['hypotheses', 'Hypotheses'], ['nexus', 'NEXUS AI'], ['report', 'Final report'], ['settings', 'Settings']];
const DIFFS = [['EASY', 'Few suspects, obvious clues'], ['MEDIUM', 'False leads and contradictions'], ['HARD', 'Subtle clues, plausible suspects'], ['EXPERT', 'Conflicting timelines, deceptive witnesses']];
const TYPES = [['RANDOM', 'Random'], ['file_theft', 'Confidential file theft'], ['sabotage', 'Corporate sabotage'], ['missing_data', 'Missing research data'], ['unauthorized_access', 'Unauthorized system access'],
  ['fake_identity', 'Fake identity investigation'], ['data_manipulation', 'Data manipulation'], ['disappearing_files', 'Disappearing project files'], ['insider_activity', 'Suspicious insider activity'],
  ['prototype_theft', 'Research prototype theft'], ['cyber_mystery', 'Fictional cyber mystery']];

const App = {
  elapsed() { return DCS.ov && DCS.ov.closed ? DCS.base : DCS.base + (Date.now() - DCS.t0) / 1000; },

  async boot() {
    $('#btn-cases').onclick = () => App.showHome();
    const bar = $('#topbar');
    const search = h('input', { type: 'search', id: 'gsearch', placeholder: 'Search evidence\u2026', 'aria-label': 'Search all evidence', style: 'width:200px;padding:5px 10px',
      onkeydown: e => { if (e.key === 'Enter') { Evidence.q = e.target.value; Evidence.filter = 'ALL'; Evidence.flag = ''; App.go('evidence'); } } });
    const acc = h('button', { class: 'btn primary', id: 'btn-accuse', onclick: () => App.go('report') }, 'Make final accusation');
    bar.insertBefore(search, $('#btn-cases')); bar.insertBefore(acc, $('#btn-cases'));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeModal(); Evidence.close(); } });
    NAV.forEach(([k, l]) => $('#nav').append(h('button', { 'data-v': k, onclick: () => App.go(k) }, l)));
    await App.showHome();
  },

  /* ---------- home ---------- */
  async showHome() {
    const home = $('#home');
    home.classList.remove('hidden');
    home.innerHTML = '';
    let diff = 'MEDIUM';
    const seg = h('div', { class: 'seg' });
    const paint = () => { seg.innerHTML = ''; DIFFS.forEach(([k, d]) => seg.append(h('button', { class: k === diff ? 'on' : '', onclick: () => { diff = k; paint(); } }, h('b', {}, k.charAt(0) + k.slice(1).toLowerCase()), h('span', {}, d)))); };
    paint();
    const type = h('select', {}, TYPES.map(([k, l]) => h('option', { value: k }, l)));
    const seed = h('input', { type: 'text', placeholder: 'Leave blank for a random case, e.g. D7A9-42F1', maxlength: 24, style: 'font-family:var(--mono)' });
    const left = h('div', {}, h('h1', { class: 'home-title' }, 'Digital Crime Scene AI'), h('div', { class: 'home-sub' }, 'The evidence doesn\u2019t lie. But it can mislead you.'),
      h('label', { class: 'f', style: 'margin-top:0' }, 'Difficulty'), seg, h('label', { class: 'f' }, 'Case type'), type, h('label', { class: 'f' }, 'Case seed'), seed,
      h('div', { style: 'margin-top:20px' }, h('button', { class: 'btn primary', style: 'padding:10px 22px', onclick: () => App.generate(diff, type.value, seed.value) }, 'Generate case')),
      h('p', { class: 'faint', style: 'font-size:12px;margin-top:16px' }, 'Everything here is fictional: people, devices, logs and companies. The same seed and difficulty always rebuild the same case.'));
    const right = h('div', {}, h('h3', { style: 'margin-bottom:10px' }, 'Your investigations'), h('div', { id: 'case-list' }, h('div', { class: 'faint' }, 'Loading\u2026')),
      h('div', { class: 'sep' }), h('div', { class: 'row wrap' },
        h('label', { class: 'btn small', style: 'cursor:pointer' }, 'Import case file', h('input', { type: 'file', accept: '.json', style: 'display:none', onchange: App.importFile })),
        h('button', { class: 'btn small', onclick: App.showSaves }, 'Load saved snapshot')),
      DCS.caseId ? h('div', { style: 'margin-top:14px' }, h('button', { class: 'btn ghost small', onclick: () => home.classList.add('hidden') }, 'Back to current case')) : null);
    home.append(h('div', { class: 'home-box' }, h('div', { id: 'home-left' }, left), right));
    try {
      const cases = await GET('/cases');
      const box = $('#case-list');
      box.innerHTML = '';
      if (!cases.length) box.append(h('div', { class: 'faint' }, 'No cases yet. Generate your first one.'));
      cases.forEach(c => box.append(h('div', { class: 'case-row', onclick: () => App.loadCase(c.id, false) },
        h('div', {}, h('div', { style: 'font-size:13.5px' }, c.title.split(' - ')[0]), h('div', { class: 'faint mono', style: 'font-size:11.5px' }, `#${c.case_number} \u00b7 ${c.difficulty.toLowerCase()} \u00b7 ${c.seed}`)),
        h('div', { style: 'text-align:right;font-size:12px' }, h('div', { style: `color:${c.status === 'ACTIVE' ? 'var(--amber)' : c.solved ? 'var(--green)' : 'var(--coral)'}` }, c.status === 'ACTIVE' ? 'In progress' : c.solved ? 'Solved' : 'Closed'), c.grade && c.grade !== '-' ? h('div', { class: 'mono' }, c.grade + ' ' + c.total + '%') : null),
      )));
    } catch (e) { $('#case-list').textContent = 'Could not reach the game server: ' + e.message; }
  },
  async generate(diff, type, seed) {
    const box = $('#home-left');
    box.innerHTML = '';
    const log = h('div', { class: 'gen-log' });
    box.append(h('h2', { style: 'margin-bottom:14px' }, 'Building a new case'), log);
    const steps = ['GENERATING WORLD...', 'GENERATING PEOPLE...', 'GENERATING DEVICES...', 'GENERATING TIMELINE...', 'GENERATING EVIDENCE...', 'CHECKING CONSISTENCY...'];
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const call = POST('/case/new', { difficulty: diff, type, seed: seed.trim() || null }).catch(e => ({ error: e.message }));
    for (const s of steps) { log.append(h('div', {}, s)); await wait(380); }
    const ov = await call;
    if (ov.error) { log.append(h('div', { style: 'color:var(--coral)' }, 'Generation failed: ' + ov.error)); log.append(h('button', { class: 'btn', style: 'margin-top:12px', onclick: App.showHome }, 'Back')); return; }
    log.append(h('div', { class: 'ok' }, 'CASE READY.'));
    await wait(500);
    await App.loadCase(ov.id, true);
  },
  async importFile(e) {
    const f = e.target.files[0];
    if (!f) return;
    try { const ov = await POST('/import', JSON.parse(await f.text())); toast('Case imported'); await App.loadCase(ov.id, false); } catch (err) { toast('Import failed: ' + err.message); }
  },
  async showSaves() {
    const rows = await GET('/saves');
    modal([h('h3', { style: 'margin-bottom:10px' }, 'Saved snapshots'), rows.length ? rows.map(s => h('div', { class: 'case-row', onclick: async () => { closeModal(); const ov = await POST('/saves/load', { name: s.name }); App.loadCase(ov.id, false); } },
      h('span', { class: 'mono', style: 'font-size:12.5px' }, s.name), h('span', { class: 'faint' }, Math.round(s.size / 1024) + ' KB'))) : h('div', { class: 'empty' }, 'No snapshots yet. Use Settings, then Save snapshot.')]);
  },

  /* ---------- case loading ---------- */
  async loadCase(id, cinema) {
    DCS.caseId = id; DCS.feedSeeded = false; DCS.lastFeed = 0;
    Graph.pos = {}; Graph.inited = false; Graph.fitted = false; Graph.hidden = new Set(); Graph.sel = null; Graph.hlEv = null; Timeline.vx = null;
    DCS.ov = await GET(CP(''));
    DCS.base = DCS.ov.elapsed || 0; DCS.t0 = Date.now();
    $('#home').classList.add('hidden');
    $('#app').classList.remove('hidden');
    if (cinema) await App.cinema(DCS.ov.opening);
    clearInterval(DCS.ticker);
    DCS.ticker = setInterval(App.tick, 1000);
    await UI.renderNexus();
    await App.refreshData(true);
    await App.go(DCS.ov.closed ? 'report' : 'graph');
  },
  async cinema(lines) {
    const c = $('#cinema');
    c.classList.remove('hidden'); c.innerHTML = '';
    let skip = false;
    c.onclick = () => { skip = true; };
    const stage = h('div', {}); c.append(stage, h('div', { class: 'cine-skip' }, 'Click to skip'));
    const wait = ms => new Promise(r => { const t = setInterval(() => { if (skip) { clearInterval(t); r(); } }, 30); setTimeout(() => { clearInterval(t); r(); }, ms); });
    for (const [i, l] of lines.entries()) {
      if (skip) break;
      const big = l === 'DIGITAL CRIME SCENE AI' || l.startsWith('CASE #');
      const amber = l.startsWith('STATUS') || l === 'INCIDENT DETECTED';
      const el = h('div', { class: 'cine-line' + (big ? ' big' : '') + (amber ? ' amber' : ''), style: 'margin:10px 0' }, l);
      stage.innerHTML = ''; stage.append(el);
      requestAnimationFrame(() => el.classList.add('show'));
      await wait(i === lines.length - 1 ? 1100 : 780);
    }
    c.style.transition = 'opacity .6s'; c.style.opacity = 0;
    await new Promise(r => setTimeout(r, 600));
    c.classList.add('hidden'); c.style.opacity = 1;
  },

  /* ---------- data refresh ---------- */
  async refreshData(full) {
    DCS.ov = await GET(CP(''));
    DCS.analysis = await GET(CP('/analysis'));
    App.paintTop();
    await UI.renderLeft();
    UI.suggestions();
    Timeline.refresh();
    if (DCS.view === 'graph') await Graph.refresh(); else Graph.data = await GET(CP('/graph'));
    if (['evidence', 'people', 'devices', 'locations', 'case', 'nexus'].includes(DCS.view) && !full) await DCS.views[DCS.view]($('#view'));
    const nb = $('#nav button[data-v="case"]');
    if (nb) { const n = DCS.analysis.contradictions.filter(c => c.severity === 'CRITICAL').length; nb.innerHTML = 'Case' + (n ? `<span class="badge" title="critical contradictions">${n}</span>` : ''); }
  },
  paintTop() {
    const ov = DCS.ov;
    $('#tb-case').textContent = '#' + ov.case_number;
    const st = $('#tb-status');
    const label = !ov.closed ? 'ACTIVE' : ov.case_status === 'SOLVED' ? 'SOLVED' : ov.case_status === 'UNSOLVED' ? 'UNSOLVED' : 'CLOSED';
    st.textContent = label; st.className = 'v stamp ' + label.toLowerCase();
    $('#tb-evidence').textContent = `${ov.evidence.discovered} / ${ov.evidence.total}`;
    $('#tb-conf').textContent = ov.confidence + '%'; $('#tb-conf-bar').style.width = ov.confidence + '%';
    $('#btn-accuse').classList.toggle('hidden', !!ov.closed);
    $('#tb-time').textContent = fmtClock(App.elapsed());
  },
  tick() {
    if (!DCS.ov) return;
    $('#tb-time').textContent = fmtClock(App.elapsed());
    if (!DCS.ov.closed && ++DCS.beat % 15 === 0) POST(CP('/heartbeat'), { elapsed: Math.floor(App.elapsed()) }).catch(() => {});
  },

  /* ---------- navigation ---------- */
  async go(view) {
    DCS.view = view;
    $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.v === view));
    const root = $('#view');
    root.classList.toggle('flush', view === 'graph');
    root.scrollTop = 0;
    $('#right').classList.remove('open');
    try { await DCS.views[view](root); } catch (e) { root.innerHTML = ''; root.append(h('div', { class: 'empty' }, 'Could not load this view: ' + e.message)); }
  },
  confirmRetry() {
    modal([h('h3', {}, 'Retry this case?'), h('p', { class: 'dim' }, 'The same case is rebuilt from its seed. Your discoveries, hypotheses and timer are reset.'),
      h('div', { class: 'row', style: 'margin-top:14px' }, h('button', { class: 'btn primary', onclick: async () => { closeModal(); const ov = await POST(CP('/retry')); await App.loadCase(ov.id, true); } }, 'Retry case'), h('button', { class: 'btn', onclick: closeModal }, 'Cancel'))]);
  },
  confirmSolution() {
    modal([h('h3', {}, 'View the solution?'), h('p', { class: 'dim' }, 'This closes the case without a score. You can retry it afterwards from the same seed.'),
      h('div', { class: 'row', style: 'margin-top:14px' }, h('button', { class: 'btn danger', onclick: async () => { closeModal(); const r = await POST(CP('/solution')); await App.refreshData(true); Suspects.reveal(r); } }, 'Show me the solution'), h('button', { class: 'btn', onclick: closeModal }, 'Keep investigating'))]);
  },
};
window.addEventListener('load', () => App.boot());
