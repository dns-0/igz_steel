# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel._grid import (GridError, letter_sequence, name_scheme, name_sequence, next_name,
                             number_sequence, reconcile_names)


def test_letters_skip_i_and_o():
    assert letter_sequence("A", 10) == list("ABCDEFGHJK")
    assert letter_sequence("M", 3) == ["M", "N", "P"]


def test_letters_wrap_to_doubles_and_triples():
    assert letter_sequence("W", 6) == ["W", "X", "Y", "Z", "AA", "BB"]
    assert next_name("HH") == "JJ"
    assert next_name("ZZ") == "AAA"
    assert letter_sequence("AA", 2) == ["AA", "BB"]


def test_numbers():
    assert number_sequence("5", 3) == ["5", "6", "7"]
    assert next_name("12") == "13"
    assert number_sequence("1", 1) == ["1"]


def test_scheme_from_start():
    assert name_scheme("A") == "letters" and name_scheme("7") == "numbers"
    assert name_sequence("A.1", 3) == ["A", "B", "C"]
    assert name_sequence("2.5", 2) == ["2", "3"]
    assert name_sequence("b", 2) == ["B", "C"]


@pytest.mark.parametrize("bad", ["I", "O", "AB", "", "#", "II"])
def test_bad_starts(bad):
    with pytest.raises(GridError):
        name_sequence(bad, 2)


def test_reconcile_regenerates_untouched_names():
    assert reconcile_names("A", 3, None) == ["A", "B", "C"]
    assert reconcile_names("A", 3, []) == ["A", "B", "C"]
    assert reconcile_names("A", 4, ["A", "B", "C"]) == ["A", "B", "C", "D"]
    assert reconcile_names("A", 2, ["A", "B", "C"]) == ["A", "B"]


def test_reconcile_keeps_renamed_lines():
    assert reconcile_names("A", 4, ["A", "B.5", "C"]) == ["A", "B.5", "C", "D"]
    assert reconcile_names("A", 2, ["A", "B.5", "C"]) == ["A", "B.5"]
    assert reconcile_names("1", 4, ["1", "2", "2A"]) == ["1", "2", "2A", "3"]
    # a changed start with untouched names is the dialog's job (it calls
    # name_sequence); reconcile treats the mismatch as renamed and keeps them
    assert reconcile_names("C", 3, ["A", "B", "C"]) == ["A", "B", "C"]
