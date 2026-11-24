/* PDF and Excel reports. The server builds both from the inputs, in the viewer's units:
   - on the calculator and tool pages, for what the page shows now (Download PDF, Download Excel, Print);
   - on the history page, for several saved results at once (window.SFReport.batch).
   The page supplies its inputs through window.SFReportSource(). */
(function () {
'use strict';
const $ = id => document.getElementById(id);

function today() {
  return new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}
function units() { return window.SFUnits ? window.SFUnits.system : 'metric'; }

async function fetchFile(url, body) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ units: units(), date: today() }, body)) });
  if (!res.ok) {
    let m = 'Could not build the report';
    try { m = (await res.json()).error || m; } catch (e) { /* not json */ }
    throw new Error(m);
  }
  const blob = await res.blob();
  const name = ((res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/) || [])[1] || 'strainforge-report';
  return { blob, name };
}

function save(file) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(file.blob);
  a.download = file.name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function printPdf(file) {
  const url = URL.createObjectURL(new Blob([file.blob], { type: 'application/pdf' }));
  const old = $('reportFrame');
  if (old) old.remove();
  const f = document.createElement('iframe');
  f.id = 'reportFrame';
  f.setAttribute('aria-hidden', 'true');
  f.style.cssText = 'position:fixed;right:0;bottom:0;width:1px;height:1px;border:0;opacity:0';
  f.onload = () => {
    setTimeout(() => {
      try { f.contentWindow.focus(); f.contentWindow.print(); }
      catch (e) { window.open(url, '_blank'); }  // some browsers won't print a PDF from a frame: open it instead
    }, 250);
  };
  f.src = url;
  document.body.appendChild(f);
  setTimeout(() => URL.revokeObjectURL(url), 120000);
}

async function busy(btn, text, work) {
  const label = btn.dataset.label || btn.textContent;
  btn.disabled = true; btn.textContent = text;
  try { await work(); }
  catch (e) { alert(e.message || 'Could not build the report'); }
  finally { btn.disabled = false; btn.textContent = label; }
}

// ---------------------------------------------------------------- calculator and tool pages
const box = $('reportPanel');
if (box && box.dataset.allowed === '1') {
  const body = format => {
    const src = window.SFReportSource ? window.SFReportSource() : null;
    if (!src) throw new Error('Wait for the results, then try again');
    return Object.assign({ format, title: src.title || box.dataset.title || '' }, src);
  };
  const pdf = $('btnPdf'), xlsx = $('btnXlsx'), prn = $('btnPrint');
  if (pdf) pdf.addEventListener('click', () => busy(pdf, 'Preparing…', async () => save(await fetchFile('/api/report', body('pdf')))));
  if (xlsx) xlsx.addEventListener('click', () => busy(xlsx, 'Preparing…', async () => save(await fetchFile('/api/report', body('xlsx')))));
  if (prn) prn.addEventListener('click', () => busy(prn, 'Preparing…', async () => printPdf(await fetchFile('/api/report', Object.assign(body('pdf'), { inline: true })))));
}

window.SFReport = {
  /** Several saved results: PDFs (a zip when there are more than one) or one Excel workbook. */
  batch(ids, format, btn, text) {
    return busy(btn, text || 'Preparing…', async () => save(await fetchFile('/api/reports/batch', { ids, format })));
  },
};
})();
