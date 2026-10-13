# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel import _db
from igz_steel._profiles import build_profile, signed_area

IN_M = 0.0254


def _shape(label):
    return _db.load().find(label)


def _area_in2(profile):
    return profile.area / IN_M ** 2


@pytest.mark.parametrize("label", ["L8X4X1", "L4X4X1/4", "L2X2X1/8"])
def test_single_angles(label):
    s = _shape(label)
    p = build_profile("L", s.dims_m(), fillets=True)
    assert _area_in2(p) == pytest.approx(s.A, rel=0.03)
    umin, vmin, umax, vmax = p.bbox
    long_leg, short_leg = max(s.dims["b"], s.dims["d"]), min(s.dims["b"], s.dims["d"])
    assert (vmax - vmin) / IN_M == pytest.approx(long_leg)        # long leg vertical
    assert (umax - umin) / IN_M == pytest.approx(short_leg)
    assert p.point("bottom_left").uv == pytest.approx((umin, vmin))  # the heel


def test_double_angles_llbb_and_slbb():
    db = _db.load()
    llbb = db.find("2L8X4X1X3/4LLBB")
    slbb = db.find("2L8X4X1X3/4SLBB")
    assert llbb is not None and slbb is not None
    for s in (llbb, slbb):
        p = build_profile("2L", s.dims_m(), fillets=True)
        assert len(p.regions) == 2
        for reg in p.regions:
            assert signed_area(reg.outer.points) > 0 and not reg.holes
        assert _area_in2(p) == pytest.approx(s.A, rel=0.03)
        assert "kdes" in s.dims          # copied from L8X4X1 by the converter
    umin, vmin, umax, vmax = build_profile("2L", llbb.dims_m()).bbox
    assert (vmax - vmin) / IN_M == pytest.approx(8.0)      # long legs back to back, vertical
    assert (umax - umin) / IN_M == pytest.approx(2 * 4.0 + 0.75)
    umin, vmin, umax, vmax = build_profile("2L", slbb.dims_m()).bbox
    assert (vmax - vmin) / IN_M == pytest.approx(4.0)
    assert (umax - umin) / IN_M == pytest.approx(2 * 8.0 + 0.75)
    equal = db.find("2L4X4X1/2X3/8")
    p = build_profile("2L", equal.dims_m())
    assert (p.bbox[2] - p.bbox[0]) / IN_M == pytest.approx(8.375)


def test_rectangular_hss_has_a_hole_and_matches_area():
    s = _shape("HSS6X6X1/2")
    p = build_profile("HSS", s.dims_m())
    reg = p.regions[0]
    assert len(reg.holes) == 1
    assert signed_area(reg.outer.points) > 0 and signed_area(reg.holes[0].points) < 0
    assert reg.outer.arc_edges and reg.holes[0].arc_edges
    assert _area_in2(p) == pytest.approx(s.A, rel=0.02)
    umin, vmin, umax, vmax = p.bbox
    assert (umax - umin) / IN_M == pytest.approx(6.0) and (vmax - vmin) / IN_M == pytest.approx(6.0)
    rect = _shape("HSS8X4X1/4")
    pr = build_profile("HSS", rect.dims_m())
    assert (pr.bbox[3] - pr.bbox[1]) / IN_M == pytest.approx(8.0)   # Ht vertical
    assert (pr.bbox[2] - pr.bbox[0]) / IN_M == pytest.approx(4.0)   # B horizontal
    # corners stay rounded even with fillets off: they define the shape
    assert build_profile("HSS", s.dims_m(), fillets=False).regions[0].outer.arc_edges


@pytest.mark.parametrize("label, family", [("HSS6.000X0.500", "HSS"), ("Pipe6STD", "PIPE")])
def test_round_sections(label, family):
    s = _shape(label)
    p = build_profile(family, s.dims_m(), segments=96)
    reg = p.regions[0]
    assert len(reg.outer.points) == 96 and len(reg.holes[0].points) == 96
    assert len(reg.outer.arc_edges) == 96
    assert _area_in2(p) == pytest.approx(s.A, rel=0.01)
    assert (p.bbox[2] - p.bbox[0]) / IN_M == pytest.approx(s.dims["OD"], abs=1e-9)
    # no vertex ids on a circle, only the named points
    assert all(not pt.id.startswith(("v", "m")) for pt in p.points)
    small = build_profile(family, s.dims_m(), segments=3)
    assert len(small.regions[0].outer.points) == 8                  # clamped to the minimum


def test_every_shape_in_the_database_builds_closed_outlines():
    db = _db.load()
    worst = 0.0
    for fam in db.families():
        for s in db.shapes(fam):
            p = build_profile(fam, s.dims_m(), fillets=True, segments=24)
            assert p.regions, s.label
            for reg in p.regions:
                assert signed_area(reg.outer.points) > 0, s.label
                for h in reg.holes:
                    assert signed_area(h.points) < 0, s.label
            assert p.area > 0, s.label
            assert p.points[0].id == "centroid"
            rel = abs(_area_in2(p) - s.A) / s.A
            worst = max(worst, rel)
            assert rel < 0.06, (s.label, rel)
    assert worst < 0.06
