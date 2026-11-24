/* PDF and Excel reports for the calculator and tool pages.
   Reads what the page shows (inputs, results, checks, tables, steps, the drawing) in the
   viewer's units. PDF: a print-ready page in a hidden frame, saved through the browser's
   print dialog. Excel: sent to /api/report.xlsx, which builds the workbook. */
(function () {
'use strict';
const box = document.getElementById('reportPanel');
if (!box || box.dataset.allowed !== '1') return;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const txt = el => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '');

function fieldValue(f) {
  const c = f.querySelector('input,select,textarea');
  if (!c) return txt(f.querySelector('.ro'));
  if (c.tagName === 'SELECT') { const o = c.options[c.selectedIndex]; return o ? o.text : ''; }
  return c.value.trim() || (c.placeholder || '').trim();
}
function tableRows(table) {
  const rows = [];
  if (!table) return rows;
  table.querySelectorAll('tbody tr').forEach(tr => {
    if (tr.classList.contains('grp')) { rows.push({ group: txt(tr) }); return; }
    const cells = [...tr.children].map(td => {
      const main = td.cloneNode(true);
      main.querySelectorAll('.small,.muted').forEach(n => { if (n !== main) n.remove(); });
      return txt(main);
    });
    if (cells.some(Boolean)) rows.push(cells);
  });
  return rows;
}

function collect() {
  const title = ($('calcTitle') && $('calcTitle').value.trim()) || box.dataset.title || txt(document.querySelector('h1'));
  const sections = [];
  // Setup (calculator: process, shape, material)
  const setup = [];
  if ($('procTitle') && $('shapeSel')) {
    setup.push(['Process', txt($('procTitle')), '']);
    document.querySelectorAll('.b-top .field').forEach(f => {
      const l = txt(f.querySelector('label,.lbl'));
      if (l) setup.push([l, fieldValue(f), '']);
    });
  }
  if (setup.length) sections.push({ title: 'Setup', columns: ['Item', 'Value', ''], rows: setup });
  // Inputs
  const inputs = [];
  document.querySelectorAll('#autoVals .field, #vars .field').forEach(f => {
    const l = txt(f.querySelector('label,.lbl'));
    const v = fieldValue(f);
    if (l && v !== '') inputs.push([l, v.replace(/^auto /, ''), txt(f.querySelector('.unit'))]);
  });
  if (inputs.length) sections.push({ title: 'Inputs', columns: ['Input', 'Value', 'Unit'], rows: inputs });
  // Results
  const kpis = [...document.querySelectorAll('#kpis .kpi')].map(k => {
    const v = k.querySelector('.v');
    const u = v && v.querySelector('.u');
    const num = v ? txt(v).replace(u ? txt(u) : '', '').trim() : '';
    return [txt(k.querySelector('.eyebrow')), num, txt(u), txt(k.querySelector('.s'))];
  });
  if (kpis.length) sections.push({ title: 'Results', columns: ['Result', 'Value', 'Unit', 'Note'], rows: kpis });
  const status = [...document.querySelectorAll('#banner .pill')].map(txt).filter(Boolean);
  if ($('values')) {
    const r = tableRows($('values'));
    if (r.length) sections.push({ title: 'Design values', columns: ['Quantity', 'Value', 'Unit'], rows: r });
  }
  const checks = [...document.querySelectorAll('#checks .check')].map(c => {
    const r = c.querySelector('.r');
    const lim = r && r.querySelector('.d');
    const val = r ? txt(r).replace(lim ? txt(lim) : '', '').trim() : '';
    const state = c.classList.contains('bad') ? 'Fails' : c.classList.contains('warn') ? 'Warning' : c.classList.contains('ok') ? 'OK' : '';
    return [txt(c.querySelector('.t')), val, txt(lim).replace(/^limit\s*/, ''), state, txt(c.querySelector('div > .d'))];
  }).filter(r => r[0]);
  if (checks.length) sections.push({ title: 'Checks', columns: ['Check', 'Value', 'Limit', 'Status', 'Note'], rows: checks });
  document.querySelectorAll('#tables .panel').forEach(p => {
    const t = p.querySelector('table');
    if (!t) return;
    const cols = [...t.querySelectorAll('thead th')].map(th => [...th.childNodes].map(n => n.textContent.trim()).filter(Boolean).join(' '));
    sections.push({ title: txt(p.querySelector('h2')), columns: cols, rows: tableRows(t) });
  });
  if ($('detail')) {
    const r = tableRows($('detail'));
    if (r.length) sections.push({ title: 'Calculation steps', columns: ['Quantity', 'Value', 'Unit'], rows: r });
  }
  const eqs = [...document.querySelectorAll('#eqs li')].map(li => [txt(li)]).filter(r => r[0]);
  const fig = document.querySelector('#figs figure:not([hidden]) svg');
  const notes = $('calcNotes') ? $('calcNotes').value.trim() : '';
  const units = window.SFUnits && window.SFUnits.system === 'imperial' ? 'Imperial (in, lbf)' : 'Metric (mm, kN)';
  const meta = [['Date', new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })],
    ['Prepared by', box.dataset.user || ''], ['Workspace', box.dataset.ws || ''], ['Units', units]];
  if (status.length) meta.push(['Status', status.join('; ')]);
  if (notes) meta.push(['Notes', notes]);
  return { title, tool: box.dataset.tool || '', meta: meta.filter(m => m[1]), sections, equations: eqs, figure: fig ? fig.outerHTML : '' };
}

