/* Built-in tool pages (slotted sleeve die, …): builds the form from the tool spec,
   asks /api/tools/<slug> for results as you type, links drawing dimensions to inputs. */
(function () {
'use strict';
const BOOT = JSON.parse(document.getElementById('boot').textContent);
const T = BOOT.tool;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const U = window.SFUnits;
const isNum = v => typeof v === 'number' && isFinite(v);
const converts = u => U.unit(u) !== (u || '');
function fmt(v, d) {
  if (!isNum(v)) return '—';
  if (d === undefined) { const a = Math.abs(v); d = a >= 1000 ? 1 : a >= 100 ? 2 : a >= 1 ? 3 : 4; if (v === 0) d = 0; }
  return v.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
}
const qty = (v, u, d) => fmt(U.out(v, u), converts(u) ? undefined : d);
const uLbl = u => esc(U.unit(u));
const unitOf = i => (i.unitBy ? (i.unitBy.map[state.values[i.unitBy.key]] || '') : (i.unit || ''));
const optVal = o => (typeof o === 'object' ? o.value : o);
const optLbl = o => (typeof o === 'object' ? o.label : o);
const inVal = (v, u) => (isNum(v) ? String(converts(u) ? +U.out(v, u).toPrecision(6) : v) : (v == null ? '' : v));

// ---------------------------------------------------------------- state (metric values)
const state = { values: {}, example: false, res: null, fig: 0, hl: '' };
(function init() {
  if (BOOT.saved) { state.values = Object.assign({}, T.example, BOOT.saved.inputs); return; }
  const q = new URLSearchParams(location.search);
  const known = T.inputs.filter(i => q.has(i.key));
  if (known.length) {
    for (const i of T.inputs) {
      const raw = q.get(i.key);
      const text = i.kind === 'select' || i.kind === 'preset';
      state.values[i.key] = raw == null || raw === '' ? (text ? T.example[i.key] : null) : (text ? raw : (isNaN(+raw) ? null : +raw));
    }
  } else { state.values = Object.assign({}, T.example); state.example = true; }
})();

// ---------------------------------------------------------------- form
function buildForm() {
  const auto = (state.res && state.res.auto) || {};
  let html = '';
  for (const g of T.groups) {
    const rows = T.inputs.filter(i => i.group === g.key).map(i => {
      const id = 'in_' + i.key, val = state.values[i.key], u = unitOf(i);
      let ctl;
      if (i.kind === 'select') {
        ctl = `<select id="${id}" data-a="${esc(i.key)}" style="font-family:var(--f-body)">${i.options.map(o => `<option value="${esc(optVal(o))}"${String(optVal(o)) === String(val) ? ' selected' : ''}>${esc(optLbl(o))}</option>`).join('')}</select>`;
      } else if (i.kind === 'preset') {
        let cur = null, opts = '';
        i.options.forEach((o, n) => {
          if (o.group !== cur) { opts += (cur === null ? '' : '</optgroup>') + `<optgroup label="${esc(o.group)}">`; cur = o.group; }
          opts += `<option value="${n}"${String(n) === String(val) ? ' selected' : ''}>${esc(o.label)}</option>`;
        });
        ctl = `<select id="${id}" data-a="${esc(i.key)}" data-preset="1" style="font-family:var(--f-body)"><option value="">Your own size</option>${opts}${cur === null ? '' : '</optgroup>'}</select>`;
      } else {
        const ph = i.placeholder ? (isNum(auto[i.key]) ? 'auto ' + fmt(U.out(auto[i.key], u)) : i.placeholder) : '';
        ctl = `<input id="${id}" data-a="${esc(i.key)}" data-u="${esc(u)}" inputmode="decimal" value="${esc(inVal(val, u))}" placeholder="${esc(ph)}">`;
      }
      return `<div class="field" data-k="${esc(i.key)}"><label for="${id}">${esc(i.label)}</label><div class="ctl">${ctl}<span class="unit">${uLbl(u)}</span></div>${i.hint ? `<div class="hint">${esc(i.hint)}</div>` : ''}</div>`;
    }).join('');
    html += g.drawer ? `<details class="drawer" id="grp_${g.key}" style="margin-top:12px"><summary>${esc(g.title)}</summary>${rows}</details>`
      : `<div class="eyebrow" style="margin:2px 0 4px">${esc(g.title)}</div>${rows}`;
  }
  const open = T.groups.filter(g => g.drawer && $('grp_' + g.key) && $('grp_' + g.key).open).map(g => g.key);
  $('vars').innerHTML = html;
  open.forEach(k => { $('grp_' + k).open = true; });
  $('varCount').textContent = T.inputs.length + ' inputs';
  $('vars').querySelectorAll('[data-a]').forEach(el => el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => {
    const key = el.dataset.a, spec = T.inputs.find(i => i.key === key);
    let v = el.value.trim();
    if (el.tagName !== 'SELECT') { if (v === '') v = null; else { const n = parseFloat(v.replace(',', '.')); v = isNaN(n) ? null : U.in(n, el.dataset.u); } }
    state.values[key] = v; state.example = false;
    if (spec.kind === 'preset') {  // a catalogue size fills several inputs
      if (v !== '') Object.assign(state.values, spec.options[+v].values);
      buildForm();
    } else if (spec.remap) {  // the load points are re-expressed in the new way of entering them
      const m = state.res && state.res.auto && state.res.auto.remap && state.res.auto.remap[v];
      if (m) Object.assign(state.values, m);
      buildForm();
    } else {
      const p = T.inputs.find(i => i.kind === 'preset' && i.fills.includes(key));
      if (p && state.values[p.key] !== '') { state.values[p.key] = ''; const ps = $('in_' + p.key); if (ps) ps.value = ''; }
    }
    calc();
  }));
  highlight(state.hl);
}
function refreshPlaceholders() {
  const auto = (state.res && state.res.auto) || {};
  for (const i of T.inputs) {
    const el = $('in_' + i.key);
    if (el && i.placeholder) el.placeholder = isNum(auto[i.key]) ? 'auto ' + fmt(U.out(auto[i.key], unitOf(i))) : i.placeholder;
  }
}

// ---------------------------------------------------------------- drawings
const tabs = [...document.querySelectorAll('.figtabs [data-fig]')];
tabs.forEach(b => b.addEventListener('click', () => showFig(+b.dataset.fig)));
function drawFigs(figs) {
  $('figs').innerHTML = figs.map((svg, i) => `<figure data-i="${i}" tabindex="0" title="Click to enlarge"${i === state.fig ? '' : ' hidden'}>${svg}<figcaption>${esc(T.title)}: ${esc((T.figures[i] || '').toLowerCase())}</figcaption></figure>`).join('');
  $('figs').querySelectorAll('text.dt[data-k]').forEach(t => t.setAttribute('role', 'button'));
  U.apply($('figs'));
  highlight(state.hl);
}
function showFig(i) {
  state.fig = i;
  $('figs').querySelectorAll('figure').forEach(f => { f.hidden = +f.dataset.i !== i; });
  tabs.forEach((b, n) => b.setAttribute('aria-selected', String(n === i)));
}
function highlight(k) {
  state.hl = k;
  let shown = false, other = -1;
  $('figs').querySelectorAll('text.dt[data-k]').forEach(t => {
    const on = !!k && t.dataset.k === k;
    t.classList.toggle('hl', on);
    if (on) { const i = +t.closest('figure').dataset.i; if (i === state.fig) shown = true; else other = i; }
  });
  if (!shown && other >= 0) showFig(other);
  $('vars').querySelectorAll('.field[data-k]').forEach(f => f.classList.toggle('hl', !!k && f.dataset.k === k));
}
$('figs').addEventListener('click', e => {
  const t = e.target.closest('text.dt[data-k]');
  if (t) {
    const f = $('vars').querySelector(`.field[data-k="${CSS.escape(t.dataset.k)}"]`);
    highlight(t.dataset.k);
    if (f) { const d = f.closest('details'); if (d) d.open = true; f.querySelector('input,select').focus(); }
    return;
  }
  const fig = e.target.closest('figure');
  if (fig) openFig(fig);
});
$('figs').addEventListener('keydown', e => { const fig = e.target.closest('figure'); if (fig && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openFig(fig); } });
function openFig(fig) {
  $('figDlgBody').innerHTML = fig.innerHTML;
  const dlg = $('figDlg');
  if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
}
$('figDlg').addEventListener('click', e => { if (e.target === $('figDlg')) $('figDlg').close(); });
$('vars').addEventListener('focusin', e => { const f = e.target.closest('.field[data-k]'); if (f) highlight(f.dataset.k); });
$('vars').addEventListener('mouseover', e => { const f = e.target.closest('.field[data-k]'); if (f) highlight(f.dataset.k); });
$('vars').addEventListener('mouseleave', () => { const f = document.activeElement && document.activeElement.closest && document.activeElement.closest('#vars .field[data-k]'); highlight(f ? f.dataset.k : ''); });

// ---------------------------------------------------------------- calculation
let seq = 0, timer = null;
function calc() { clearTimeout(timer); timer = setTimeout(run, 120); }
async function run() {
  const my = ++seq;
  $('resPanel').classList.add('loading');
  let res;
  try {
    const r = await fetch('/api/tools/' + encodeURIComponent(T.slug), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values: state.values }) });
    res = await r.json();
    if (!r.ok) throw new Error(res.error || 'Calculation failed');
  } catch (e) {
    if (my === seq) { $('banner').innerHTML = `<span class="pill bad"><span class="dot"></span>${esc(e.message || 'Connection problem')}</span>`; $('resPanel').classList.remove('loading'); }
    return;
  }
  if (my !== seq) return;
  $('resPanel').classList.remove('loading');
  state.res = res;
  refreshPlaceholders();
  draw();
  const q = new URLSearchParams();
  for (const i of T.inputs) { const v = state.values[i.key]; if (v !== null && v !== undefined && v !== '') q.set(i.key, isNum(v) ? +v.toPrecision(10) : v); }
  if (BOOT.saved) q.set('calc', BOOT.saved.id);
  history.replaceState(null, '', location.pathname + '?' + q);
  const here = encodeURIComponent(location.pathname + '?' + q);
  ['signupSave', 'loginSave'].forEach(id => { const a = $(id); if (a) a.href = a.href.split('?')[0] + '?next=' + here; });
}

