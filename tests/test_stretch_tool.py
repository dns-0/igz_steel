# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtGui import QVector3D

from igz_steel import _db, _host
from igz_steel._tools import StretchMemberTool, xyz


class FakeViewport:
    def __init__(self):
        self.tool = "stretch"

    def update(self):
        pass

    def flash_status(self, text, msec=2500):
        pass

    def set_active_tool(self, tool):
        self.tool = tool


class Ctx:
    def __init__(self, vp, p):
        self.viewport = vp
        self.world = QVector3D(*p)


def _member(length, direction=(1, 0, 0), start=(1, 2, 3)):
    shape = _db.load().find("W12X26")
    params = _host.new_params("W12X26", "imperial", "centroid", 0.0, False, 24)
    g = _host.make_group(_host.member_parts(shape, params, start, direction, length))
    calls = []

    def on_commit(fixed, d, L):
        calls.append((fixed, d, L))
        return True
    t = StretchMemberTool(g, shape, _host.member_params(g), on_commit)
    t.calls = calls
    return t


def test_grip_near_the_end_stretches_from_the_start():
    t = _member(3.0)
    vp = FakeViewport()
    assert t.rubber_band_lines() and t.start_point is None      # grips drawn while idle
    t.on_click(Ctx(vp, (3.9, 2.1, 3)))                          # near the end (4,2,3)
    assert xyz(t.start_point) == pytest.approx((1, 2, 3))
    t.on_hover(Ctx(vp, (10, 7, 3)))                             # off axis: projected
    t.on_click(Ctx(vp, (10, 7, 3)))
    assert t.calls == [(pytest.approx((1, 2, 3)), pytest.approx((1, 0, 0)), pytest.approx(9.0))]
    assert t.start_point is None


def test_grip_near_the_start_stretches_from_the_end_and_can_flip():
    t = _member(3.0)
    vp = FakeViewport()
    t.on_click(Ctx(vp, (1.1, 2, 3)))                            # near the start (1,2,3)
    assert xyz(t.start_point) == pytest.approx((4, 2, 3))
    t.on_click(Ctx(vp, (-2, 2, 3)))                             # behind the start: grows left
    assert t.calls[-1] == (pytest.approx((4, 2, 3)), pytest.approx((-1, 0, 0)), pytest.approx(6.0))
    t.refresh()
    t.on_click(Ctx(vp, (1.1, 2, 3)))
    t.on_click(Ctx(vp, (6, 2, 3)))                              # past the fixed end: flips
    assert t.calls[-1] == (pytest.approx((4, 2, 3)), pytest.approx((1, 0, 0)), pytest.approx(2.0))


def test_typed_length_from_the_fixed_end():
    t = _member(3.0)
    vp = FakeViewport()
    assert t.on_value(vp, 2.0) is False                         # no grip yet
    t.on_click(Ctx(vp, (4, 2, 3)))
    assert t.on_value(vp, 2.5) is True
    assert t.calls[-1] == (pytest.approx((1, 2, 3)), pytest.approx((1, 0, 0)), pytest.approx(2.5))
    t.on_click(Ctx(vp, (4, 2, 3)))
    assert t.on_value(vp, -1.0) is True
    assert t.calls[-1][1] == pytest.approx((-1, 0, 0))
    t.on_click(Ctx(vp, (4, 2, 3)))
    assert t.on_value(vp, 0.0) is False and t.on_value(vp, (1, 2, 3)) is False
    assert t.on_value(vp, 5000.0) is False


def test_profile_object_has_a_free_direction():
    t = _member(0.0)
    vp = FakeViewport()
    t.on_click(Ctx(vp, (1, 2, 3)))
    assert xyz(t.start_point) == pytest.approx((1, 2, 3))
    t.on_hover(Ctx(vp, (1, 2, 8)))
    assert len(t.rubber_band_lines()) > 0
    t.on_click(Ctx(vp, (1, 2, 8)))
    assert t.calls[-1] == (pytest.approx((1, 2, 3)), pytest.approx((0, 0, 1)), pytest.approx(5.0))
    t.on_click(Ctx(vp, (1, 2, 3)))
    assert t.on_value(vp, 2.0) is False                         # no hover direction yet
    t.on_hover(Ctx(vp, (2, 2, 3)))
    assert t.on_value(vp, 2.0) is True
    assert t.calls[-1][1] == pytest.approx((1, 0, 0))


def test_escape_cancels_the_grip_then_leaves():
    t = _member(3.0)
    vp = FakeViewport()
    t.on_click(Ctx(vp, (4, 2, 3)))
    t.on_cancel(vp)
    assert t.start_point is None and t.calls == [] and vp.tool == "stretch"
    t.on_cancel(vp)
    assert vp.tool is None


def test_preview_follows_projection():
    t = _member(3.0)
    vp = FakeViewport()
    idle = len(t.rubber_band_lines())
    t.on_click(Ctx(vp, (4, 2, 3)))
    t.on_hover(Ctx(vp, (7, 9, 3)))
    lines = t.rubber_band_lines()
    assert len(lines) > idle
    xs = {round(v.x(), 6) for a, b in lines for v in (a, b)}
    assert max(xs) == pytest.approx(7.0) and min(xs) >= 0.9     # grip crosses extend 0.06 m
    assert "W12X26" in t.status_clause()
