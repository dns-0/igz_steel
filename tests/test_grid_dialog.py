# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtGui import QImage

from igz_steel._grid import FT_M, Level, RectGrid, dump_block


@pytest.fixture
def dialog(qapp):
    from igz_steel._grid_dialog import GridDialog
    d = GridDialog(None, units="imperial", persist=False)
    d.confirm = lambda title, text: True
    yield d
    d.close()
    d.deleteLater()
    qapp.processEvents()


def main_block():
    g = RectGrid(id="g1", name="Main", origin=(0.0, 0.0, 30.48),
                 x_text="25', 30'", x_spacings=[25 * FT_M, 30 * FT_M],
                 y_text="20'", y_spacings=[20 * FT_M],
                 extend={k: 5 * FT_M for k in ("x_neg", "x_pos", "y_neg", "y_pos")},
                 levels=[Level("EL 100'-0\"", 30.48), Level("EL 112'-0\"", 34.1376)])
    return dump_block([g], "g1", "imperial")


def test_empty_document_shows_a_default_grid(dialog):
    assert dialog.grid_combo.count() == 1 and dialog.current_grid().kind == "rect"
    assert dialog.levels_table.rowCount() == 1
    assert dialog.x_spacing.text() == "3@25'" and dialog.apply_button.isEnabled()
    assert dialog.preview._grid is dialog.current_grid()


def test_bad_spacing_disables_apply_and_shows_message(dialog):
    dialog.x_spacing.setText("3@")
    assert not dialog.apply_button.isEnabled()
    assert "after @" in dialog.status_label.text()
    assert dialog.preview._grid.x_spacings == pytest.approx([25 * FT_M] * 3)   # last good state kept
    dialog.x_spacing.setText("25', 3@30', 25'")
    assert dialog.apply_button.isEnabled() and dialog.status_label.text() == ""


def test_apply_emits_block(dialog):
    got = []
    dialog.applied.connect(got.append)
    dialog.x_spacing.setText("25', 3@30', 25'")
    dialog.y_spacing.setText("4@20'")
    dialog.origin_z.setText("100'")
    dialog.origin_z.editingFinished.emit()
    dialog.rotation_spin.setValue(30.0)
    dialog.extend_edit.setText("5'")
    dialog.extend_edit.editingFinished.emit()
    dialog.apply_button.click()
    assert len(got) == 1
    g = got[0]["grids"][0]
    assert g["x"]["spacings"] == pytest.approx([25 * FT_M] + [30 * FT_M] * 3 + [25 * FT_M])
    assert g["x"]["names"] == ["A", "B", "C", "D", "E", "F"] and g["y"]["names"] == ["1", "2", "3", "4", "5"]
    assert g["origin"][2] == pytest.approx(30.48) and g["levels"][0]["z"] == pytest.approx(30.48)
    assert g["rotation_deg"] == 30.0 and g["extend"]["y_pos"] == pytest.approx(5 * FT_M)
    assert got[0]["units"] == "imperial" and got[0]["active_grid"] == "g1"


def test_load_block_fills_fields_and_units_switch_reformats(dialog):
    dialog.load_block(main_block())
    assert dialog.grid_combo.currentText() == "Main"
    assert dialog.x_spacing.text() == "25', 30'" and dialog.levels_table.rowCount() == 2
    assert dialog.levels_table.item(0, 1).text() == "100'-0\""
    assert dialog.origin_z.text() == "100'-0\""
    dialog.metric_radio.setChecked(True)
    assert dialog.levels_table.item(0, 1).text() == "30.480 m" and dialog.units() == "metric"
    assert dialog.block()["units"] == "metric"
    dialog.load_block(main_block())                       # the block's units win on load
    assert dialog.units() == "imperial"


def test_start_change_regenerates_and_rename_survives_spacing_change(dialog):
    dialog.x_start.setText("C")
    dialog.x_start.editingFinished.emit()
    assert dialog.current_grid().x_names == ["C", "D", "E", "F"]
    dialog.preview.renamed.emit("x", 1, "D.5")
    assert dialog.current_grid().x_names[1] == "D.5"
    dialog.x_spacing.setText("4@25'")
    assert dialog.current_grid().x_names == ["C", "D.5", "E", "F", "G"]
    dialog.swap_button.click()
    assert dialog.current_grid().x_start == "1" and dialog.current_grid().y_start == "C"
    assert dialog.current_grid().x_names == ["1", "2", "3", "4", "5"]


