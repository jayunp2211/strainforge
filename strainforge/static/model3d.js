// 3D view of the blank (before) and the formed part (after), drawn to the entered dimensions.
// Parts are mostly round, so each one is a lathe profile [radius, height] revolved around the axis;
// trimmed hexagon and square heads are extruded polygons. Lengths the calculator doesn't ask for
// (shank length, blank height, cut length) are derived from volume constancy or a sensible default.
import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';

const PI = Math.PI;
const pos = (v, d) => (typeof v === 'number' && isFinite(v) && v > 0 ? v : d);

// ---- profile helpers (r, y) ------------------------------------------------
// sections: [[rBottom, rTop, height], ...] stacked from y0 upward. Returns a closed lathe profile.
function stack(sections, y0 = 0) {
  const pts = [[0, y0]];
  let y = y0;
  for (const [rb, rt, h] of sections) {
    if (!(h > 0)) continue;
    pts.push([rb, y]);
    y += h;
    pts.push([rt, y]);
  }
  pts.push([0, y]);
  return { pts, h: y - y0 };
}
const cyl = (d, h) => [d / 2, d / 2, h];
const cone = (d1, d2, h) => [d1 / 2, d2 / 2, h];
const vol = sections => sections.reduce((a, [rb, rt, h]) => a + (h > 0 ? PI * h / 3 * (rb * rb + rb * rt + rt * rt) : 0), 0);
// Curved (barrel / dome) section approximated by n slices along r(t), t in 0..1.
function curve(rf, h, n = 14) {
  const out = [];
  for (let i = 0; i < n; i++) out.push([rf(i / n), rf((i + 1) / n), h / n]);
  return out;
}
// Blank cylinder of diameter d holding the given volume.
const blankFor = (d, v) => [cyl(d, v / (PI * d * d / 4))];

