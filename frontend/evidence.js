/* evidence.js - evidence browser, detail drawer, entity drawer */
const Evidence = {
  filter: 'ALL', flag: '', q: '',

  async open(id) {
    try {
      const d = await GET(CP('/evidence/' + id));
      Evidence.drawer(Evidence.renderDetail(d), id);
      DCS.selected = id;
      if (Graph.highlightEvidence) Graph.highlightEvidence(id);
    } catch (e) { toast(e.message); }
  },
  drawer(content, title) {
    const dr = $('#drawer');
    dr.classList.remove('hidden');
    dr.innerHTML = '';
    dr.append(h('div', { class: 'drawer-head' }, h('div', { style: 'flex:1' }, title ? h('span', { class: 'mono dim' }, title) : ''),
      h('button', { class: 'btn small ghost', onclick: Evidence.close, 'aria-label': 'Close' }, 'Close')), h('div', { class: 'drawer-body' }, content));
  },
  close() { $('#drawer').classList.add('hidden'); },

  renderDetail(d) {
    const root = h('div', {});
    root.append(h('div', { class: 'row wrap', style: 'margin-bottom:6px' }, evTagStatic(d.id), h('span', { class: 'chip', style: 'cursor:default' }, d.type.replace('_', ' ').toLowerCase()), relPill(d.reliability), h('span', { class: 'mono dim' }, d.time)),
      h('h3', { style: 'margin:6px 0 12px;font-size:18px' }, d.title));
    d.contradictions.forEach(c => root.append(h('div', { class: 'alert-contra' }, h('b', {}, '\u26A0 Contradiction detected \u00b7 ' + c.severity.toLowerCase() + ' '), c.text, ' ', evTags(c.evidence_ids))));
    if (d.email) {
      const e = d.email;
      root.append(h('div', { class: 'doc' },
        h('div', { class: 'hdr' }, h('b', {}, 'From'), h('span', {}, e.from), h('b', {}, 'To'), h('span', {}, e.to.join(', ')),
          e.cc.length ? [h('b', {}, 'Cc'), h('span', {}, e.cc.join(', '))] : null,
          h('b', {}, 'Time'), h('span', {}, e.time), h('b', {}, 'Subject'), h('span', {}, e.subject),
          e.origin ? [h('b', {}, 'Origin'), h('span', {}, e.origin)] : null,
          h('b', {}, 'Attach'), h('span', {}, e.attachments.length ? e.attachments.join(', ') : 'none')),
        h('div', { class: 'body' }, e.body)));
    }
    if (d.message) {
      const m = d.message, first = m.lines[0] ? m.lines[0].name : '';
      root.append(h('div', { class: 'dim', style: 'font-size:12.5px;margin-bottom:8px' }, `${m.a} \u2194 ${m.b}`),
        h('div', { class: 'convo' }, m.lines.map(l => h('div', { class: 'bubble' + (l.name !== first ? ' r' : '') }, h('div', { class: 'who' }, `${l.name} \u00b7 ${l.time}`), l.text))));
    }
    if (d.data && d.data.text) root.append(h('div', { class: 'doc' }, h('div', { class: 'body' }, d.data.text)));
    if (d.data && d.data.claims && d.data.claims.length) root.append(h('div', { class: 'note', style: 'margin-top:10px' }, 'Claims on record: ', d.data.claims.map(c => c.quote).join('; ')));
    if (d.file) root.append(Evidence.fileCard(d.file));
    if (d.image) root.append(Evidence.imageCard(d.image));
    if (d.events) root.append(h('table', { class: 't', style: 'margin-top:10px' },
      h('tr', {}, ['Time', 'Event', 'Account', 'Device / place'].map(x => h('th', {}, x))),
      d.events.map(e => h('tr', {}, h('td', { class: 'mono' }, e.time), h('td', {}, e.description), h('td', {}, e.actor), h('td', {}, [e.device, e.location].filter(Boolean).join(' \u00b7 '))))));
    if (!d.email && !d.message && !d.file && !d.image && !d.events && !(d.data && d.data.text)) root.append(h('p', {}, d.summary));
    root.append(h('div', { class: 'note', style: 'margin-top:14px' }, d.reliability_note));
    if (d.related.length) root.append(h('div', { class: 'corr', style: 'margin-top:12px' }, h('div', { class: 'lab' }, 'AI CORRELATION DETECTED'),
      d.related.map(r => h('div', {}, `${r.label.toLowerCase()} \u2013 confidence ${r.confidence}%`))));
    root.append(h('div', { class: 'sep' }), h('div', { class: 'dim', style: 'font-size:12px;margin-bottom:6px' }, 'Connected to'),
      h('div', { class: 'row wrap' }, d.entity_names.map(n => h('button', { class: 'chip', onclick: () => Evidence.openEntity(n.ref) }, n.name))));
    root.append(Evidence.pinRow(d.id));
    return root;
  },
  pinRow(id) {
    const wrap = h('div', { style: 'margin-top:16px' });
    GET(CP('/hypotheses')).then(hs => {
      if (!hs.length) return;
      const sel = h('select', { style: 'max-width:220px' }, hs.map(x => h('option', { value: x.id }, `#${String(x.id).padStart(2, '0')} ${x.title.slice(0, 34)}`)));
      const pin = side => async () => { await POST(CP(`/hypotheses/${sel.value}/pin`), { evidence_id: id, side }); toast('Pinned to hypothesis'); App.refreshData(); };
      wrap.append(h('div', { class: 'dim', style: 'font-size:12px;margin-bottom:6px' }, 'Add to a hypothesis'),
        h('div', { class: 'row' }, sel, h('button', { class: 'btn small', onclick: pin('support') }, 'Supports'), h('button', { class: 'btn small', onclick: pin('against') }, 'Against')));
    }).catch(() => {});
    return wrap;
  },
  fileCard(f) {
    return h('div', {},
      h('dl', { class: 'kv' }, h('dt', {}, 'Filename'), h('dd', { class: 'mono' }, f.filename), h('dt', {}, 'Owner'), h('dd', {}, f.owner),
        h('dt', {}, 'Created'), h('dd', {}, f.created), h('dt', {}, 'Modified'), h('dd', {}, f.modified), h('dt', {}, 'Size'), h('dd', {}, f.size),
        h('dt', {}, 'Location'), h('dd', {}, f.location), h('dt', {}, 'Identifier'), h('dd', { class: 'mono' }, f.hash)),
      f.authorized.length ? h('div', { style: 'margin-top:10px' }, h('div', { class: 'dim', style: 'font-size:12px' }, 'Authorized access'),
        h('div', { class: 'row wrap', style: 'margin-top:4px' }, f.authorized.map(a => h('button', { class: 'chip', onclick: () => Evidence.openEntity(a.ref) }, a.name)))) : null,
      h('div', { class: 'dim', style: 'font-size:12px;margin:12px 0 4px' }, 'Access history'),
      h('table', { class: 't' }, f.history.map(x => h('tr', { class: x.restricted ? 'restricted' : '' }, h('td', { class: 'mono' }, x.time), h('td', {}, x.action), h('td', {}, x.who || ''), h('td', {}, x.evidence_id ? evTag(x.evidence_id) : (x.device || ''))))));
  },
  imageCard(im) {
    return h('div', {}, h('div', { class: 'ph', html: Evidence.scene(im) }),
      h('dl', { class: 'kv', style: 'margin-top:10px' }, h('dt', {}, 'Timestamp'), h('dd', { class: 'mono' }, im.time), h('dt', {}, 'Location'), h('dd', {}, im.location),
        h('dt', {}, 'Device'), h('dd', {}, im.device),
        Object.entries(im.metadata || {}).map(([k, v]) => [h('dt', {}, k.replace(/_/g, ' ')), h('dd', {}, String(v))])),
      h('div', { class: 'faint', style: 'font-size:12px;margin-top:6px' }, 'Placeholder render generated from the case metadata. Fictional.'));
  },
  scene(im) {
    let s = 7; for (const c of (im.seed + im.time)) s = (s * 31 + c.charCodeAt(0)) >>> 0;
    const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    const W = 480, H = 270;
    let g = `<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#101820"/><stop offset="1" stop-color="#05080b"/></linearGradient>
      <filter id="n"><feTurbulence baseFrequency="0.9" numOctaves="2" seed="${Math.floor(rnd() * 90)}"/><feColorMatrix values="0 0 0 0 .5  0 0 0 0 .6  0 0 0 0 .6  0 0 0 .09 0"/></filter></defs>
      <rect width="${W}" height="${H}" fill="url(#bg)"/>`;
    if (im.scene === 'parking') {
      g += `<path d="M0 ${H} L${W * .38} 120 L${W * .62} 120 L${W} ${H} Z" fill="#0b1118"/><path d="M${W * .5} 120 L${W * .5} ${H}" stroke="#3a4a58" stroke-dasharray="14 12" stroke-width="3"/>`;
      g += `<rect x="150" y="150" width="190" height="78" rx="14" fill="#1b2733" stroke="#314456"/><rect x="170" y="130" width="150" height="40" rx="10" fill="#17212c"/><rect x="195" y="196" width="100" height="22" rx="2" fill="#cfd6dc" opacity=".8"/>
        <text x="245" y="212" font-size="14" text-anchor="middle" fill="#222" font-family="monospace">NX-${im.metadata.plate ? String(im.metadata.plate).slice(3) : '0000'}</text>
        <circle cx="168" cy="196" r="7" fill="#f0e7b8" opacity=".85"/><circle cx="322" cy="196" r="7" fill="#f0e7b8" opacity=".85"/>`;
    } else {
      g += `<path d="M0 0 L${W * .3} 70 L${W * .3} 210 L0 ${H} Z" fill="#0c141c"/><path d="M${W} 0 L${W * .7} 70 L${W * .7} 210 L${W} ${H} Z" fill="#0c141c"/><rect x="${W * .3}" y="70" width="${W * .4}" height="140" fill="#080d13"/>
        <rect x="${W * .43}" y="86" width="${W * .14}" height="124" fill="#1a2a3a" stroke="#2c4258"/><rect x="${W * .46}" y="96" width="14" height="20" fill="#2a3d50"/>`;
      g += `<path d="M232 150 q-14 4 -16 24 l0 52 l34 0 l0 -52 q-2 -20 -18 -24 z" fill="#05090d" stroke="#16222d"/><circle cx="233" cy="138" r="11" fill="#05090d" stroke="#16222d"/>`;
    }
    g += `<rect width="${W}" height="${H}" filter="url(#n)"/><text x="12" y="22" fill="#9fb3c4" font-family="monospace" font-size="13">${esc((im.metadata.camera || 'CAM') + ' \u00b7 ' + im.time)}</text><circle cx="${W - 18}" cy="17" r="5" fill="#e5645e"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(im.caption)}">${g}</svg>`;
  },

  async openEntity(ref) {
    try {
      const d = await GET(CP('/entity/' + ref));
      Evidence.drawer(Evidence.renderEntity(d), ref);
      if (Graph.focus) Graph.focus(ref);
    } catch (e) { toast(e.message); }
  },
  renderEntity(d) {
    const root = h('div', {});
    const meta = TYPE_META[d.kind] || TYPE_META.person;
    root.append(h('div', { class: 'row', style: 'gap:12px;margin-bottom:6px' }, h('div', { style: 'font-size:30px' }, meta[0]),
      h('div', { style: 'flex:1' }, h('h3', { style: 'font-size:19px' }, d.name), h('div', { class: 'faint mono', style: 'font-size:12px' }, `${d.ref} \u00b7 ${meta[2].toLowerCase()}`)),
      ['person', 'device', 'location', 'file'].includes(d.kind) ? h('button', { class: 'btn primary', disabled: !d.more || DCS.ov.closed, title: d.more ? 'Look for more evidence here' : 'Nothing further to recover',
        onclick: async e => { const r = await examine(d.ref, e.target); if (r) Evidence.openEntity(d.ref); } }, d.more ? 'Examine' : 'Fully examined') : null));
    if (d.profile) root.append(Suspects.profileBlock(d.profile));
    if (d.device) root.append(h('dl', { class: 'kv', style: 'margin-top:10px' }, h('dt', {}, 'Kind'), h('dd', {}, d.device.kind), h('dt', {}, 'Owner'), h('dd', {}, d.device.owner), h('dt', {}, 'Location'), h('dd', {}, d.device.location)),
      h('div', { class: 'dim', style: 'font-size:12px;margin:12px 0 4px' }, 'Recovered activity'),
      d.device.log.length ? h('table', { class: 't' }, d.device.log.map(l => h('tr', {}, h('td', { class: 'mono' }, l.time), h('td', {}, l.description), h('td', {}, evTag(l.evidence_id))))) : h('div', { class: 'empty' }, 'No activity recovered yet. Examine this device.'));
    if (d.location) root.append(h('dl', { class: 'kv', style: 'margin-top:10px' }, h('dt', {}, 'Building'), h('dd', {}, d.location.building), h('dt', {}, 'Devices'), h('dd', {}, d.location.devices.join(', ') || 'none')),
      h('div', { class: 'dim', style: 'font-size:12px;margin:12px 0 4px' }, 'People recorded here'),
      d.location.people.length ? h('table', { class: 't' }, d.location.people.map(p => h('tr', {}, h('td', { class: 'mono' }, p.time), h('td', {}, p.who), h('td', {}, evTag(p.evidence_id))))) : h('div', { class: 'empty' }, 'No badge records recovered yet.'));
    if (d.file) root.append(Evidence.fileCard(d.file));
    root.append(h('div', { class: 'sep' }), h('div', { class: 'dim', style: 'font-size:12px;margin-bottom:6px' }, `Evidence (${d.evidence.length})`),
      d.evidence.length ? h('div', { class: 'grid' }, d.evidence.map(Evidence.card)) : h('div', { class: 'empty' }, 'No evidence discovered for this yet.'));
    if (d.connections.length) root.append(h('div', { class: 'sep' }), h('div', { class: 'dim', style: 'font-size:12px;margin-bottom:6px' }, 'Connections'),
      d.connections.map(c => h('div', { class: 'row', style: 'padding:2px 0;font-size:13px' }, h('span', { class: 'mono faint', style: 'width:100px;font-size:11px' }, c.type), h('a', { href: '#', onclick: e => { e.preventDefault(); Evidence.openEntity(c.other); }, style: 'color:var(--ice)' }, c.other_name), c.label ? h('span', { class: 'faint' }, c.label) : null, c.evidence_id ? evTag(c.evidence_id) : null)));
    return root;
  },

  card(e) {
    return h('div', { class: 'ev-card' + (e.reviewed ? '' : ' unread'), onclick: () => Evidence.open(e.id) },
      h('div', { class: 'top' }, evTagStatic(e.id), h('span', { class: 'faint', style: 'font-size:11.5px' }, e.type.replace('_', ' ').toLowerCase()), h('span', { class: 'mono dim', style: 'margin-left:auto;font-size:12px' }, e.time)),
      h('div', { class: 'ttl' }, e.title), h('div', { class: 'sum' }, e.summary),
      h('div', { class: 'row wrap', style: 'margin-top:8px;gap:6px' }, relPill(e.reliability), (e.flags || []).map(f => h('span', { class: 'flag ' + f }, f === 'cluster' ? 'in activity cluster' : f))));
  },
};
function evTagStatic(id) { return h('span', { class: 'tag', style: 'cursor:default' }, id); }

