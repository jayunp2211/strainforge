/* Strainforge units: every calculation runs and is saved in metric. This script only
   changes what people see and type. The choice is kept per browser. */
(function () {
'use strict';
// metric unit -> imperial unit, factor (imperial = metric × f)
const IMP = {
  'mm': ['in', 1 / 25.4],
  'mm²': ['in²', 1 / 645.16],
  'mm³': ['in³', 1 / 16387.064],
  'N/mm²': ['ksi', 0.1450377377],
  'Nmm/mm³': ['in·kip/in³', 0.1450377377],
  'kN': ['tonf', 1 / 8.896443230521],
  'N': ['lbf', 1 / 4.4482216152605],
  'N/mm': ['lbf/in', 25.4 / 4.4482216152605],
  'kJ': ['ft·lbf', 737.5621493],
};
const KEY = 'sf-units';
const IMPERIAL_LOCALES = /^(en-US|en-LR|my)\b/i;
let sys;
try { sys = localStorage.getItem(KEY); } catch (e) { sys = null; }
if (sys !== 'metric' && sys !== 'imperial') sys = IMPERIAL_LOCALES.test(navigator.language || '') ? 'imperial' : 'metric';

const imp = () => sys === 'imperial';
const conv = u => (imp() && IMP[u]) || null;

const U = {
  get system() { return sys; },
  set(next) {
    if (next !== 'metric' && next !== 'imperial' || next === sys) return;
    sys = next;
    try { localStorage.setItem(KEY, sys); } catch (e) { /* private window: keep for this page only */ }
    syncToggles();
    U.apply(document);
    window.dispatchEvent(new CustomEvent('sf-units', { detail: sys }));
  },
  /** Unit label to show for a metric unit. */
  unit(u) { const c = conv(u); return c ? c[0] : (u || ''); },
  /** Metric value -> value to show. */
  out(v, u) { const c = conv(u); return c && typeof v === 'number' && isFinite(v) ? v * c[1] : v; },
  /** Value typed by the person -> metric value to store. */
  in(v, u) { const c = conv(u); return c && typeof v === 'number' && isFinite(v) ? v / c[1] : v; },
  /** Rewrite "12.50 mm" style text (check descriptions and limits) in the chosen system. */
  text(s) {
    if (!imp() || typeof s !== 'string') return s;
    return s.replace(/(-?\d[\d,]*(?:\.\d+)?)\s?(mm³|mm²|mm|kN|kJ|N\/mm²|N\/mm|N)(?![\w²³/])/g, (m, num, u) => {
      const v = U.out(parseFloat(num.replace(/,/g, '')), u);
      return U.num(v) + ' ' + U.unit(u);
    });
  },
  /** Plain number formatting with sensible decimals. */
  num(v, d) {
    if (typeof v !== 'number' || !isFinite(v)) return '—';
    if (d === undefined) { const a = Math.abs(v); d = a >= 1000 ? 1 : a >= 100 ? 2 : a >= 1 ? 3 : 4; if (v === 0) d = 0; }
    return v.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
  },
  /** Fill server-rendered quantities: <span data-qty="554.07" data-unit="kN" data-d="1">. */
  apply(root) {
    (root || document).querySelectorAll('[data-qty]').forEach(el => {
      const v = parseFloat(el.dataset.qty), u = el.dataset.unit;
      if (!isFinite(v)) return;
      let d = el.dataset.d === undefined ? undefined : +el.dataset.d;
      if (conv(u)) d = undefined; // converted values pick their own decimals
      el.textContent = U.num(U.out(v, u), d);
    });
    (root || document).querySelectorAll('[data-unit-label]').forEach(el => { el.textContent = U.unit(el.dataset.unitLabel); });
    (root || document).querySelectorAll('[data-units-text]').forEach(el => {
      el.textContent = imp() ? el.dataset.imperial : el.dataset.metric;
    });
  },
};

function syncToggles() {
  document.querySelectorAll('[data-units]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.units === sys)));
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-units]');
  if (b) U.set(b.dataset.units);
});
window.SFUnits = U;
function start() { syncToggles(); U.apply(document); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