// ---- the shapes ------------------------------------------------------------
// Each returns { before: Part[], after: Part[], notes: string[] }.
// Part = { sections } (revolved) or { prism: { sides, across, h }, below } or { hollow: pts }.
const SHAPES = {
  1(v) { // cut-off piece
    const d = pos(v.C49, 10), L = 2 * d;
    return { before: [{ sections: [cyl(d, 4 * d)] }], after: [{ sections: [cyl(d, L)] }],
      notes: ['Cut length isn’t an input, so the piece is shown 2 × D long.'] };
  },
  2(v, p) { return headed(v, 'flat', p); },
  3(v) { return headed(v, 'dome'); },
  4(v) { // cylinder -> trapezoid head on shank
    const d0 = pos(v.C49, 14), lf = pos(v.C54, 3 * d0);
    const head = [cone(pos(v.C50, d0 * 1.3), pos(v.C51, d0 * 1.15), pos(v.C53, d0 * 0.7))];
    return preform(d0, lf, head);
  },
  5(v) { // cylinder -> double trapezoid
    const d0 = pos(v.C49, 14), lf = pos(v.C57, 3 * d0);
    return preform(d0, lf, dblTrap(pos(v.C52, d0 * 1.05), pos(v.C50, d0 * 1.4), pos(v.C51, d0 * 1.15), pos(v.C54, d0), pos(v.C55, d0 * 0.3)));
  },
  6(v) { // cylinder -> spherical (barrel)
    const d0 = pos(v.C49, 14), lf = pos(v.C57, 3 * d0);
    return preform(d0, lf, barrel(pos(v.C52, d0 * 1.05), pos(v.C50, d0 * 1.4), pos(v.C51, d0 * 1.15), pos(v.C54, d0)));
  },
  7(v) { // trapezoid -> cylindrical shelf
    const dmax = pos(v.C49, 18), lf = pos(v.C55, 20), ds = pos(v.C57, 14);
    const pre = [cone(dmax, pos(v.C50, dmax * 0.9), pos(v.C52, 12))];
    return shelf(ds, lf, pre, pos(v.C53, 24), pos(v.C54, 3));
  },
  8(v) { // double trapezoid -> cylindrical shelf
    const du = pos(v.C51, 15), lf = pos(v.C58, 20);
    const pre = dblTrap(du, pos(v.C49, 20), pos(v.C50, 16), pos(v.C53, 14), pos(v.C54, 4));
    return shelf(du, lf, pre, pos(v.C55, 24), pos(v.C57, 3));
  },
  10(v) { // sphere -> cylindrical flat
    const du = pos(v.C51, 15), lf = pos(v.C58, 20);
    const pre = barrel(du, pos(v.C49, 20), pos(v.C50, 16), pos(v.C53, 14));
    return shelf(du, lf, pre, pos(v.C55, 24), pos(v.C57, 3));
  },
  11(v) { // reduction
    const d1 = pos(v.C49, 11), d2 = Math.min(pos(v.C50, d1 * 0.9), d1), a = pos(v.C51, 10);
    const s = pos(v.C52, 1.5 * d1), total = 4 * d1;
    const coneH = (d1 - d2) / 2 / Math.tan(Math.max(1, a) * PI / 180);
    const after = [cyl(d2, s), cone(d2, d1, coneH)];
    const vAfter = vol(after), upper = Math.max(total * PI * d1 * d1 / 4 - vAfter, d1) / (PI * d1 * d1 / 4);
    after.push(cyl(d1, upper));
    return { before: [{ sections: [cyl(d1, total)] }], after: [{ sections: after }],
      notes: [`Reduced length shown as ${v.C52 > 0 ? 'S' : '1.5 × D1 (S not entered)'}.`] };
  },
  12(v) { // forward (trap) extrusion
    const d1 = pos(v.C49, 14), d2 = Math.min(pos(v.C50, d1 * 0.7), d1), a = pos(v.C51, 12);
    const h0 = pos(v.C52, 2 * d1), s = Math.min(pos(v.C53, h0 * 0.6), h0 * 0.95);
    const coneH = (d1 - d2) / 2 / Math.tan(Math.max(1, a) * PI / 180);
    const lower = s * (d1 * d1) / (d2 * d2);
    return { before: [{ sections: [cyl(d1, h0)] }],
      after: [{ sections: [cyl(d2, lower), cone(d2, d1, coneH), cyl(d1, Math.max(h0 - s - coneH / 3, d1 * 0.2))] }], notes: [] };
  },
  13(v) { // backward extrusion (cup)
    const din = pos(v.C49, 15), dout = Math.max(pos(v.C50, 20), din * 1.1), h0 = pos(v.C52, 15), hb = pos(v.C53, 8);
    const v0 = PI * dout * dout / 4 * h0;
    const hc = hb + Math.max(v0 - PI * dout * dout / 4 * hb, 0) / (PI * (dout * dout - din * din) / 4);
    const ro = dout / 2, ri = din / 2;
    return { before: [{ sections: [cyl(dout, h0)] }],
      after: [{ hollow: [[0, 0], [ro, 0], [ro, hc], [ri, hc], [ri, hb], [0, hb]] }],
      notes: ['Cup height follows from the blank volume.'] };
  },
  14(v) { // piercing
    const h0 = pos(v.C48, 6), t = Math.min(pos(v.C49, 3), h0), d = pos(v.C50, 8), ro = d * 1.25, ri = d / 2;
    return { before: [{ hollow: [[0, 0], [ro, 0], [ro, h0], [ri, h0], [ri, t], [0, t]] }],
      after: [{ hollow: [[ri, 0], [ro, 0], [ro, h0], [ri, h0]] }, { sections: [cyl(d, t)], dy: -t - 4, dx: 0 }],
      notes: ['Outer diameter isn’t an input, so it is shown as 2.5 × d. The slug is shown below the part.'] };
  },
  15(v) { return trim(v, 6, pos(v.C51, 17)); },
  16(v) { return trim(v, 4, pos(v.C51, 14)); },
  17(v) { return trim(v, 0, pos(v.C51, 18)); },
};

function headed(v, kind, p) {
  const d0 = pos(v.C49, 14), d1 = pos(v.C50, 24), h1 = pos(v.C51, 2.2);
  const ds = p === 3 ? d0 : pos(v.C52, d0), shank = 2.5 * ds; // Open Upset uses C52 for Hs, not the shank
  const head = kind === 'dome' ? curve(t => Math.sqrt(Math.max(1 - t * t, 0)) * d1 / 2 || 0.01, h1) : [cyl(d1, h1)];
  const after = [cyl(ds, shank), ...head];
  return { before: [{ sections: blankFor(d0, vol(after)) }], after: [{ sections: after }],
    notes: ['Shank length isn’t an input, so it is shown 2.5 × its diameter; the blank holds the same volume.'] };
}
function dblTrap(dUnder, dMax, dAbove, htv, habove) {
  const ha = Math.min(habove, htv * 0.9);
  return [cone(dUnder, dMax, htv - ha), cone(dMax, dAbove, ha)];
}
function barrel(dUnder, dMax, dAbove, htv) {
  // smooth curve through dUnder (bottom), dMax (middle), dAbove (top)
  return curve(t => {
    const a = dUnder / 2, m = dMax / 2, b = dAbove / 2;
    return (1 - t) * (1 - t) * a + 2 * t * (1 - t) * (2 * m - (a + b) / 2) + t * t * b;
  }, htv, 16);
}
function preform(d0, lf, head) {
  const after = [cyl(d0, lf), ...head];
  return { before: [{ sections: blankFor(d0, vol(after)) }], after: [{ sections: after }], notes: [] };
}
function shelf(ds, lf, pre, d1, hk) {
  return { before: [{ sections: [cyl(ds, lf), ...pre] }], after: [{ sections: [cyl(ds, lf), cyl(d1, hk)] }], notes: [] };
}
function trim(v, sides, across) {
  const d0 = pos(v.C49, 20), h1 = pos(v.C50, 8), shank = d0 * 0.55, L = shank * 2.5;
  return { before: [{ sections: [cyl(shank, L), cyl(d0, h1)] }],
    after: [sides ? { sections: [cyl(shank, L)], prism: { sides, across, h: h1, y: L } } : { sections: [cyl(shank, L), cyl(Math.min(across, d0), h1)] }],
    notes: ['Shank diameter isn’t an input, so it is shown as 0.55 × D0.'] };
}