// ---------------------------------------------------------------- PDF (browser print)
function reportHtml(r) {
  const defs = [...document.querySelectorAll('body > svg')].map(s => s.outerHTML).join('');
  const styles = [...document.querySelectorAll('head style')].map(s => s.outerHTML).join('');
  const isN = v => /^[−-]?[\d.,]+$/.test(String(v).trim());
  const sec = s => {
    // A column is right-aligned when most of its filled cells are numbers.
    const num = s.columns.map((c, i) => {
      if (!i) return false;
      const vals = s.rows.filter(r => !r.group).map(r => r[i]).filter(v => v && v !== '—');
      return vals.length > 0 && vals.filter(isN).length >= vals.length / 2;
    });
    return `<section><h2>${esc(s.title)}</h2><table><thead><tr>${s.columns.map((c, i) => `<th${num[i] ? ' class="n"' : ''}>${esc(c)}</th>`).join('')}</tr></thead><tbody>${
      s.rows.map(row => row.group ? `<tr class="g"><td colspan="${s.columns.length}">${esc(row.group)}</td></tr>`
        : `<tr>${row.map((v, i) => `<td${num[i] ? ' class="n"' : ''}>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></section>`;
  };
  return `<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8"><title>${esc(r.title)}</title>
<link rel="stylesheet" href="${location.origin}/static/app.css">${styles}
<style>
  @page { size: A4; margin: 14mm 12mm; }
  html, body { background: #fff !important; color: #1d2731; }
  body { font: 10.5pt/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; padding: 0; }
  .doc { max-width: 186mm; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #0b6e8a; padding-bottom: 6px; margin-bottom: 10px; }
  header .brand { font-weight: 700; color: #0b6e8a; font-size: 11pt; }
  h1 { font-size: 16pt; margin: 0; }
  h2 { font-size: 11.5pt; margin: 14px 0 4px; color: #0b6e8a; break-after: avoid; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px; margin: 0 0 6px; }
  dt { font-weight: 600; } dd { margin: 0; }
  table { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
  th, td { text-align: left; padding: 3px 6px; border-bottom: 1px solid #dfe5ea; vertical-align: top; }
  th { background: #e7f1fb; font-weight: 600; }
  .n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  tr.g td { font-weight: 600; background: #f3f5f7; }
  tr { break-inside: avoid; }
  figure { margin: 6px 0; break-inside: avoid; } figure svg { width: 100%; max-height: 110mm; }
  ul.eqs { margin: 0; padding-left: 18px; font-size: 9.5pt; }
  footer { margin-top: 14px; font-size: 8.5pt; color: #6b7785; border-top: 1px solid #dfe5ea; padding-top: 4px; }
</style></head><body>${defs}<div class="doc">
<header><div><div class="brand">Strainforge</div><h1>${esc(r.title)}</h1></div><div class="small">${esc(r.meta[0] ? r.meta[0][1] : '')}</div></header>
<dl>${r.meta.slice(1).map(m => `<dt>${esc(m[0])}</dt><dd>${esc(m[1])}</dd>`).join('')}</dl>
${r.figure ? `<section><h2>Drawing</h2><figure>${r.figure}</figure></section>` : ''}
${r.sections.map(sec).join('')}
${r.equations.length ? `<section><h2>Equations</h2><ul class="eqs">${r.equations.map(e => `<li>${esc(e[0])}</li>`).join('')}</ul></section>` : ''}
<footer>Generated with Strainforge (${esc(location.origin)}). Results are estimates for tool design; confirm critical steps with simulation or trials.</footer>
</div></body></html>`;
}
function printPdf() {
  const r = collect();
  const old = document.getElementById('reportFrame');
  if (old) old.remove();
  const f = document.createElement('iframe');
  f.id = 'reportFrame';
  f.setAttribute('aria-hidden', 'true');
  f.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden';
  document.body.appendChild(f);
  const d = f.contentDocument;
  d.open(); d.write(reportHtml(r)); d.close();
  const go = () => { try { f.contentWindow.focus(); f.contentWindow.print(); } catch (e) { alert('Your browser blocked printing. Try again, or use Excel.'); } };
  const link = d.querySelector('link[rel=stylesheet]');
  if (link && !link.sheet) { link.addEventListener('load', go, { once: true }); link.addEventListener('error', go, { once: true }); } else setTimeout(go, 50);
}

// ---------------------------------------------------------------- Excel
async function downloadXlsx(btn) {
  const r = collect();
  const body = { title: r.title, meta: r.meta, sections: r.sections.concat(r.equations.length ? [{ title: 'Equations', columns: [], rows: r.equations }] : []) };
  btn.disabled = true;
  try {
    const res = await fetch('/api/report.xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!res.ok) { let m = 'Could not build the report'; try { m = (await res.json()).error || m; } catch (e) { /* not json */ } throw new Error(m); }
    const blob = await res.blob();
    const name = ((res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/) || [])[1] || 'strainforge-report.xlsx';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (e) { alert(e.message); } finally { btn.disabled = false; }
}

const pdf = $('btnPdf'), xlsx = $('btnXlsx');
if (pdf) pdf.addEventListener('click', printPdf);
if (xlsx) xlsx.addEventListener('click', () => downloadXlsx(xlsx));
window.SFReport = { collect };
})();
