# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel._grid import (FT_M, IN_M, GridError, fmt_length, parse_angle_list, parse_length,
                             parse_spacing_list)


@pytest.mark.parametrize("text, feet", [
    ("25'", 25), ("25'-6\"", 25.5), ("25' 6\"", 25.5), ("25'6\"", 25.5),
    ("25'-6 1/2\"", 25 + 6.5 / 12), ("306\"", 25.5), ("25.5'", 25.5), ("25", 25),
    ("1/2\"", 0.5 / 12), ("25 ft", 25), ("6 in", 0.5), ("-5'", -5), (".5'", 0.5)])
def test_imperial_forms(text, feet):
    assert parse_length(text, "imperial") == pytest.approx(feet * FT_M)


@pytest.mark.parametrize("text, metres", [
    ("7.62", 7.62), ("7.62m", 7.62), ("7.62 m", 7.62), ("7620mm", 7.62), ("762cm", 7.62),
    ("-1.5", -1.5)])
def test_metric_forms(text, metres):
    assert parse_length(text, "metric") == pytest.approx(metres)


def test_explicit_symbols_work_in_either_system():
    assert parse_length("25'", "metric") == pytest.approx(25 * FT_M)
    assert parse_length("7620mm", "imperial") == pytest.approx(7.62)


@pytest.mark.parametrize("text", ["", "abc", "25'x", "1/0\"", "3@", "25''"])
def test_bad_lengths(text):
    with pytest.raises(GridError):
        parse_length(text, "imperial")


def test_spacing_list_with_repeats_and_spaces():
    out = parse_spacing_list("25', 3@30', 25'", "imperial")
    assert out == pytest.approx([25 * FT_M, 30 * FT_M, 30 * FT_M, 30 * FT_M, 25 * FT_M])
    assert parse_spacing_list("3@30' 25'", "imperial") == pytest.approx([30 * FT_M] * 3 + [25 * FT_M])
    assert parse_spacing_list("25' 6\", 10'", "imperial") == pytest.approx([25.5 * FT_M, 10 * FT_M])
    assert parse_spacing_list("3@25' 6\"", "imperial") == pytest.approx([25.5 * FT_M] * 3)
    assert parse_spacing_list("2@7.62 5", "metric") == pytest.approx([7.62, 7.62, 5.0])
    assert parse_spacing_list("25 30 30", "imperial") == pytest.approx([25 * FT_M, 30 * FT_M, 30 * FT_M])


@pytest.mark.parametrize("text, feet", [
    ("25' 6\" 3@30' 25'", [25.5, 30, 30, 30, 25]),
    ("25' 6\" 30'", [25.5, 30]),
    ("3@25' 6\" 25'", [25.5, 25.5, 25.5, 25]),
    ("25'-6\" 10'", [25.5, 10]),
    ("6 1/2\" 3@1'", [6.5 / 12, 1, 1, 1]),
    ("25’ 6” 30′", [25.5, 30]),
    ("25 ft 6 in 10 ft", [25.5, 10])])
def test_spacing_list_keeps_feet_and_inches_together_without_commas(text, feet):
    assert parse_spacing_list(text, "imperial") == pytest.approx([f * FT_M for f in feet])


def test_spacing_list_names_stray_text():
    with pytest.raises(GridError, match='"x"'):
        parse_spacing_list("25' x 30'", "imperial")
    with pytest.raises(GridError, match="greater than zero"):
        parse_spacing_list("25' -5'", "imperial")
    assert parse_spacing_list("7620mm 2@5 m", "metric") == pytest.approx([7.62, 5.0, 5.0])
    assert parse_angle_list("30 30° 2@45 deg") == [30.0, 30.0, 45.0, 45.0]


@pytest.mark.parametrize("text, msg", [
    ("", "at least one"), ("3@", "after @"), ("0@25'", "at least 1"),
    ("25', 0", "greater than zero"), ("-5'", "greater than zero"), ("5000", "typo"),
    ("250@10'", "At most")])
def test_spacing_errors(text, msg):
    with pytest.raises(GridError, match=msg):
        parse_spacing_list(text, "imperial")


def test_angle_lists():
    assert parse_angle_list("6@30") == [30.0] * 6
    assert parse_angle_list("30, 30°, 45 deg") == [30.0, 30.0, 45.0]
    assert parse_angle_list("12@30") == [30.0] * 12
    with pytest.raises(GridError, match="360"):
        parse_angle_list("13@30")
    with pytest.raises(GridError, match="greater than zero"):
        parse_angle_list("30, -30")
    with pytest.raises(GridError, match="angle"):
        parse_angle_list("30, x")


@pytest.mark.parametrize("metres, text", [
    (7.62, "25'-0\""), (25.5 * FT_M, "25'-6\""), (6.5 * IN_M, "0'-6 1/2\""),
    (-5 * FT_M, "-5'-0\""), (0.0, "0'-0\""), (0.75 * IN_M, "0'-0 3/4\"")])
def test_fmt_imperial(metres, text):
    assert fmt_length(metres, "imperial") == text


def test_fmt_never_shows_negative_zero():
    assert fmt_length(-0.0001, "imperial") == "0'-0\""
    assert fmt_length(-0.0, "imperial") == "0'-0\""
    assert fmt_length(-0.0001, "metric") == "0.000 m"
    assert fmt_length(-0.0, "metric") == "0.000 m"
    assert fmt_length(-0.002, "metric") == "-0.002 m"
    assert fmt_length(-IN_M / 16, "imperial") == "-0'-0 1/16\""


def test_fmt_metric_and_round_trip():
    assert fmt_length(7.772, "metric") == "7.772 m"
    for v in (0.3048, 7.62, 12.3456):
        assert parse_length(fmt_length(v, "imperial"), "imperial") == pytest.approx(v, abs=IN_M / 32)
        assert parse_length(fmt_length(v, "metric"), "metric") == pytest.approx(v, abs=0.0005)


def test_huge_repeat_count_rejected_before_expansion():
    with pytest.raises(GridError, match="At most"):
        parse_spacing_list("999999999@1'", "imperial")
