/* suspects.js - people, devices, locations, case view, hypotheses, accusation, reveal */
const Suspects = {
  openPerson(ref) { Evidence.openEntity(ref); },

  gauge(label, pct, color, note) {
    return h('div', { class: 'gauge' }, h('div', { class: 'lab' }, h('span', {}, label), h('span', { class: 'mono' }, pct == null ? note || 'untested' : pct + '%')),
      h('div', { class: 'bar' }, h('i', { style: `width:${pct || 0}%;background:${color}` })));
  },
  profileBlock(p) {
    const root = h('div', { style: 'margin-top:8px' });
    root.append(h('dl', { class: 'kv' }, h('dt', {}, 'Role'), h('dd', {}, p.role), h('dt', {}, 'Age'), h('dd', {}, p.age), h('dt', {}, 'Access level'), h('dd', {}, p.access_level.toLowerCase()),
      h('dt', {}, 'Known devices'), h('dd', {}, p.known_devices ? `${p.known_devices} (${p.devices.join(', ')})` : 'none assigned'), h('dt', {}, 'Last seen'), h('dd', {}, p.last_seen),
      p.kind === 'suspect' ? [h('dt', {}, 'Motive'), h('dd', { style: p.motive === 'UNKNOWN' ? 'color:var(--faint)' : '' }, p.motive === 'UNKNOWN' ? 'Unknown' : p.motive)] : null));
    if (p.bio) root.append(h('div', { class: 'dim', style: 'font-size:12.5px;margin-top:8px' }, p.bio));
    if (p.alibi) root.append(h('div', { class: 'alibi' }, p.alibi));
    if (p.kind === 'suspect') {
      root.append(Suspects.gauge('AI consistency', p.consistency, p.consistency != null && p.consistency < 70 ? 'var(--coral)' : 'var(--green)', 'untested'), Suspects.gauge('Suspicion', p.suspicion, 'var(--coral)'), Suspects.gauge('Evidence chain', p.chain, 'var(--amber)'));
      if (p.alibi_status === 'contradicted') root.append(h('div', { class: 'contra-flag', style: 'margin-top:8px' }, '\u26A0 Alibi contradiction detected'));
      if (p.checklist.length) root.append(h('div', { style: 'margin-top:10px' }, p.checklist.map(c => h('div', { class: 'chk ' + c.icon }, h('span', { class: 'ic' }, { ok: '\u2714', warn: '\u26A0', no: '\u2716', clear: '\u25CB' }[c.icon]), h('span', {}, c.text, ' ', evTags((c.evidence || []).slice(0, 3)))))));
      else root.append(h('div', { class: 'faint', style: 'margin-top:10px;font-size:12.5px' }, 'No evidence assessed yet.'));
    } else if (p.statements && p.statements.length) {
      root.append(h('div', { class: 'dim', style: 'font-size:12px;margin-top:10px' }, 'Statements'), evTags(p.statements));
    }
    return root;
  },
  chainBlock(ch) {
    if (!ch) return h('div', { class: 'empty' }, 'No lead yet. Establish the incident window first.');
    const complete = ch.complete;
    const root = h('div', {}, h('div', { class: 'row between', style: 'margin-bottom:8px' }, h('b', { style: 'font-family:var(--serif);font-size:15px' }, ch.name ? `Evidence chain: ${ch.name}` : 'Evidence chain'),
      h('span', { class: 'mono', style: `color:${complete ? 'var(--green)' : 'var(--amber)'}` }, (complete ? 'CHAIN STRENGTH ' : 'CHAIN INCOMPLETE ') + ch.strength + '%')));
    root.append(h('div', { class: 'chain' }, ch.steps.map(s => h('div', { class: 'step ' + s.status }, h('div', { class: 'dot' }, { ok: '\u2713', partial: '~', contradicted: '\u00d7', missing: '' }[s.status]),
      h('div', {}, h('div', {}, s.label), h('div', { class: 'n' }, s.note)), h('div', {}, evTags((s.evidence || []).slice(0, 2)))))));
    if (ch.missing.length) root.append(h('div', { class: 'note warn', style: 'margin-top:8px' }, 'Missing: ', ch.missing.join(', ')));
    return root;
  },
};

