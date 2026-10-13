# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtWidgets import QMainWindow, QMenu

from igz_steel import _core, _host, KEY


class FakeViewport:
    def __init__(self, scene, history):
        self.scene, self.history = scene, history
        self.tool = None
        self.flashes = []

    def set_active_tool(self, tool):
        self.tool = tool

    def update(self):
        pass

    def notify_scene_changed(self):
        pass

    def flash_status(self, text, msec=2500):
        self.flashes.append(text)


class FakeApp:
    def __init__(self, window, scene, history):
        self.key = KEY
        self.window = window
        self.viewport = FakeViewport(scene, history)
        self._scene = scene
        self.menus, self.actions, self.context_fns, self.outliner_fns, self.doc_fns = [], [], [], [], []

    @property
    def scene(self):
        return self._scene

    def add_menu(self, title):
        m = QMenu(title, self.window)
        self.menus.append(m)
        return m

    def add_menu_action(self, text, fn, shortcut=None, tip=None):
        self.actions.append((text, fn))

    def add_context_menu(self, fn):
        self.context_fns.append(fn)

    def add_outliner_kind(self, fn):
        self.outliner_fns.append(fn)

    def on_document_changed(self, fn):
        self.doc_fns.append(fn)


class FakeBox:
    messages = []

    @classmethod
    def information(cls, parent, title, text):
        cls.messages.append(("info", text))

    @classmethod
    def critical(cls, parent, title, text):
        cls.messages.append(("error", text))

    warning = critical


@pytest.fixture
def app(qapp, monkeypatch):
    from core.scene import Scene
    from core.history import History
    monkeypatch.setattr(_core, "QMessageBox", FakeBox)
    FakeBox.messages = []
    scene = Scene()
    window = QMainWindow()
    fake = FakeApp(window, scene, History(scene))
    _core.setup(fake)
    fake.session = _core._SESSIONS[id(fake)]
    yield fake
    window.close()


def test_setup_registers_ui(app):
    assert [m.title() for m in app.menus] == ["Steel"]
    titles = [a.text() for a in app.menus[0].actions() if not a.isSeparator()]
    assert titles[:4] == ["Place member…", "Stretch member", "Edit member…", "Bill of Materials…"]
    assert len(app.context_fns) == 1 and len(app.outliner_fns) == 1 and len(app.doc_fns) == 1
    from PySide6.QtWidgets import QToolBar
    assert app.window.findChild(QToolBar, "igz_steel_toolbar") is not None


def test_place_flow_inserts_a_member_with_layer(app):
    s = app.session
    s.on_place({"label": "W12X26", "unit_system": "imperial", "insertion": "top", "roll": 0.0,
                "fillets": True, "segments": 24, "layer": "Beams", "length": 0.0})
    tool = app.viewport.tool
    assert tool is not None and tool.name == "Place steel member"
    assert tool.on_member((0, 0, 0), (1, 0, 0), 3.0) is True
    groups = [g for g in app.scene.groups if _host.is_steel_group(g)]
    assert len(groups) == 1 and groups[0].layer == "Beams" and groups[0].ifc["class"] == "IfcBeam"
    assert app.scene.layer("Beams") is not None
    assert tool.on_profile((5, 5, 0)) is True
    assert len([g for g in app.scene.groups if _host.is_steel_group(g)]) == 2
    assert app.scene.groups[-1].name == "W12X26 (profile)"


def test_edit_and_stretch_need_exactly_one_member(app):
    s = app.session
    assert s.single_selected() is None
    assert FakeBox.messages and FakeBox.messages[-1][0] == "info"
    s.on_place({"label": "HSS6X6X1/2", "unit_system": "imperial", "insertion": "centroid",
                "roll": 0.0, "fillets": True, "segments": 24, "layer": "", "length": 0.0})
    app.viewport.tool.on_member((0, 0, 0), (0, 0, 1), 4.0)
    g = app.scene.groups[-1]
    app.scene.selection = {g}
    assert s.single_selected() is g
    s.open_stretch()
    assert app.viewport.tool.name == "Stretch steel member"
    assert app.viewport.tool.on_commit((0, 0, 0), (0, 0, 1), 6.0) is True
    assert _host.member_params(g)["length"] == 6.0
    s.open_edit()
    assert s.dialog.mode == "edit" and s.dialog.current_shape().label == "HSS6X6X1/2"
    s.on_update({"label": "W12X26", "unit_system": "imperial", "insertion": "centroid",
                 "roll": 90.0, "fillets": False, "segments": 24, "layer": "Columns", "length": 2.0})
    p = _host.member_params(g)
    assert p["label"] == "W12X26" and p["length"] == 2.0 and p["roll"] == 90.0
    assert g.layer == "Columns" and g.name == "W12X26"
    assert _host.member_endpoints(g)[1] == pytest.approx((0, 0, 2))


