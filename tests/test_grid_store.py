# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel._grid import (FT_M, GridError, Level, RectGrid, add_levels, default_rect_grid,
                             dump_block, grid_from_dict, new_grid_id, parse_block, unique_name)


def good(gid="g1", name="Main"):
    return RectGrid(id=gid, name=name, x_spacings=[7.62], y_spacings=[6.096],
                    levels=[Level("EL 100'-0\"", 30.48)]).to_dict()


def test_parse_block_skips_bad_grids_and_keeps_good_ones():
    raw = {"version": 1, "grids": [good(), {"id": "g2", "kind": "rect", "x": {}},
                                   {"id": "g3", "kind": "cube"}, "junk"],
           "active_grid": "g3", "units": "metric"}
    grids, meta, errors = parse_block(raw)
    assert [g.id for g in grids] == ["g1"]
    assert len(errors) == 3 and "grid 2" in errors[0]
    assert meta == {"active_grid": "g1", "units": "metric"}    # g3 is gone, so the first grid


def test_parse_block_tolerates_garbage_and_newer_versions():
    assert parse_block(None) == ([], {"active_grid": None, "units": "imperial"}, [])
    assert parse_block({}) == ([], {"active_grid": None, "units": "imperial"}, [])
    grids, _meta, errors = parse_block("nope")
    assert grids == [] and errors
    grids, meta, _ = parse_block({"version": 7, "grids": [good()], "future_key": 1, "units": "cubits"})
    assert len(grids) == 1 and meta["units"] == "imperial"
    grids, _meta, errors = parse_block({"grids": "not a list"})
    assert grids == [] and errors


def test_duplicate_ids_are_renumbered():
    grids, _, _ = parse_block({"grids": [good("g1"), good("g1", "Other")]})
    assert [g.id for g in grids] == ["g1", "g2"]


def test_dump_round_trip_and_ids():
    grids, meta, _ = parse_block({"grids": [good()], "active_grid": "g1", "units": "metric"})
    block = dump_block(grids, meta["active_grid"], meta["units"])
    assert block["version"] == 1 and block["grids"][0] == good() and block["units"] == "metric"
    assert dump_block([], None, "cubits")["units"] == "imperial"
    assert new_grid_id(grids) == "g2"
    assert unique_name(grids, "Main") == "Main 2" and unique_name(grids, "Rack") == "Rack"
    assert grid_from_dict(good()).kind == "rect"
    with pytest.raises(GridError):
        grid_from_dict({"id": "x", "kind": "hex"})


def test_add_levels_up_and_down_with_patterns():
    base = [Level("EL 100'-0\"", 30.48)]
    up = add_levels(base, 2, 12 * FT_M, "up", "T.O.S. EL {el}", "imperial")
    assert [lv.name for lv in up] == ["EL 100'-0\"", "T.O.S. EL 112'-0\"", "T.O.S. EL 124'-0\""]
    assert up[-1].z == pytest.approx(30.48 + 24 * FT_M)
    down = add_levels(base, 1, 3.0, "down", "Level {n}", "metric")
    assert [lv.name for lv in down] == ["Level 2", "EL 100'-0\""]
    assert down[0].z == pytest.approx(27.48)
    assert add_levels(base, 1, 1.0, "up", "EL {el}", "metric")[-1].name == "EL 31.480 m"


def test_add_levels_refuses_bad_input():
    base = [Level("a", 0.0), Level("b", 6.0)]
    with pytest.raises(GridError, match="at least one"):
        add_levels(base, 0, 3.0, "up")
    with pytest.raises(GridError, match="greater than zero"):
        add_levels(base, 1, 0.0, "up")
    with pytest.raises(GridError, match="pattern"):
        add_levels(base, 1, 3.0, "up", "EL {elevation}")
    with pytest.raises(GridError, match="At most"):
        add_levels(base, 99, 1.0, "up")
    for pattern in ("EL {el.nope}", "Level {n[0]}", "EL {el:d}"):     # Attribute-, Type-, ValueError
        with pytest.raises(GridError, match="pattern"):
            add_levels(base, 1, 3.0, "up", pattern)


def test_negative_extend_in_a_block_is_clamped():
    d = good()
    d["extend"] = {"x_neg": -2.0, "x_pos": 1.0}
    g = grid_from_dict(d)
    assert g.extend == {"x_neg": 0.0, "x_pos": 1.0, "y_neg": 0.0, "y_pos": 0.0}


def test_default_grid():
    g = default_rect_grid("g1", "Grid 1", "imperial")
    assert g.x_text == "3@25'" and g.y_text == "2@20'" and g.x_names == ["A", "B", "C", "D"]
    assert g.levels[0].name == "EL 0'-0\"" and g.extend["x_neg"] == pytest.approx(5 * FT_M)
    m = default_rect_grid("g1", "Grid 1", "metric")
    assert m.x_text == "3@8" and m.levels[0].name == "EL 0.000 m"
