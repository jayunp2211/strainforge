/* Strainforge calculator front end: collects inputs, asks /api/calc for results, saves to history. */
(function () {
'use strict';
const BOOT = JSON.parse(document.getElementById('boot').textContent);
const SHAPE_DRAW = JSON.parse(document.getElementById('shapeDraw').textContent);
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const PROCS = BOOT.processes;
let MATS = BOOT.materials.slice();

const state = {
  p: 6, shape: { 1: 1, 2: 2, 3: 2, 4: 4, 5: 7, 6: 11, 7: 12, 8: 13, 9: 14, 10: 15 },
  mat: MATS.some(m => m.name === 'CuZr') ? 'CuZr' : (MATS[0] || {}).name,
  inputs: {}, example: {}, sweep: null,
  saved: null, dirty: false, res: null,
};
const key = () => state.p + '-' + state.shape[state.p];
function curInputs() {
  const k = key();
  if (!state.inputs[k]) { state.inputs[k] = Object.assign({}, BOOT.presets[k] || {}); state.example[k] = !!BOOT.presets[k]; }
  return state.inputs[k];
}

function fmt(v, d) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'object' && v.error) return '<span class="err" title="No valid result for these inputs">' + esc(v.error) + '</span>';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v !== 'number') return esc(v);
  if (d === undefined) { const a = Math.abs(v); d = a >= 1000 ? 1 : a >= 100 ? 2 : a >= 1 ? 3 : 4; if (v === 0) d = 0; }
  return v.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
}
const isNum = v => typeof v === 'number' && isFinite(v);
// Units: the server works in metric; SFUnits converts for display and typed input.
const U = window.SFUnits;
const converts = u => U.unit(u) !== (u || '');
const qty = (v, u, d) => fmt(U.out(v, u), converts(u) && d !== undefined ? Math.max(d, 1) : d);
const uLbl = u => esc(U.unit(u));
const inVal = (v, u) => (isNum(v) && converts(u) ? String(+U.out(v, u).toPrecision(6)) : v);

// ---------------------------------------------------------------- materials
function matObj(name) { return MATS.find(m => m.name === name); }
function drawMatSelect() {
  $('matSel').innerHTML = MATS.map(m => `<option value="${esc(m.name)}">${esc(m.name)}${m.custom ? ' (custom)' : ''}</option>`).join('');
  $('matSel').value = state.mat;
  $('matCount').textContent = MATS.length + ' materials';
  drawMatTable();
}
function drawMatTable() {
  const q = $('matSearch').value.trim().toLowerCase();
  $('matTable').querySelector('tbody').innerHTML = MATS.filter(m => !q || m.name.toLowerCase().includes(q)).map(m =>
    `<tr data-m="${esc(m.name)}" class="${m.name === state.mat ? 'sel' : ''}" tabindex="0"><td>${esc(m.name)}${m.custom ? ' <span class="chip">custom</span>' : ''}</td><td class="v">${qty(m.C, 'N/mm²', 0)}</td><td class="v">${fmt(m.n, 3)}</td><td class="v">${m.Rm == null ? '—' : qty(m.Rm, 'N/mm²', 1)}</td></tr>`).join('');
}
$('matSel').addEventListener('change', e => { state.mat = e.target.value; touch(); drawMatTable(); calc(); });
$('matSearch').addEventListener('input', drawMatTable);
$('matTable').addEventListener('click', e => pickRow(e.target.closest('tr[data-m]')));
$('matTable').addEventListener('keydown', e => { if (e.key === 'Enter') pickRow(e.target.closest('tr[data-m]')); });
function pickRow(tr) {
  if (!tr) return;
  state.mat = tr.dataset.m; $('matSel').value = state.mat; touch(); drawMatTable(); calc();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------- process rail and shapes
document.querySelectorAll('#rail .proc').forEach(b => b.addEventListener('click', () => { state.p = +b.dataset.p; touch(); render(); }));
$('shapeSel').addEventListener('change', e => { state.shape[state.p] = +e.target.value; touch(); render(); });
$('btnExample').addEventListener('click', () => { const k = key(); state.inputs[k] = Object.assign({}, BOOT.presets[k] || {}); state.example[k] = true; touch(); render(); });
$('btnClear').addEventListener('click', () => { const k = key(); state.inputs[k] = {}; state.example[k] = false; touch(); render(); });
$('sensVar').addEventListener('change', () => { state.sweep = $('sensVar').value || null; calc(); });

function render() {
  const p = state.p;
  document.querySelectorAll('#rail .proc').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.p === p)));
  $('procTitle').textContent = PROCS[p - 1];
  $('procNote').textContent = BOOT.notes[p] || '';
  const shapes = BOOT.processShapes[p];
  $('shapeSel').innerHTML = shapes.map(s => `<option value="${s}">${esc(BOOT.shapeNames[s])}</option>`).join('');
  $('shapeSel').value = String(state.shape[p]);
  $('shapeSel').disabled = shapes.length < 2;
  drawFigs();
  state.formKey = null;
  calc();
}