/* ---------------- people ---------------- */
DCS.views.people = async function (root) {
  const ppl = await GET(CP('/people'));
  root.innerHTML = '';
  const card = (p, i) => h('div', { class: 'sus-card' },
    h('div', { class: 'row between' }, h('span', { class: 'no' }, p.kind === 'suspect' ? `Suspect #${String(i + 1).padStart(2, '0')}` : p.kind), p.kind === 'suspect' && p.suspicion >= 60 ? h('span', { class: 'flag contradiction' }, 'high suspicion') : null),
    h('h3', { style: 'font-size:19px' }, p.name), h('div', { class: 'dim', style: 'margin-bottom:4px' }, p.role),
    Suspects.profileBlock(p),
    h('div', { class: 'row', style: 'margin-top:12px' }, h('button', { class: 'btn small', onclick: () => Evidence.openEntity(p.ref) }, 'Open file'),
      h('button', { class: 'btn small', disabled: !p.more || DCS.ov.closed, onclick: async e => { await examine(p.ref, e.target); } }, p.more ? 'Examine' : 'Fully examined'),
      p.kind === 'suspect' ? h('button', { class: 'btn small', onclick: () => Hypo.start(p) }, 'New hypothesis') : null));
  const sus = ppl.filter(p => p.kind === 'suspect');
  root.append(h('div', { class: 'sus-grid' }, sus.map(card)),
    h('div', { class: 'section-title', style: 'padding:6px 18px' }, 'Victim and witnesses'),
    h('div', { class: 'sus-grid', style: 'padding-top:6px' }, ppl.filter(p => p.kind !== 'suspect').map(card)));
};

/* ---------------- devices ---------------- */
DCS.views.devices = async function (root) {
  const rows = await GET(CP('/devices'));
  root.innerHTML = '';
  root.append(h('div', { class: 'sus-grid' }, rows.map(d => h('div', { class: 'sus-card' },
    h('div', { class: 'row between' }, h('span', { class: 'no' }, d.ref + ' \u00b7 ' + d.kind), d.more && !d.examined ? h('span', { class: 'flag cluster' }, 'unexamined') : null),
    h('h3', {}, '\u{1F4BB} ' + d.name),
    h('dl', { class: 'kv', style: 'margin-top:8px' }, h('dt', {}, 'Owner'), h('dd', {}, d.owner), h('dt', {}, 'Location'), h('dd', {}, d.location), h('dt', {}, 'Last activity'), h('dd', {}, d.last_activity),
      h('dt', {}, 'Connections'), h('dd', {}, d.connections + ' external'), h('dt', {}, 'Events'), h('dd', {}, d.events + ' recovered')),
    h('div', { class: 'row', style: 'margin-top:12px' }, h('button', { class: 'btn small', onclick: () => Evidence.openEntity(d.ref) }, 'Open'),
      h('button', { class: 'btn small', disabled: !d.more || DCS.ov.closed, onclick: e => examine(d.ref, e.target) }, d.more ? 'Examine' : 'Fully examined'))))));
};

/* ---------------- locations ---------------- */
DCS.views.locations = async function (root) {
  const rows = await GET(CP('/locations'));
  root.innerHTML = '';
  root.append(h('div', { class: 'sus-grid' }, rows.map(l => h('div', { class: 'sus-card' },
    h('div', { class: 'row between' }, h('span', { class: 'no' }, l.ref + ' \u00b7 ' + l.building), l.more && !l.examined ? h('span', { class: 'flag cluster' }, 'unexamined') : null),
    h('h3', {}, '\u{1F4CD} ' + l.name),
    h('div', { class: 'dim', style: 'font-size:12.5px;margin:6px 0' }, 'Devices: ' + (l.devices.join(', ') || 'none')),
    l.people.length ? h('table', { class: 't' }, l.people.map(p => h('tr', {}, h('td', { class: 'mono' }, p.time), h('td', {}, p.who), h('td', {}, evTag(p.evidence_id))))) : h('div', { class: 'faint', style: 'font-size:12.5px' }, 'No badge records recovered yet.'),
    h('div', { class: 'row', style: 'margin-top:12px' }, h('button', { class: 'btn small', onclick: () => Evidence.openEntity(l.ref) }, 'Open'),
      h('button', { class: 'btn small', disabled: !l.more || DCS.ov.closed, onclick: e => examine(l.ref, e.target) }, l.more ? 'Examine' : 'Fully examined'))))));
};

