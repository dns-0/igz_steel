# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtGui import QImage, QVector3D

from igz_steel._grid import FT_M, GridError, Level, RadialGrid


@pytest.fixture
def radial(qapp):
    from igz_steel._grid_dialog import RadialDialog
    d = RadialDialog(None, "imperial", grid_id="g2", name="Tank")
    yield d
    d.close()
    d.deleteLater()
    qapp.processEvents()


def test_radial_dialog_builds_a_grid(radial):
    radial.center_x.setText("60'")
    radial.center_y.setText("0")
    radial.center_z.setText("100'")
    radial.radii_edit.setText("10', 2@15'")
    radial.radii_start.setText("A")
    radial.angles_edit.setText("6@30")
    radial.start_angle_spin.setValue(0.0)
    radial.angles_start.setText("1")
    radial.tangent_edit.setText("20'")
    radial.ext_in_edit.setText("5'")
    radial.ext_out_edit.setText("5'")
    radial.ext_arc_edit.setText("0")
    radial.bubbles_combo.setCurrentIndex(1)
    for e in (radial.center_x, radial.radii_edit, radial.angles_edit, radial.tangent_edit):
        e.editingFinished.emit()
    g = radial.result_grid()
    assert isinstance(g, RadialGrid) and g.id == "g2" and g.name == "Tank"
    assert g.origin == pytest.approx((60 * FT_M, 0.0, 30.48))
    assert g.radii == pytest.approx([10 * FT_M, 15 * FT_M, 15 * FT_M]) and g.radii_names == ["A", "B", "C"]
    assert g.steps_deg == [30.0] * 6 and g.angle_names == ["1", "2", "3", "4", "5", "6", "7"]
    assert g.tangent == pytest.approx(20 * FT_M) and g.extend["radial_in"] == pytest.approx(5 * FT_M)
    assert g.bubbles == "all" and g.levels[0].z == pytest.approx(30.48)
    assert radial.preview._grid is not None
    img = QImage(400, 300, QImage.Format_ARGB32)
    radial.preview.resize(400, 300)
    radial.preview.render(img)
    assert radial.preview._bubbles_px


def test_radial_dialog_reports_errors_and_prefills(radial):
    radial.angles_edit.setText("13@30")
    radial.angles_edit.editingFinished.emit()
    assert "360" in radial.status_label.text() and not radial.ok_button.isEnabled()
    with pytest.raises(GridError):
        radial.result_grid()
    from igz_steel._grid_dialog import RadialDialog
    g = RadialGrid(id="g5", name="Dome", radii=[3.0], radii_text="3", steps_deg=[45.0] * 8,
                   angles_text="8@45", tangent=1.0, levels=[Level("L", 2.0)])
    d = RadialDialog(None, "metric", grid=g)
    assert d.radii_edit.text() == "3" and d.angles_edit.text() == "8@45"
    assert d.tangent_edit.text() == "1.000 m" and d.result_grid().closed
    assert d.result_grid().levels[0].name == "L"
    d.set_center((1.0, 2.0, 3.0))
    assert d.result_grid().origin == pytest.approx((1.0, 2.0, 3.0))
    d.deleteLater()


def test_add_levels_dialog(qapp):
    from igz_steel._grid_dialog import AddLevelsDialog
    d = AddLevelsDialog(None, [Level("EL 100'-0\"", 30.48)], "imperial")
    d.count_spin.setValue(3)
    d.spacing_edit.setText("12'")
    d.direction_combo.setCurrentIndex(0)
    d.pattern_combo.setCurrentText("T.O.S. EL {el}")
    levels = d.result_levels()
    assert [lv.name for lv in levels][1:] == ["T.O.S. EL 112'-0\"", "T.O.S. EL 124'-0\"", "T.O.S. EL 136'-0\""]
    d.direction_combo.setCurrentIndex(1)
    d.count_spin.setValue(1)
    assert d.result_levels()[0].z == pytest.approx(30.48 - 12 * FT_M)
    d.spacing_edit.setText("x")
    with pytest.raises(GridError):
        d.result_levels()
    d.deleteLater()


