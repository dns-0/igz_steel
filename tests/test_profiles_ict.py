# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel import _db
from igz_steel._profiles import build_profile, signed_area

IN_M = 0.0254


def _shape(label):
    return _db.load().find(label)


def _area_in2(profile):
    return profile.area / IN_M ** 2


@pytest.mark.parametrize("label, tol", [("W12X26", 0.015), ("W44X408", 0.015),
                                        ("HP14X117", 0.015), ("S24X121", 0.02),
                                        ("M12X11.8", 0.02)])
def test_i_shapes_match_tabulated_area_and_box(label, tol):
    s = _shape(label)
    for fillets in (True, False):
        p = build_profile(s.family, s.dims_m(), fillets=fillets)
        assert len(p.regions) == 1 and not p.regions[0].holes
        assert signed_area(p.regions[0].outer.points) > 0
        assert _area_in2(p) == pytest.approx(s.A, rel=tol)
        umin, vmin, umax, vmax = p.bbox
        assert (umax - umin) / IN_M == pytest.approx(s.dims["bf"], abs=1e-9)
        assert (vmax - vmin) / IN_M == pytest.approx(s.dims["d"], abs=1e-9)
        assert p.centroid == pytest.approx((0.0, 0.0), abs=1e-12)
    with_f = build_profile(s.family, s.dims_m(), fillets=True)
    without = build_profile(s.family, s.dims_m(), fillets=False)
    assert len(with_f.regions[0].outer.points) == 12 + 4 * 4   # 4 fillets add 4 points each
    assert len(without.regions[0].outer.points) == 12
    assert with_f.regions[0].outer.arc_edges and not without.regions[0].outer.arc_edges


def test_insertion_points_are_stable_across_fillets():
    s = _shape("W12X26")
    a = build_profile("W", s.dims_m(), fillets=True)
    b = build_profile("W", s.dims_m(), fillets=False)
    ids_a = [p.id for p in a.points]
    ids_b = [p.id for p in b.points]
    assert ids_a == ids_b
    assert ids_a[:9] == ["centroid", "top", "bottom", "left", "right",
                         "top_left", "top_right", "bottom_left", "bottom_right"]
    assert a.point("v3").uv == pytest.approx(b.point("v3").uv)
    assert a.point("top").uv == pytest.approx((0.0, 12.2 / 2 * IN_M))
    assert a.point("bottom_left").uv == pytest.approx((-6.49 / 2 * IN_M, -12.2 / 2 * IN_M))
    assert a.point("nope") is a.points[0]            # unknown id -> centroid
    # vertex ids skip points that coincide with named points, midpoints exist
    assert any(p.id.startswith("m") for p in a.points)


@pytest.mark.parametrize("label", ["C15X50", "MC18X58", "C3X4.1"])
def test_channels(label):
    s = _shape(label)
    p = build_profile(s.family, s.dims_m(), fillets=True)
    assert _area_in2(p) == pytest.approx(s.A, rel=0.03)   # sloped flanges, toe radii ignored
    umin, vmin, umax, vmax = p.bbox
    assert (umax - umin) / IN_M == pytest.approx(s.dims["bf"], abs=1e-9)
    assert (vmax - vmin) / IN_M == pytest.approx(s.dims["d"], abs=1e-9)
    # the web is on the left: the left bbox edge is a full-height straight side
    outer = p.regions[0].outer.points
    left = [pt for pt in outer if abs(pt[0] - umin) < 1e-12]
    assert len(left) == 2 and abs(left[0][1] - left[1][1]) / IN_M == pytest.approx(s.dims["d"])


@pytest.mark.parametrize("label", ["WT6X13", "MT6X5.9", "ST12X60.5"])
def test_tees(label):
    s = _shape(label)
    p = build_profile(s.family, s.dims_m(), fillets=True)
    assert _area_in2(p) == pytest.approx(s.A, rel=0.02)
    umin, vmin, umax, vmax = p.bbox
    assert (umax - umin) / IN_M == pytest.approx(s.dims["bf"], abs=1e-9)
    assert (vmax - vmin) / IN_M == pytest.approx(s.dims["d"], abs=1e-9)
    # flange on top: the top bbox edge spans the full flange width
    outer = p.regions[0].outer.points
    top = [pt for pt in outer if abs(pt[1] - vmax) < 1e-12]
    assert abs(top[0][0] - top[1][0]) / IN_M == pytest.approx(s.dims["bf"])


def test_unknown_family_raises():
    with pytest.raises(ValueError):
        build_profile("XX", {})
