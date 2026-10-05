/* timeline.js - persistent bottom band (zoom/pan) and the full timeline view (filters) */
const Timeline = {
  data: { entries: [], window: null }, vx: null, filters: { person: '', device: '', type: '', suspicious: false },
  LANES: ['badge', 'device', 'comms', 'media', 'other'],

  lane(e) {
    if (['badge_in', 'badge_out', 'badge_room', 'camera_detect'].includes(e.type)) return 0;
    if (['email', 'message'].includes(e.type)) return 2;
    if (e.type === 'image') return 3;
    if (e.kind === 'event') return 1;
    return 4;
  },
  color(e) {
    if (e.suspicious) return '#e5645e';
    return { badge: '#cba983', device: '#b39df0', comms: '#e8b44c', media: '#7fcfc5' }[Timeline.LANES[Timeline.lane(e)]] || '#7ab8ea';
  },
  filtered() {
    const f = Timeline.filters;
    return Timeline.data.entries.filter(e =>
      (!f.person || e.actors.includes(f.person)) && (!f.device || e.device_ref === f.device) &&
      (!f.type || e.type === f.type) && (!f.suspicious || e.suspicious));
  },
  async refresh() {
    Timeline.data = await GET(CP('/timeline'));
    Timeline.renderBand();
    if (DCS.view === 'timeline') DCS.views.timeline($('#view'));
  },

  /* ---- bottom band ---- */
  renderBand() {
    const box = $('#bottom');
    if (!box) return;
    const entries = Timeline.filtered();
    const w = Timeline.data.window;
    box.innerHTML = '';
    const sus = Timeline.data.entries.filter(e => e.suspicious).length;
    box.append(h('div', { class: 'tl-head' }, h('span', { style: 'font-family:var(--serif);font-size:15px' }, 'Timeline'),
      h('span', { class: 'faint' }, `${entries.length} events` + (sus ? ` \u00b7 ${sus} flagged suspicious` : '') + (w && w.exact ? ` \u00b7 incident window ${minToStr(w.start)}\u2013${minToStr(w.end)}` : '')),
      h('span', { class: 'spacer' }),
      h('button', { class: 'btn small', onclick: () => Timeline.zoom(0.7) }, 'Zoom in'), h('button', { class: 'btn small', onclick: () => Timeline.zoom(1.4) }, 'Zoom out'),
      h('button', { class: 'btn small', onclick: () => { Timeline.vx = null; Timeline.renderBand(); } }, 'Fit'),
      h('button', { class: 'btn small', onclick: () => App.go('timeline') }, 'Open full timeline')));
    const band = h('div', { id: 'tl-band' });
    box.append(band);
    if (!entries.length) { band.append(h('div', { class: 'empty' }, 'No events yet. Examine devices and locations to build the timeline.')); return; }
    const mins = entries.map(e => e.minute);
    let lo = Math.min(...mins) - 20, hi = Math.max(...mins) + 20;
    if (w && w.exact) { lo = Math.min(lo, w.start - 10); hi = Math.max(hi, w.end + 10); }
    if (!Timeline.vx) Timeline.vx = [lo, hi];
    const [a, b] = Timeline.vx;
    const W = band.clientWidth || 900, H = band.clientHeight || 110, pad = 26;
    const X = m => pad + (m - a) / (b - a) * (W - pad * 2);
    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
    if (w && w.exact) svg += `<rect class="tl-win" x="${X(w.start)}" y="4" width="${Math.max(2, X(w.end) - X(w.start))}" height="${H - 24}" rx="3"/>`;
    const span = b - a, step = span > 600 ? 120 : span > 300 ? 60 : span > 120 ? 30 : span > 50 ? 10 : 5;
    for (let m = Math.ceil(a / step) * step; m <= b; m += step) svg += `<line class="tl-tick" x1="${X(m)}" x2="${X(m)}" y1="4" y2="${H - 18}"/><text class="tl-txt" x="${X(m)}" y="${H - 5}" text-anchor="middle">${minToStr(m)}</text>`;
    const laneH = (H - 28) / 5;
    entries.forEach((e, i) => {
      if (e.minute < a - 5 || e.minute > b + 5) return;
      const cy = 10 + Timeline.lane(e) * laneH + laneH / 2 + ((i % 3) - 1) * 2;
      svg += `<circle class="tl-dot${e.suspicious ? ' sus' : ''}" data-i="${i}" cx="${X(e.minute)}" cy="${cy}" r="${e.suspicious ? 6 : 4.5}" fill="${Timeline.color(e)}" stroke="#0a0f15"/>`;
    });
    svg += '</svg>';
    band.innerHTML = svg;
    $$('.tl-dot', band).forEach(d => {
      const e = entries[+d.dataset.i];
      d.addEventListener('click', () => { Evidence.open(e.evidence_id); });
      d.addEventListener('pointerenter', ev => Timeline.tip(ev, e));
      d.addEventListener('pointermove', ev => Timeline.tip(ev, e));
      d.addEventListener('pointerleave', () => { const t = $('.tl-tip'); if (t) t.remove(); });
    });
    const svgEl = $('svg', band);
    svgEl.addEventListener('wheel', ev => {
      ev.preventDefault();
      const r = band.getBoundingClientRect(), f = ev.deltaY < 0 ? 0.8 : 1.25, cm = a + (ev.clientX - r.left - pad) / (W - pad * 2) * (b - a);
      Timeline.vx = [cm - (cm - a) * f, cm + (b - cm) * f]; Timeline.renderBand();
    }, { passive: false });
    let drag = null;
    svgEl.addEventListener('pointerdown', ev => { if (ev.target.classList.contains('tl-dot')) return; drag = { x: ev.clientX, vx: [...Timeline.vx] }; });
    svgEl.addEventListener('pointermove', ev => { if (!drag) return; const dm = (ev.clientX - drag.x) / (W - pad * 2) * (drag.vx[1] - drag.vx[0]); Timeline.vx = [drag.vx[0] - dm, drag.vx[1] - dm]; Timeline.renderBand(); });
    window.addEventListener('pointerup', () => { drag = null; }, { once: true });
  },
  tip(ev, e) {
    let t = $('.tl-tip');
    if (!t) { t = h('div', { class: 'tl-tip' }); document.body.append(t); }
    t.innerHTML = `<b class="mono">${e.time}</b> ${esc(e.label)}<br><span class="faint">${e.evidence_id} \u00b7 ${e.reliability.toLowerCase()}${e.suspicious ? ' \u00b7 flagged suspicious' : ''}</span>`;
    t.style.left = Math.min(window.innerWidth - 340, ev.clientX + 12) + 'px'; t.style.top = (ev.clientY - 62) + 'px';
  },
  zoom(f) {
    if (!Timeline.vx) return;
    const [a, b] = Timeline.vx, c = (a + b) / 2;
    Timeline.vx = [c - (c - a) * f, c + (b - c) * f]; Timeline.renderBand();
  },
};

