# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-section outlines of AISC shapes. Pure Python, metres, tuples.

Coordinates: ``u`` across the section (horizontal), ``v`` along the web
(vertical, +v up). Every finished profile is centred on its centroid.
Outer loops run counter-clockwise, holes clockwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

ARC_SEGMENTS = 4
MIN_ROUND_SEGMENTS = 8
MAX_ROUND_SEGMENTS = 96
DEFAULT_ROUND_SEGMENTS = 24


@dataclass
class Loop:
    points: list                      # [(u, v)], closed implicitly
    arc_edges: set = field(default_factory=set)   # edge i: points[i] -> points[i+1]


@dataclass
class Region:
    outer: Loop                       # counter-clockwise
    holes: list                       # [Loop], clockwise


@dataclass
class InsertionPoint:
    id: str
    label: str
    uv: tuple


@dataclass
class Profile:
    regions: list                     # [Region]
    points: list                      # [InsertionPoint]
    centroid: tuple                   # always (0.0, 0.0) after centring
    area: float                       # m^2
    bbox: tuple                       # (umin, vmin, umax, vmax)

    def point(self, insertion_id):
        for p in self.points:
            if p.id == insertion_id:
                return p
        return self.points[0]


# ---------------------------------------------------------------- helpers

def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 0 else (0.0, 0.0)


def signed_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def polygon_centroid(pts):
    a = signed_area(pts)
    if abs(a) < 1e-18:
        n = len(pts)
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        w = x0 * y1 - x1 * y0
        cx += (x0 + x1) * w
        cy += (y0 + y1) * w
    return (cx / (6.0 * a), cy / (6.0 * a))


def round_corners(corners, segs=ARC_SEGMENTS):
    """Replace every corner ``(u, v, r)`` with ``r > 0`` by a tangent arc of
    ``segs`` segments. Works for convex and concave corners alike. A fillet
    that would not fit between its neighbours is skipped (sharp corner)."""
    n = len(corners)
    pts = []
    arc_edges = set()
    for i, (u, v, r) in enumerate(corners):
        if r <= 0.0:
            pts.append((u, v))
            continue
        pu, pv, _ = corners[i - 1]
        nu, nv, _ = corners[(i + 1) % n]
        d1 = _unit((pu - u, pv - v))
        d2 = _unit((nu - u, nv - v))
        cos_t = max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1]))
        theta = math.acos(cos_t)
        if theta < 1e-6 or abs(theta - math.pi) < 1e-6:
            pts.append((u, v))
            continue
        tdist = r / math.tan(theta / 2.0)
        if (tdist > 0.5 * math.hypot(pu - u, pv - v) + 1e-12
                or tdist > 0.5 * math.hypot(nu - u, nv - v) + 1e-12):
            pts.append((u, v))
            continue
        t1 = (u + d1[0] * tdist, v + d1[1] * tdist)
        t2 = (u + d2[0] * tdist, v + d2[1] * tdist)
        bis = _unit((d1[0] + d2[0], d1[1] + d2[1]))
        cdist = r / math.sin(theta / 2.0)
        c = (u + bis[0] * cdist, v + bis[1] * cdist)
        a1 = math.atan2(t1[1] - c[1], t1[0] - c[0])
        a2 = math.atan2(t2[1] - c[1], t2[0] - c[0])
        sweep = a2 - a1
        while sweep > math.pi:
            sweep -= 2.0 * math.pi
        while sweep < -math.pi:
            sweep += 2.0 * math.pi
        first = len(pts)
        for k in range(segs + 1):
            a = a1 + sweep * k / segs
            pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
        arc_edges.update(range(first, first + segs))
    return Loop(pts, arc_edges)


def reverse_loop(loop):
    n = len(loop.points)
    pts = list(reversed(loop.points))
    arcs = {(n - 2 - i) % n for i in loop.arc_edges}
    return Loop(pts, arcs)


def circle_loop(r, segments):
    segments = max(MIN_ROUND_SEGMENTS, min(MAX_ROUND_SEGMENTS, int(segments)))
    pts = [(r * math.cos(2.0 * math.pi * k / segments),
            r * math.sin(2.0 * math.pi * k / segments)) for k in range(segments)]
    return Loop(pts, set(range(segments)))


# ---------------------------------------------------------------- builders
# Each builder returns [(outer_corners, [hole_corners, ...]), ...] with
# corners as (u, v, r). Any origin: the assembly recentres on the centroid.