/* ---------------- case overview ---------------- */
DCS.views.case = async function (root) {
  const a = DCS.analysis = await GET(CP('/analysis'));
  const ov = DCS.ov;
  root.innerHTML = '';
  const lead = a.lead.ref ? await GET(CP('/chain/' + a.lead.ref)) : null;
  root.append(
    h('div', { class: 'hero' },
      h('div', { class: 'faint', style: 'font-size:12.5px' }, `${ov.company} \u00b7 ${ov.date} \u00b7 ${ov.project || ''}`),
      h('h2', {}, ov.title.split(' - ').join(': ')),
      h('p', { class: 'dim', style: 'max-width:760px;font-family:var(--serif);font-size:15.5px' }, ov.summary),
      h('div', { class: 'facts' }, [['Evidence found', `${ov.evidence.discovered} of ${ov.evidence.total}`], ['Suspects', ov.counts.suspects], ['Devices', ov.counts.devices], ['Locations', ov.counts.locations],
        ['Alert raised', ov.incident_time], ['Incident window', a.window.exact ? `${minToStr(a.window.start)}\u2013${minToStr(a.window.end)}` : 'not established']].map(([k, v]) => h('div', { class: 'fact' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v))))),
    h('div', { class: 'pad grid', style: 'grid-template-columns:repeat(auto-fit,minmax(380px,1fr));align-items:start' },
      h('div', { class: 'card' }, h('h3', { style: 'margin-bottom:10px' }, a.lead.name ? `Current lead: ${a.lead.name} (${a.lead.confidence}%)` : 'No clear lead yet'), Suspects.chainBlock(lead)),
      h('div', { class: 'grid' },
        h('div', { class: 'card' }, h('h3', { style: 'margin-bottom:8px' }, 'Contradictions'),
          a.contradictions.length ? a.contradictions.map(c => h('div', { class: 'alert-contra' }, h('b', {}, '\u26A0 ' + c.severity.toLowerCase() + ' '), c.text, ' ', evTags(c.evidence_ids.slice(0, 3)))) : h('div', { class: 'faint' }, 'None detected yet. Statements are tested as evidence arrives.')),
        h('div', { class: 'card' }, h('h3', { style: 'margin-bottom:8px' }, 'NEXUS correlations'),
          a.correlations.length ? a.correlations.map(c => h('div', { class: 'corr', style: 'margin-bottom:8px' }, h('div', { class: 'lab' }, c.label + ' \u00b7 ' + c.confidence + '%'), h('div', { style: 'font-size:13px;margin:3px 0' }, c.text), evTags(c.evidence_ids))) : h('div', { class: 'faint' }, 'No correlations yet.')),
        h('div', { class: 'card' }, h('h3', { style: 'margin-bottom:8px' }, 'Strongest evidence'),
          a.strongest.length ? a.strongest.map(s => h('div', { class: 'row', style: 'padding:3px 0' }, evTag(s.id), h('span', { style: 'font-size:13px;flex:1' }, s.title), relPill(s.reliability))) : h('div', { class: 'faint' }, 'Nothing yet.')),
        h('div', { class: 'card' }, h('h3', { style: 'margin-bottom:8px' }, 'Where to look next'),
          a.unexamined.length ? a.unexamined.map(u => h('div', { class: 'row', style: 'padding:3px 0' }, h('span', { style: 'flex:1' }, u.name), h('button', { class: 'btn small', disabled: ov.closed, onclick: e => examine(u.ref, e.target) }, 'Examine'))) : h('div', { class: 'faint' }, 'Every known source has been examined.')))));
};

