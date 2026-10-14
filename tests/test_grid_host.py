# SPDX-License-Identifier: GPL-3.0-or-later
import math
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage, QPainter, QPalette, QVector3D

from igz_steel._grid import Level, RectGrid, dump_block

FT = 0.3048


class FakeViewport:
    snap_threshold_px = 10.0

    def __init__(self):
        self.scene = SimpleNamespace(edit_group=None, version=0)
        self.camera = SimpleNamespace(yaw=0.0, pitch=0.0, distance=10.0, perspective=False,
                                      target=QVector3D(0, 0, 0))
        self.updates = 0

    def _world_to_pixel(self, v):           # crude oblique projection, enough for pixels
        return (100.0 + v.x() * 10.0, 300.0 - v.y() * 10.0 - v.z() * 10.0)

    def width(self):
        return 800

    def height(self):
        return 600

    def update(self):
        self.updates += 1

    def palette(self):
        return QPalette()

    def backgroundRole(self):
        return QPalette.Window


class FakeApp:
    def __init__(self, raw=None):
        self._raw = raw
        self.viewport = FakeViewport()
        self.registered = {}
        self.sets = []

    def document_data(self, default=None):
        return self._raw if self._raw is not None else default

    def set_document_data(self, value):
        self.sets.append(value)
        self._raw = value

    def add_overlay(self, fn):
        self.registered["overlay"] = fn

    def add_snap_provider(self, fn):
        self.registered["snap"] = fn

    def add_pickable(self, pick, on_select=None, delete=None):
        self.registered["pick"] = (pick, on_select, delete)


def block(*grids, active="g1", units="imperial"):
    return dump_block(list(grids), active, units)


def main_grid(**kw):
    base = dict(id="g1", name="Main", x_spacings=[7.62], y_spacings=[6.096],
                extend={"x_neg": 1.0, "x_pos": 1.0, "y_neg": 1.0, "y_pos": 1.0},
                levels=[Level("EL 100", 0.0), Level("EL 112", 12 * FT)])
    base.update(kw)
    return RectGrid(**base)


def world_px(vp, p):
    return vp._world_to_pixel(QVector3D(*p))


@pytest.fixture
def store():
    from igz_steel._grid_host import GridStore
    app = FakeApp(block(main_grid()))
    return GridStore(app), app


def test_reload_reads_block_and_skips_bad_grids():
    from igz_steel._grid_host import GridStore
    raw = block(main_grid())
    raw["grids"].append({"id": "g2", "kind": "rect", "x": {}})
    s = GridStore(FakeApp(raw))
    assert [g.id for g in s.grids] == ["g1"] and len(s.errors) == 1
    assert s.raw_block()["grids"][0]["id"] == "g1"
    assert GridStore(FakeApp(None)).grids == []


def test_snap_hits_nearest_node_on_any_level(store):
    s, app = store
    vp = app.viewport
    target = (7.62, 6.096, 12 * FT)                    # B-2 on the upper level
    px, py = world_px(vp, target)
    res = s.snap(vp, SimpleNamespace(point=QVector3D(0, 0, 0)), px + 3, py - 2)
    assert res is not None and res.label == "B-2 · EL 112" and res.kind == "reference"
    assert (res.point.x(), res.point.y(), res.point.z()) == pytest.approx(target)
    assert s.snap(vp, SimpleNamespace(point=QVector3D(0, 0, 0)), px + 40, py) is None


def test_snap_tip_names_grid_when_several_exist():
    from igz_steel._grid_host import GridStore
    other = main_grid(id="g2", name="Rack", origin=(50.0, 0.0, 0.0))
    s = GridStore(FakeApp(block(main_grid(), other)))
    vp = s.app.viewport
    px, py = world_px(vp, (0.0, 0.0, 0.0))
    res = s.snap(vp, SimpleNamespace(point=QVector3D(0, 0, 0)), px, py)
    assert res.label == "Main A-1 · EL 100"


def test_snap_is_silent_while_editing_or_hidden(store):
    s, app = store
    vp = app.viewport
    px, py = world_px(vp, (0.0, 0.0, 0.0))
    vp.scene.edit_group = object()
    assert s.snap(vp, SimpleNamespace(point=QVector3D()), px, py) is None
    vp.scene.edit_group = None
    s.grids[0].visible = False
    s.invalidate()
    assert s.snap(vp, SimpleNamespace(point=QVector3D()), px, py) is None


def test_snap_never_raises(store):
    s, app = store
    assert s.snap(None, None, None, None) is None


def test_projection_cache_follows_camera_and_data(store):
    s, app = store
    vp = app.viewport
    first = s.nodes_px(vp)
    assert len(first) == 8 and s.nodes_px(vp) is first
    vp.camera.yaw = 0.5
    assert s.nodes_px(vp) is not first
    again = s.nodes_px(vp)
    s.invalidate()
    assert s.nodes_px(vp) is not again


def test_paint_runs_offscreen_with_and_without_batch_projection(qapp, store):
    s, app = store
    vp = app.viewport
    img = QImage(800, 600, QImage.Format_ARGB32)
    painter = QPainter(img)
    s.paint(vp, painter)
    painter.end()
    assert not s._overlay_failed

    def world_to_pixels(points):
        px = [100.0 + p[0] * 10.0 for p in points]
        py = [300.0 - p[1] * 10.0 - p[2] * 10.0 for p in points]
        return px, py, [True] * len(points)
    app.world_to_pixels = world_to_pixels
    s.invalidate()
    painter = QPainter(img)
    s.paint(vp, painter)
    painter.end()
    assert not s._overlay_failed

    app.world_to_pixels = lambda pts: (_ for _ in ()).throw(RuntimeError("boom"))
    s.invalidate()
    assert len(s.nodes_px(vp)) == 8                   # fell back to the per-point helper


def test_paint_error_disables_overlay_once(qapp, store):
    s, app = store
    s.grids[0].lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad"))
    img = QImage(80, 60, QImage.Format_ARGB32)
    painter = QPainter(img)
    s.paint(app.viewport, painter)
    s.paint(app.viewport, painter)
    painter.end()
    assert s._overlay_failed


def test_pick_select_and_delete(qapp, store):
    s, app = store
    vp = app.viewport
    g = s.grids[0]
    cx, cy, _bubble = s.bubble_centres(vp, g)[0]
    assert s.pick(vp, cx + 2, cy - 2) == "g1"
    assert s.pick(vp, cx + 60, cy) is None
    s.on_select("g1")
    assert s.selected_id == "g1" and vp.updates >= 1
    s.on_select(None)
    assert s.selected_id is None
    s.confirm = lambda grid: False
    s.delete("g1")
    assert app.sets == []
    s.confirm = lambda grid: True
    s.delete("g1")
    assert app.sets[-1]["grids"] == [] and app.sets[-1]["active_grid"] is None
    assert s.grids == []


def test_double_pick_requests_edit(store):
    s, app = store
    got = []
    s.on_edit_request = got.append
    s.on_select("g1")
    s.on_select("g1")
    assert got == ["g1"]


def test_register_guards_missing_api():
    from igz_steel._grid_host import GridStore
    app = FakeApp(block(main_grid()))
    del FakeApp.add_pickable
    try:
        s = GridStore(app)
        s.register()
        assert "overlay" in app.registered and "snap" in app.registered and "pick" not in app.registered
    finally:
        FakeApp.add_pickable = lambda self, pick, on_select=None, delete=None: self.registered.__setitem__("pick", (pick, on_select, delete))
    app = FakeApp(block(main_grid()))
    GridStore(app).register()
    assert "pick" in app.registered