#: Families rolled with a 1:6 slope on the inner flange faces. Their
#: tabulated ``tf`` is the AVERAGE thickness, so the flange is thicker at the
#: web by half the slope across the flange and the fillet is smaller than
#: ``kdes - tf`` by that amount.
SLOPED_FLANGES = {"S", "C", "MC", "ST"}
FLANGE_SLOPE = 1.0 / 6.0


def _fillet_radius(dims, key_thickness, fillets):
    if not fillets:
        return 0.0
    k = dims.get("kdes")
    t = dims.get(key_thickness)
    if k is None or t is None:
        return 0.0
    r = k - t
    if dims.get("_sloped"):
        bf, tw = dims.get("bf", 0.0), dims.get("tw", 0.0)
        r -= 0.5 * FLANGE_SLOPE * max(0.0, bf - tw)
    return max(0.0, r)


def _i_shape(dims, fillets):
    d, bf, tw, tf = dims["d"], dims["bf"], dims["tw"], dims["tf"]
    r = _fillet_radius(dims, "tf", fillets)
    hb, hd, hw = bf / 2.0, d / 2.0, tw / 2.0
    outer = [(-hb, -hd, 0), (hb, -hd, 0), (hb, -hd + tf, 0), (hw, -hd + tf, r),
             (hw, hd - tf, r), (hb, hd - tf, 0), (hb, hd, 0), (-hb, hd, 0),
             (-hb, hd - tf, 0), (-hw, hd - tf, r), (-hw, -hd + tf, r), (-hb, -hd + tf, 0)]
    return [(outer, [])]


def _channel(dims, fillets):
    d, bf, tw, tf = dims["d"], dims["bf"], dims["tw"], dims["tf"]
    r = _fillet_radius(dims, "tf", fillets)
    outer = [(0, 0, 0), (bf, 0, 0), (bf, tf, 0), (tw, tf, r),
             (tw, d - tf, r), (bf, d - tf, 0), (bf, d, 0), (0, d, 0)]
    return [(outer, [])]


def _tee(dims, fillets):
    d, bf, tw, tf = dims["d"], dims["bf"], dims["tw"], dims["tf"]
    r = _fillet_radius(dims, "tf", fillets)
    hb, hw = bf / 2.0, tw / 2.0
    outer = [(-hw, 0, 0), (hw, 0, 0), (hw, d - tf, r), (hb, d - tf, 0),
             (hb, d, 0), (-hb, d, 0), (-hb, d - tf, 0), (-hw, d - tf, r)]
    return [(outer, [])]


_BUILDERS = {
    "W": _i_shape, "M": _i_shape, "S": _i_shape, "HP": _i_shape,
    "C": _channel, "MC": _channel,
    "WT": _tee, "MT": _tee, "ST": _tee,
}

NAMED = [("top", "Top centre"), ("bottom", "Bottom centre"),
         ("left", "Left centre"), ("right", "Right centre"),
         ("top_left", "Top left"), ("top_right", "Top right"),
         ("bottom_left", "Bottom left"), ("bottom_right", "Bottom right")]