/* ---------------- NEXUS console ---------------- */
DCS.views.nexus = async function (root) {
  const a = DCS.analysis = await GET(CP('/analysis'));
  root.innerHTML = '';
  const ask = q => { $('#nx-in').value = q; UI.ask(q); };
  const ov = DCS.ov, nm = ov.suspects.map(s => s.name.split(' ')[0]);
  const prompts = ['Who had access to the stolen file?', ...nm.slice(0, 3).map(n => `Show me everything connected to ${n}`), 'What happened between 23:00 and 23:30?', ...nm.slice(0, 2).map(n => `Which evidence contradicts ${n}'s statement?`),
    'What evidence is missing?', 'Which suspects had opportunity?', 'Show me the strongest evidence', 'Who was near Laptop #04 at 23:20?'];
  root.append(h('div', { class: 'pad', style: 'max-width:980px' }, h('h2', {}, 'NEXUS analysis console'),
    h('p', { class: 'dim', style: 'max-width:680px' }, 'NEXUS reads only what you have discovered. Answers cite evidence ids, and its confidence reflects how reliable and how plentiful that evidence is. Pick a question or type your own in the panel on the right.'),
    h('div', { class: 'row wrap', style: 'margin:12px 0 18px' }, prompts.map(p => h('button', { class: 'chip', onclick: () => ask(p) }, p))),
    h('div', { class: 'grid', style: 'grid-template-columns:repeat(auto-fit,minmax(300px,1fr))' },
      h('div', { class: 'card' }, h('h3', {}, 'Evidence quality'), h('div', { style: 'margin-top:8px' }, Object.entries(a.reliability_mix).map(([k, v]) => h('div', { class: 'row', style: 'padding:3px 0' }, h('span', { class: 'rel ' + k, style: 'width:110px;text-align:center' }, k), h('div', { class: 'gauge', style: 'flex:1;margin:0' }, h('div', { class: 'bar' }, h('i', { style: `width:${Math.min(100, v * 6)}%;background:var(--ice)` }))), h('span', { class: 'mono' }, v))))),
      h('div', { class: 'card' }, h('h3', {}, 'Suspicion by suspect'), h('div', { style: 'margin-top:8px' }, ov.suspects.map(s => { const x = a.suspicion[s.ref]; return h('div', { class: 'gauge', style: 'margin:8px 0' }, h('div', { class: 'lab' }, h('span', {}, s.name), h('span', { class: 'mono' }, x.score + '%' + (x.opportunity === 'absent' ? ' \u00b7 cleared' : ''))), h('div', { class: 'bar' }, h('i', { style: `width:${x.score}%;background:${x.opportunity === 'absent' ? 'var(--green)' : 'var(--coral)'}` }))); })))))); 
};

