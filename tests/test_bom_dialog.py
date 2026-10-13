# SPDX-License-Identifier: GPL-3.0-or-later
from igz_steel import _bom


def _records():
    return [{"label": "W12X26", "family": "W", "length_m": 3.0, "weight_per_m": 38.7,
             "layer": "Beams", "ifc_class": "IfcBeam", "uid": 11},
            {"label": "W12X26", "family": "W", "length_m": 2.0, "weight_per_m": 38.7,
             "layer": "Beams", "ifc_class": "IfcBeam", "uid": 12},
            {"label": "HSS6X6X1/2", "family": "HSS", "length_m": 4.0, "weight_per_m": 47.9,
             "layer": "Columns", "ifc_class": "IfcColumn", "uid": 13}]


def test_bom_dialog_fills_tables_and_exports(qapp, tmp_path):
    from igz_steel._dialog import BomDialog
    selected = []
    d = BomDialog(None, lambda: _bom.collect(_records()), selected.append,
                  lambda m: f"{m:.2f} m", lambda kg: f"{kg:.1f} kg")
    d.refresh()
    assert d.rows_table.rowCount() == 3 and d.summary_table.rowCount() == 2
    assert d.rows_table.item(0, 0).text() == "W12X26-1"
    assert d.rows_table.item(2, 3).text() == "4.00 m"
    assert d.summary_table.item(0, 2).text() == "2"
    assert "3 members" in d.totals_label.text() and "9.00 m" in d.totals_label.text()
    d._on_row_activated(2, 0)
    assert selected == [13]
    out = tmp_path / "bom.csv"
    assert d.export_csv(str(out)) == str(out)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("mark,label,family,length,weight") and "TOTAL" in text
    d.close()


def test_bom_dialog_empty(qapp):
    from igz_steel._dialog import BomDialog
    d = BomDialog(None, lambda: _bom.collect([]), lambda uid: None, str, str)
    d.refresh()
    assert d.rows_table.rowCount() == 0 and "0 members" in d.totals_label.text()
    d.close()
