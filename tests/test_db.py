# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

EXPECTED_COUNTS = {"W": 289, "M": 16, "S": 28, "HP": 22, "C": 32, "MC": 40,
                   "L": 137, "WT": 289, "MT": 14, "ST": 28, "2L": 639,
                   "HSS": 714, "PIPE": 51}


def test_2l_label_parser():
    from devtools.build_db import parse_2l
    assert parse_2l("2L12X12X1-3/8X3/4") == (12.0, 12.0, 1.375, 0.75, None)
    assert parse_2l("2L8X4X1LLBB") == (8.0, 4.0, 1.0, 0.0, True)
    assert parse_2l("2L8X4X1X3/4SLBB") == (8.0, 4.0, 1.0, 0.75, False)
    with pytest.raises(ValueError):
        parse_2l("2L8X4Xbad")


def test_database_loads_with_expected_counts():
    from igz_steel import _db
    db = _db.load()
    assert db.families() == list(EXPECTED_COUNTS)
    for fam, n in EXPECTED_COUNTS.items():
        assert len(db.shapes(fam)) == n, fam
    assert sum(len(db.shapes(f)) for f in db.families()) == 2299


def test_find_imperial_and_metric_label_give_same_shape():
    from igz_steel import _db
    db = _db.load()
    a = db.find("W12X26")
    b = db.find("w310x38.7")
    assert a is not None and a is b
    assert a.family == "W" and a.dims["d"] == 12.2 and a.dims["bf"] == 6.49
    assert a.dims["tw"] == 0.23 and a.dims["tf"] == 0.38 and a.dims["kdes"] == 0.68
    assert a.W == 26 and abs(a.weight_per_ft() - 26) < 1e-9
    assert abs(a.weight_per_m() - 38.7) < 1e-9
    assert abs(a.dims_m()["d"] - 12.2 * 0.0254) < 1e-12
    assert a.label_for("metric") == "W310X38.7" and a.label_for("imperial") == "W12X26"


def test_family_specific_fields():
    from igz_steel import _db
    db = _db.load()
    hss = db.find("HSS6X6X1/2")
    assert hss.round is False and hss.dims["Ht"] == 6 and hss.dims["B"] == 6
    assert hss.dims["tdes"] == 0.465
    rnd = db.find("HSS6.000X0.500")
    assert rnd.round is True and rnd.dims["OD"] == 6.0
    pipe = db.find("Pipe6STD")
    assert pipe.family == "PIPE" and pipe.dims["OD"] == 6.625 and pipe.dims["tdes"] == 0.261
    ang = db.find("L8X4X1")
    assert ang.dims["t"] == 1.0 and {ang.dims["b"], ang.dims["d"]} == {8.0, 4.0}
    dbl = db.find("2L12X12X1-3/8X3/4")
    assert dbl.dims["gap"] == 0.75 and dbl.dims_m()["llbb"] is True
    assert abs(dbl.dims_mm["gap"] - 19.05) < 1e-6


def test_search_filters_by_substring_and_family():
    from igz_steel import _db
    db = _db.load()
    hits = db.search("12x26")
    assert [s.label for s in hits] == ["W12X26"]
    assert all(s.family == "HSS" for s in db.search("6X6", family="HSS"))
    assert db.search("zzz") == []