/* ---------------- hypotheses ---------------- */
const Hypo = {
  start(p) { App.go('hypotheses').then(() => { const s = $('#h-suspect'); if (s) { s.value = p.ref; $('#h-title').value = `${p.name} is responsible.`; $('#h-title').focus(); } }); },
};
DCS.views.hypotheses = async function (root) {
  const list = await GET(CP('/hypotheses'));
  root.innerHTML = '';
  const sel = h('select', { id: 'h-suspect' }, h('option', { value: '' }, 'No specific suspect'), DCS.ov.suspects.map(s => h('option', { value: s.ref }, s.name)));
  const title = h('textarea', { id: 'h-title', placeholder: 'e.g. Marcus stole the research archive.' });
  const kind = h('select', { id: 'h-kind' }, h('option', { value: 'who' }, 'Who did it'), h('option', { value: 'how' }, 'How it happened'), h('option', { value: 'why' }, 'Why it happened'));
  const form = h('div', { class: 'card', style: 'margin-bottom:18px' }, h('h3', {}, 'New hypothesis'),
    h('label', { class: 'f' }, 'Your theory'), title, h('div', { class: 'grid', style: 'grid-template-columns:1fr 1fr;gap:10px' }, h('div', {}, h('label', { class: 'f' }, 'About'), sel), h('div', {}, h('label', { class: 'f' }, 'Type'), kind)),
    h('div', { style: 'margin-top:12px' }, h('button', { class: 'btn primary', disabled: DCS.ov.closed, onclick: async () => {
      try { await POST(CP('/hypotheses'), { title: title.value, suspect_ref: sel.value || null, kind: kind.value }); DCS.views.hypotheses(root); App.refreshData(true); } catch (e) { toast(e.message); } } }, 'Record hypothesis')));
  root.append(h('div', { class: 'pad', style: 'max-width:900px' }, h('h2', { style: 'margin-bottom:14px' }, 'Hypotheses'), form,
    list.length ? list.map(x => {
      const an = x.analysis, col = an.confidence >= 70 ? 'var(--green)' : an.confidence >= 40 ? 'var(--amber)' : 'var(--coral)';
      return h('div', { class: 'card', style: 'margin-bottom:14px' },
        h('div', { class: 'row between' }, h('span', { class: 'mono faint' }, `Hypothesis #${String(x.id).padStart(2, '0')}`), h('button', { class: 'btn small danger', onclick: async () => { await api('DELETE', CP('/hypotheses/' + x.id)); DCS.views.hypotheses(root); } }, 'Delete')),
        h('h3', { style: 'margin:4px 0 8px;font-size:17px' }, '\u201C' + x.title + '\u201D'),
        x.suspect_ref ? [Suspects.gauge('Current confidence', an.confidence, col)] : h('div', { class: 'faint' }, 'No suspect attached, so no automatic scoring.'),
        h('div', { class: 'grid', style: 'grid-template-columns:1fr 1fr;margin-top:12px' },
          h('div', {}, h('div', { class: 'dim', style: 'font-size:12px;margin-bottom:4px' }, 'Supporting'), an.support.length ? an.support.map(s => h('div', { class: 'chk ok' }, h('span', { class: 'ic' }, '\u2714'), h('span', {}, s.text, ' ', evTags(s.evidence.slice(0, 3))))) : h('div', { class: 'faint' }, 'None yet'),
            x.pinned_support.length ? h('div', { style: 'margin-top:6px' }, h('span', { class: 'faint', style: 'font-size:12px' }, 'Pinned by you: '), evTags(x.pinned_support)) : null),
          h('div', {}, h('div', { class: 'dim', style: 'font-size:12px;margin-bottom:4px' }, 'Against'), an.against.length ? an.against.map(s => h('div', { class: 'chk no' }, h('span', { class: 'ic' }, '\u2716'), h('span', {}, s.text, ' ', evTags((s.evidence || []).slice(0, 2))))) : h('div', { class: 'faint' }, 'None yet'),
            x.pinned_against.length ? h('div', { style: 'margin-top:6px' }, h('span', { class: 'faint', style: 'font-size:12px' }, 'Pinned by you: '), evTags(x.pinned_against)) : null)));
    }) : h('div', { class: 'empty' }, 'No hypotheses yet. Record a theory, then pin evidence from any evidence card.')));
};