def test_levels_table_edits_and_buttons(dialog):
    dialog.load_block(main_block())
    dialog.levels_table.selectRow(1)
    assert dialog.current_grid().active_level == 1
    dialog.add_level_button.click()                        # one level above the top, same spacing
    assert dialog.levels_table.rowCount() == 3
    assert dialog.current_grid().levels[-1].z == pytest.approx(34.1376 + 3.6576)
    dialog.levels_table.item(2, 1).setText("130'")
    assert dialog.current_grid().levels[-1].z == pytest.approx(130 * FT_M)
    dialog.levels_table.item(2, 0).setText("Roof")
    assert dialog.current_grid().levels[-1].name == "Roof"
    dialog.levels_table.selectRow(2)
    dialog.remove_level_button.click()
    assert dialog.levels_table.rowCount() == 2
    dialog.levels_table.selectRow(0)
    dialog.remove_level_button.click()
    dialog.remove_level_button.click()
    assert dialog.levels_table.rowCount() == 1             # the last level stays
    dialog.levels_table.item(0, 1).setText("garbage")
    assert "garbage" not in dialog.levels_table.item(0, 1).text() and dialog.status_label.text()


def test_single_level_follows_origin_z(dialog):
    dialog.origin_z.setText("50'")
    dialog.origin_z.editingFinished.emit()
    assert dialog.current_grid().levels[0].z == pytest.approx(50 * FT_M)


def test_grid_list_buttons(dialog):
    dialog.ask_text = lambda title, label, default: ("Pipe Rack", True)
    dialog.new_rect_button.click()
    assert dialog.grid_combo.count() == 2 and dialog.current_grid().name == "Pipe Rack"
    dialog.dup_button.click()
    assert dialog.grid_combo.count() == 3 and dialog.current_grid().name == "Pipe Rack 2"
    dialog.ask_text = lambda title, label, default: ("Renamed", True)
    dialog.rename_button.click()
    assert dialog.current_grid().name == "Renamed" and dialog.grid_combo.currentText() == "Renamed"
    dialog.visible_check.setChecked(False)
    assert dialog.current_grid().visible is False
    dialog.delete_button.click()
    assert dialog.grid_combo.count() == 2
    dialog.delete_button.click()
    dialog.delete_button.click()
    assert dialog.grid_combo.count() == 1                  # a document keeps at least one grid in the dialog


def test_preview_paints_rect_grid(dialog):
    dialog.load_block(main_block())
    dialog.preview.resize(400, 300)
    img = QImage(400, 300, QImage.Format_ARGB32)
    dialog.preview.render(img)
    assert dialog.preview._bubbles_px                      # bubbles were laid out
    hit = dialog.preview.bubble_at(*dialog.preview._bubbles_px[0][:2])
    assert hit is not None and hit[0] in ("x", "y")


def test_pick_signals_and_setters(dialog):
    got = []
    dialog.pick_origin_requested.connect(lambda: got.append("o"))
    dialog.pick_direction_requested.connect(lambda: got.append("d"))
    dialog.pick_origin_button.click()
    dialog.pick_dir_button.click()
    assert got == ["o", "d"]
    dialog.set_origin((1.0, 2.0, 3.0))
    assert dialog.current_grid().origin == pytest.approx((1.0, 2.0, 3.0))
    assert dialog.origin_x.text() == "3'-3 3/8\""
    dialog.set_rotation(12.5)
    assert dialog.rotation_spin.value() == 12.5 and dialog.current_grid().rotation_deg == 12.5


def test_document_change_reloads_and_notes_it(dialog):
    dialog.x_spacing.setText("9@10'")
    dialog.load_block(main_block(), notice="Reloaded from the document")
    assert dialog.x_spacing.text() == "25', 30'" and "Reloaded" in dialog.status_label.text()


def test_extend_mode_toggle_keeps_stored_extents(dialog):
    dialog.extend_edit.setText("5'")
    dialog.extend_edit.editingFinished.emit()
    dialog.extend_all.setChecked(False)
    g = dialog.current_grid()
    assert all(v == pytest.approx(5 * FT_M) for v in g.extend.values())
    assert all(e.text() == "5'-0\"" for e in dialog.extend_edits.values())
    dialog.extend_edits["x_neg"].setText("2'")
    dialog.extend_edits["x_neg"].editingFinished.emit()
    assert g.extend["x_neg"] == pytest.approx(2 * FT_M) and g.extend["x_pos"] == pytest.approx(5 * FT_M)
    dialog.extend_all.setChecked(True)
    assert dialog.extend_edit.text() == "2'-0\""
    assert all(v == pytest.approx(2 * FT_M) for v in dialog.current_grid().extend.values())


def test_reload_clears_error_marks(dialog):
    dialog.x_spacing.setText("3@")
    assert dialog.x_spacing.styleSheet() != "" and not dialog.apply_button.isEnabled()
    dialog.load_block(main_block())
    assert dialog.x_spacing.styleSheet() == "" and dialog.x_spacing.toolTip() == ""
    assert dialog.apply_button.isEnabled()


