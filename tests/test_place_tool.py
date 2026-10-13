# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtGui import QVector3D

from igz_steel import _db, _host
from igz_steel._tools import PlaceMemberTool, xyz


class FakeViewport:
    def __init__(self):
        self.updates = 0
        self.flashes = []
        self.tool = "place"

    def update(self):
        self.updates += 1

    def flash_status(self, text, msec=2500):
        self.flashes.append(text)

    def set_active_tool(self, tool):
        self.tool = tool


class Ctx:
    def __init__(self, vp, p):
        self.viewport = vp
        self.world = QVector3D(*p)


@pytest.fixture
def tool():
    shape = _db.load().find("W12X26")
    params = _host.new_params("W12X26", "imperial", "centroid", 0.0, False, 24)
    calls = {"member": [], "profile": []}

    def on_member(start, direction, length):
        calls["member"].append((start, direction, length))
        return True

    def on_profile(start):
        calls["profile"].append(start)
        return True
    t = PlaceMemberTool(shape, params, on_member, on_profile)
    t.calls = calls
    return t


def test_xyz_accepts_vectors_and_tuples():
    assert xyz(QVector3D(1, 2, 3)) == (1.0, 2.0, 3.0)
    assert xyz((1, 2, 3)) == (1.0, 2.0, 3.0)


def test_two_clicks_make_a_member(tool):
    vp = FakeViewport()
    tool.on_activate(vp)
    assert tool.start_point is None and tool.vcb_label == "Length"
    tool.on_hover(Ctx(vp, (0, 0, 0)))
    tool.on_click(Ctx(vp, (1, 2, 3)))
    assert isinstance(tool.start_point, QVector3D) and xyz(tool.start_point) == (1, 2, 3)
    tool.on_hover(Ctx(vp, (4, 2, 3)))
    tool.on_click(Ctx(vp, (4, 2, 3)))
    assert tool.calls["member"] == [((1.0, 2.0, 3.0), pytest.approx((1, 0, 0)), pytest.approx(3.0))]
    assert tool.start_point is None                     # ready for the next member
    assert vp.updates >= 2


def test_second_click_on_the_start_is_ignored(tool):
    vp = FakeViewport()
    tool.on_click(Ctx(vp, (1, 1, 1)))
    tool.on_click(Ctx(vp, (1, 1, 1)))
    assert tool.calls["member"] == [] and tool.start_point is not None


def test_typed_length_extends_the_hover_direction(tool):
    vp = FakeViewport()
    assert tool.on_value(vp, 2.0) is False               # nothing started yet
    tool.on_click(Ctx(vp, (0, 0, 0)))
    assert tool.on_value(vp, 2.0) is False               # no hover direction yet
    tool.on_hover(Ctx(vp, (0, 1, 0)))
    assert tool.on_value(vp, 3.6576) is True
    start, d, L = tool.calls["member"][-1]
    assert d == pytest.approx((0, 1, 0)) and L == pytest.approx(3.6576)
    tool.on_click(Ctx(vp, (0, 0, 0)))
    tool.on_hover(Ctx(vp, (0, 1, 0)))
    assert tool.on_value(vp, -2.0) is True               # negative flips
    assert tool.calls["member"][-1][1] == pytest.approx((0, -1, 0))
    assert tool.calls["member"][-1][2] == pytest.approx(2.0)


def test_rejected_values_commit_nothing(tool):
    vp = FakeViewport()
    tool.on_click(Ctx(vp, (0, 0, 0)))
    tool.on_hover(Ctx(vp, (1, 0, 0)))
    assert tool.on_value(vp, 0.0) is False
    assert tool.on_value(vp, 0.0004) is False            # under MIN_LENGTH
    assert tool.on_value(vp, 5000.0) is False            # over MAX_LENGTH
    assert tool.on_value(vp, (1.0, 2.0)) is False        # rectangle-style tuple
    assert tool.on_value(vp, "abc") is False
    tool.on_hover(Ctx(vp, (0, 0, 0)))                    # hover back on the start
    assert tool.on_value(vp, 2.0) is False
    assert tool.calls["member"] == [] and tool.start_point is not None


def test_typed_offset_triplet(tool):
    vp = FakeViewport()
    tool.on_click(Ctx(vp, (1, 1, 1)))
    assert tool.on_value(vp, (0.0, 0.0, 2.0)) is True
    assert tool.calls["member"][-1] == ((1.0, 1.0, 1.0), pytest.approx((0, 0, 1)), pytest.approx(2.0))


def test_escape_after_start_places_a_profile_and_before_start_leaves(tool):
    vp = FakeViewport()
    tool.on_click(Ctx(vp, (2, 2, 0)))
    tool.on_cancel(vp)
    assert tool.calls["profile"] == [(2.0, 2.0, 0.0)] and tool.start_point is None
    tool.on_cancel(vp)
    assert vp.tool is None


def test_preview_lines(tool):
    vp = FakeViewport()
    n = len(tool.profile.regions[0].outer.points)
    assert tool.rubber_band_lines() == []
    tool.on_hover(Ctx(vp, (0, 0, 0)))
    lines = tool.rubber_band_lines()
    assert len(lines) == n and isinstance(lines[0][0], QVector3D)
    tool.on_click(Ctx(vp, (0, 0, 0)))
    tool.on_hover(Ctx(vp, (0, 0, 0)))
    assert len(tool.rubber_band_lines()) == n            # degenerate: outline only
    tool.on_hover(Ctx(vp, (5, 0, 0)))
    assert len(tool.rubber_band_lines()) == 3 * n
    assert "W12X26" in tool.status_clause()


def test_commit_failure_keeps_the_start(tool):
    vp = FakeViewport()
    tool.on_member = lambda s, d, L: False
    tool.on_click(Ctx(vp, (0, 0, 0)))
    tool.on_click(Ctx(vp, (1, 0, 0)))
    assert tool.start_point is not None