/* ---------------- final accusation ---------------- */
DCS.views.report = async function (root) {
  root.innerHTML = '';
  if (DCS.ov.closed) {
    const r = await GET(CP('/result'));
    root.append(h('div', { class: 'pad', style: 'max-width:760px' }, h('h2', {}, r.headline || 'Case closed'), h('p', { class: 'dim' }, r.messages ? r.messages.join(' ') : 'The solution was viewed.'),
      h('div', { class: 'row', style: 'margin-top:16px' }, h('button', { class: 'btn primary', onclick: () => Suspects.reveal(r) }, 'Replay the reveal'),
        h('a', { class: 'btn', href: `/api/case/${DCS.caseId}/report`, target: '_blank', style: 'text-decoration:none' }, 'Open investigation report'),
        h('button', { class: 'btn', onclick: () => App.showHome() }, 'New case'))));
    return;
  }
  const opt = await GET(CP('/options'));
  const ev = (await GET(CP('/evidence'))).items;
  const f = { who: h('select', {}, h('option', { value: '' }, 'Choose a suspect'), opt.suspects.map(s => h('option', { value: s.ref }, s.name))),
    why: h('select', {}, h('option', { value: '' }, 'Choose a motive'), opt.motives.map(s => h('option', { value: s.key }, s.label))),
    how: h('select', {}, h('option', { value: '' }, 'Choose a method'), opt.methods.map(s => h('option', { value: s.key }, s.label))),
    when: h('input', { type: 'text', placeholder: 'HH:MM, e.g. 23:17', maxlength: 5 }), text: h('textarea', { placeholder: 'Explain your reasoning: access, presence, timeline, contradictions.', style: 'min-height:110px' }) };
  const picks = new Set();
  const list = h('div', { style: 'max-height:230px;overflow:auto;border:1px solid var(--line2);border-radius:6px;padding:6px 10px;background:#0d141c' }, ev.map(e => h('label', { class: 'row', style: 'padding:3px 0;cursor:pointer;font-size:13px' },
    h('input', { type: 'checkbox', onchange: x => { x.target.checked ? picks.add(e.id) : picks.delete(e.id); } }), evTagStatic(e.id), h('span', { style: 'flex:1' }, e.title), relPill(e.reliability))));
  const submit = h('button', { class: 'btn primary', onclick: async () => {
    if (!f.who.value) return toast('Choose who you are accusing.');
    if (!confirm('Submit your final accusation? The case will close and the truth will be revealed.')) return;
    submit.disabled = true;
    try {
      const r = await POST(CP('/accuse'), { suspect_ref: f.who.value, motive_key: f.why.value || null, method_key: f.how.value || null, time: f.when.value, evidence: [...picks], explanation: f.text.value, elapsed: App.elapsed() });
      DCS.ov.closed = true; await App.refreshData(true); Suspects.reveal(r);
    } catch (e) { toast(e.message); submit.disabled = false; }
  } }, 'Submit investigation');
  root.append(h('div', { class: 'pad', style: 'max-width:820px' }, h('h2', {}, 'Make final accusation'), h('p', { class: 'dim' }, 'You can accuse at any point, but the case closes when you submit. Back your theory with evidence you have actually found.'),
    h('div', { class: 'grid', style: 'grid-template-columns:1fr 1fr' }, h('div', {}, h('label', { class: 'f' }, 'Who?'), f.who), h('div', {}, h('label', { class: 'f' }, 'Why?'), f.why),
      h('div', {}, h('label', { class: 'f' }, 'When did it happen?'), f.when), h('div', {}, h('label', { class: 'f' }, 'How?'), f.how)),
    h('label', { class: 'f' }, `Evidence (${ev.length} discovered)`), list, h('label', { class: 'f' }, 'Your explanation'), f.text, h('div', { style: 'margin-top:16px' }, submit)));
};

