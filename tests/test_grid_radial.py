# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from igz_steel._grid import GridError, Level, RadialGrid

C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))
C60, S60 = math.cos(math.radians(60)), math.sin(math.radians(60))


def rg(**kw):
    base = dict(id="g2", name="Tank", radii=[3.0, 2.0], steps_deg=[30.0, 30.0, 30.0],
                start_deg=0.0, tangent=0.0,
                extend={"radial_in": 0.5, "radial_out": 1.0, "arc": 0.0},
                levels=[Level("L", 0.0)])
    base.update(kw)
    return RadialGrid(**base)


def of(lines, direction):
    return [l for l in lines if l.direction == direction]


def test_radii_angles_and_names():
    g = rg()
    assert g.radius_values() == [3.0, 5.0]
    assert g.angle_values() == [0.0, 30.0, 60.0, 90.0]
    assert g.radii_names == ["A", "B"] and g.angle_names == ["1", "2", "3", "4"]
    assert g.kind == "radial" and not g.closed


def test_radial_line_endpoints_and_bubble():
    line = of(rg().lines(), "angles")[1]
    a, b = line.points
    assert a == pytest.approx((2.5 * C30, 2.5 * S30, 0.0))
    assert b == pytest.approx((6.0 * C30, 6.0 * S30, 0.0))
    assert line.name == "2" and len(line.bubbles) == 1
    assert line.bubbles[0].at == pytest.approx(b)
    assert line.bubbles[0].toward == pytest.approx((C30, S30))
    assert len(of(rg(bubbles="all").lines(), "angles")[1].bubbles) == 2


def test_arc_passes_through_every_radial_line():
    arc = of(rg().lines(), "radii")[1]
    assert arc.name == "B"
    for deg in (0.0, 30.0, 60.0, 90.0):
        p = (5.0 * math.cos(math.radians(deg)), 5.0 * math.sin(math.radians(deg)), 0.0)
        assert any(math.dist(p, q) < 1e-9 for q in arc.points)
    assert all(abs(math.hypot(x, y) - 5.0) < 1e-9 for x, y, _ in arc.points)
    assert len(arc.points) >= 23


def test_tangent_legs():
    g = rg(tangent=2.0, extend={"radial_in": 0.0, "radial_out": 0.0, "arc": 0.5})
    arc = of(g.lines(), "radii")[0]                       # r = 3
    first, second, last = arc.points[0], arc.points[1], arc.points[-1]
    assert second == pytest.approx((3.0, 0.0, 0.0))
    assert math.dist(first, second) == pytest.approx(2.5)
    assert first == pytest.approx((3.0, -2.5, 0.0))      # tangent at 0° toward smaller angles
    assert last == pytest.approx((-2.5, 3.0, 0.0))       # tangent at 90° toward larger angles
    assert (first[0] - second[0]) * second[0] + (first[1] - second[1]) * second[1] == pytest.approx(0.0)
    assert arc.bubbles[0].at == pytest.approx(first) and arc.bubbles[0].toward == pytest.approx((0.0, -1.0))
    nodes = {n.names: n.at for n in g.intersections()}
    assert nodes[("A", "T1")] == pytest.approx(first) and nodes[("A", "T2")] == pytest.approx(last)
    assert nodes[("B", "3")] == pytest.approx((5.0 * C60, 5.0 * S60, 0.0))
    assert len(nodes) == 2 * 4 + 4


def test_arc_extension_without_tangent():
    g = rg(extend={"radial_in": 0.0, "radial_out": 0.0, "arc": 1.5})
    arc = of(g.lines(), "radii")[0]                       # r = 3: 1.5 m of arc = 28.65°
    x, y, _ = arc.points[0]
    assert math.degrees(math.atan2(y, x)) == pytest.approx(-math.degrees(1.5 / 3.0))
    x, y, _ = arc.points[-1]
    assert math.degrees(math.atan2(y, x)) == pytest.approx(90.0 + math.degrees(1.5 / 3.0))
    assert ("A", "T1") not in {n.names for n in g.intersections()}


def test_closed_circle_has_no_duplicate_line_and_no_legs():
    g = rg(steps_deg=[90.0] * 4, tangent=2.0)
    assert g.closed
    assert len(of(g.lines(), "angles")) == 4
    assert len(g.intersections()) == 8
    arc = of(g.lines(), "radii")[0]
    assert math.dist(arc.points[0], arc.points[-1]) < 1e-9
    assert all(abs(math.hypot(x, y) - 3.0) < 1e-9 for x, y, _ in arc.points)


def test_corner_marks_rotation_and_round_trip():
    g = rg(rotation_deg=90.0, origin=(1.0, 1.0, 2.0), tangent=1.0, levels=[Level("L", 2.0)])
    nodes = {n.names: n.at for n in g.intersections()}
    assert nodes[("A", "1")] == pytest.approx((1.0, 4.0, 2.0))      # 0° turned to world +Y
    marks = g.corner_marks()
    assert len(marks) == 5 and marks[-1] == pytest.approx((1.0, 1.0, 2.0))
    d = g.to_dict()
    assert RadialGrid.from_dict(d).to_dict() == d


def test_editing_and_names():
    g = rg()
    g.rename_line("radii", 0, "A.5")
    g.set_radii([3.0, 2.0, 2.0], "10', 2@6.5'")
    assert g.radii_names == ["A.5", "B", "C"] and g.radii_text == "10', 2@6.5'"
    g.set_angles([45.0, 45.0], "2@45")
    assert g.angle_names == ["1", "2", "3"] and g.angle_values() == [0.0, 45.0, 90.0]
    g.set_start("angles", "10")
    assert g.angle_names == ["10", "11", "12"]
    with pytest.raises(GridError):
        RadialGrid.from_dict({"id": "x", "kind": "radial", "radii": {"spacings": []},
                              "angles": {"steps_deg": [30]}})
    valid = {"id": "x", "kind": "radial", "radii": {"spacings": [2.0]},
             "angles": {"steps_deg": [30.0]}}
    with pytest.raises(GridError):
        RadialGrid.from_dict({**valid, "tangent": float("nan")})
    with pytest.raises(GridError):
        RadialGrid.from_dict({**valid, "extend": "abc"})
