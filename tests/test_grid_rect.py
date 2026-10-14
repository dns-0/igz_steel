# SPDX-License-Identifier: GPL-3.0-or-later
import json
import math

import pytest

from igz_steel._grid import GridError, Level, RectGrid


def grid(**kw):
    base = dict(id="g1", name="Main", x_spacings=[7.62, 9.144], y_spacings=[6.096],
                extend={"x_neg": 1.0, "x_pos": 2.0, "y_neg": 3.0, "y_pos": 4.0},
                levels=[Level("EL 112", 34.1376), Level("EL 100", 30.48)])
    base.update(kw)
    return RectGrid(**base)


def by(lines, direction, index):
    return next(l for l in lines if l.direction == direction and l.index == index)


def test_names_and_levels_normalised():
    g = grid()
    assert g.x_names == ["A", "B", "C"] and g.y_names == ["1", "2"]
    assert [lv.name for lv in g.levels] == ["EL 100", "EL 112"]      # sorted by z
    assert g.level().z == 30.48 and g.kind == "rect"


def test_line_endpoints_with_extend():
    lines = grid().lines()
    pts = by(lines, "x", 1).points
    a, b = pts[0], pts[-1]
    assert a == pytest.approx((7.62, -3.0, 30.48)) and b == pytest.approx((7.62, 10.096, 30.48))
    pts = by(lines, "y", 0).points
    a, b = pts[0], pts[-1]
    assert a == pytest.approx((-1.0, 0.0, 30.48)) and b == pytest.approx((18.764, 0.0, 30.48))
    assert by(lines, "x", 1).name == "B" and by(lines, "y", 1).name == "2"


def test_lines_have_a_vertex_at_every_crossing():
    g = grid()
    xl = by(g.lines(), "x", 1)
    assert len(xl.points) == len(g.y_names) + 2
    assert xl.points[1:-1] == pytest.approx([(7.62, 0.0, 30.48), (7.62, 6.096, 30.48)])
    yl = by(g.lines(), "y", 1)
    assert len(yl.points) == len(g.x_names) + 2
    assert yl.points[1:-1] == pytest.approx([(0.0, 6.096, 30.48), (7.62, 6.096, 30.48),
                                             (16.764, 6.096, 30.48)])
    ys = [p[1] for p in xl.points]
    assert ys == sorted(ys)                                            # in order along the line


def test_bubbles_top_left_and_all():
    g = grid()
    xl = by(g.lines(), "x", 0)
    assert len(xl.bubbles) == 1
    assert xl.bubbles[0].at == pytest.approx((0.0, 10.096, 30.48))
    assert xl.bubbles[0].toward == pytest.approx((0.0, 1.0))
    yl = by(g.lines(), "y", 0)
    assert yl.bubbles[0].at == pytest.approx((-1.0, 0.0, 30.48))
    assert yl.bubbles[0].toward == pytest.approx((-1.0, 0.0))
    assert all(len(l.bubbles) == 2 for l in grid(bubbles="all").lines())


def test_rotation_turns_everything_as_a_unit():
    g = grid(rotation_deg=90.0, origin=(10.0, 5.0, 0.0), levels=[Level("L", 0.0)])
    nodes = {n.names: n.at for n in g.intersections()}
    assert nodes[("A", "1")] == pytest.approx((10.0, 5.0, 0.0))
    assert nodes[("B", "1")] == pytest.approx((10.0, 12.62, 0.0))      # local +X -> world +Y
    assert nodes[("A", "2")] == pytest.approx((3.904, 5.0, 0.0))       # local +Y -> world -X
    assert by(g.lines(), "x", 0).bubbles[0].toward == pytest.approx((-1.0, 0.0))
    assert g.corner_marks()[1] == pytest.approx((10.0, 21.764, 0.0))


def test_intersections_levels_and_corners():
    g = grid()
    assert len(g.intersections()) == 6
    assert {round(n.at[2], 4) for n in g.intersections(1)} == {34.1376}
    assert g.corner_marks(1)[2] == pytest.approx((16.764, 6.096, 34.1376))
    assert len(g.corner_marks()) == 4


def test_nearest_across_levels():
    g = grid()
    node, level, d = g.nearest((7.7, 6.0, 34.0))
    assert node.names == ("B", "2") and level.name == "EL 112" and d < 0.3
    _node, level, _d = g.nearest((7.7, 6.0, 34.0), level_index=0)
    assert level.name == "EL 100"


def test_rename_set_spacings_and_set_start():
    g = grid()
    g.rename_line("x", 1, "B.5")
    g.set_spacings("x", [7.62, 9.144, 3.0], "25', 30', 10'")
    assert g.x_names == ["A", "B.5", "C", "D"] and g.x_text == "25', 30', 10'"
    g.set_spacings("y", [6.096, 6.096], "2@20'")
    assert g.y_names == ["1", "2", "3"]
    g.set_start("x", "C")
    assert g.x_names == ["C", "D", "E", "F"] and g.x_start == "C"
    with pytest.raises(GridError):
        g.set_start("y", "I")


def test_set_levels_keeps_active_in_range():
    g = grid(active_level=1)
    g.set_levels([Level("only", 1.0)])
    assert g.active_level == 0 and g.level().name == "only"


def test_round_trip_json():
    g = grid(rotation_deg=15.0, bubbles="all", active_level=1, visible=False,
             x_text="25', 30'", y_text="20'")
    g.rename_line("y", 0, "1A")
    d = g.to_dict()
    json.dumps(d)
    g2 = RectGrid.from_dict(d)
    assert g2.to_dict() == d and g2.y_names[0] == "1A" and g2.visible is False


@pytest.mark.parametrize("patch", [
    {"x": {"spacings": [], "names": [], "start": "A", "text": ""}},
    {"origin": [0, 0]},
    {"x": {"spacings": [-1.0], "start": "A", "text": ""}},
    {"levels": "nope"},
    {"rotation_deg": "fast"},
    {"extend": [1]},
    {"extend": "abc"},
    {"active_level": float("inf")},
    {"rotation_deg": float("nan")},
    {"x": {"spacings": [float("nan")], "names": [], "start": "A", "text": ""}},
    {"levels": [{"name": "a", "z": float("inf")}]}])
def test_from_dict_rejects_bad_blocks(patch):
    d = grid().to_dict()
    d.update(patch)
    with pytest.raises(GridError):
        RectGrid.from_dict(d)


def test_from_dict_fills_defaults():
    d = grid().to_dict()
    d["x"]["names"] = ["A", "B"]            # wrong length -> regenerated
    del d["levels"]
    d.pop("bubbles")
    g = RectGrid.from_dict(d)
    assert g.x_names == ["A", "B", "C"] and g.bubbles == "top_left"
    assert len(g.levels) == 1 and g.levels[0].z == pytest.approx(d["origin"][2])
