// Owner dashboard charts: single-series bar charts with a hover tooltip. Plain SVG, no library.
(() => {
  const data = JSON.parse(document.getElementById('charts').textContent);
  const series = {
    signups: { rows: data.weeks, key: 'signups', unit: ['account', 'accounts'], prefix: 'Week of ' },
    calcs: { rows: data.weeks, key: 'calcs', unit: ['calculation', 'calculations'], prefix: 'Week of ' },
    views: { rows: data.days, key: 'views', unit: ['visit', 'visits'], prefix: '' },
  };
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  const nice = max => { if (max <= 40) return Math.ceil(max / 4) * 4; const p = Math.pow(10, Math.floor(Math.log10(max))); return Math.ceil(max / p * 2) / 2 * p; };

  function draw(box) {
    const cfg = series[box.dataset.chart];
    const rows = cfg.rows, W = Math.max(box.clientWidth, 280), H = 190, L = 34, R = 6, T = 10, B = 26;
    const vals = rows.map(r => Number(r[cfg.key]) || 0);
    const top = nice(Math.max(...vals, 1));
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${cfg.unit[1]}: ` + rows.map((r, i) => `${r.label} ${vals[i]}`).join(', ') });
    const y = v => T + (H - T - B) * (1 - v / top);
    for (let i = 0; i <= 4; i++) {
      const v = top / 4 * i;
      svg.append(el('line', { class: 'grid-l', x1: L, x2: W - R, y1: y(v), y2: y(v) }));
      const t = el('text', { x: L - 6, y: y(v) + 4, 'text-anchor': 'end' }); t.textContent = Number.isInteger(v) ? v : v.toFixed(1); svg.append(t);
    }
    const slot = (W - L - R) / rows.length, bw = Math.max(3, Math.min(34, slot * 0.62));
    const every = Math.ceil(rows.length / Math.max(2, Math.floor((W - L) / 64)));
    const tip = document.createElement('div'); tip.className = 'tip'; tip.hidden = true;
    rows.forEach((r, i) => {
      const cx = L + slot * i + slot / 2, v = vals[i], h = Math.max(v ? 2 : 0, y(0) - y(v));
      if (h) {
        const r4 = Math.min(4, bw / 2, h);
        const x0 = cx - bw / 2, y0 = y(0) - h;
        svg.append(el('path', { class: 'bar-r' + (i === rows.length - 1 ? ' hot' : ''),
          d: `M${x0},${y(0)} V${y0 + r4} Q${x0},${y0} ${x0 + r4},${y0} H${x0 + bw - r4} Q${x0 + bw},${y0} ${x0 + bw},${y0 + r4} V${y(0)} Z` }));
      }
      if ((rows.length - 1 - i) % every === 0) {
        const t = el('text', { x: cx, y: H - 8, 'text-anchor': 'middle' }); t.textContent = r.label; svg.append(t);
      }
      const hit = el('rect', { class: 'hit', x: L + slot * i, y: T, width: slot, height: H - T - B });
      hit.addEventListener('mouseenter', () => {
        tip.innerHTML = `${cfg.prefix}${r.label}: <b>${v}</b> ${v === 1 ? cfg.unit[0] : cfg.unit[1]}`;
        tip.style.left = (cx / W * 100) + '%'; tip.style.top = (y(v) / H * box.clientHeight) + 'px'; tip.hidden = false;
      });
      hit.addEventListener('mouseleave', () => { tip.hidden = true; });
      svg.append(hit);
    });
    box.replaceChildren(svg, tip);
  }
  const boxes = document.querySelectorAll('[data-chart]');
  boxes.forEach(draw);
  let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => boxes.forEach(draw), 120); });
})();