// ---------------------------------------------------------------- drawings
// One large drawing at a time (tooling or part). Dimension labels and inputs are linked:
// focusing an input highlights its dimension, clicking a dimension jumps to its input.
const dimKey = s => String(s || '').toLowerCase().replace(/\s+/g, '').replace(/^ho$/, 'h0');
let figIdx = 0, figKeys = '';

function drawFigs() {
  const p = state.p, s = state.shape[p];
  const proc = document.querySelector(`#rail .proc[data-p="${p}"] .thumb`).innerHTML;
  const figs = [`<figure tabindex="0" title="Click to enlarge">${proc}<figcaption>${esc(PROCS[p - 1])}: tooling</figcaption></figure>`];
  if (SHAPE_DRAW[s]) figs.push(`<figure tabindex="0" title="Click to enlarge">${SHAPE_DRAW[s]}<figcaption>${esc(BOOT.shapeNames[s])}: before and after</figcaption></figure>`);
  if (figIdx === 1 && figs.length < 2) figIdx = 0;
  $('figs').innerHTML = figs.map((f, i) => f.replace('<figure ', `<figure data-i="${i}" ${i === figIdx ? '' : 'hidden '}`)).join('');
  $('tabPart').disabled = figs.length < 2;
  showFig(figIdx);
  $('figs').querySelectorAll('text.dt').forEach(t => {
    t.dataset.k = '|' + t.textContent.split('/').map(dimKey).join('|') + '|';
    t.setAttribute('role', 'button');
  });
  highlightDim(figKeys);
}

function showFig(i) {
  figIdx = i;
  $('figs').querySelectorAll('figure').forEach(f => { f.hidden = +f.dataset.i !== i; });
  ['tabTool', 'tabPart', 'tab3d'].forEach((t, n) => $(t).setAttribute('aria-selected', String(n === i)));
  $('m3d').hidden = i !== 2;
  $('figs').hidden = i === 2;
  document.querySelector('.figtip').hidden = i === 2;
  if (i === 2) draw3d();
}

// 3D view: loaded on first use (three.js is large), then redrawn whenever inputs change.
let m3d = null, m3dLoading = null;
function draw3d() {
  if ($('m3d').hidden) return;
  if (!m3d) {
    if (!m3dLoading) {
      m3dLoading = import('/static/model3d.js?v=' + BOOT.assetVersion)
        .then(mod => { $('m3dMsg').remove(); m3d = mod.mount($('m3dView')); draw3d(); })
        .catch(() => { $('m3dMsg').textContent = 'The 3D view could not load in this browser.'; });
    }
    return;
  }
  const vals = {};
  for (const [k, v] of Object.entries(curInputs())) if (typeof v === 'number') vals[k] = v;
  const notes = m3d.update(state.shape[state.p], vals, state.p, U.system === 'imperial' ? 12.7 : 10) || [];
  $('m3dNotes').textContent = notes.join(' ');
}

function highlightDim(k) {
  figKeys = k;
  let hitShown = false, hitOther = -1;
  $('figs').querySelectorAll('text.dt').forEach(t => {
    const on = !!k && t.dataset.k.includes('|' + k + '|');
    t.classList.toggle('hl', on);
    if (on) { const i = +t.closest('figure').dataset.i; if (i === figIdx) hitShown = true; else hitOther = i; }
  });
  if (!hitShown && hitOther >= 0 && figIdx !== 2) showFig(hitOther);
  $('vars').querySelectorAll('.field[data-k]').forEach(f => f.classList.toggle('hl', !!k && f.dataset.k === k));
}