// ---- three.js scene ---------------------------------------------------------
function cssColor(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

export function mount(el) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  el.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(24, 1, 0.1, 5000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(3, 5, 4); scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.8); rim.position.set(-4, 2, -3); scene.add(rim);
  const group = new THREE.Group(); scene.add(group);
  const steel = new THREE.MeshStandardMaterial({ color: 0xc3ccd5, metalness: 0.35, roughness: 0.42, side: THREE.DoubleSide });
  const formed = new THREE.MeshStandardMaterial({ color: 0x7fa9c8, metalness: 0.35, roughness: 0.4, side: THREE.DoubleSide });
  let raf = 0, visible = true;

  function size() {
    const w = el.clientWidth || 300, h = el.clientHeight || 260;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%';
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  new ResizeObserver(size).observe(el);
  new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) loop(); }).observe(el);
  function loop() {
    cancelAnimationFrame(raf);
    if (!visible || !el.isConnected) return;
    controls.update(); renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }

  function build(part, mat) {
    const g = new THREE.Group();
    if (part.sections) {
      const { pts } = stack(part.sections);
      g.add(new THREE.Mesh(new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(Math.max(r, 0.001), y)), 72), mat));
    }
    if (part.hollow) {
      g.add(new THREE.Mesh(new THREE.LatheGeometry(part.hollow.map(([r, y]) => new THREE.Vector2(Math.max(r, 0.001), y)), 72), mat));
    }
    if (part.prism) {
      const { sides, across, h, y } = part.prism;
      const R = across / 2 / Math.cos(PI / sides); // across flats -> corner radius
      const geo = new THREE.CylinderGeometry(R, R, h, sides, 1, false, PI / sides);
      const m = new THREE.Mesh(geo, mat); m.position.y = y + h / 2; g.add(m);
    }
    g.position.set(part.dx || 0, part.dy || 0, 0);
    return g;
  }

  let lastSig = '';
  function update(shape, vals, proc, cell = 10) {
    const f = SHAPES[shape];
    if (!f) return [];
    const sig = proc + '/' + shape + '/' + cell + JSON.stringify(vals);
    const model = f(vals, proc);
    if (sig === lastSig) return model.notes;
    lastSig = sig;
    group.clear();
    const before = new THREE.Group(), after = new THREE.Group();
    model.before.forEach(p => before.add(build(p, steel)));
    model.after.forEach(p => after.add(build(p, formed)));
    const bb = new THREE.Box3().setFromObject(before), ba = new THREE.Box3().setFromObject(after);
    const wb = bb.max.x - bb.min.x, wa = ba.max.x - ba.min.x, gap = Math.max(wb, wa) * 0.6 + 4;
    before.position.x = -(wa / 2 + gap / 2); after.position.x = wb / 2 + gap / 2;
    before.position.y -= bb.min.y; after.position.y -= ba.min.y;
    group.add(before, after);
    // floor grid for scale: `cell` mm squares (10 mm, or 12.7 mm = ½ in)
    const span = Math.ceil((Math.max(wb + wa + gap, 30) * 1.4) / (2 * cell)) * 2 * cell;
    const grid = new THREE.GridHelper(span, Math.round(span / cell), 0x9aa8b5, 0xd5dde4);
    grid.position.y = -0.01; group.add(grid);
    // frame both parts
    const box = new THREE.Box3().setFromObject(before).union(new THREE.Box3().setFromObject(after)), c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
    const r = Math.max(s.x * 0.62, s.y * 0.75, s.z);
    const dist = r / Math.sin((camera.fov * PI / 180) / 2);
    controls.target.copy(c);
    camera.position.set(c.x + dist * 0.25, c.y + dist * 0.32, c.z + dist * 0.92);
    camera.near = dist / 100; camera.far = dist * 10; camera.updateProjectionMatrix();
    size(); loop();
    return model.notes;
  }
  size();
  return { update };
}
