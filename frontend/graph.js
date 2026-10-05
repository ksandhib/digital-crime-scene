/* graph.js - the evidence board. Dependency-free force-directed graph on SVG.
   Every node and edge is a row in the case database; edges appear only once their evidence is found. */
const Graph = {
  data: { nodes: [], edges: [] }, pos: {}, hidden: new Set(), tx: 0, ty: 0, k: 1, sel: null, hover: null, q: '',
  hlEv: null, raf: 0, alpha: 0, root: null, drag: null, size: { w: 800, h: 500 },
  ANCHOR: { person: [-190, 0], device: [200, -130], location: [210, 170], file: [-10, 210], org: [-280, -180],
    email: [20, -210], message: [-200, -170], image: [-210, 190], event: [340, 10] },

  async refresh() {
    Graph.data = await GET(CP('/graph'));
    Graph.seed();
    if (Graph.root && document.body.contains(Graph.root)) { Graph.build(); Graph.heat(0.5); }
  },
  seed() {
    const nbr = {};
    Graph.data.edges.forEach(e => { (nbr[e.source] = nbr[e.source] || []).push(e.target); (nbr[e.target] = nbr[e.target] || []).push(e.source); });
    const counts = {};
    Graph.data.nodes.forEach(n => {
      if (Graph.pos[n.id]) return;
      const a = Graph.ANCHOR[n.type] || [0, 0];
      const placed = (nbr[n.id] || []).map(i => Graph.pos[i]).filter(Boolean);
      let x, y;
      if (placed.length) { x = placed.reduce((s, p) => s + p.x, 0) / placed.length; y = placed.reduce((s, p) => s + p.y, 0) / placed.length; x += (Math.random() - .5) * 70; y += (Math.random() - .5) * 70; }
      else { const c = counts[n.type] = (counts[n.type] || 0) + 1; const ang = c * 2.4; x = a[0] + Math.cos(ang) * 30 * Math.sqrt(c); y = a[1] + Math.sin(ang) * 30 * Math.sqrt(c); }
      Graph.pos[n.id] = { x, y, vx: 0, vy: 0 };
    });
  },
  visibleNodes() { return Graph.data.nodes.filter(n => !Graph.hidden.has(n.type)); },
  radius(n) { return (n.type === 'person' ? 19 : 15) + Math.min(9, n.degree * 0.5); },

  build() {
    const root = Graph.root, svg = $('#graph-svg', root);
    const vp = $('#vp', svg);
    vp.innerHTML = '';
    const vis = new Set(Graph.visibleNodes().map(n => n.id));
    const mk = id => { const g = document.createElementNS('http://www.w3.org/2000/svg', 'g'); g.id = id; return g; };
    const eg = mk('edges'), lg = mk('elabels'), ng = mk('nodes');
    Graph.edgeEls = []; Graph.nodeEls = {};
    Graph.data.edges.forEach(e => {
      if (!vis.has(e.source) || !vis.has(e.target)) return;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('class', 'edge'); line.setAttribute('marker-end', 'url(#arrow)');
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('class', 'edge-label'); t.setAttribute('text-anchor', 'middle'); t.textContent = e.type.toLowerCase() + (e.label ? ' \u00b7 ' + e.label : '');
      t.style.display = 'none';
      eg.append(line); lg.append(t);
      Graph.edgeEls.push({ e, line, t });
    });
    Graph.visibleNodes().forEach(n => {
      const m = TYPE_META[n.type] || TYPE_META.person, r = Graph.radius(n);
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'node');
      g.innerHTML = `<circle class="body" r="${r}" stroke="${m[1]}"/><text class="ico">${m[0]}</text>
        <text class="lbl" y="${r + 13}">${esc(n.label.length > 24 ? n.label.slice(0, 23) + '\u2026' : n.label)}</text>` +
        (n.more && !n.examined ? `<circle class="more" cx="${r * .72}" cy="${-r * .72}" r="4.5"><title>Unexamined data</title></circle>` : '');
      g.addEventListener('pointerdown', ev => Graph.startDrag(ev, n));
      g.addEventListener('pointerenter', () => { Graph.hover = n.id; Graph.style(); });
      g.addEventListener('pointerleave', () => { Graph.hover = null; Graph.style(); });
      ng.append(g);
      Graph.nodeEls[n.id] = { n, g };
    });
    vp.append(eg, lg, ng);
    Graph.style(); Graph.paint();
    const c = $('#g-count', root);
    if (c) c.textContent = `${Graph.visibleNodes().length} nodes \u00b7 ${Graph.edgeEls.length} connections`;
  },

  neighbors(id) {
    const s = new Set([id]);
    Graph.edgeEls.forEach(({ e }) => { if (e.source === id) s.add(e.target); if (e.target === id) s.add(e.source); });
    return s;
  },
  style() {
    const focusId = Graph.hover || Graph.sel;
    const nb = focusId ? Graph.neighbors(focusId) : null;
    const q = Graph.q.trim().toLowerCase();
    Graph.edgeEls.forEach(({ e, line, t }) => {
      const onEv = Graph.hlEv && e.evidence_id === Graph.hlEv;
      const on = (focusId && (e.source === focusId || e.target === focusId)) || onEv;
      line.setAttribute('class', 'edge' + (on ? ' hl' : (focusId || Graph.hlEv) ? ' dim' : ''));
      t.style.display = on || Graph.k > 1.6 ? '' : 'none';
    });
    Object.values(Graph.nodeEls).forEach(({ n, g }) => {
      const match = q && (n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || (n.sub || '').toLowerCase().includes(q) || (n.evidence_id || '').toLowerCase() === q);
      const hlNode = Graph.hlEv && (n.evidence_id === Graph.hlEv || Graph.edgeEls.some(x => x.e.evidence_id === Graph.hlEv && (x.e.source === n.id || x.e.target === n.id)));
      let cls = 'node';
      if (nb && !nb.has(n.id) && !hlNode) cls += ' dim';
      if (Graph.hlEv && !hlNode && !nb) cls += ' dim';
      if (match) cls += ' match';
      if (Graph.sel === n.id) cls += ' sel';
      g.setAttribute('class', cls);
    });
  },
  paint() {
    Graph.edgeEls.forEach(({ e, line, t }) => {
      const a = Graph.pos[e.source], b = Graph.pos[e.target];
      if (!a || !b) return;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
      const rs = Graph.radius(Graph.nodeEls[e.source].n) + 2, rt = Graph.radius(Graph.nodeEls[e.target].n) + 5;
      line.setAttribute('x1', a.x + dx / d * rs); line.setAttribute('y1', a.y + dy / d * rs);
      line.setAttribute('x2', b.x - dx / d * rt); line.setAttribute('y2', b.y - dy / d * rt);
      t.setAttribute('x', (a.x + b.x) / 2); t.setAttribute('y', (a.y + b.y) / 2 - 3);
    });
    Object.values(Graph.nodeEls).forEach(({ n, g }) => { const p = Graph.pos[n.id]; if (p) g.setAttribute('transform', `translate(${p.x},${p.y})`); });
  },
  vpTransform() { const vp = $('#vp', Graph.root); if (vp) vp.setAttribute('transform', `translate(${Graph.tx},${Graph.ty}) scale(${Graph.k})`); },

  /* ---- physics ---- */
  heat(a) { Graph.alpha = Math.max(Graph.alpha, a); if (!Graph.raf) Graph.raf = requestAnimationFrame(Graph.tick); },
  tick() {
    Graph.raf = 0;
    if (!Graph.root || !document.body.contains(Graph.root)) return;
    Graph.step();
    Graph.paint();
    Graph.alpha *= 0.985;
    if (Graph.alpha > 0.012 || Graph.drag) Graph.raf = requestAnimationFrame(Graph.tick);
  },
  prewarm(n) { for (let i = 0; i < n; i++) { Graph.alpha = Math.max(0.08, 1 - i / n); Graph.step(); } Graph.paint(); },
  step() {
    const ns = Graph.visibleNodes(), P = Graph.pos, a = Graph.alpha;
    for (let i = 0; i < ns.length; i++) {
      const p = P[ns[i].id];
      for (let j = i + 1; j < ns.length; j++) {
        const q = P[ns[j].id];
        let dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy;
        if (d2 < 1) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = 1; }
        if (d2 > 160000) continue;
        const d = Math.sqrt(d2), f = 11000 / d2 * a;
        dx = dx / d * f; dy = dy / d * f;
        p.vx += dx; p.vy += dy; q.vx -= dx; q.vy -= dy;
      }
      const an = Graph.ANCHOR[ns[i].type] || [0, 0];
      p.vx += (an[0] - p.x) * 0.004 * a; p.vy += (an[1] - p.y) * 0.004 * a;
      p.vx -= p.x * 0.002 * a; p.vy -= p.y * 0.002 * a;
    }
    Graph.edgeEls.forEach(({ e }) => {
      const s = P[e.source], t = P[e.target];
      if (!s || !t) return;
      const dx = t.x - s.x, dy = t.y - s.y, d = Math.hypot(dx, dy) || 1, L = 135;
      const f = (d - L) * 0.045 * a;
      s.vx += dx / d * f; s.vy += dy / d * f; t.vx -= dx / d * f; t.vy -= dy / d * f;
    });
    ns.forEach(n => {
      const p = P[n.id];
      if (Graph.drag && Graph.drag.id === n.id) { p.vx = p.vy = 0; return; }
      p.vx *= 0.8; p.vy *= 0.8; p.x += p.vx; p.y += p.vy;
    });
  },

  /* ---- interaction ---- */
  toWorld(ev) { const r = $('#graph-svg', Graph.root).getBoundingClientRect(); return { x: (ev.clientX - r.left - Graph.tx) / Graph.k, y: (ev.clientY - r.top - Graph.ty) / Graph.k }; },
  startDrag(ev, n) {
    ev.stopPropagation();
    Graph.drag = { id: n.id, moved: false, sx: ev.clientX, sy: ev.clientY };
    ev.target.closest('.node').setPointerCapture(ev.pointerId);
    Graph.heat(0.35);
  },
  onMove(ev) {
    if (Graph.drag) {
      const d = Graph.drag;
      if (Math.hypot(ev.clientX - d.sx, ev.clientY - d.sy) > 4) d.moved = true;
      const w = Graph.toWorld(ev), p = Graph.pos[d.id];
      p.x = w.x; p.y = w.y; Graph.paint(); Graph.heat(0.25);
    } else if (Graph.pan) {
      Graph.tx = Graph.pan.tx + ev.clientX - Graph.pan.x; Graph.ty = Graph.pan.ty + ev.clientY - Graph.pan.y; Graph.vpTransform();
    }
  },
  onUp() {
    if (Graph.drag) {
      const d = Graph.drag; Graph.drag = null;
      if (!d.moved) Graph.click(d.id);
    }
    if (Graph.pan) { Graph.pan = null; $('#graph-svg', Graph.root).classList.remove('panning'); }
  },
  click(id) {
    Graph.sel = id; Graph.style();
    const n = Graph.data.nodes.find(x => x.id === id);
    if (!n) return;
    if (['email', 'message', 'image', 'event'].includes(n.type) && n.evidence_id) Evidence.open(n.evidence_id);
    else Evidence.openEntity(id);
  },
  focus(ref, center) {
    Graph.sel = ref; Graph.hlEv = null; Graph.style();
    if (center && Graph.pos[ref]) { Graph.tx = Graph.size.w / 2 - Graph.pos[ref].x * Graph.k; Graph.ty = Graph.size.h / 2 - Graph.pos[ref].y * Graph.k; Graph.vpTransform(); }
  },
  highlightEvidence(id) { Graph.hlEv = id; Graph.sel = null; if (Graph.root) Graph.style(); },
  zoom(f, cx, cy) {
    const k2 = Math.min(3, Math.max(0.3, Graph.k * f));
    cx = cx ?? Graph.size.w / 2; cy = cy ?? Graph.size.h / 2;
    Graph.tx = cx - (cx - Graph.tx) * (k2 / Graph.k); Graph.ty = cy - (cy - Graph.ty) * (k2 / Graph.k); Graph.k = k2;
    Graph.vpTransform(); Graph.style();
  },
  fit() {
    const ns = Graph.visibleNodes().map(n => Graph.pos[n.id]).filter(Boolean);
    if (!ns.length) return;
    const xs = ns.map(p => p.x), ys = ns.map(p => p.y);
    const minx = Math.min(...xs) - 60, maxx = Math.max(...xs) + 60, miny = Math.min(...ys) - 70, maxy = Math.max(...ys) + 60;
    Graph.k = Math.min(1.4, Math.max(0.3, Math.min(Graph.size.w / (maxx - minx), Graph.size.h / (maxy - miny))));
    Graph.tx = Graph.size.w / 2 - (minx + maxx) / 2 * Graph.k; Graph.ty = Graph.size.h / 2 - (miny + maxy) / 2 * Graph.k;
    Graph.vpTransform(); Graph.style();
  },
  search(q) {
    Graph.q = q; Graph.style();
    const m = Graph.visibleNodes().find(n => q && (n.label.toLowerCase().includes(q.toLowerCase()) || n.id.toLowerCase() === q.toLowerCase()));
    if (m) Graph.focus(m.id, true);
  },
};

