# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel import _db


@pytest.fixture
def dialog(qapp):
    from igz_steel._dialog import MemberDialog
    d = MemberDialog(_db.load())
    d.set_layers(["Layer 0", "Steel"])
    yield d
    d.close()
    d.deleteLater()
    qapp.processEvents()


def test_filter_selects_and_reads_out(dialog):
    assert dialog.family_combo.currentText() == "W"
    dialog.filter_edit.setText("12X26")
    assert dialog.shape_list.count() == 1
    dialog.shape_list.setCurrentRow(0)
    p = dialog.params()
    assert p["label"] == "W12X26" and p["unit_system"] == "imperial"
    assert p["insertion"] == "centroid" and p["fillets"] is True and p["segments"] == 24
    assert p["layer"] == "Layer 0"
    assert "12.200 in" in dialog.readout.text() and "26" in dialog.readout.text()
    assert dialog.place_button.isEnabled()
    assert dialog.preview.selected() == "centroid"
    dialog.preview.pick("top")
    assert dialog.params()["insertion"] == "top"
    assert not dialog.segments_spin.isEnabled()          # not a round section


def test_no_match_disables_place_and_place_is_harmless(dialog):
    got = []
    dialog.place_requested.connect(got.append)
    dialog.filter_edit.setText("zzz")
    assert dialog.shape_list.count() == 0
    assert not dialog.place_button.isEnabled()
    dialog.place_button.click()
    dialog._on_place()
    assert got == [] and dialog.current_shape() is None


def test_metric_labels_and_round_sections(dialog):
    dialog.metric_radio.setChecked(True)
    dialog.filter_edit.setText("310X38.7")
    assert dialog.shape_list.count() == 1 and dialog.shape_list.item(0).text() == "W310X38.7"
    dialog.shape_list.setCurrentRow(0)
    assert dialog.params()["unit_system"] == "metric" and dialog.params()["label"] == "W12X26"
    assert "310.0 mm" in dialog.readout.text()
    dialog.family_combo.setCurrentText("PIPE")
    dialog.filter_edit.setText("")
    dialog.shape_list.setCurrentRow(0)
    assert dialog.segments_spin.isEnabled()
    dialog.segments_spin.setValue(48)
    assert dialog.params()["segments"] == 48


def test_place_emits_params_with_typed_layer_and_roll(dialog):
    got = []
    dialog.place_requested.connect(got.append)
    dialog.filter_edit.setText("W12X26")
    dialog.shape_list.setCurrentRow(0)
    dialog.layer_combo.setEditText("Beams")
    dialog.roll_buttons[1].click()                       # the 90 preset
    dialog.fillets_check.setChecked(False)
    dialog.place_button.click()
    assert len(got) == 1
    p = got[0]
    assert p["layer"] == "Beams" and p["roll"] == 90.0 and p["fillets"] is False


def test_edit_mode_loads_and_updates(dialog):
    got = []
    dialog.update_requested.connect(got.append)
    params = {"label": "HSS6X6X1/2", "unit_system": "imperial", "insertion": "bottom",
              "roll": 45.0, "fillets": True, "segments": 24}
    dialog.set_mode("edit")
    dialog.load(params, "Columns", 3.5)
    assert dialog.update_button.isVisible() or dialog.mode == "edit"
    assert dialog.family_combo.currentText() == "HSS"
    assert dialog.current_shape().label == "HSS6X6X1/2"
    assert dialog.preview.selected() == "bottom"
    assert dialog.roll_spin.value() == 45.0
    assert dialog.layer_combo.currentText() == "Columns"
    assert dialog.length_spin.value() == pytest.approx(3.5)
    dialog.length_spin.setValue(4.0)
    dialog._on_update()
    assert got and got[0]["length"] == pytest.approx(4.0) and got[0]["insertion"] == "bottom"
    dialog.set_mode("place")
    assert dialog.mode == "place"


def test_preview_pick_by_pixel(qapp):
    from igz_steel._dialog import SectionPreview
    from igz_steel._profiles import build_profile
    s = _db.load().find("W12X26")
    w = SectionPreview()
    w.resize(300, 300)
    w.set_profile(build_profile("W", s.dims_m()))
    px, py = w.point_pixel("top_left")
    heard = []
    w.point_picked.connect(heard.append)
    w.pick_at(px + 2, py - 2)
    assert w.selected() == "top_left" and heard == ["top_left"]
    w.pick_at(px + 200, py)                              # far away: nothing changes
    assert w.selected() == "top_left"