def test_main_dialog_creates_and_edits_radial_grids(qapp):
    from igz_steel._grid_dialog import GridDialog
    d = GridDialog(None, units="imperial", persist=False)
    d.ask_text = lambda title, label, default: ("Tank", True)
    d.new_radial_button.click()
    rd = d._radial_dialog
    assert rd is not None and rd.isVisible() and not d.isEnabled()
    rd.radii_edit.setText("10', 15'")
    rd.angles_edit.setText("4@45")
    rd.radii_edit.editingFinished.emit()
    rd.ok_button.click()
    qapp.processEvents()
    assert d.isEnabled() and d.current_grid().kind == "radial" and d.current_grid().name == "Tank"
    assert d.grid_combo.count() == 2
    assert "10', 15'" in d.radial_summary.text()
    d.edit_radial_button.click()
    rd = d._radial_dialog
    rd.tangent_edit.setText("6'")
    rd.tangent_edit.editingFinished.emit()
    rd.ok_button.click()
    qapp.processEvents()
    assert d.current_grid().tangent == pytest.approx(6 * FT_M)
    d.edit_radial_button.click()
    d._radial_dialog.cancel_button.click()
    qapp.processEvents()
    assert d.isEnabled() and d.current_grid().tangent == pytest.approx(6 * FT_M)
    got = []
    d.pick_origin_requested.connect(lambda: got.append(1))
    d.edit_radial_button.click()
    d._radial_dialog.pick_center_button.click()
    assert got == [1]
    d.set_origin((5.0, 6.0, 7.0))
    assert d._radial_dialog.result_grid().origin == pytest.approx((5.0, 6.0, 7.0))
    d._radial_dialog.cancel_button.click()
    d.close()
    d.deleteLater()


class FakeViewport:
    def __init__(self):
        self.tool = "select"
        self.flashes = []

    def set_active_tool(self, tool):
        self.tool = tool

    def flash_status(self, text, msec):
        self.flashes.append(text)

    def update(self):
        pass


def ctx(vp, x, y, z=0.0):
    from tools.base import ToolContext
    return ToolContext(viewport=vp, world=QVector3D(x, y, z))


def test_pick_point_tool():
    from igz_steel._grid_dialog import PickPointTool
    got = []
    vp = FakeViewport()
    t = PickPointTool(got.append, previous="select")
    t.on_activate(vp)
    t.on_click(ctx(vp, 1.0, 2.0, 3.0))
    assert got == [(1.0, 2.0, 3.0)] and vp.tool == "select"
    t2 = PickPointTool(got.append, previous=None)
    t2.on_cancel(vp)
    assert vp.tool is None and len(got) == 1


def test_pick_direction_tool():
    from igz_steel._grid_dialog import PickDirectionTool
    got = []
    vp = FakeViewport()
    t = PickDirectionTool(got.append, previous="select")
    t.on_activate(vp)
    t.on_click(ctx(vp, 0.0, 0.0))
    assert t.start_point is not None and got == []
    t.on_hover(ctx(vp, 3.0, 3.0))
    assert len(t.rubber_band_lines()) == 1
    t.on_click(ctx(vp, 3.0, 3.0))
    assert got == pytest.approx([45.0]) and vp.tool == "select"
    t = PickDirectionTool(got.append, previous="select")
    t.on_click(ctx(vp, 0.0, 0.0))
    t.on_click(ctx(vp, 0.0, 0.0))                 # same point: ignored, still waiting
    assert len(got) == 1 and t.start_point is not None
    t.on_cancel(vp)
    assert t.start_point is None


def test_radial_dialog_keeps_stored_values_exact_through_display_rounding(qapp):
    from igz_steel._grid_dialog import RadialDialog
    g = RadialGrid(id="g5", name="Dome", origin=(1.23456789, 2.34567891, 3.45678912),
                   radii=[3.0], radii_text="3", steps_deg=[45.0] * 8, angles_text="8@45",
                   rotation_deg=12.3456789, start_deg=7.6543219, tangent=1.23456789,
                   extend={"radial_in": 0.123456789, "radial_out": 0.2345678912, "arc": 0.3456789123},
                   levels=[Level("L", 3.45678912)])
    d = RadialDialog(None, "metric", grid=g)
    d.bubbles_combo.setCurrentIndex(1)                   # an unrelated edit re-reads every field
    d.radii_edit.editingFinished.emit()
    out = d.result_grid()
    assert out.origin == g.origin and out.tangent == g.tangent and out.extend == g.extend
    assert out.rotation_deg == g.rotation_deg and out.start_deg == g.start_deg
    d.rotation_spin.setValue(30.0)
    d.start_angle_spin.setValue(-15.0)
    d.center_x.setText("4")
    d.center_x.editingFinished.emit()
    out = d.result_grid()
    assert out.rotation_deg == 30.0 and out.start_deg == -15.0 and out.origin[0] == 4.0
    assert out.origin[1:] == g.origin[1:]
    d.deleteLater()


