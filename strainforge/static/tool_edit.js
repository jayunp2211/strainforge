// Calculator builder for the site owner: edit inputs and result formulas, live preview, save.
(() => {
  const boot = JSON.parse(document.getElementById('boot').textContent);
  const tool = boot.tool, $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d) => Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  let dirty = false;

  function inRow(i = {}) {
    const d = document.createElement('div'); d.className = 'brow in';
    d.innerHTML = `<input class="tf key" data-f="key" placeholder="d0" value="${esc(i.key)}" aria-label="Name in formulas">
      <input class="tf" data-f="label" placeholder="Wire diameter" value="${esc(i.label)}" aria-label="Label">
      <input class="tf" data-f="unit" placeholder="unit" value="${esc(i.unit)}" aria-label="Unit">
      <input class="tf" data-f="default" inputmode="decimal" placeholder="0" value="${esc(i.default ?? 0)}" aria-label="Default value">
      <button class="btn sm danger x" type="button" title="Remove input" aria-label="Remove input">×</button>
      <input class="tf formula" data-f="hint" placeholder="Hint under the field (optional)" value="${esc(i.hint)}" aria-label="Hint" style="font-family:inherit">`;
    return d;
  }
  function outRow(o = {}) {
    const d = document.createElement('div'); d.className = 'brow out';
    d.innerHTML = `<input class="tf key" data-f="key" placeholder="F" value="${esc(o.key)}" aria-label="Name in formulas">
      <input class="tf" data-f="label" placeholder="Forming force" value="${esc(o.label)}" aria-label="Label">
      <input class="tf" data-f="unit" placeholder="unit" value="${esc(o.unit)}" aria-label="Unit">
      <input class="tf" data-f="decimals" type="number" min="0" max="6" value="${esc(o.decimals ?? 2)}" aria-label="Decimals">
      <button class="btn sm danger x" type="button" title="Remove result" aria-label="Remove result">×</button>
      <input class="tf formula" data-f="formula" placeholder="= formula, e.g. kf(phi)*PI()*d^2/4/1000" value="${esc(o.formula)}" aria-label="Formula">
      <label class="mainpick"><input type="radio" name="main" data-f="main" ${o.main ? 'checked' : ''}> Headline result</label>`;
    return d;
  }
  tool.spec.inputs.forEach(i => $('ins').append(inRow(i)));
  tool.spec.outputs.forEach(o => $('outsEd').append(outRow(o)));

  const mats = boot.materials || [];
  $('prevMat').innerHTML = mats.map(m => `<option>${esc(m.name)}</option>`).join('');
  if (mats.some(m => m.name === 'CuZr')) $('prevMat').value = 'CuZr';

  function collect() {
    const rows = (id) => [...$(id).children].map(r => {
      const o = {}; r.querySelectorAll('[data-f]').forEach(e => { o[e.dataset.f] = e.type === 'radio' ? e.checked : e.value; }); return o;
    });
    return {
      id: tool.id, title: $('title').value, slug: $('slug').value, summary: $('summary').value, published: $('published').checked,
      spec: { material: $('material').checked, inputs: rows('ins'), outputs: rows('outsEd'), notes: $('notes').value },
    };
  }

  let seq = 0, timer;
  async function preview() {
    const body = collect(), n = ++seq;
    $('prevMatRow').hidden = !body.spec.material;
    const values = {}; body.spec.inputs.forEach(i => { if (i.key) values[i.key] = i.default; });
    const r = await fetch('/api/admin/tools/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec: body.spec, values, material: $('prevMat').value }) });
    const res = await r.json();
    if (n !== seq) return;
    $('prevErr').hidden = r.ok; $('prevErr').textContent = res.error || '';
    if (!r.ok) return;
    $('prevOuts').innerHTML = res.outputs.map(o => `<div class="out${o.main ? ' main' : ''}"><div class="l">${esc(o.label)} <span class="muted mono">${esc(o.key)}</span></div>
      ${o.error ? `<div class="v">—</div><div class="e">${esc(o.error)}</div>` : `<div class="v">${fmt(o.value, o.decimals)}<span class="u">${esc(o.unit)}</span></div>`}</div>`).join('');
  }
  const changed = () => { dirty = true; clearTimeout(timer); timer = setTimeout(preview, 250); };
  document.querySelector('.builder').addEventListener('input', changed);
  document.querySelector('.builder').addEventListener('change', changed);
  document.querySelector('.builder').addEventListener('click', e => {
    const x = e.target.closest('.x'); if (!x) return;
    x.closest('.brow').remove(); changed();
  });
  $('addIn').addEventListener('click', () => { const r = inRow(); $('ins').append(r); r.querySelector('input').focus(); });
  $('addOut').addEventListener('click', () => { const r = outRow(); $('outsEd').append(r); r.querySelector('input').focus(); });
  $('title').addEventListener('input', () => {
    $('slugShow').textContent = $('slug').value || $('title').value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || '…';
  });
  $('slug').addEventListener('input', () => { $('slugShow').textContent = $('slug').value || '…'; });

  document.querySelectorAll('[data-save]').forEach(b => b.addEventListener('click', async () => {
    document.querySelectorAll('[data-save]').forEach(x => { x.disabled = true; });
    const r = await fetch('/api/admin/tools', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collect()) });
    const res = await r.json();
    document.querySelectorAll('[data-save]').forEach(x => { x.disabled = false; });
    if (!r.ok) { $('prevErr').hidden = false; $('prevErr').textContent = res.error || 'Could not save'; $('prevErr').scrollIntoView({ block: 'center', behavior: 'smooth' }); return; }
    dirty = false;
    location.href = '/admin/tools/' + res.id + '?msg=' + encodeURIComponent($('published').checked ? 'Saved. It is live at /calculator/' + res.slug : 'Saved as a draft. Tick “Live for everyone” to publish it.');
  }));
  addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  preview();
})();