/* ---------------- cinematic reveal ---------------- */
Suspects.reveal = async function (r) {
  const ov = document.createElement('div');
  ov.className = 'reveal'; ov.style.cssText = 'position:fixed;z-index:150;inset:0';
  document.body.append(ov);
  const lines = ['ANALYZING INVESTIGATION...', 'CORRELATING EVIDENCE...', 'RECONSTRUCTING TIMELINE...', 'ACCESSING CASE TRUTH...'];
  const wait = ms => new Promise(res => setTimeout(res, ms));
  const t = h('div', { class: 'cine-line show', style: 'margin-top:30vh;font-size:16px' });
  ov.append(t);
  for (const l of lines) { t.textContent = l; await wait(r.revealed_only ? 150 : 750); }
  ov.innerHTML = '';
  const tr = r.truth;
  const rv = (el, i) => { el.classList.add('rv'); el.style.animationDelay = (i * 0.28) + 's'; return el; };
  let i = 0;
  const solved = r.solved;
  ov.append(
    rv(h('div', { class: 'faint mono' }, `Case #${DCS.ov.case_number} \u00b7 ${DCS.ov.difficulty.toLowerCase()}`), i++),
    r.revealed_only ? rv(h('div', { class: 'big' }, 'SOLUTION REVEALED'), i++) : rv(h('div', { class: 'big ' + (solved ? 'solved' : 'unsolved') }, (solved ? '\u{1F389} ' : '') + r.headline), i++),
    r.messages ? rv(h('p', { class: 'dim', style: 'font-size:16px;font-family:var(--serif)' }, r.messages.join(' ')), i++) : null,
    rv(h('div', { class: 'card', style: 'width:min(980px,100%);margin:10px 0' }, h('h3', {}, 'What actually happened'),
      h('dl', { class: 'kv', style: 'margin-top:8px;grid-template-columns:130px 1fr' }, h('dt', {}, 'Perpetrator'), h('dd', {}, tr.perpetrator.name), h('dt', {}, 'Motive'), h('dd', {}, tr.motive.label), h('dt', {}, 'Method'), h('dd', {}, tr.method.detail),
        h('dt', {}, 'When'), h('dd', {}, `${tr.time}, ${tr.location}`), h('dt', {}, 'Device'), h('dd', {}, tr.device),
        h('dt', {}, 'Stated departure'), h('dd', {}, `${tr.stated_departure} (badge: ${tr.actual_departure})`))), i++));
  if (r.your_theory) ov.append(rv(h('div', { class: 'cmp', style: 'margin-bottom:12px' },
    h('div', { class: 'card' }, h('h3', {}, 'Your theory'), h('dl', { class: 'kv', style: 'margin-top:8px' }, h('dt', {}, 'Who'), h('dd', {}, r.your_theory.who), h('dt', {}, 'Why'), h('dd', {}, r.your_theory.motive), h('dt', {}, 'How'), h('dd', {}, r.your_theory.method), h('dt', {}, 'When'), h('dd', {}, r.your_theory.time)), r.your_theory.explanation ? h('div', { class: 'alibi' }, r.your_theory.explanation) : null),
    h('div', { class: 'card' }, h('h3', {}, 'Actual events'), tr.timeline.map(x => h('div', { class: 'row', style: 'padding:2px 0;font-size:13px' }, h('span', { class: 'mono dim', style: 'width:46px' }, x.time), h('span', { style: 'flex:1' }, x.text), evTag(x.evidence_id))))), i++));
  else ov.append(rv(h('div', { class: 'card', style: 'width:min(980px,100%);margin-bottom:12px' }, h('h3', {}, 'Actual timeline'), tr.timeline.map(x => h('div', { class: 'row', style: 'padding:2px 0;font-size:13px' }, h('span', { class: 'mono dim', style: 'width:46px' }, x.time), h('span', { style: 'flex:1' }, x.text), evTag(x.evidence_id)))), i++));
  ov.append(rv(h('div', { class: 'card', style: 'width:min(980px,100%);margin-bottom:12px' }, h('h3', {}, 'Red herrings in this case'), tr.red_herrings.length ? tr.red_herrings.map(x => h('div', { style: 'padding:4px 0;font-size:13.5px' }, h('b', {}, x.suspect + ': '), x.explanation)) : h('div', { class: 'faint' }, 'None.')), i++));
  if (!r.revealed_only) {
    const labels = { evidence: 'Evidence discovered', interpretation: 'Evidence interpreted', false_leads: 'False leads avoided', timeline: 'Timeline accuracy', suspects: 'Suspect analysis', conclusion: 'Final conclusion' };
    ov.append(rv(h('div', { class: 'row', style: 'gap:30px;margin:10px 0' }, h('div', { class: 'grade', style: `color:${solved ? 'var(--green)' : 'var(--coral)'}` }, r.grade), h('div', {}, h('div', { class: 'dim' }, 'Investigation score'), h('div', { style: 'font-family:var(--serif);font-size:34px' }, r.total + '%'))), i++),
      rv(h('div', { class: 'score-grid' }, Object.entries(r.categories).map(([k, v]) => h('div', { class: 'card' }, Suspects.gauge(labels[k], v, v >= 70 ? 'var(--green)' : v >= 45 ? 'var(--amber)' : 'var(--coral)')))), i++));
    if ((r.achievements || []).length) ov.append(rv(h('div', { class: 'row', style: 'margin-top:12px' }, r.achievements.map(k => h('span', { class: 'chip on' }, '\u{1F3C6} ' + (k.replace(/_/g, ' '))))), i++));
  }
  ov.append(rv(h('div', { class: 'row', style: 'margin:22px 0 40px' }, !r.revealed_only ? h('a', { class: 'btn', href: `/api/case/${DCS.caseId}/report`, target: '_blank', style: 'text-decoration:none' }, 'Investigation report') : null,
    h('button', { class: 'btn primary', onclick: () => { ov.remove(); App.showHome(); } }, 'New case'), h('button', { class: 'btn', onclick: () => { ov.remove(); App.go('report'); } }, 'Close')), i++));
};
