# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel import _bom, _units


def test_is_imperial_follows_model_unit(monkeypatch):
    import core.units as cu
    cu.set_model_unit("ft-in")
    assert _units.is_imperial() is True
    assert _units.fmt_weight(100.0) == "220.5 lb"
    assert _units.fmt_len(0.3048).startswith("1'")
    cu.set_model_unit("m")
    assert _units.is_imperial() is False
    assert _units.fmt_weight(1234.56) == "1,234.6 kg"
    assert _units.fmt_len(1.5) == "1.50 m"


def test_formatting_survives_a_document_without_units(monkeypatch):
    import core.units as cu

    def boom():
        raise AttributeError("no units")
    monkeypatch.setattr(cu, "model_unit", boom)
    monkeypatch.setattr(cu, "fmt_len", boom)
    assert _units.is_imperial() is False
    assert _units.fmt_len(2.0) == "2.000 m"
    assert _units.fmt_weight(2.0) == "2.0 kg"


def test_fmt_dim():
    assert _units.fmt_dim(12.2, "imperial") == "12.200 in"
    assert _units.fmt_dim(310.0, "metric") == "310.0 mm"


def _rec(label, family, length, wpm, layer="Layer 0", ifc="IfcBeam", uid=None):
    return {"label": label, "family": family, "length_m": length, "weight_per_m": wpm,
            "layer": layer, "ifc_class": ifc, "uid": uid or id(label) + int(length * 1000)}


def test_collect_marks_sums_and_sorts():
    records = [_rec("W12X26", "W", 3.0, 38.7, uid=1),
               _rec("HSS6X6X1/2", "HSS", 2.0, 47.9, "Columns", "IfcColumn", uid=2),
               _rec("W12X26", "W", 4.0, 38.7, uid=3),
               _rec("W12X26", "W", 0.0, 38.7, uid=4)]          # a profile object
    bom = _bom.collect(records)
    assert [r.mark for r in bom.rows] == ["W12X26-1", "HSS6X6X1/2-1", "W12X26-2", "W12X26-3"]
    assert bom.rows[3].is_profile is True and bom.rows[3].weight_kg == 0.0
    assert bom.rows[0].weight_kg == pytest.approx(3.0 * 38.7)
    assert [s.label for s in bom.summary] == ["W12X26", "HSS6X6X1/2"]   # family order W before HSS
    w = bom.summary[0]
    assert w.count == 2 and w.total_length_m == pytest.approx(7.0)
    assert w.total_weight_kg == pytest.approx(7.0 * 38.7)
    assert bom.count == 3
    assert bom.total_length_m == pytest.approx(9.0)
    assert bom.total_weight_kg == pytest.approx(7.0 * 38.7 + 2.0 * 47.9)


def test_csv_has_header_rows_summary_and_totals():
    bom = _bom.collect([_rec("W12X26", "W", 3.0, 38.7, uid=1)])
    text = _bom.to_csv(bom, lambda m: f"{m:.2f} m", lambda kg: f"{kg:.1f} kg")
    lines = text.splitlines()
    assert lines[0] == "mark,label,family,length,weight,layer,ifc_class,length_m,weight_kg"
    assert lines[1].startswith("W12X26-1,W12X26,W,3.00 m,116.1 kg,Layer 0,IfcBeam,3.0,116.1")
    assert "" in lines
    assert "label,family,count,total_length,total_weight,total_length_m,total_weight_kg" in lines
    assert lines[-1].startswith("TOTAL,,1,3.00 m,116.1 kg")


def test_empty_bom():
    bom = _bom.collect([])
    assert bom.rows == [] and bom.summary == [] and bom.count == 0
    assert _bom.to_csv(bom, str, str).splitlines()[0].startswith("mark,")
