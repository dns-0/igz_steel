# SPDX-License-Identifier: GPL-3.0-or-later
import math
from collections import Counter

import pytest

from igz_steel import _db
from igz_steel._geometry import (MIN_LENGTH, apply_matrix, direction_and_length, extrude,
                                 ifc_class_for, member_end, member_matrix, preview_segments)
from igz_steel._profiles import build_profile


def _profile(label, **kw):
    s = _db.load().find(label)
    return build_profile(s.family, s.dims_m(), **kw)


def _loops(face):
    if isinstance(face, tuple):
        outer, holes = face
        return [outer] + list(holes)
    return [face]


def _edge_counts(mesh):
    counts = Counter()
    for face in mesh.faces:
        for loop in _loops(face):
            n = len(loop)
            for i in range(n):
                a = tuple(round(c, 9) for c in loop[i])
                b = tuple(round(c, 9) for c in loop[(i + 1) % n])
                counts[frozenset((a, b))] += 1
    return counts


def _normal(face):
    """Newell normal: valid for concave outlines, unlike a 3-point cross product."""
    nx = ny = nz = 0.0
    n = len(face)
    for i in range(n):
        x0, y0, z0 = face[i]
        x1, y1, z1 = face[(i + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return (nx, ny, nz)


def test_w_member_is_watertight_and_outward():
    prof = _profile("W12X26", fillets=False)
    m = extrude(prof, 3.0, (0.0, 0.0))
    n_outer = len(prof.regions[0].outer.points)
    assert len(m.faces) == 2 + n_outer
    assert set(_edge_counts(m).values()) == {2}
    assert m.soft_pairs == set()
    # caps: start at x=0 facing -X, end at x=3 facing +X
    assert _normal(m.faces[0])[0] < 0 and all(p[0] == 0.0 for p in m.faces[0])
    assert _normal(m.faces[1])[0] > 0 and all(p[0] == 3.0 for p in m.faces[1])
    outer = prof.regions[0].outer.points
    for i, quad in enumerate(m.faces[2:]):
        n = _normal(quad)
        a, b = outer[i], outer[(i + 1) % n_outer]
        expected = (b[1] - a[1], -(b[0] - a[0]))      # right-hand normal of a CCW edge
        assert n[0] == pytest.approx(0.0)
        assert n[1] * expected[0] + n[2] * expected[1] > 0   # outward from the material


def test_fillets_produce_soft_pairs_only_at_arcs():
    prof = _profile("W12X26", fillets=True)
    m = extrude(prof, 1.0, (0.0, 0.0))
    assert m.soft_pairs
    for i, j in m.soft_pairs:
        assert 2 <= i < len(m.faces) and 2 <= j < len(m.faces)
    # 4 fillets x 4 arc edges -> 5 longitudinal edges per fillet softened
    assert len(m.soft_pairs) == 4 * 5


def test_hss_member_has_holes_and_inward_hole_quads():
    prof = _profile("HSS6X6X1/2")
    m = extrude(prof, 2.0, (0.0, 0.0))
    assert isinstance(m.faces[0], tuple) and len(m.faces[0][1]) == 1
    assert set(_edge_counts(m).values()) == {2}
    n_outer = len(prof.regions[0].outer.points)
    hole = prof.regions[0].holes[0].points
    hole_quads = m.faces[2 + n_outer:]
    assert len(hole_quads) == len(hole)
    for i, quad in enumerate(hole_quads):
        n = _normal(quad)
        a, b = hole[i], hole[(i + 1) % len(hole)]
        expected = (b[1] - a[1], -(b[0] - a[0]))      # for a CW hole this points into the void
        assert n[1] * expected[0] + n[2] * expected[1] > 0


def test_insertion_point_moves_profile_to_local_origin():
    prof = _profile("W12X26", fillets=False)
    top = prof.point("top").uv
    m = extrude(prof, 1.0, top)
    zs = [p[2] for p in m.faces[1]]
    assert max(zs) == pytest.approx(0.0)              # top of steel on the axis


def test_zero_length_gives_a_profile_face():
    prof = _profile("HSS6X6X1/2")
    m = extrude(prof, 0.0, (0.0, 0.0))
    assert len(m.faces) == 1 and isinstance(m.faces[0], tuple)
    assert _normal(m.faces[0][0])[0] > 0
    two = extrude(_profile("2L4X4X1/2X3/8"), MIN_LENGTH / 2, (0.0, 0.0))
    assert len(two.faces) == 2


def test_member_matrix_axes():
    m = member_matrix((1.0, 2.0, 3.0), (1.0, 0.0, 0.0))
    assert apply_matrix(m, (5.0, 0.0, 0.0)) == pytest.approx((6.0, 2.0, 3.0))
    assert apply_matrix(m, (0.0, 0.0, 1.0)) == pytest.approx((1.0, 2.0, 4.0))   # profile up = world Z
    m = member_matrix((0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert apply_matrix(m, (0.0, 0.0, 1.0)) == pytest.approx((0.0, 0.0, 1.0))
    m = member_matrix((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))                        # a column
    assert apply_matrix(m, (0.0, 0.0, 1.0)) == pytest.approx((0.0, 1.0, 0.0))   # profile up = world Y
    assert apply_matrix(m, (2.0, 0.0, 0.0)) == pytest.approx((0.0, 0.0, 2.0))
    m = member_matrix((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), roll_deg=90.0)
    assert apply_matrix(m, (0.0, 1.0, 0.0)) == pytest.approx((0.0, 0.0, 1.0))   # u now points up
    assert apply_matrix(m, (0.0, 0.0, 1.0)) == pytest.approx((0.0, -1.0, 0.0))
    d = (1.0, 1.0, 1.0)
    m = member_matrix((0.0, 0.0, 0.0), d)
    x = apply_matrix(m, (1.0, 0.0, 0.0))
    assert x == pytest.approx(tuple(c / math.sqrt(3) for c in d))
    z = apply_matrix(m, (0.0, 0.0, 1.0))
    assert abs(sum(a * b for a, b in zip(x, z))) < 1e-12 and z[2] > 0


def test_direction_length_end_and_ifc():
    d, L = direction_and_length((0, 0, 0), (0, 3, 4))
    assert L == pytest.approx(5.0) and d == pytest.approx((0, 0.6, 0.8))
    assert direction_and_length((1, 1, 1), (1, 1, 1)) == (None, 0.0)
    assert member_end((1, 1, 1), (0, 0, 1), 2.5) == pytest.approx((1, 1, 3.5))
    assert ifc_class_for((0, 0, 1)) == "IfcColumn"
    assert ifc_class_for((0, 0, -1)) == "IfcColumn"
    assert ifc_class_for((1, 0, 0.05)) == "IfcBeam"
    assert ifc_class_for((1, 0, 1)) == "IfcMember"
    assert ifc_class_for((0.05, 0, 1)) == "IfcColumn"


def test_preview_segments():
    prof = _profile("W12X26", fillets=False)
    n = len(prof.regions[0].outer.points)
    segs = preview_segments(prof, (0.0, 0.0), (0, 0, 0), (1, 0, 0), 2.0, 0.0)
    assert len(segs) == 2 * n + n                       # two outlines + longitudinal lines
    segs0 = preview_segments(prof, (0.0, 0.0), (0, 0, 0), (1, 0, 0), 0.0, 0.0)
    assert len(segs0) == n
    xs = {round(p[0], 9) for a, b in segs for p in (a, b)}
    assert xs == {0.0, 2.0}
