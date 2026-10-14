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


def test_unrelated_document_change_keeps_dialog_edits(session):
    import copy
    s, app = session
    d = s.open_grids()
    d.apply_button.click()
    assert "Reloaded" not in d.status_label.text() and d.status_label.text() == ""
    d.x_spacing.setText("5@10'")                                        # not applied yet
    app.set_document_data(copy.deepcopy(app._raw))                     # e.g. a member edit
    for fn in app.changed:                                             # e.g. a selection click
        fn()
    assert d.x_spacing.text() == "5@10'" and d.status_label.text() == ""
    assert d.current_grid().x_spacings == pytest.approx([10 * 0.3048] * 5)


def test_own_apply_refreshes_quietly_and_keeps_the_view(session):
    s, app = session
    d = s.open_grids()
    d.preview._fit_pending = False
    d.preview._scale = 3.25
    d.x_spacing.setText("2@25'")
    d.apply_button.click()
    assert d.status_label.text() == "" and not d.preview._fit_pending
    assert d.preview._scale == 3.25 and d.x_spacing.text() == "2@25'"
    other = RectGrid(id="g9", name="Other", x_spacings=[1.0], y_spacings=[1.0], levels=[Level("L", 0.0)])
    app.set_document_data(dump_block([other], "g9", "imperial"))
    assert "Reloaded" in d.status_label.text() and d.preview._fit_pending


def test_viewport_delete_reaches_the_dialog_when_the_hook_runs_later(session):
    s, app = session
    d = s.open_grids()
    d.ask_text = lambda title, label, default: ("Rack", True)
    d.new_rect_button.click()
    d.apply_button.click()
    assert d.grid_combo.count() == 2
    hooks, app.changed = app.changed, []                               # a host that fires the hook later
    s.grids.confirm = lambda grid: True
    s.grids.delete(s.grids.grids[-1].id)
    for fn in hooks:
        fn()
    assert d.grid_combo.count() == 1 and "Reloaded" in d.status_label.text()
    d.x_spacing.setText("5@10'")
    for fn in hooks:                                                   # nothing new: edits stay
        fn()
    assert d.x_spacing.text() == "5@10'"


def test_grid_guard_message(session, monkeypatch):
    from igz_steel import _core
    s, app = session
    shown = []
    monkeypatch.setattr(_core.QMessageBox, "information",
                        lambda parent, title, text: shown.append(text))
    app.viewport.scene.edit_group = object()
    s.on_grids_applied(s.grids.raw_block())
    assert shown == ["Close the group you are editing before changing grids."]
    assert app._raw is None


def test_chained_picks_restore_the_original_tool(session):
    s, app = session
    d = s.open_grids()
    app.viewport.tool = "select"
    d.pick_origin_button.click()
    assert type(app.viewport.tool).__name__ == "PickPointTool"
    d.pick_dir_button.click()                                          # before finishing the origin pick
    tool = app.viewport.tool
    assert type(tool).__name__ == "PickDirectionTool" and tool.previous == "select"
    tool.on_click(SimpleNamespace(viewport=app.viewport, world=QVector3D(0, 0, 0)))
    tool.on_click(SimpleNamespace(viewport=app.viewport, world=QVector3D(1, 1, 0)))
    assert app.viewport.tool == "select"


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