function draw() {
  const res = state.res;
  if (!res) return;
  $('exChip').hidden = !state.example;
  const kv = x => (isNum(x.value) ? qty(x.value, x.unit, x.decimals !== undefined ? x.decimals : Math.abs(x.value) >= 1000 ? 0 : Math.abs(x.value) >= 100 ? 1 : 2) + `<span class="u">${uLbl(x.unit)}</span>` : esc(x.text || '—'));
  $('kpis').innerHTML = res.kpis.length ? res.kpis.map(x => `<div class="kpi${x.main ? ' main' : ''}"><div class="eyebrow">${esc(x.label)}</div><div class="v">${kv(x)}</div><div class="s">${esc(U.text(x.sub || ''))}</div></div>`).join('')
    : '<p class="sub small" style="margin:0">Results appear once the dimensions are filled in.</p>';
  $('banner').innerHTML = res.warnings.length ? res.warnings.map(t => `<span class="pill bad"><span class="dot"></span>${esc(U.text(t))}</span>`).join('')
    : (res.checks.some(c => c.state === 'warn') ? '<span class="pill warn"><span class="dot"></span>Within limits, see the notes under Design checks</span>' : '<span class="pill ok"><span class="dot"></span>All design checks pass</span>');
  $('values').querySelector('tbody').innerHTML = res.values.map(v => `<tr class="${v.key ? 'key' : ''}"><td>${esc(v.label)}${v.note ? `<div class="small muted" style="font-weight:400">${esc(v.note)}</div>` : ''}</td><td class="v">${qty(v.value, v.unit, v.decimals !== undefined ? v.decimals : Number.isInteger(v.value) && !v.unit ? 0 : 3)}</td><td class="u">${uLbl(v.unit)}</td></tr>`).join('')
    || '<tr><td class="muted">—</td></tr>';
  $('checks').innerHTML = res.checks.length ? res.checks.map(c => `<div class="check ${c.state}"><span class="stripe"></span><div><div class="t">${esc(c.title)}</div><div class="d">${esc(c.desc)}</div></div><div class="r">${esc(U.text(c.value))}<div class="d">limit ${esc(U.text(c.limit))}</div></div></div>`).join('')
    : '<div class="check na"><span class="stripe"></span><div><div class="t">No checks yet</div><div class="d">Fill in the dimensions first.</div></div><div class="r"></div></div>';
  $('tables').innerHTML = (res.tables || []).map(t => `<div class="panel"><div class="phead"><h2>${esc(t.title)}</h2><span class="eyebrow">${esc(t.sub || '')}</span></div>
    <div class="tblwrap"><table class="grid"><thead><tr>${t.columns.map((c, n) => `<th${n ? ' style="text-align:right"' : ''}>${esc(c.label)}${c.unit ? `<div class="small muted" style="font-weight:400">${uLbl(c.unit)}</div>` : ''}</th>`).join('')}</tr></thead>
    <tbody>${t.rows.map(r => `<tr>${r.map((v, n) => n === 0 ? `<td>${esc(v)}</td>` : `<td class="v">${v && v.error ? `<span class="err">${esc(v.error)}</span>` : qty(v, t.columns[n].unit)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    ${(t.foot || []).map(f => `<p class="sub small" style="margin:8px 0 0">${esc(U.text(f))}</p>`).join('')}</div>`).join('');
  $('detail').querySelector('tbody').innerHTML = res.steps.map(d => d.group ? `<tr class="grp"><td colspan="3">${esc(d.group)}</td></tr>`
    : `<tr class="${d.key ? 'key' : ''}"><td>${esc(d.label)}</td><td class="v">${qty(d.value, d.unit)}</td><td class="u">${uLbl(d.unit)}</td></tr>`).join('');
  $('eqs').innerHTML = res.equations.map(e => `<li>${esc(e)}</li>`).join('')
    + (U.system === 'imperial' ? '<li class="muted">The equations work in mm, N/mm² and kN. Inputs are converted to metric before calculating and results are converted back for display.</li>' : '');
  drawFigs(res.figures);
}

// ---------------------------------------------------------------- saving (any signed-in account)
const save = { row: BOOT.saved, dirty: false };
const canSave = BOOT.canSave && $('btnSave');
const when = t => { try { return new Date(t).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; } };
function touch() { if (canSave && !save.dirty) { save.dirty = true; drawSave(); } }
function drawSave() {
  if (!canSave) return;
  const r = save.row;
  $('btnSaveNew').hidden = !r; $('btnNew').hidden = !r;
  $('btnSave').textContent = r ? 'Save changes' : 'Save';
  $('saveState').textContent = r ? (save.dirty ? 'Unsaved changes' : 'Saved') : '';
  $('saveMeta').innerHTML = r ? `Created by ${esc(r.created_by_name || 'someone')} · last saved ${esc(when(r.updated_at))} by ${esc(r.updated_by_name || 'someone')}`
    : `Saving stores it in ${esc(BOOT.workspace.name)}${BOOT.workspace.kind === 'team' ? ', where your whole team can open and edit it' : ''}.`;
}
async function doSave(asNew, force) {
  const b = { title: $('calcTitle').value, notes: $('calcNotes').value, values: state.values };
  if (asNew && save.row) b.title = (b.title || save.row.title).replace(/( \(copy\))?$/, ' (copy)');
  const update = save.row && !asNew;
  if (update) { b.expected = save.row.updated_at; b.force = !!force; }
  $('btnSave').disabled = true;
  try {
    const url = '/api/tools/' + encodeURIComponent(T.slug) + '/saved' + (update ? '/' + save.row.id : '');
    const r = await fetch(url, { method: update ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) });
    const out = await r.json();
    if (r.status === 409) {
      if (confirm('Someone saved a newer version of this result. Replace it with yours? Cancel keeps theirs; you can then use Save as copy.')) return doSave(false, true);
      return;
    }
    if (!r.ok) throw new Error(out.error || 'Could not save');
    save.row = out; save.dirty = false; BOOT.saved = out;
    $('calcTitle').value = out.title;
    drawSave();
    const q = new URLSearchParams(location.search); q.set('calc', out.id);
    history.replaceState(null, '', location.pathname + '?' + q);
    const rp = $('reportPanel'); if (rp) rp.dataset.title = out.title;
  } catch (e) { alert(e.message || 'Could not save'); }
  finally { $('btnSave').disabled = false; }
}
if (canSave) {
  if (save.row) { $('calcTitle').value = save.row.title; $('calcNotes').value = save.row.notes || ''; if (save.row.notes) $('notesBox').open = true; }
  $('btnSave').addEventListener('click', () => doSave(false));
  $('btnSaveNew').addEventListener('click', () => doSave(true));
  $('calcTitle').addEventListener('input', touch);
  $('calcNotes').addEventListener('input', touch);
  $('vars').addEventListener('input', touch);
  $('vars').addEventListener('change', touch);
  drawSave();
}

$('btnExample').addEventListener('click', () => { touch(); state.values = Object.assign({}, T.example); state.example = true; buildForm(); calc(); });
$('btnClear').addEventListener('click', () => {
  const keep = {};
  const drawer = new Set(T.groups.filter(g => g.drawer).map(g => g.key));
  for (const i of T.inputs) keep[i.key] = drawer.has(i.group) || i.kind === 'select' ? T.example[i.key] : null;
  state.values = keep; state.example = false; touch(); buildForm(); calc();
});
window.addEventListener('sf-units', () => { buildForm(); draw(); });

buildForm();
run();
})();
