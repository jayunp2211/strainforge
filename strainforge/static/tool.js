// Runs an owner-built calculator: builds the form from its spec, asks the server for results as you type.
(() => {
  const boot = JSON.parse(document.getElementById('boot').textContent);
  const spec = boot.spec, form = document.getElementById('form'), outs = document.getElementById('outs');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d) => Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const url = new URLSearchParams(location.search);

  let html = '';
  if (spec.material) {
    html += `<div class="field"><label for="mat">Material</label><div class="ctl"><select id="mat">${boot.materials.map(m =>
      `<option ${m.name === (url.get('material') || (boot.materials.some(x => x.name === 'CuZr') ? 'CuZr' : '')) ? 'selected' : ''}>${esc(m.name)}</option>`).join('')}</select></div>
      <div class="hint" id="matHint"></div></div>`;
  }
  for (const i of spec.inputs) {
    const v = url.has(i.key) ? url.get(i.key) : i.default;
    html += `<div class="field"><label for="in-${esc(i.key)}">${esc(i.label)}</label>
      <div class="ctl"><input id="in-${esc(i.key)}" data-key="${esc(i.key)}" inputmode="decimal" value="${esc(v)}"><span class="unit">${esc(i.unit)}</span></div>
      ${i.hint ? `<div class="hint">${esc(i.hint)}</div>` : ''}</div>`;
  }
  form.innerHTML = html;

  let seq = 0, timer;
  async function calc() {
    const values = {};
    form.querySelectorAll('[data-key]').forEach(e => { values[e.dataset.key] = e.value.trim(); });
    const mat = document.getElementById('mat');
    const n = ++seq;
    document.getElementById('resPanel').classList.add('loading');
    let res;
    try {
      const r = await fetch('/api/tools/' + encodeURIComponent(boot.slug), { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values, material: mat && mat.value }) });
      res = await r.json();
      if (!r.ok) throw new Error(res.error || 'Could not calculate');
    } catch (e) {
      if (n === seq) outs.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
      return;
    } finally { if (n === seq) document.getElementById('resPanel').classList.remove('loading'); }
    if (n !== seq) return;
    if (mat && res.material) {
      document.getElementById('matHint').textContent = `C = ${res.material.C} N/mm², n = ${res.material.n}` + (res.material.Rm ? `, Rm = ${Math.round(res.material.Rm)} N/mm²` : '');
    }
    outs.innerHTML = res.outputs.map(o => `<div class="out${o.main ? ' main' : ''}"><div class="l">${esc(o.label)}</div>
      ${o.error ? `<div class="v">—</div><div class="e">${esc(o.error)}</div>` : `<div class="v">${fmt(o.value, o.decimals)}<span class="u">${esc(o.unit)}</span></div>`}</div>`).join('');
    const q = new URLSearchParams(values); if (mat) q.set('material', mat.value);
    history.replaceState(null, '', location.pathname + '?' + q);
  }
  form.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(calc, 180); });
  document.getElementById('reset').addEventListener('click', () => {
    spec.inputs.forEach(i => { form.querySelector(`[data-key="${CSS.escape(i.key)}"]`).value = i.default; });
    calc();
  });
  calc();
})();
