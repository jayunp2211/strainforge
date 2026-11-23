"""Vector tooling diagrams (cross-sections and before/after product shapes).

Every drawing is plain SVG styled through CSS classes so it follows the
page theme:  .tl tool steel (hatched)  .wp workpiece  .wp2 formed zone
.dm dimension  .cl centre line  .mv motion arrow  .tx label text
"""
from __future__ import annotations

import math

W, H = 420, 300


class Sk:
    def __init__(self, w=W, h=H):
        self.w, self.h, self.p = w, h, []

    # ---- primitives -------------------------------------------------
    def rect(self, x, y, w, h, cls="tl", rx=0):
        self.p.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}"/>')
        return self

    def poly(self, pts, cls="tl"):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.p.append(f'<polygon class="{cls}" points="{d}"/>')
        return self

    def path(self, d, cls="tl"):
        self.p.append(f'<path class="{cls}" d="{d}"/>')
        return self

    def line(self, x1, y1, x2, y2, cls="ln"):
        self.p.append(f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        return self

    def text(self, x, y, s, anchor="middle", cls="tx"):
        self.p.append(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{s}</text>')
        return self

    def cl(self, x, y1, y2):
        return self.line(x, y1, x, y2, "cl")

    def hcl(self, y, x1, x2):
        return self.line(x1, y, x2, y, "cl")

    # ---- dimensions -------------------------------------------------
    def hdim(self, x1, x2, y, label, ext_from=None, above=True):
        if ext_from is not None:
            self.line(x1, ext_from, x1, y + (-4 if y < ext_from else 4), "dx")
            self.line(x2, ext_from, x2, y + (-4 if y < ext_from else 4), "dx")
        self.line(x1, y, x2, y, "dm")
        self._arrow(x1, y, 1, 0)
        self._arrow(x2, y, -1, 0)
        self.text((x1 + x2) / 2, y - 5 if above else y + 13, label, cls="dt")
        return self

    def vdim(self, y1, y2, x, label, ext_from=None, side="right"):
        if ext_from is not None:
            self.line(ext_from, y1, x + (4 if x > ext_from else -4), y1, "dx")
            self.line(ext_from, y2, x + (4 if x > ext_from else -4), y2, "dx")
        self.line(x, y1, x, y2, "dm")
        self._arrow(x, y1, 0, 1)
        self._arrow(x, y2, 0, -1)
        tx = x + 6 if side == "right" else x - 6
        self.text(tx, (y1 + y2) / 2 + 4, label, anchor="start" if side == "right" else "end", cls="dt")
        return self

    def _arrow(self, x, y, dx, dy, s=6):
        if dx:
            pts = [(x, y), (x + dx * s, y - s * 0.4), (x + dx * s, y + s * 0.4)]
        else:
            pts = [(x, y), (x - s * 0.4, y + dy * s), (x + s * 0.4, y + dy * s)]
        self.poly(pts, "ah")

    def move(self, x, y1, y2, label=""):
        self.line(x, y1, x, y2, "mv")
        d = 1 if y2 > y1 else -1
        self.poly([(x, y2), (x - 6, y2 - d * 10), (x + 6, y2 - d * 10)], "mvh")
        if label:
            self.text(x + 10, (y1 + y2) / 2, label, anchor="start", cls="mt")
        return self

    def hmove(self, y, x1, x2, label=""):
        self.line(x1, y, x2, y, "mv")
        d = 1 if x2 > x1 else -1
        self.poly([(x2, y), (x2 - d * 10, y - 6), (x2 - d * 10, y + 6)], "mvh")
        if label:
            self.text((x1 + x2) / 2, y - 9, label, cls="mt")
        return self

    def arrow_between(self, x1, x2, y):
        self.line(x1, y, x2 - 10, y, "fa")
        self.poly([(x2, y), (x2 - 12, y - 6), (x2 - 12, y + 6)], "fah")
        return self

    def svg(self, title):
        body = "".join(self.p)
        return (f'<svg class="dwg" viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{title}" '
                f'xmlns="http://www.w3.org/2000/svg"><title>{title}</title>{body}</svg>')


# -------------------------------------------------------------------------
# helpers for symmetric parts (centre line at cx)
def body(sk, cx, profile, cls="wp"):
    """profile: list of (half_width, y) from top to bottom; mirrored around cx."""
    right = [(cx + w, y) for w, y in profile]
    left = [(cx - w, y) for w, y in reversed(profile)]
    sk.poly(right + left, cls)


def round_head_path(cx, top, r_head, h_head, r_stem, bottom, crown=True):
    """Mushroom/spherical head on a stem."""
    if crown:
        d = (f"M{cx - r_stem},{bottom} L{cx - r_stem},{top + h_head} L{cx - r_head},{top + h_head} "
             f"Q{cx - r_head},{top} {cx},{top} Q{cx + r_head},{top} {cx + r_head},{top + h_head} "
             f"L{cx + r_stem},{top + h_head} L{cx + r_stem},{bottom} Z")
    return d


# -------------------------------------------------------------------------
# PROCESS cross-sections
def proc_cut_off():
    s = Sk()
    y0, D = 130, 44
    s.rect(40, y0 - 70, 150, 70 - D / 2).rect(40, y0 + D / 2, 150, 80)          # quill (stationary)
    s.rect(196, y0 - 90, 90, 90 - D / 2 - 0, "tl2")                             # moving knife top
    s.rect(196, y0 + D / 2, 90, 40, "tl2")
    s.rect(70, y0 - D / 2, 210, D, "wp")
    s.rect(196, y0 - D / 2, 84, D, "wp2")
    s.line(193, y0 - 80, 193, y0 + 90, "cut")
    s.hcl(y0, 20, 300)
    s.vdim(y0 - D / 2, y0 + D / 2, 320, "D", ext_from=282)
    s.hmove(y0 + 95, 230, 290, "knife")
    s.move(240, y0 - 112, y0 - 92)
    s.text(115, y0 + 118, "stationary quill").text(242, y0 + 118, "cut-off piece")
    return s.svg("Cut off")


def _die_with_bore(s, cx, top, bottom, r_bore, outer=150):
    s.rect(cx - outer, top, outer - r_bore, bottom - top)
    s.rect(cx + r_bore, top, outer - r_bore, bottom - top)


def proc_closed_upset():
    s = Sk()
    cx, dtop = 210, 175
    r0, r1, h1 = 22, 62, 30
    _die_with_bore(s, cx, dtop, 285, r0)
    s.poly([(cx - 150, 40), (cx + 150, 40), (cx + 150, dtop), (cx + r1, dtop), (cx + r1, dtop - h1),
            (cx - r1, dtop - h1), (cx - r1, dtop), (cx - 150, dtop)], "tl2")  # punch with head cavity
    s.rect(cx - r0, dtop, 2 * r0, 110, "wp")
    s.rect(cx - r1, dtop - h1, 2 * r1, h1, "wp2")
    s.cl(cx, 30, 290)
    s.hdim(cx - r0, cx + r0, 270, "d0")
    s.hdim(cx - r1, cx + r1, dtop - h1 - 16, "D1 / d1")
    s.vdim(dtop - h1, dtop, cx + r1 + 30, "H1 / h1")
    s.move(cx - 110, 12, 34, "")
    s.text(cx - 96, 26, "punch", anchor="start", cls="mt")
    s.text(cx + 105, 230, "die", cls="mt")
    return s.svg("Closed upset")


def proc_open_upset():
    s = Sk()
    cx, dtop = 210, 175
    r0, r1, h1 = 22, 70, 28
    _die_with_bore(s, cx, dtop, 285, r0)
    s.rect(cx - 150, 60, 300, dtop - h1 - 60, "tl2")
    s.rect(cx - r0, dtop, 2 * r0, 110, "wp")
    s.path(f"M{cx - r1 + 8},{dtop - h1} L{cx + r1 - 8},{dtop - h1} Q{cx + r1 + 4},{dtop - h1 / 2} {cx + r1 - 8},{dtop} "
           f"L{cx - r1 + 8},{dtop} Q{cx - r1 - 4},{dtop - h1 / 2} {cx - r1 + 8},{dtop - h1} Z", "wp2")
    s.cl(cx, 40, 290)
    s.hdim(cx - r0, cx + r0, 270, "d0")
    s.hdim(cx - r1, cx + r1, 48, "D1 / d1", ext_from=dtop - h1)
    s.vdim(dtop - h1, dtop, cx + r1 + 30, "h1", ext_from=cx + r1)
    s.vdim(dtop - h1 / 2, dtop, cx - r1 - 26, "h/2", ext_from=cx - r1, side="left")
    s.text(cx + 105, 230, "die", cls="mt").text(cx, 90, "flat punch", cls="mt")
    return s.svg("Open upset")


def proc_setting():
    s = Sk()
    cx, dtop = 210, 190
    r0 = 20
    _die_with_bore(s, cx, dtop, 290, r0)
    # punch with conical cavity
    s.poly([(cx - 150, 30), (cx + 150, 30), (cx + 150, dtop - 70), (cx + 30, dtop - 70), (cx + 22, dtop - 4),
            (cx - 22, dtop - 4), (cx - 30, dtop - 70), (cx - 150, dtop - 70)], "tl2")
    s.poly([(cx - 30, dtop - 70), (cx + 30, dtop - 70), (cx + 38, dtop - 4), (cx - 38, dtop - 4)], "wp2")
    s.rect(cx - r0, dtop - 4, 2 * r0, 104, "wp")
    s.rect(cx - 150, dtop - 4, 150 - 38, 4, "tl2").rect(cx + 38, dtop - 4, 112, 4, "tl2")
    s.cl(cx, 20, 295)
    s.hdim(cx - r0, cx + r0, 275, "D0")
    s.hdim(cx - 38, cx + 38, dtop - 22, "D1 max")
    s.hdim(cx - 30, cx + 30, dtop - 84, "D1 min top")
    s.vdim(dtop - 70, dtop - 4, cx + 62, "Htv", ext_from=cx + 38)
    s.text(cx - 100, 80, "preform punch", cls="mt")
    return s.svg("Setting to perform")


def proc_pre_upset():
    s = Sk()
    cx, dtop = 210, 190
    r0, r1, h = 18, 64, 30
    _die_with_bore(s, cx, dtop, 290, r0)
    s.rect(cx - 150, 40, 300, dtop - h - 40, "tl2")
    s.rect(cx - r0, dtop, 2 * r0, 100, "wp")
    s.rect(cx - r1, dtop - h, 2 * r1, h, "wp2", rx=6)
    # ghost of the preform
    s.poly([(cx - 26, dtop - h - 42), (cx + 26, dtop - h - 42), (cx + 34, dtop - h), (cx - 34, dtop - h)], "ghost")
    s.cl(cx, 30, 295)
    s.hdim(cx - r0, cx + r0, 275, "d")
    s.hdim(cx - r1, cx + r1, dtop - h / 2 + 4, "D1")
    s.vdim(dtop - h, dtop, cx + r1 + 26, "Hk")
    s.text(cx, 30, "dashed: preform from the previous station", cls="mt")
    return s.svg("Pre-upsetting form")


def proc_reduction():
    s = Sk()
    cx = 210
    r1, r2, cone_top, cone_bot = 34, 26, 150, 172
    s.poly([(cx - 150, 110), (cx - r1, 110), (cx - r1, cone_top), (cx - r2, cone_bot), (cx - r2, 290), (cx - 150, 290)])
    s.poly([(cx + 150, 110), (cx + r1, 110), (cx + r1, cone_top), (cx + r2, cone_bot), (cx + r2, 290), (cx + 150, 290)])
    s.rect(cx - r1, 50, 2 * r1, 100, "wp")
    s.poly([(cx - r1, cone_top), (cx + r1, cone_top), (cx + r2, cone_bot), (cx - r2, cone_bot)], "wp2")
    s.rect(cx - r2, cone_bot, 2 * r2, 80, "wp2")
    s.rect(cx - r1 - 4, 14, 2 * r1 + 8, 36, "tl2")
    s.cl(cx, 8, 296)
    s.hdim(cx - r1, cx + r1, 96, "D1", ext_from=110)
    s.hdim(cx - r2, cx + r2, 278, "D2")
    s.vdim(50, cone_top, cx - r1 - 40, "LK", ext_from=cx - r1, side="left")
    a = math.degrees(math.atan((r1 - r2) / (cone_bot - cone_top)))
    s.path(f"M{cx + r1 + 30},{cone_top} A 40 40 0 0 1 {cx + r2 + 30 - 4},{cone_bot + 6}", "dm")
    s.text(cx + r1 + 44, cone_top + 20, "α", anchor="start", cls="dt")
    s.move(cx + 80, 18, 52, "S")
    return s.svg("Reduction")


def proc_trap():
    s = Sk()
    cx = 210
    r1, r2, ct, cb = 40, 24, 150, 182
    s.poly([(cx - 150, 60), (cx - r1, 60), (cx - r1, ct), (cx - r2, cb), (cx - r2, 290), (cx - 150, 290)])
    s.poly([(cx + 150, 60), (cx + r1, 60), (cx + r1, ct), (cx + r2, cb), (cx + r2, 290), (cx + 150, 290)])
    s.rect(cx - r1, 92, 2 * r1, ct - 92, "wp")
    s.poly([(cx - r1, ct), (cx + r1, ct), (cx + r2, cb), (cx - r2, cb)], "wp2")
    s.rect(cx - r2, cb, 2 * r2, 70, "wp2")
    s.rect(cx - r1 + 2, 30, 2 * r1 - 4, 62, "tl2")
    s.cl(cx, 20, 296)
    s.hdim(cx - r1, cx + r1, 112, "d1", above=False)
    s.hdim(cx - r2, cx + r2, 272, "d2")
    s.vdim(92, ct, cx - r1 - 34, "H0", ext_from=cx - r1, side="left")
    s.text(cx + r1 + 12, ct + 26, "α", anchor="start", cls="dt")
    s.move(cx + 70, 24, 56, "S")
    s.text(cx - 100, 40, "closed die", cls="mt")
    return s.svg("Trap extrusion")


def proc_backward():
    s = Sk()
    cx = 210
    r_die, r_p, bottom = 66, 46, 250
    s.rect(cx - 170, 70, 170 - r_die, 220).rect(cx + r_die, 70, 170 - r_die, 220).rect(cx - r_die, bottom, 2 * r_die, 40)
    # cup
    s.path(f"M{cx - r_die},{bottom} L{cx - r_die},{96} L{cx - r_p},{96} L{cx - r_p},{bottom - 34} "
           f"L{cx + r_p},{bottom - 34} L{cx + r_p},{96} L{cx + r_die},{96} L{cx + r_die},{bottom} Z", "wp2")
    s.poly([(cx - r_p, 20), (cx + r_p, 20), (cx + r_p, bottom - 40), (cx + r_p - 10, bottom - 34),
            (cx - r_p + 10, bottom - 34), (cx - r_p, bottom - 40)], "tl2")
    s.cl(cx, 10, 296)
    s.hdim(cx - r_p, cx + r_p, 60, "d1 (punch)")
    s.hdim(cx - r_die, cx + r_die, 284, "d2 (die)", above=True)
    s.vdim(bottom - 34, bottom, cx + r_die + 30, "H1", ext_from=cx + r_die)
    s.vdim(96, bottom, cx - r_die - 30, "H0", ext_from=cx - r_die, side="left")
    s.move(cx + 110, 20, 54, "S")
    return s.svg("Backward extrusion")


def proc_piercing():
    s = Sk()
    cx = 210
    rd, T = 26, 22
    s.rect(cx - 160, 150, 160 - 70, 140).rect(cx + 70, 150, 90, 140)
    s.path(f"M{cx - 70},{150} L{cx - 70},{110} L{cx - rd},{110} L{cx - rd},{110 + T} L{cx + rd},{110 + T} "
           f"L{cx + rd},{110} L{cx + 70},{110} L{cx + 70},{150} Z", "wp")
    s.rect(cx - rd, 110, 2 * rd, T, "wp2")
    s.rect(cx - rd, 30, 2 * rd, 78, "tl2")
    s.rect(cx - rd + 2, 150, 2 * rd - 4, 140, "tl")
    s.cl(cx, 20, 296)
    s.hdim(cx - rd, cx + rd, 22, "d")
    s.vdim(110, 110 + T, cx + 100, "T", ext_from=cx + 70)
    s.vdim(110, 150, cx - 100, "H0", ext_from=cx - 70, side="left")
    s.text(cx + 90, 70, "piercing punch", anchor="start", cls="mt")
    return s.svg("Piercing")


def proc_trimming():
    s = Sk()
    cx = 210
    r0, rs, h = 76, 48, 26
    s.rect(cx - 170, 150, 170 - rs, 140).rect(cx + rs, 150, 170 - rs, 140)
    s.rect(cx - r0, 150 - h, 2 * r0, h, "wp")
    s.rect(cx - rs, 150 - h, 2 * rs, h, "wp2")
    s.rect(cx - 30, 150, 60, 140, "wp")
    s.rect(cx - 150, 40, 300, 150 - h - 40 - 2, "tl2")
    s.line(cx - rs, 120, cx - rs, 160, "cut").line(cx + rs, 120, cx + rs, 160, "cut")
    s.cl(cx, 30, 296)
    s.hdim(cx - r0, cx + r0, 112, "D0", ext_from=150 - h)
    s.hdim(cx - rs, cx + rs, 170, "SW / Z / D1", above=False)
    s.vdim(150 - h, 150, cx + r0 + 26, "H1", ext_from=cx + r0)
    s.text(cx - 125, 270, "trimming die", anchor="start", cls="mt")
    return s.svg("Trimming")


# -------------------------------------------------------------------------
# PRODUCT shapes: start part  →  end part
def _two(title, draw_a, draw_b, ya=None):
    s = Sk()
    draw_a(s, 110)
    s.arrow_between(180, 236, 150)
    draw_b(s, 318)
    return s.svg(title)


def _cyl(s, cx, r, top, bottom, label="D0", cls="wp", dim_y=None):
    s.rect(cx - r, top, 2 * r, bottom - top, cls, rx=3)
    s.cl(cx, top - 10, bottom + 10)
    s.hdim(cx - r, cx + r, dim_y if dim_y else top - 14, label, ext_from=top)


def _head_part(s, cx, r_head, h_head, r_stem, top=90, stem_len=150, shape="flat", labels=("D1", "H1", "d steel")):
    bottom = top + h_head + stem_len
    s.rect(cx - r_stem, top + h_head, 2 * r_stem, stem_len, "wp")
    if shape == "flat":
        s.rect(cx - r_head, top, 2 * r_head, h_head, "wp2", rx=4)
    elif shape == "mushroom":
        s.path(f"M{cx - r_head},{top + h_head} Q{cx - r_head},{top} {cx},{top} Q{cx + r_head},{top} {cx + r_head},{top + h_head} Z", "wp2")
    s.cl(cx, top - 10, bottom + 10)
    s.hdim(cx - r_head, cx + r_head, top - 14, labels[0], ext_from=top + (h_head if shape != "flat" else 0))
    s.vdim(top, top + h_head, cx + r_head + 16, labels[1], ext_from=cx + r_head)
    if labels[2]:
        s.hdim(cx - r_stem, cx + r_stem, bottom + 16, labels[2], above=False)


def shape_cutoff():
    s = Sk()
    s.rect(60, 120, 300, 60, "wp", rx=2)
    s.path("M360,120 L372,120 Q380,150 368,180 L360,180 Z", "wp2")
    s.hcl(150, 40, 390)
    s.vdim(120, 180, 40, "D", ext_from=60, side="left")
    s.hdim(60, 372, 104, "cut length", ext_from=120)
    s.text(210, 220, "Wire cut to length (sheared end on the right)", cls="mt")
    return s.svg("Cut-off piece")


def shape_cyl_flat():
    def a(s, cx):
        _cyl(s, cx, 26, 80, 250, "D0")
        s.vdim(80, 250, cx - 44, "H0", ext_from=cx - 26, side="left")

    def b(s, cx):
        _head_part(s, cx, 56, 32, 26, top=120, stem_len=100, labels=("D1", "H1", "d steel"))
    return _two("Cylindrical to cylindrical flat", a, b)


def shape_mushroom():
    def a(s, cx):
        _cyl(s, cx, 26, 80, 250, "D0")

    def b(s, cx):
        _head_part(s, cx, 60, 40, 26, top=110, stem_len=100, shape="mushroom", labels=("D1", "H1", "d steel"))
    return _two("Cylindrical to mushroom head", a, b)


def _trap_preform(s, cx, top, d_max, d_top, h_cone, stem_r, stem_len, labels=("D1 max", "D1 min top", "Htv", "Hsp", "Lf")):
    s.poly([(cx - d_top, top), (cx + d_top, top), (cx + d_max, top + h_cone), (cx - d_max, top + h_cone)], "wp2")
    s.rect(cx - stem_r, top + h_cone, 2 * stem_r, stem_len, "wp")
    s.cl(cx, top - 10, top + h_cone + stem_len + 10)
    s.hdim(cx - d_top, cx + d_top, top - 14, labels[1], ext_from=top)
    s.hdim(cx - d_max, cx + d_max, top + h_cone + 14, labels[0], above=False)
    s.vdim(top, top + h_cone, cx + d_max + 16, labels[2], ext_from=cx + d_max)
    s.vdim(top + h_cone, top + h_cone + stem_len, cx - stem_r - 22, labels[4], ext_from=cx - stem_r, side="left")


def shape_cyl_trap():
    def a(s, cx):
        _cyl(s, cx, 24, 70, 260, "D0")

    def b(s, cx):
        _trap_preform(s, cx, 80, 40, 28, 70, 24, 110)
    return _two("Cylindrical to trapezoid", a, b)


def _double_trap(s, cx, top, d_mid, d_top, d_bot, h1, h2, stem_r, stem_len, lab_top="D1 min top", lab_mid="D1 max", lab_bot="D1 min bottom"):
    s.poly([(cx - d_top, top), (cx + d_top, top), (cx + d_mid, top + h1), (cx + d_bot, top + h1 + h2),
            (cx - d_bot, top + h1 + h2), (cx - d_mid, top + h1)], "wp2")
    s.rect(cx - stem_r, top + h1 + h2, 2 * stem_r, stem_len, "wp")
    s.cl(cx, top - 10, top + h1 + h2 + stem_len + 10)
    s.hdim(cx - d_top, cx + d_top, top - 14, lab_top, ext_from=top)
    s.hdim(cx - d_mid, cx + d_mid, top + h1 + 4, lab_mid)
    s.hdim(cx - d_bot, cx + d_bot, top + h1 + h2 + 14, lab_bot, above=False)
    s.vdim(top, top + h1, cx + d_mid + 12, "Ha", ext_from=cx + d_mid)
    s.vdim(top, top + h1 + h2, cx - d_mid - 12, "Htv", ext_from=cx - d_mid, side="left")


def shape_cyl_double_trap():
    def a(s, cx):
        _cyl(s, cx, 24, 70, 260, "D0")

    def b(s, cx):
        _double_trap(s, cx, 80, 42, 28, 30, 36, 30, 24, 110)
    return _two("Cylindrical to double trapezoid", a, b)


def _sphere_preform(s, cx, top, r, h, stem_r, stem_len, lab="D1 max"):
    s.path(f"M{cx - r * 0.65},{top} L{cx + r * 0.65},{top} Q{cx + r * 1.25},{top + h / 2} {cx + r * 0.7},{top + h} "
           f"L{cx - r * 0.7},{top + h} Q{cx - r * 1.25},{top + h / 2} {cx - r * 0.65},{top} Z", "wp2")
    s.rect(cx - stem_r, top + h, 2 * stem_r, stem_len, "wp")
    s.cl(cx, top - 10, top + h + stem_len + 10)
    s.hdim(cx - r * 0.95, cx + r * 0.95, top + h / 2, lab)
    s.vdim(top, top + h, cx + r + 14, "Htv", ext_from=cx + r * 0.7)
    s.text(cx, top + h / 2 + 18, "V sphere", cls="dt")


def shape_cyl_sphere():
    def a(s, cx):
        _cyl(s, cx, 24, 70, 260, "D0")

    def b(s, cx):
        _sphere_preform(s, cx, 80, 44, 80, 24, 100)
    return _two("Cylindrical to spherical shape", a, b)


def shape_trap_flat():
    def a(s, cx):
        _trap_preform(s, cx, 80, 40, 28, 70, 24, 110, labels=("D0 max", "D0 min top", "Htv", "Hsp", "Lf"))

    def b(s, cx):
        _head_part(s, cx, 58, 30, 24, top=120, stem_len=110, labels=("D1", "Hk", "d steel"))
    return _two("Trapezoid to cylindrical flat", a, b)


def shape_double_trap_flat():
    def a(s, cx):
        _double_trap(s, cx, 80, 42, 28, 30, 36, 30, 24, 110, "D0 min top", "D0 max", "D0 min bottom")

    def b(s, cx):
        _head_part(s, cx, 58, 30, 24, top=120, stem_len=110, labels=("D1", "Hk", ""))
    return _two("Double trapezoid to cylindrical flat", a, b)


def shape_sphere_flat():
    def a(s, cx):
        _sphere_preform(s, cx, 80, 44, 80, 24, 100, lab="D0 max")

    def b(s, cx):
        _head_part(s, cx, 58, 30, 24, top=120, stem_len=110, labels=("D1", "Hk", ""))
    return _two("Spherical shape to cylindrical flat", a, b)


def shape_reduce():
    def a(s, cx):
        _cyl(s, cx, 30, 60, 260, "D1")

    def b(s, cx):
        s.rect(cx - 30, 60, 60, 110, "wp", rx=3)
        s.poly([(cx - 30, 170), (cx + 30, 170), (cx + 22, 190), (cx - 22, 190)], "wp2")
        s.rect(cx - 22, 190, 44, 70, "wp2")
        s.cl(cx, 50, 270)
        s.hdim(cx - 30, cx + 30, 46, "D1", ext_from=60)
        s.hdim(cx - 22, cx + 22, 276, "D2", above=False)
        s.text(cx + 40, 186, "α", anchor="start", cls="dt")
    return _two("Reduced shank", a, b)


def shape_extrusion():
    def a(s, cx):
        _cyl(s, cx, 34, 70, 250, "d1")

    def b(s, cx):
        s.rect(cx - 34, 50, 68, 100, "wp", rx=3)
        s.poly([(cx - 34, 150), (cx + 34, 150), (cx + 18, 176), (cx - 18, 176)], "wp2")
        s.rect(cx - 18, 176, 36, 100, "wp2")
        s.cl(cx, 40, 286)
        s.hdim(cx - 34, cx + 34, 42, "d1", ext_from=50)
        s.hdim(cx - 18, cx + 18, 290, "d2", above=True)
        s.text(cx + 42, 170, "α", anchor="start", cls="dt")
    return _two("Forward extruded part", a, b)


def shape_backward():
    def a(s, cx):
        _cyl(s, cx, 44, 150, 250, "d2")
        s.vdim(150, 250, cx - 62, "H0", ext_from=cx - 44, side="left")

    def b(s, cx):
        s.path(f"M{cx - 44},250 L{cx - 44},70 L{cx - 30},70 L{cx - 30},222 L{cx + 30},222 L{cx + 30},70 L{cx + 44},70 L{cx + 44},250 Z", "wp2")
        s.cl(cx, 60, 262)
        s.hdim(cx - 30, cx + 30, 140, "d1")
        s.hdim(cx - 44, cx + 44, 268, "d2", above=False)
        s.vdim(222, 250, cx + 62, "H1", ext_from=cx + 44)
    return _two("Backward extruded cup", a, b)


def shape_punch():
    def a(s, cx):
        s.path(f"M{cx - 50},200 L{cx - 50},110 L{cx + 50},110 L{cx + 50},200 Z", "wp")
        s.rect(cx - 26, 110, 52, 50, "wp2")
        s.cl(cx, 96, 214)
        s.hdim(cx - 26, cx + 26, 96, "d")
        s.vdim(160, 200, cx + 66, "T", ext_from=cx + 50)

    def b(s, cx):
        s.path(f"M{cx - 50},200 L{cx - 50},110 L{cx - 26},110 L{cx - 26},200 Z M{cx + 26},200 L{cx + 26},110 L{cx + 50},110 L{cx + 50},200 Z", "wp")
        s.rect(cx - 26, 230, 52, 18, "wp2", rx=2)
        s.cl(cx, 96, 260)
        s.text(cx, 272, "slug", cls="mt")
        s.hdim(cx - 26, cx + 26, 96, "d")
    return _two("Pierced part", a, b)


def _trim(title, kind):
    def a(s, cx):
        _head_part(s, cx, 60, 30, 22, top=110, stem_len=110, labels=("D0", "H1", ""))

    def b(s, cx):
        top, hh = 110, 30
        s.rect(cx - 22, top + hh, 44, 110, "wp")
        if kind == "hex":
            s.rect(cx - 46, top, 92, hh, "wp2")
            s.line(cx - 16, top, cx - 16, top + hh, "ln").line(cx + 16, top, cx + 16, top + hh, "ln")
            lab = "SW"
        elif kind == "square":
            s.rect(cx - 42, top, 84, hh, "wp2")
            s.line(cx, top, cx, top + hh, "ln")
            lab = "Z"
        else:
            s.rect(cx - 44, top, 88, hh, "wp2", rx=4)
            lab = "D1"
        s.cl(cx, top - 10, top + hh + 120)
        s.hdim(cx - 44, cx + 44, top - 14, lab, ext_from=top)
        s.vdim(top, top + hh, cx + 60, "H1", ext_from=cx + 44)
        # plan view
        py = 270
        if kind == "hex":
            pts = [(cx + 26 * math.cos(math.radians(a)), py + 26 * math.sin(math.radians(a))) for a in range(0, 360, 60)]
            s.poly(pts, "wp2")
        elif kind == "square":
            s.rect(cx - 20, py - 20, 40, 40, "wp2")
        else:
            s.path(f"M{cx - 22},{py} a22,22 0 1,0 44,0 a22,22 0 1,0 -44,0", "wp2")
    return _two(title, a, b)


PROCESS_DRAWINGS = {1: proc_cut_off, 2: proc_closed_upset, 3: proc_open_upset, 4: proc_setting, 5: proc_pre_upset,
                    6: proc_reduction, 7: proc_trap, 8: proc_backward, 9: proc_piercing, 10: proc_trimming}
SHAPE_DRAWINGS = {1: shape_cutoff, 2: shape_cyl_flat, 3: shape_mushroom, 4: shape_cyl_trap, 5: shape_cyl_double_trap,
                  6: shape_cyl_sphere, 7: shape_trap_flat, 8: shape_double_trap_flat, 10: shape_sphere_flat,
                  11: shape_reduce, 12: shape_extrusion, 13: shape_backward, 14: shape_punch,
                  15: lambda: _trim("Hexagon head", "hex"), 16: lambda: _trim("Square head", "square"),
                  17: lambda: _trim("Round head", "round")}

SVG_CSS = """
.dwg{width:100%;height:auto;display:block}
.dwg .tl{fill:url(#hatch);stroke:var(--d-ink);stroke-width:1.4}
.dwg .tl2{fill:url(#hatch2);stroke:var(--d-ink);stroke-width:1.4}
.dwg .wp{fill:var(--d-wp);stroke:var(--d-ink);stroke-width:1.6}
.dwg .wp2{fill:var(--d-wp2);stroke:var(--d-ink);stroke-width:1.6}
.dwg .ghost{fill:none;stroke:var(--d-muted);stroke-width:1.2;stroke-dasharray:5 4}
.dwg .ln{stroke:var(--d-ink);stroke-width:1.2}
.dwg .cl{stroke:var(--d-muted);stroke-width:1;stroke-dasharray:14 4 3 4}
.dwg .cut{stroke:var(--d-accent);stroke-width:1.6;stroke-dasharray:4 3}
.dwg .dm{stroke:var(--d-dim);stroke-width:1;fill:none}
.dwg .dx{stroke:var(--d-dim);stroke-width:.8;opacity:.7}
.dwg .ah{fill:var(--d-dim)}
.dwg .dt{fill:var(--d-dim);font:600 12px var(--f-mono, monospace)}
.dwg .tx,.dwg .mt{fill:var(--d-muted);font:500 11px var(--f-body, sans-serif)}
.dwg .mv{stroke:var(--d-accent);stroke-width:2.2}
.dwg .mvh{fill:var(--d-accent)}
.dwg .fa{stroke:var(--d-muted);stroke-width:2}
.dwg .fah{fill:var(--d-muted)}
"""

SVG_DEFS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
            '<pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            '<rect width="8" height="8" style="fill:var(--d-tool)"/><line x1="0" y1="0" x2="0" y2="8" style="stroke:var(--d-hatch);stroke-width:1.2"/></pattern>'
            '<pattern id="hatch2" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">'
            '<rect width="8" height="8" style="fill:var(--d-tool2)"/><line x1="0" y1="0" x2="0" y2="8" style="stroke:var(--d-hatch);stroke-width:1.2"/></pattern>'
            '</defs></svg>')


def all_drawings():
    return ({k: f() for k, f in PROCESS_DRAWINGS.items()}, {k: f() for k, f in SHAPE_DRAWINGS.items()})