['tabTool', 'tabPart', 'tab3d'].forEach((t, i) => $(t).addEventListener('click', () => showFig(i)));
$('figs').addEventListener('click', e => {
  const t = e.target.closest('text.dt');
  if (t) {
    const keys = t.dataset.k.split('|').filter(Boolean);
    const field = [...$('vars').querySelectorAll('.field[data-k]')].find(f => keys.includes(f.dataset.k));
    if (field) { highlightDim(field.dataset.k); field.querySelector('input,select')?.focus(); }
    else highlightDim(keys[0]);
    return;
  }
  const fig = e.target.closest('figure');
  if (fig) openFig(fig);
});
$('figs').addEventListener('keydown', e => { const fig = e.target.closest('figure'); if (fig && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openFig(fig); } });
function openFig(fig) {
  const dlg = $('figDlg');
  $('figDlgBody').innerHTML = fig.innerHTML;
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
}
$('figDlg').addEventListener('click', e => { if (e.target === $('figDlg')) $('figDlg').close(); });

// ---------------------------------------------------------------- variables form
function buildForm(res) {
  const inp = curInputs();
  const rows = res.inputs;
  let html = '';
  for (const x of rows) {
    const id = 'in_' + x.cell, val = inp[x.cell];
    let ctl;
    if (x.kind === 'select') {
      const opts = [''].concat(x.options || []);
      ctl = `<select id="${id}" data-a="${x.cell}">${opts.map(o => `<option value="${esc(o)}"${(val || '') === o ? ' selected' : ''}>${o ? esc(o) : 'Not chosen'}</option>`).join('')}</select>`;
    } else {
      const ph = x.cell === 'C47' ? 'auto' : x.cell === 'C48' ? (state.p === 8 ? 'enter K1' : 'auto') : '';
      ctl = `<input id="${id}" data-a="${x.cell}" data-u="${esc(x.unit)}" inputmode="decimal" value="${val == null ? '' : esc(inVal(val, x.unit))}" placeholder="${ph}">`;
    }
    const extra = x.k1 ? `<div class="hint" id="k1hint"></div>` : '';
    html += `<div class="field" data-k="${esc(dimKey(x.label))}"><label for="${id}">${esc(x.label)}</label><div class="ctl">${ctl}<span class="unit">${uLbl(x.unit)}</span></div>${x.hint ? `<div class="hint">${esc(x.hint)}</div>` : ''}${extra}</div>`;
  }
  $('vars').innerHTML = html;
  highlightDim(figKeys);
  $('varCount').textContent = rows.length + ' inputs';
  $('vars').querySelectorAll('[data-a]').forEach(el => {
    el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => {
      let v = el.value.trim();
      if (el.tagName !== 'SELECT') { if (v === '') v = null; else { const n = parseFloat(v.replace(',', '.')); v = isNaN(n) ? v : U.in(n, el.dataset.u); } }
      inp[el.dataset.a] = v; state.example[key()] = false; touch(); calc();
    });
  });
}

function drawAuto(res) {
  $('autoVals').innerHTML = res.auto.map(x => `<div class="field"><span class="lbl">${esc(x.label)}</span><div class="ro">${qty(x.value, x.unit)} <span class="unit">${uLbl(x.unit)}</span><span class="tag">automatic</span></div>${x.hint ? `<div class="hint">${esc(x.hint)}</div>` : ''}</div>`).join('');
  const k1row = res.inputs.find(x => x.k1);
  if (k1row && $('k1hint')) {
    $('k1hint').innerHTML = `<button class="btn sm" type="button" data-k1="theoretical">Use theoretical ${fmt(k1row.k1.theoretical, 3)}</button> <button class="btn sm" type="button" data-k1="simulation">Use simulation ${fmt(k1row.k1.simulation, 3)}</button>`;
    $('k1hint').querySelectorAll('[data-k1]').forEach(b => b.addEventListener('click', () => {
      const v = k1row.k1[b.dataset.k1];
      if (isNum(v)) { curInputs().C48 = +v.toFixed(4); $('in_C48').value = curInputs().C48; state.example[key()] = false; touch(); calc(); }
    }));
  }
}

