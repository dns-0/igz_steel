# SPDX-License-Identifier: GPL-3.0-or-later
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QMenu

from igz_steel._grid import Level, RectGrid, dump_block


class FakeViewport:
    def __init__(self):
        self.scene = SimpleNamespace(edit_group=None, selection=set(), layers=[], groups=[], version=0)
        self.history = SimpleNamespace(last_error=None, execute=lambda cmd: None)
        self.tool = None
        self.updates = 0

    def set_active_tool(self, tool):
        self.tool = tool

    def update(self):
        self.updates += 1

    def _world_to_pixel(self, v):
        return (v.x(), v.y())


class FakeApp:
    def __init__(self):
        self.window = None
        self.viewport = FakeViewport()
        self.registered = {}
        self.menu_actions = []
        self.context = []
        self.changed = []
        self._raw = None

    def document_data(self, default=None):
        return self._raw if self._raw is not None else default

    def set_document_data(self, value):
        self._raw = value
        for fn in self.changed:
            fn()

    def add_menu(self, title):
        return None

    def add_context_menu(self, fn):
        self.context.append(fn)

    def add_outliner_kind(self, fn):
        pass

    def on_document_changed(self, fn):
        self.changed.append(fn)

    def add_overlay(self, fn):
        self.registered["overlay"] = fn

    def add_snap_provider(self, fn):
        self.registered["snap"] = fn

    def add_pickable(self, pick, on_select=None, delete=None):
        self.registered["pick"] = (pick, on_select, delete)


@pytest.fixture
def session(qapp):
    from igz_steel import _core
    app = FakeApp()
    _core.setup(app)
    s = _core._SESSIONS[id(app)]
    yield s, app
    if s.grid_dialog_ is not None:
        s.grid_dialog_.close()
        s.grid_dialog_.deleteLater()
    qapp.processEvents()


def test_setup_registers_grid_hooks(session):
    s, app = session
    assert {"overlay", "snap", "pick"} <= set(app.registered)
    assert s.grids.grids == []


def test_apply_writes_block_and_dialog_reloads_on_change(session):
    s, app = session
    d = s.open_grids()
    d.x_spacing.setText("2@25'")
    d.apply_button.click()
    assert app._raw["grids"][0]["x"]["text"] == "2@25'"
    assert s.grids.grids[0].x_text == "2@25'"
    other = RectGrid(id="g9", name="Other", x_spacings=[1.0], y_spacings=[1.0], levels=[Level("L", 0.0)])
    app.set_document_data(dump_block([other], "g9", "imperial"))        # like Undo would
    assert d.grid_combo.currentText() == "Other" and "Reloaded" in d.status_label.text()


def test_pick_tools_round_trip(session):
    s, app = session
    d = s.open_grids()
    d.pick_origin_button.click()
    tool = app.viewport.tool
    assert type(tool).__name__ == "PickPointTool"
    tool.on_click(SimpleNamespace(viewport=app.viewport, world=QVector3D(1.0, 2.0, 3.0)))
    assert d.current_grid().origin == pytest.approx((1.0, 2.0, 3.0))
    d.pick_dir_button.click()
    tool = app.viewport.tool
    assert type(tool).__name__ == "PickDirectionTool"
    tool.on_click(SimpleNamespace(viewport=app.viewport, world=QVector3D(0, 0, 0)))
    tool.on_click(SimpleNamespace(viewport=app.viewport, world=QVector3D(0, 5, 0)))
    assert d.rotation_spin.value() == pytest.approx(90.0)


def test_context_menu_entries(session):
    s, app = session
    menu = QMenu()
    s.context_menu(menu, [])
    texts = [a.text() for a in menu.actions() if a.text()]
    assert "Steel grids…" in texts and "Edit grid…" not in texts
    d = s.open_grids()
    d.apply_button.click()
    s.grids.selected_id = "g1"
    menu = QMenu()
    s.context_menu(menu, [])
    texts = [a.text() for a in menu.actions() if a.text()]
    assert "Edit grid…" in texts and "Delete grid" in texts


def test_version_and_icons():
    import os
    import igz_steel
    from igz_steel import _core
    assert igz_steel.__version__ == "1.1.0"
    assert os.path.exists(os.path.join(_core._ICONS, "tb_grid.svg"))
    assert os.path.exists(os.path.join(_core._ICONS, "tb_grid_light.svg"))