def test_unrelated_edit_keeps_origin_and_rotation_exact(dialog):
    dialog.set_origin((1.0, 2.0, 3.0))
    dialog.set_rotation(12.345)
    dialog.x_spacing.setText("4@10'")
    g = dialog.current_grid()
    assert g.origin == (1.0, 2.0, 3.0)
    assert g.rotation_deg == pytest.approx(12.345)


def test_unit_switch_keeps_spacings_meaning(dialog):
    dialog.x_spacing.setText("25, 30")
    g = dialog.current_grid()
    before = list(g.x_spacings)
    dialog.metric_radio.setChecked(True)
    assert dialog.x_spacing.text() == "7.620 m, 9.144 m"
    assert g.x_spacings == pytest.approx(before)
    dialog.x_spacing.setText("3@30'")
    dialog.imperial_radio.setChecked(True)
    dialog.metric_radio.setChecked(True)
    assert dialog.x_spacing.text() == "3@30'"
    assert g.x_spacings == pytest.approx([30 * FT_M] * 3)


def test_retext_spacings_helper():
    from igz_steel._grid_dialog import retext_spacings
    assert retext_spacings("3@30'", [30 * FT_M] * 3, "metric") == "3@30'"
    assert retext_spacings("25, 30", [25 * FT_M, 30 * FT_M], "metric") == "7.620 m, 9.144 m"
    assert retext_spacings("3@", [1.0], "imperial") == "3'-3 3/8\""


def test_rename_failure_is_reported(dialog):
    dialog.preview.renamed.emit("x", 99, "Z")
    assert dialog.status_label.text()
    dialog._set_status("")
    dialog.preview.renamed.emit("x", 0, "  ")
    assert dialog.status_label.text()


def test_duplicate_line_name_warns(dialog):
    dialog.preview.renamed.emit("x", 1, "A")
    assert dialog.current_grid().x_names[:2] == ["A", "A"]
    assert dialog.status_label.text() == 'Name "A" is used twice'
    assert dialog.apply_button.isEnabled()                   # allowed, only a warning
    dialog.preview.renamed.emit("x", 1, "B.5")
    assert dialog.status_label.text() == ""


def test_renamed_line_survives_typing_through_a_spacing(dialog):
    dialog.x_spacing.setText("30', 30', 30', 25'")
    assert dialog.current_grid().x_names == ["A", "B", "C", "D", "E"]
    dialog.preview.renamed.emit("x", 4, "E-ROOF")
    dialog.x_spacing.setText("30', 30', 30', ")              # mid-edit: the last bay is gone
    assert dialog.current_grid().x_names == ["A", "B", "C", "D"]
    dialog.x_spacing.setText("30', 30', 30', 28'")
    assert dialog.current_grid().x_names == ["A", "B", "C", "D", "E-ROOF"]
    dialog.x_spacing.editingFinished.emit()                  # commits the names as they are
    dialog.x_spacing.setText("30', 30', 30'")
    dialog.x_spacing.setText("30', 30', 30', 28'")
    assert dialog.current_grid().x_names[-1] == "E-ROOF"


def test_committed_names_follow_start_and_swap(dialog):
    dialog.preview.renamed.emit("y", 1, "2A")
    dialog.y_start.setText("5")
    dialog.y_start.editingFinished.emit()
    dialog.y_spacing.setText("3@20'")
    assert dialog.current_grid().y_names == ["5", "6", "7", "8"]
    dialog.swap_button.click()
    dialog.x_spacing.setText("2@25'")
    assert dialog.current_grid().x_names == ["5", "6", "7"]


def test_unchanged_start_keeps_renamed_lines(dialog):
    dialog.preview.renamed.emit("x", 1, "B.5")
    dialog.x_start.editingFinished.emit()
    assert dialog.current_grid().x_names[1] == "B.5"
    dialog.x_start.setText(" A ")
    dialog.x_start.editingFinished.emit()
    assert dialog.current_grid().x_names[1] == "B.5"


def test_enter_in_a_field_presses_no_button(dialog, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    asked = []
    dialog.ask_text = lambda *a: (asked.append(a), ("X", True))[1]
    dialog.show()
    qapp.processEvents()
    dialog.x_spacing.setFocus()
    QTest.keyClick(dialog.x_spacing, Qt.Key_Return)
    QTest.keyClick(dialog.origin_x, Qt.Key_Enter)
    qapp.processEvents()
    assert dialog.grid_combo.count() == 1 and asked == []
    assert not any(b.autoDefault() or b.isDefault() for b in dialog.findChildren(QPushButton))