// ---------------------------------------------------------------- calculation
let seq = 0, timer = null;
function calc() { clearTimeout(timer); timer = setTimeout(run, 120); }
async function run() {
  const my = ++seq;
  const m = matObj(state.mat);
  const body = { process: state.p, shape: state.shape[state.p], material: state.mat, inputs: curInputs(), sweep: state.sweep };
  if (m && m.custom) body.custom = { name: m.name, C: m.C, n: m.n, Rm: m.Rm };
  $('resPanel').classList.add('loading');
  let res;
  try {
    const r = await fetch('/api/calc', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    res = await r.json();
    if (!r.ok) throw new Error(res.error || 'Calculation failed');
  } catch (e) {
    if (my === seq) { $('banner').innerHTML = `<span class="pill bad"><span class="dot"></span>${esc(e.message || 'Connection problem')}</span>`; $('resPanel').classList.remove('loading'); }
    return;
  }
  if (my !== seq) return;
  $('resPanel').classList.remove('loading');
  state.res = res;
  const fk = key();
  if (state.formKey !== fk) { buildForm(res); state.formKey = fk; drawSensSelect(res); }
  else drawSensSelect(res);
  if (!res.sweep && state.sweep !== ($('sensVar').value || null)) { state.sweep = $('sensVar').value || null; if (state.sweep) { calc(); } }
  drawAuto(res);
  drawResults(res);
  draw3d();
}

function drawResults(res) {
  const p = state.p, r = res.results;
  $('roKf').innerHTML = `${qty(res.kf, 'N/mm²', 0)} <span class="unit">${uLbl('N/mm²')}</span>`;
  $('roN').innerHTML = fmt(res.n, 3);
  $('exChip').hidden = !state.example[key()];
  const kp = [
    { k: 'Load F', v: r.F, u: 'kN', s: 'Press force for this step', main: true },
    { k: 'Energy W', v: r.W, u: 'kJ', s: p === 1 ? 'Not calculated for cut off' : 'Forming work' },
    { k: 'Deformation grade φ', v: r.phi, u: '', s: r.phiNote },
    { k: r.checkLabel, v: r.check, u: r.checkUnit, s: r.checkNote },
  ];
  $('kpis').innerHTML = kp.map(x => `<div class="kpi${x.main ? ' main' : ''}"><div class="eyebrow">${esc(x.k)}</div><div class="v">${qty(x.v, x.u, converts(x.u) && isNum(x.v) && Math.abs(U.out(x.v, x.u)) >= 100 ? 1 : undefined)}${isNum(x.v) && x.u ? `<span class="u">${uLbl(x.u)}</span>` : ''}</div><div class="s">${esc(x.s)}</div></div>`).join('');
  const w = res.warnings;
  $('banner').innerHTML = w.length ? w.map(t => `<span class="pill bad"><span class="dot"></span>${esc(t)}</span>`).join('')
    : (!isNum(r.F) || r.F === 0 ? `<span class="pill warn"><span class="dot"></span>Enter the dimensions to get a load</span>` : `<span class="pill ok"><span class="dot"></span>All tooling checks pass</span>`);
  $('resSub').textContent = res.processName + ' · ' + res.material;
  $('checks').innerHTML = res.checks.length ? res.checks.map(c =>
    `<div class="check ${c.state}"><span class="stripe"></span><div><div class="t">${esc(c.title)}</div><div class="d">${esc(U.text(c.desc))}</div></div><div class="r">${esc(U.text(c.value))}<div class="d">limit ${esc(U.text(c.limit))}</div></div></div>`).join('')
    : `<div class="check na"><span class="stripe"></span><div><div class="t">No process checks</div><div class="d">There are no limit checks for ${esc(res.processName)}.</div></div><div class="r"></div></div>`;
  $('detail').querySelector('tbody').innerHTML = res.detail.map(d => d.group ? `<tr class="grp"><td colspan="3">${esc(d.group)}</td></tr>`
    : `<tr class="${d.key ? 'key' : ''}"><td>${esc(d.label)}</td><td class="v">${qty(d.value, d.unit)}</td><td class="u">${uLbl(d.unit)}</td></tr>`).join('');
  $('eqs').innerHTML = res.equations.map(e => `<li>${esc(e)}</li>`).join('')
    + (U.system === 'imperial' ? '<li class="muted">The equations work in mm, N/mm², kN and kJ. Inputs are converted to metric before calculating and results are converted back for display.</li>' : '');
  drawChart(res);
}

// ---------------------------------------------------------------- sensitivity chart
function drawSensSelect(res) {
  const sel = $('sensVar'), inp = curInputs();
  const opts = res.inputs.filter(x => x.kind !== 'select' && isNum(inp[x.cell]) && inp[x.cell] !== 0);
  const prev = state.sweep;
  sel.innerHTML = opts.map(x => `<option value="${x.cell}">${esc(x.label)}${x.unit ? ' (' + uLbl(x.unit) + ')' : ''}</option>`).join('');
  if (opts.some(o => o.cell === prev)) sel.value = prev;
}
function drawChart(res) {
  const sel = $('sensVar');
  if (!sel.value) { $('chart').innerHTML = '<p class="sub">Enter values to see how the load reacts.</p>'; return; }
  if (!res.sweep || res.sweep.cell !== sel.value) { $('chart').innerHTML = '<p class="sub">Calculating…</p>'; return; }
  const xu = (res.inputs.find(x => x.cell === res.sweep.cell) || {}).unit;
  const pts = res.sweep.points.map(([x, y]) => ({ x: U.out(x, xu), y: y === null ? null : U.out(y, 'kN') }));
  const ys = pts.filter(p => p.y !== null).map(p => p.y);
  if (!ys.length) { $('chart').innerHTML = '<p class="sub">No valid load in this range.</p>'; return; }
  const W = 560, H = 232, l = 56, r = 26, t = 12, b = 40;
  let y0 = Math.min(...ys), y1 = Math.max(...ys); if (y1 - y0 < 1e-9) { y0 -= 1; y1 += 1; }
  const pad = (y1 - y0) * 0.08; y0 = Math.min(...ys) >= 0 ? Math.max(0, y0 - pad) : y0 - pad; y1 += pad;
  const x0 = pts[0].x, x1 = pts[pts.length - 1].x, base = pts[12].x;
  const X = x => l + (x - x0) / (x1 - x0) * (W - l - r), Y = y => t + (1 - (y - y0) / (y1 - y0)) * (H - t - b);
  let d = '', started = false;
  pts.forEach(p => { if (p.y === null) { started = false; return; } d += (started ? 'L' : 'M') + X(p.x).toFixed(1) + ',' + Y(p.y).toFixed(1); started = true; });
  const valid = pts.filter(p => p.y !== null);
  const area = 'M' + X(valid[0].x).toFixed(1) + ',' + (H - b) + valid.map(p => 'L' + X(p.x).toFixed(1) + ',' + Y(p.y).toFixed(1)).join('') + 'L' + X(valid[valid.length - 1].x).toFixed(1) + ',' + (H - b) + 'Z';
  let grid = '';
  for (let i = 0; i <= 4; i++) { const v = y0 + (y1 - y0) * i / 4; grid += `<line x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${fmt(v, v >= 100 ? 0 : 1)}</text>`; }
  for (const f of [0.7, 0.85, 1, 1.15, 1.3]) { const x = base * f; grid += `<text x="${X(x)}" y="${H - b + 16}" text-anchor="middle">${fmt(x, Math.abs(x) >= 100 ? 0 : 2)}</text>`; }
  const cur = pts[12];
  const mark = cur.y !== null ? `<line x1="${X(cur.x)}" x2="${X(cur.x)}" y1="${t}" y2="${H - b}" stroke="var(--muted)" stroke-dasharray="3 3"/><circle cx="${X(cur.x)}" cy="${Y(cur.y)}" r="4.5" fill="var(--chart-line)" stroke="var(--panel)" stroke-width="2"/><text x="${Math.min(X(cur.x) + 8, W - r - 70)}" y="${Math.max(Y(cur.y) - 8, t + 10)}" style="fill:var(--ink)">${fmt(cur.y, 1)} ${uLbl('kN')}</text>` : '';
  $('chart').innerHTML = `<div class="tblwrap"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Load against ${esc(sel.options[sel.selectedIndex].text)}"><path d="${area}" fill="var(--accent-soft)"/>${grid}<path d="${d}" fill="none" stroke="var(--chart-line)" stroke-width="2"/>${mark}<text x="${W - r}" y="${H - 2}" text-anchor="end">${esc(sel.options[sel.selectedIndex].text)} →  (dashed line = current value)</text></svg></div>`;
}

// ---------------------------------------------------------------- saving
const canSave = BOOT.canSave && $('btnSave');
function touch() { if (!state.dirty) { state.dirty = true; drawSaveState(); } }
function toast(t) { const d = document.createElement('div'); d.className = 'toast'; d.textContent = t; document.body.appendChild(d); setTimeout(() => d.remove(), 2600); }
function when(iso) { const d = new Date(iso); return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); }