DCS.views.timeline = async function (root) {
  const d = Timeline.data, f = Timeline.filters;
  root.innerHTML = '';
  const sel = (key, label, opts) => h('select', { 'aria-label': label, style: 'max-width:190px', onchange: e => { f[key] = e.target.value; Timeline.renderBand(); DCS.views.timeline(root); } },
    h('option', { value: '' }, label), opts.map(o => h('option', { value: o.v, selected: f[key] === o.v }, o.t)));
  const rows = Timeline.filtered();
  root.append(h('div', { class: 'toolbar' },
    sel('person', 'All people', d.people.map(p => ({ v: p.ref, t: p.name }))), sel('device', 'All devices', d.devices.map(p => ({ v: p.ref, t: p.name }))),
    sel('type', 'All event types', d.types.map(t => ({ v: t, t: t.replace(/_/g, ' ') }))),
    h('button', { class: 'chip' + (f.suspicious ? ' on' : ''), onclick: () => { f.suspicious = !f.suspicious; Timeline.renderBand(); DCS.views.timeline(root); } }, 'Highlight suspicious only'),
    h('span', { class: 'dim', style: 'margin-left:auto;font-size:12.5px' }, `${rows.length} events`)));
  if (!rows.length) { root.append(h('div', { class: 'empty' }, 'No events match. Examine more devices, people and locations.')); return; }
  const list = h('div', { class: 'tl-list' });
  rows.forEach(e => list.append(h('div', { class: 'tl-item' + (e.suspicious ? ' sus' : ''), onclick: () => Evidence.open(e.evidence_id) },
    h('div', { class: 'tm' }, e.time), h('div', { class: 'rail' }, h('i')),
    h('div', { class: 'tx' }, h('div', {}, e.label), h('div', { class: 'sub' }, [e.actor_names.join(', '), e.evidence_id, e.reliability.toLowerCase()].filter(Boolean).join(' \u00b7 '))))));
  root.append(list);
};