DCS.views.evidence = async function (root) {
  root.innerHTML = '';
  const types = ['ALL', 'PEOPLE', 'DEVICES', 'FILES', 'MESSAGES', 'EMAILS', 'LOCATIONS', 'EVENTS'];
  const flags = [['HIGH', 'High confidence'], ['SUSPICIOUS', 'Suspicious'], ['CONTRADICTIONS', 'Contradictions'], ['UNRESOLVED', 'Unresolved']];
  const grid = h('div', { class: 'ev-grid' }), count = h('span', { class: 'dim', style: 'margin-left:auto;font-size:12.5px' });
  const load = async () => {
    const r = await GET(CP(`/evidence?type=${Evidence.filter}&flag=${Evidence.flag}&q=${encodeURIComponent(Evidence.q)}`));
    grid.innerHTML = '';
    r.items.forEach(e => grid.append(Evidence.card(e)));
    if (!r.items.length) grid.append(h('div', { class: 'empty', style: 'grid-column:1/-1' }, r.discovered ? 'No evidence matches these filters.' : 'Nothing discovered yet. Examine a device, person or location.'));
    count.textContent = `${r.items.length} shown \u00b7 ${r.discovered} of ${r.total} discovered`;
  };
  const chips = h('div', { class: 'row wrap', style: 'gap:6px' });
  const paint = () => {
    chips.innerHTML = '';
    types.forEach(t => chips.append(h('button', { class: 'chip' + (Evidence.filter === t ? ' on' : ''), onclick: () => { Evidence.filter = t; paint(); load(); } }, t === 'ALL' ? 'All evidence' : t.charAt(0) + t.slice(1).toLowerCase())));
    chips.append(h('span', { class: 'faint', style: 'padding:0 4px' }, '|'));
    flags.forEach(([k, l]) => chips.append(h('button', { class: 'chip' + (Evidence.flag === k ? ' on' : ''), onclick: () => { Evidence.flag = Evidence.flag === k ? '' : k; paint(); load(); } }, l)));
  };
  let timer;
  const search = h('input', { type: 'search', placeholder: 'Search people, E-ids, devices, files, times, keywords', value: Evidence.q, 'aria-label': 'Search evidence',
    oninput: e => { Evidence.q = e.target.value; clearTimeout(timer); timer = setTimeout(load, 180); } });
  root.append(h('div', { class: 'toolbar' }, search, chips, count), grid);
  paint(); await load();
};