function drawSaveState() {
  if (!canSave) return;
  const s = state.saved;
  $('btnSaveNew').hidden = !s; $('btnNew').hidden = !s; $('versionsBox').hidden = !s;
  $('btnSave').textContent = s ? 'Save changes' : 'Save';
  $('saveState').textContent = s ? (state.dirty ? 'Unsaved changes' : 'Saved') : '';
  $('saveMeta').innerHTML = s ? `Created by ${esc(s.created_by_name || 'someone')} · last saved ${esc(when(s.updated_at))} by ${esc(s.updated_by_name || 'someone')}` : `Saving stores it in ${esc(BOOT.workspace.name)}${BOOT.workspace.kind === 'team' ? ', where your whole team can open and edit it' : ''}.`;
}

function payload() {
  const m = matObj(state.mat);
  const b = { title: $('calcTitle').value, notes: $('calcNotes').value, process: state.p, shape: state.shape[state.p], material: state.mat, inputs: curInputs() };
  if (m && m.custom) b.custom = { name: m.name, C: m.C, n: m.n, Rm: m.Rm };
  return b;
}

// What the report buttons send: the inputs as they are now, with the name and notes from the Save box.
window.SFReportSource = () => {
  const m = matObj(state.mat);
  const source = { kind: 'calc', process: state.p, shape: state.shape[state.p], material: state.mat, inputs: curInputs() };
  if (m && m.custom) source.custom = { name: m.name, C: m.C, n: m.n, Rm: m.Rm };
  return { source, title: ($('calcTitle') && $('calcTitle').value.trim()) || (state.saved && state.saved.title) || '',
    notes: $('calcNotes') ? $('calcNotes').value : '' };
};