def test_open_container_is_refused(app):
    s = app.session
    from core.group import Group
    app.scene.edit_group = Group(name="open")
    s.on_place({"label": "W12X26", "unit_system": "imperial", "insertion": "centroid",
                "roll": 0.0, "fillets": True, "segments": 24, "layer": "", "length": 0.0})
    assert app.viewport.tool.on_member((0, 0, 0), (1, 0, 0), 3.0) is False
    assert FakeBox.messages[-1][0] == "info" and not app.scene.groups


def test_context_menu_outliner_and_bom(app):
    s = app.session
    s.on_place({"label": "W12X26", "unit_system": "imperial", "insertion": "centroid",
                "roll": 0.0, "fillets": True, "segments": 24, "layer": "", "length": 0.0})
    app.viewport.tool.on_member((0, 0, 0), (1, 0, 0), 3.0)
    g = app.scene.groups[-1]
    menu = QMenu()
    s.context_menu(menu, [g])
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == \
        ["Edit steel member…", "Stretch steel member"]
    empty = QMenu()
    s.context_menu(empty, [])
    assert empty.actions() == []
    kind = s.outliner_kind(g)
    assert kind["type"] == "Steel member" and ("Shape", "W12X26") in kind["props"]
    from core.group import Group
    assert s.outliner_kind(Group(name="x")) is None
    bom = s.collect_bom()
    assert bom.count == 1 and bom.rows[0].label == "W12X26"
    s.select_uid(g.uid)
    assert app.scene.selection == {g}
    s.open_bom()
    assert s.bom_dialog.rows_table.rowCount() == 1
    s.on_document_changed()


def test_load_icon_has_pixmap(qapp):
    from PySide6.QtWidgets import QWidget
    icon = _core.load_icon("tb_place", QWidget())
    assert not icon.isNull()


def test_edit_and_stretch_keep_a_member_where_the_host_moved_it(app):
    from PySide6.QtGui import QMatrix4x4, QVector3D
    s = app.session
    s.on_place({"label": "W12X26", "unit_system": "imperial", "insertion": "centroid",
                "roll": 0.0, "fillets": True, "segments": 24, "layer": "", "length": 0.0})
    app.viewport.tool.on_member((0, 0, 0), (1, 0, 0), 3.0)
    g = app.scene.groups[-1]
    moved = QMatrix4x4()
    moved.translate(0.0, 10.0, 0.0)
    g.xform = moved * g.xform                      # Move tool
    rot = QMatrix4x4()
    rot.rotate(30.0, 1.0, 0.0, 0.0)
    g.xform = g.xform * rot                        # Rotate about the axis
    app.scene.selection = {g}
    s.open_edit()
    assert s.dialog.roll_spin.value() == pytest.approx(30.0, abs=1e-6)
    s.on_update({"label": "W12X26", "unit_system": "imperial", "insertion": "centroid",
                 "roll": 30.0, "fillets": True, "segments": 24, "layer": "", "length": 5.0})
    assert _host.member_endpoints(g) == (pytest.approx((0, 10, 0)), pytest.approx((5, 10, 0)))
    app.scene.selection = {g}
    s.open_stretch()
    assert app.viewport.tool.on_commit((0, 10, 0), (1, 0, 0), 2.0) is True
    up = g.xform.map(QVector3D(0, 0, 1)) - g.xform.map(QVector3D(0, 0, 0))
    assert (up.y(), up.z()) == pytest.approx((-0.5, 0.8660254), abs=1e-6)   # roll kept


def test_menu_entries_survive_a_checked_argument(app, qapp):
    hits = []
    fn = _core._deferred(lambda: hits.append(1))
    fn(True)                                        # a triggered(bool) delivered to the slot
    fn()
    qapp.processEvents()
    assert hits == [1, 1]
    for a in app.menus[0].actions():
        if not a.isSeparator() and a.text() != "Show steel toolbar":
            a.trigger()
    qapp.processEvents()