def _close(a, b, eps=1e-9):
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _assemble(raw_regions, segs=ARC_SEGMENTS):
    """Round the corners, build the loops, centre on the centroid and derive
    the insertion points from the SHARP corners (so ids never depend on the
    fillet setting)."""
    regions = []
    sharp_all = []
    area = 0.0
    cx = cy = 0.0
    for outer_corners, hole_corner_lists in raw_regions:
        outer = outer_corners if isinstance(outer_corners, Loop) else round_corners(outer_corners, segs)
        a = signed_area(outer.points)
        c = polygon_centroid(outer.points)
        area += a
        cx += a * c[0]
        cy += a * c[1]
        holes = []
        for hc in hole_corner_lists:
            h = hc if isinstance(hc, Loop) else round_corners(hc, segs)
            ha = signed_area(h.points)
            hcen = polygon_centroid(h.points)
            area -= ha
            cx -= ha * hcen[0]
            cy -= ha * hcen[1]
            holes.append(reverse_loop(h))
        regions.append(Region(outer, holes))
        sharp_all.append([] if isinstance(outer_corners, Loop)
                         else [(u, v) for (u, v, _r) in outer_corners])
    cx, cy = (cx / area, cy / area) if area > 0 else (0.0, 0.0)

    def shift(p):
        return (p[0] - cx, p[1] - cy)

    for reg in regions:
        reg.outer.points = [shift(p) for p in reg.outer.points]
        for h in reg.holes:
            h.points = [shift(p) for p in h.points]
    us = [p[0] for reg in regions for p in reg.outer.points]
    vs = [p[1] for reg in regions for p in reg.outer.points]
    bbox = (min(us), min(vs), max(us), max(vs))
    umin, vmin, umax, vmax = bbox
    named_uv = {"top": (0.0, vmax), "bottom": (0.0, vmin), "left": (umin, 0.0),
                "right": (umax, 0.0), "top_left": (umin, vmax), "top_right": (umax, vmax),
                "bottom_left": (umin, vmin), "bottom_right": (umax, vmin)}
    points = [InsertionPoint("centroid", "Centroid", (0.0, 0.0))]
    points += [InsertionPoint(i, label, named_uv[i]) for i, label in NAMED]
    k = 0
    vertices = []
    midpoints = []
    for sharp in sharp_all:
        n = len(sharp)
        for i in range(n):
            a = shift(sharp[i])
            b = shift(sharp[(i + 1) % n])
            vertices.append((f"v{k}", a))
            midpoints.append((f"m{k}", ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)))
            k += 1
    for ident, uv in vertices + midpoints:
        if any(_close(uv, p.uv) for p in points):
            continue
        points.append(InsertionPoint(ident, ident, uv))
    return Profile(regions, points, (0.0, 0.0), area, bbox)


def _angle_corners(vert, horiz, t, r):
    """Heel at the origin, vertical leg along +v, horizontal leg along +u."""
    return [(0, 0, 0), (horiz, 0, 0), (horiz, t, 0), (t, t, r), (t, vert, 0), (0, vert, 0)]


def _angle(dims, fillets):
    b, d, t = dims["b"], dims["d"], dims["t"]
    r = _fillet_radius(dims, "t", fillets)
    return [(_angle_corners(max(b, d), min(b, d), t, r), [])]


def _double_angle(dims, fillets):
    b, d, t = dims["b"], dims["d"], dims["t"]
    gap = dims.get("gap", 0.0)
    llbb = dims.get("llbb", True)
    long_leg, short_leg = max(b, d), min(b, d)
    vert, horiz = (long_leg, short_leg) if llbb else (short_leg, long_leg)
    r = _fillet_radius(dims, "t", fillets)
    right = [(u + gap / 2.0, v, rr) for (u, v, rr) in _angle_corners(vert, horiz, t, r)]
    left = [(-u, v, rr) for (u, v, rr) in right][::-1]       # mirror, winding restored
    return [(right, []), (left, [])]


def _hss_rect(dims, fillets, segments=None):
    H, B, t = dims["Ht"], dims["B"], dims["tdes"]
    hb, hh = B / 2.0, H / 2.0
    ro, ri = 2.0 * t, t
    outer = [(-hb, -hh, ro), (hb, -hh, ro), (hb, hh, ro), (-hb, hh, ro)]
    ib, ih = hb - t, hh - t
    hole = [(-ib, -ih, ri), (ib, -ih, ri), (ib, ih, ri), (-ib, ih, ri)]
    return [(outer, [hole])]


def _round_tube(dims, fillets, segments=DEFAULT_ROUND_SEGMENTS):
    ro = dims["OD"] / 2.0
    ri = ro - dims["tdes"]
    return [(circle_loop(ro, segments), [circle_loop(ri, segments)])]


def _hss(dims, fillets, segments=DEFAULT_ROUND_SEGMENTS):
    if "OD" in dims:
        return _round_tube(dims, fillets, segments)
    return _hss_rect(dims, fillets, segments)


_BUILDERS.update({"L": _angle, "2L": _double_angle, "HSS": _hss, "PIPE": _round_tube})
_WITH_SEGMENTS = {"HSS", "PIPE"}


def build_profile(family, dims, fillets=True, segments=DEFAULT_ROUND_SEGMENTS):
    builder = _BUILDERS.get(family)
    if builder is None:
        raise ValueError(f"unknown shape family {family!r}")
    dims = dict(dims)
    dims["_sloped"] = family in SLOPED_FLANGES
    if family in _WITH_SEGMENTS:
        return _assemble(builder(dims, fillets, segments))
    return _assemble(builder(dims, fillets))