async function save(asNew, force) {
  const b = payload();
  try { Object.assign(b, window.SFProject.body()); } catch (e) { toast(e.message); return; }
  if (!b.title.trim()) { $('calcTitle').focus(); $('calcTitle').placeholder = 'Give it a name first'; return; }
  if (asNew && state.saved) b.title = b.title.replace(/( \(copy\))?$/, ' (copy)');
  const update = state.saved && !asNew;
  if (update) { b.expected = state.saved.updated_at; b.force = !!force; }
  $('btnSave').disabled = true;
  try {
    const r = await fetch(update ? '/api/calculations/' + state.saved.id : '/api/calculations', { method: update ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) });
    const out = await r.json();
    if (r.status === 409) { showConflict(out.current); return; }
    if (!r.ok) throw new Error(out.error || 'Could not save');
    adopt(out, false);
    window.SFProject.adopt(out);
    $('conflict').hidden = true;
    history.replaceState(null, '', '/calculator?calc=' + out.id);
    toast(update ? 'Changes saved' : 'Saved to ' + BOOT.workspace.name);
  } catch (e) { toast(e.message); }
  finally { $('btnSave').disabled = false; }
}

function showConflict(cur) {
  const c = $('conflict');
  c.hidden = false;
  c.innerHTML = `<span><b>${esc(cur.updated_by_name || 'Someone')}</b> saved a newer version at ${esc(when(cur.updated_at))}.</span>
    <button class="btn sm" type="button" data-c="load">Load theirs</button>
    <button class="btn sm" type="button" data-c="force">Overwrite with mine</button>
    <button class="btn sm" type="button" data-c="copy">Save mine as a copy</button>`;
  c.querySelector('[data-c=load]').onclick = () => { adopt(cur, true); c.hidden = true; };
  c.querySelector('[data-c=force]').onclick = () => save(false, true);
  c.querySelector('[data-c=copy]').onclick = () => save(true);
}

function adopt(row, loadInputs) {
  state.saved = row;
  if (loadInputs) {
    const inp = Object.assign({}, row.inputs || {});
    const mp = inp._material; delete inp._material;
    const curM = matObj(row.material);
    if (mp && (!curM || (!curM.custom && (Math.abs(curM.C - mp.C) > 1e-9 || Math.abs(curM.n - mp.n) > 1e-9)))) {
      // Use the material values this calculation was saved with.
      if (curM) { MATS = MATS.filter(m => m !== curM); setTimeout(() => toast('Using the material values saved with this calculation; the library has changed since.'), 400); }
      MATS.push(Object.assign({ custom: true }, mp)); MATS.sort((a, b) => a.name.localeCompare(b.name));
    }
    state.p = row.process; state.shape[row.process] = row.shape; state.mat = row.material;
    state.inputs[row.process + '-' + row.shape] = inp; state.example[row.process + '-' + row.shape] = false;
    $('calcTitle').value = row.title; $('calcNotes').value = row.notes || '';
    window.SFProject.adopt(row);
    if (row.notes) $('notesBox').open = true;
    drawMatSelect(); render();
  }
  state.dirty = false;
  drawSaveState();
  $('versions').innerHTML = ''; $('versionsBox').open = false;
}