DCS.views.graph = async function (root) {
  root.innerHTML = '';
  const wrap = h('div', { id: 'graph-wrap' });
  const ns = 'http://www.w3.org/2000/svg';
  wrap.innerHTML = `<svg id="graph-svg" role="img" aria-label="Interactive evidence board">
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#4b6580"/></marker></defs>
    <rect id="g-bg" width="100%" height="100%" fill="transparent"/><g id="vp"></g></svg>`;
  const tools = h('div', { class: 'g-tools' },
    h('input', { type: 'search', placeholder: 'Find a node or evidence id', 'aria-label': 'Search the board', oninput: e => Graph.search(e.target.value) }),
    h('button', { class: 'btn small', onclick: () => { Graph.fit(); } }, 'Fit view'),
    h('button', { class: 'btn small', onclick: () => { Graph.hlEv = null; Graph.sel = null; Graph.style(); Evidence.close(); } }, 'Clear highlight'),
    h('span', { class: 'faint', style: 'font-size:12px', id: 'g-count' }));
  const legend = h('div', { class: 'g-legend' });
  Object.entries(TYPE_META).forEach(([t, m]) => legend.append(h('button', { class: 'chip' + (Graph.hidden.has(t) ? '' : ' on'), title: 'Show or hide ' + m[2].toLowerCase() + ' nodes',
    onclick: e => { Graph.hidden.has(t) ? Graph.hidden.delete(t) : Graph.hidden.add(t); e.currentTarget.classList.toggle('on'); Graph.build(); Graph.heat(.3); } }, m[0] + ' ' + m[2])));
  legend.querySelectorAll('.chip').forEach(c => { if (!Graph.hidden.size) c.classList.add('on'); });
  const zoom = h('div', { class: 'g-zoom' }, h('button', { class: 'btn', 'aria-label': 'Zoom in', onclick: () => Graph.zoom(1.25) }, '+'), h('button', { class: 'btn', 'aria-label': 'Zoom out', onclick: () => Graph.zoom(0.8) }, '\u2212'));
  const hint = h('div', { class: 'g-info' }, 'Drag to move \u00b7 scroll to zoom \u00b7 click a node for details \u00b7 amber dot = unexamined data');
  wrap.append(tools, legend, zoom, hint);
  root.append(wrap);
  Graph.root = wrap;
  const svg = $('#graph-svg', wrap);
  const measure = () => { const r = svg.getBoundingClientRect(); Graph.size = { w: r.width, h: r.height }; };
  measure();
  if (!Graph.inited) { Graph.tx = Graph.size.w / 2; Graph.ty = Graph.size.h / 2; Graph.k = 1; Graph.inited = true; }
  svg.addEventListener('pointerdown', ev => { if (ev.target.closest('.node')) return; Graph.pan = { x: ev.clientX, y: ev.clientY, tx: Graph.tx, ty: Graph.ty }; svg.classList.add('panning'); Graph.sel = null; Graph.hlEv = null; Graph.style(); });
  svg.addEventListener('pointermove', Graph.onMove);
  window.addEventListener('pointerup', Graph.onUp);
  svg.addEventListener('wheel', ev => { ev.preventDefault(); const r = svg.getBoundingClientRect(); Graph.zoom(ev.deltaY < 0 ? 1.12 : 0.89, ev.clientX - r.left, ev.clientY - r.top); }, { passive: false });
  window.addEventListener('resize', measure);
  Graph.data = await GET(CP('/graph'));
  Graph.seed(); Graph.build(); Graph.vpTransform();
  if (!Graph.fitted) { Graph.prewarm(220); Graph.fit(); Graph.fitted = true; }
  Graph.alpha = 0.15; Graph.heat(0.15);
};