def test_unit_switch_retexts_radial_radii(qapp):
    from igz_steel._grid_dialog import GridDialog
    d = GridDialog(None, units="imperial", persist=False)
    d.ask_text = lambda title, label, default: ("Tank", True)
    d.new_radial_button.click()
    rd = d._radial_dialog
    rd.radii_edit.setText("10, 15")
    rd.ok_button.click()
    qapp.processEvents()
    g = d.current_grid()
    before = list(g.radii)
    d.metric_radio.setChecked(True)
    assert g.radii_text == "3.048 m, 4.572 m" and g.radii == pytest.approx(before)
    d.close()
    d.deleteLater()


def test_set_center_clears_stale_errors(radial):
    radial.angles_edit.setText("13@30")
    radial.angles_edit.editingFinished.emit()
    assert not radial.ok_button.isEnabled()
    radial.set_center((1.0, 2.0, 3.0))
    assert radial.ok_button.isEnabled() and radial.status_label.text() == ""
    assert radial.angles_edit.styleSheet() == ""
    assert radial.result_grid().origin == pytest.approx((1.0, 2.0, 3.0))


def test_radial_renamed_lines_survive_typing(radial):
    radial.radii_edit.setText("20', 15', 15'")
    radial.angles_edit.setText("3@30")
    assert radial._grid.radii_names == ["A", "B", "C"]
    radial.preview.renamed.emit("radii", 2, "C-OUT")
    radial.preview.renamed.emit("angles", 3, "4-END")
    radial.radii_edit.setText("20', 15', ")
    radial.angles_edit.setText("2@30, ")
    assert radial._grid.radii_names == ["A", "B"] and radial._grid.angle_names == ["1", "2", "3"]
    radial.radii_edit.setText("20', 15', 18'")
    radial.angles_edit.setText("2@30, 40")
    assert radial._grid.radii_names == ["A", "B", "C-OUT"]
    assert radial._grid.angle_names == ["1", "2", "3", "4-END"]
    radial.radii_edit.editingFinished.emit()
    radial.radii_start.setText("P")                         # a changed start regenerates and commits
    radial.radii_start.editingFinished.emit()
    radial.radii_edit.setText("20', 15', 18', 9'")
    assert radial._grid.radii_names == ["P", "Q", "R", "S"]


def test_enter_presses_no_button_in_sub_dialogs(qapp, radial):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    from igz_steel._grid_dialog import AddLevelsDialog
    picks = []
    radial.pick_center_requested.connect(lambda: picks.append(1))
    radial.show()
    qapp.processEvents()
    radial.radii_edit.setFocus()
    QTest.keyClick(radial.radii_edit, Qt.Key_Return)
    qapp.processEvents()
    assert picks == [] and radial.isVisible()
    d = AddLevelsDialog(None, [Level("L", 0.0)], "imperial")
    for dlg in (radial, d):
        assert not any(b.autoDefault() or b.isDefault() for b in dlg.findChildren(QPushButton))
    d.deleteLater()


def test_reopening_radial_dialog_replaces_the_open_one(qapp):
    from igz_steel._grid_dialog import GridDialog
    d = GridDialog(None, units="imperial", persist=False)
    d.ask_text = lambda title, label, default: ("Tank", True)
    d.new_radial_button.click()
    first = d._radial_dialog
    d._open_radial(None)
    assert not first.isVisible()
    qapp.processEvents()
    second = d._radial_dialog
    assert second is not None and second is not first and second.isVisible()
    assert not d.isEnabled() and d.grid_combo.count() == 1
    second.cancel_button.click()
    qapp.processEvents()
    assert d.isEnabled() and d._radial_dialog is None
    d.close()
    d.deleteLater()