if (canSave) {
  $('btnSave').addEventListener('click', () => save(false));
  $('btnSaveNew').addEventListener('click', () => save(true));
  $('calcTitle').addEventListener('input', touch);
  $('calcNotes').addEventListener('input', touch);
  window.SFProject.onChange(touch);
  $('calcTitle').addEventListener('keydown', e => { if (e.key === 'Enter') save(false); });
  document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(false); } });
  $('versionsBox').addEventListener('toggle', async () => {
    if (!$('versionsBox').open || !state.saved) return;
    $('versions').innerHTML = '<p class="small muted">Loading…</p>';
    const r = await fetch('/api/calculations/' + state.saved.id + '/versions');
    const vs = await r.json();
    if (!r.ok) { $('versions').innerHTML = `<p class="small err">${esc(vs.error)}</p>`; return; }
    $('versions').innerHTML = vs.map((v, i) => `<div class="ver"><span>${esc(when(v.created_at))} · ${esc(v.edited_by_name || '')}<br><span class="muted">${esc(PROCS[v.process - 1])} · ${esc(v.material)} · F <span class="num">${qty((v.summary || {}).F, 'kN', 1)}</span> ${uLbl('kN')}</span></span>${i === 0 ? '<span class="chip">current</span>' : `<button class="btn sm" type="button" data-v="${i}">Restore</button>`}</div>`).join('');
    $('versions').querySelectorAll('[data-v]').forEach(b => b.addEventListener('click', () => {
      const v = vs[+b.dataset.v];
      const keep = state.saved;
      adopt(Object.assign({}, keep, { process: v.process, shape: v.shape, material: v.material, inputs: v.inputs, notes: v.notes, title: v.title || keep.title }), true);
      state.saved = keep; state.dirty = true; drawSaveState();
      toast('Version loaded. Press Save changes to keep it.');
    }));
  });
  // Live updates: check whether a teammate saved a newer version.
  setInterval(async () => {
    if (!state.saved || document.hidden) return;
    try {
      const r = await fetch('/api/calculations/' + state.saved.id);
      if (!r.ok) return;
      const cur = await r.json();
      if (cur.updated_at !== state.saved.updated_at && $('conflict').hidden) {
        if (!state.dirty) { adopt(cur, true); toast((cur.updated_by_name || 'A teammate') + ' updated this calculation'); }
        else showConflict(cur);
      }
    } catch (e) { /* offline: try again later */ }
  }, 20000);
  window.addEventListener('beforeunload', e => { if (state.dirty && state.saved) { e.preventDefault(); e.returnValue = ''; } });
}

// ---------------------------------------------------------------- unit switch
function drawUnits() {
  $('m3dGrid').textContent = U.system === 'imperial' ? 'Floor grid: ½ in squares.' : 'Floor grid: 10 mm squares.';
  drawMatTable();
  const res = state.res;
  if (!res) return;
  buildForm(res); state.formKey = key();
  drawSensSelect(res); drawAuto(res); drawResults(res); draw3d();
}
window.addEventListener('sf-units', drawUnits);

// ---------------------------------------------------------------- start
$('m3dGrid').textContent = U.system === 'imperial' ? 'Floor grid: ½ in squares.' : 'Floor grid: 10 mm squares.';
drawMatSelect();
if (BOOT.saved && canSave) adopt(BOOT.saved, true);
else { if (canSave) drawSaveState(); render(); }
$('vars').addEventListener('focusin', e => { const f = e.target.closest('.field[data-k]'); if (f) highlightDim(f.dataset.k); });
$('vars').addEventListener('mouseover', e => { const f = e.target.closest('.field[data-k]'); if (f) highlightDim(f.dataset.k); });
$('vars').addEventListener('mouseleave', () => { const f = document.activeElement?.closest?.('#vars .field[data-k]'); highlightDim(f ? f.dataset.k : ''); });
})();
