# igz_steel Grids Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add layout grids to igz_steel: a Grid Creator dialog (rectangular and radial grids, levels, live preview), a viewport overlay with drafting bubbles, and cursor snapping to grid intersections on every level, saved in the document.

**Architecture:** `_grid.py` is pure Python (parsing, naming, geometry, document block) and is unit tested without Qt. `_grid_host.py` turns that geometry into the host's overlay, snap provider and pickable items through `ExtensionApp`. `_grid_dialog.py` is the Qt dialog with a `GridPreview` widget, the radial and add-levels sub-dialogs and two pick tools. `_core.py` wires a toolbar button, menu and context-menu entries and owns one `GridStore` and one `GridDialog` per session.

**Tech Stack:** Python 3.12-compatible, PySide6 (ships with IngeTrazo), IngeTrazo 0.5.8 Extension API 2 (`document_data`, `set_document_data`, `add_overlay`, `add_snap_provider`, `add_pickable`, `world_to_pixels`), pytest with the stubs under `tests/stubs/`.

**Spec:** `docs/superpowers/specs/2026-10-13-igz-steel-grid-design.md`

**Project root:** `C:\INGETRAZO EXTENSIONS\STEEL SHAPES EXTENSION` (all paths relative to it). Run commands from this folder in Git Bash. Tests: `.venv/Scripts/python -m pytest -q`.

## Global Constraints

- Every `.py` file starts with `# SPDX-License-Identifier: GPL-3.0-or-later`.
- No syntax newer than Python 3.12.
- Runtime imports limited to stdlib, PySide6 and IngeTrazo's own modules (`core.*`, `tools.base`, `views.*`); `_grid.py` imports only stdlib.
- All lengths in metres inside; `IN_M = 0.0254`, `FT_M = 0.3048`.
- Grids are an overlay, never scene geometry; the document block lives under the extension key through `app.document_data` / `app.set_document_data`; every mutation writes the whole block once (one undo step).
- Limits: 200 lines per direction, 200 angles, 100 levels, 50 grids, spacing at most 1000 m, duplicate elevations closer than 1 mm refused.
- Letters skip I and O; after Z come AA, BB …; letters along X and numbers along Y by default.
- Dialog default unit system imperial, with a Metric switch; the block carries `"units"`; `QSettings("igz_steel", "igz_steel")` key `grid_units` is the default for new documents.
- Overlay and snap provider never raise (catch, log once, continue).
- Host calls that may be absent are guarded: `add_pickable`, `world_to_pixels`, `_clip_pixel_line`, `snap_threshold_px`, `flash_status`.
- `igz_steel/__init__.py` defines no `Tool` subclass.
- Tests must pass before each commit.

## Review Focus

1. A spacing list whose items contain spaces (`25' 6"`) next to whitespace-separated items (`3@30' 25'`) must parse as the user reads it, never as six items. Test in Task 1.
2. A hand-edited or future-version block with one broken grid must load the other grids and never disable the overlay. Tests in Tasks 5 and 6.
3. Rotating a grid must move every bubble, node and level together; a 90° grid must place local +X along world +Y. Tests in Tasks 3 and 4.
4. Changing a spacing count after renaming one line must keep the renamed line, and changing the start name must regenerate all names. Tests in Tasks 2 and 7.
5. A radial grid whose steps sum to exactly 360° must not draw a duplicate radial line, must not grow tangent legs, and must still snap at every intersection. Test in Task 4.

---

### Task 1: Length and angle parsing in `_grid.py`

**Files:**
- Create: `igz_steel/_grid.py`
- Test: `tests/test_grid_parse.py`

**Interfaces:**
- Produces: `GridError(ValueError)`, constants `IN_M`, `FT_M`, `UNITS`, `MAX_LINES`, `MAX_LEVELS`, `MAX_GRIDS`, `MAX_SPACING`, `LEVEL_TOL`; `parse_length(text, units="imperial") -> float`, `parse_spacing_list(text, units="imperial") -> list[float]`, `parse_angle_list(text) -> list[float]`, `fmt_length(metres, units="imperial") -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_parse.py`:

```python
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


def test_fmt_metric_and_round_trip():
    assert fmt_length(7.772, "metric") == "7.772 m"
    for v in (0.3048, 7.62, 12.3456):
        assert parse_length(fmt_length(v, "imperial"), "imperial") == pytest.approx(v, abs=IN_M / 32)
        assert parse_length(fmt_length(v, "metric"), "metric") == pytest.approx(v, abs=0.0005)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_parse.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'igz_steel._grid'`.

- [ ] **Step 3: Write the parsing part of `_grid.py`**

`igz_steel/_grid.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout grids: parsing, naming, geometry and the document block.

Pure Python: no Qt, no host. Every length is metres; angles are degrees,
counter-clockwise seen from above, measured from the grid's own X axis.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

IN_M = 0.0254
FT_M = 0.3048
UNITS = ("imperial", "metric")
MAX_LINES = 200
MAX_LEVELS = 100
MAX_GRIDS = 50
MAX_SPACING = 1000.0
LEVEL_TOL = 0.001
BLOCK_VERSION = 1
ARC_STEP_DEG = 4.0


class GridError(ValueError):
    """A user-facing problem with a grid definition."""


# ------------------------------------------------------------ parsing

_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_RE_BARE = re.compile(rf"^{_NUMBER}$")
_RE_METRIC = re.compile(rf"^({_NUMBER})\s*(mm|cm|m)$")
_RE_IMPERIAL = re.compile(
    rf"^(?:(?P<ft>{_NUMBER})\s*(?:'|ft)\s*-?\s*)?"
    rf"(?:(?P<inw>\d+(?:\.\d+)?)?\s*(?:(?P<num>\d+)\s*/\s*(?P<den>\d+))?\s*(?:\"|in))?$")
_RE_REPEAT = re.compile(r"^(\d+)\s*@\s*(.*)$")
_RE_ANGLE = re.compile(rf"^(-?{_NUMBER})\s*(?:°|deg)?$")
_QUOTES = {"\u201d": '"', "\u2033": '"', "\u2019": "'", "\u2032": "'"}


def _clean(text):
    s = str(text).strip()
    for bad, good in _QUOTES.items():
        s = s.replace(bad, good)
    return s


def parse_length(text, units="imperial"):
    """``25'``, ``25'-6"``, ``306"``, ``6 1/2"``, ``7.62 m``, ``7620mm``… to metres.
    A bare number is feet in imperial and metres in metric; a unit symbol
    is honoured in either system. Raises ``GridError``."""
    if units not in UNITS:
        raise GridError(f"Unknown unit system {units!r}")
    s = _clean(text)
    if not s:
        raise GridError("Enter a length")
    sign = 1.0
    if s[0] in "+-":
        sign = -1.0 if s[0] == "-" else 1.0
        s = s[1:].strip()
    if _RE_BARE.match(s):
        v = float(s)
        return sign * (v * FT_M if units == "imperial" else v)
    m = _RE_METRIC.match(s)
    if m:
        return sign * float(m.group(1)) * {"mm": 0.001, "cm": 0.01, "m": 1.0}[m.group(2)]
    m = _RE_IMPERIAL.match(s)
    if m and (m.group("ft") or m.group("inw") or m.group("num")):
        feet = float(m.group("ft") or 0.0)
        inches = float(m.group("inw") or 0.0)
        if m.group("num"):
            den = int(m.group("den"))
            if den == 0:
                raise GridError(f'Cannot read "{text}": a fraction cannot have a zero denominator')
            inches += int(m.group("num")) / den
        return sign * (feet * FT_M + inches * IN_M)
    raise GridError(f'Cannot read "{text}" as a length')


def _split_items(text):
    return [c.strip() for c in re.split(r"[,;]", str(text)) if c.strip()]


def _expand_one(item, parse_one, what):
    m = _RE_REPEAT.match(item)
    if not m:
        return [parse_one(item)]
    count, rest = int(m.group(1)), m.group(2).strip()
    if not rest:
        raise GridError(f'Cannot read "{item}": expected a {what} after @')
    if count < 1:
        raise GridError(f'Cannot read "{item}": the repeat count must be at least 1')
    return [parse_one(rest)] * count


def _expand(chunk, parse_one, what):
    """A comma-separated chunk: first as one item (imperial items may hold a
    space, ``25' 6"``), else split on whitespace."""
    try:
        return _expand_one(chunk, parse_one, what)
    except GridError:
        parts = chunk.split()
        if len(parts) < 2:
            raise
    out = []
    for p in parts:
        out.extend(_expand_one(p, parse_one, what))
    return out


def parse_spacing_list(text, units="imperial"):
    """``25', 3@30', 25'`` to a list of metres. Raises ``GridError``."""
    chunks = _split_items(text)
    if not chunks:
        raise GridError("Enter at least one spacing")
    out = []
    for c in chunks:
        out.extend(_expand(c, lambda s: parse_length(s, units), "spacing"))
    for v in out:
        if v <= 0:
            raise GridError("Spacings must be greater than zero")
        if v > MAX_SPACING:
            raise GridError(f"A spacing above {MAX_SPACING:g} m looks like a typo")
    if len(out) + 1 > MAX_LINES:
        raise GridError(f"At most {MAX_LINES} lines in one direction")
    return out


def _parse_angle(s):
    m = _RE_ANGLE.match(_clean(s))
    if not m:
        raise GridError(f'Cannot read "{s}" as an angle in degrees')
    return float(m.group(1))


def parse_angle_list(text):
    """``6@30`` or ``30, 30, 45`` to degrees per step. Raises ``GridError``."""
    chunks = _split_items(text)
    if not chunks:
        raise GridError("Enter at least one angle step")
    out = []
    for c in chunks:
        out.extend(_expand(c, _parse_angle, "angle"))
    for v in out:
        if v <= 0:
            raise GridError("Angle steps must be greater than zero")
    if sum(out) > 360.0 + 1e-9:
        raise GridError("The angle steps sweep more than 360°")
    if len(out) + 1 > MAX_LINES:
        raise GridError(f"At most {MAX_LINES} radial lines")
    return out


def fmt_length(metres, units="imperial"):
    """``25'-6 1/2"`` (to the 1/16) or ``7.620 m``."""
    v = float(metres)
    if units == "metric":
        return f"{v:.3f} m"
    sign = "-" if v < 0 else ""
    sixteenths = int(round(abs(v) / IN_M * 16))
    feet, rem = divmod(sixteenths, 12 * 16)
    inches, frac = divmod(rem, 16)
    if frac == 0:
        return f"{sign}{feet}'-{inches}\""
    g = math.gcd(frac, 16)
    return f"{sign}{feet}'-{inches} {frac // g}/{16 // g}\""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_parse.py -q`
Expected: all pass. If `"25''"` parses instead of failing, the imperial regex is letting a trailing quote through; it must not match because `'` is only consumed once.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid.py tests/test_grid_parse.py
git commit -m "feat(grid): length, spacing and angle parsing with imperial and metric forms"
```

---

### Task 2: Grid line names

**Files:**
- Modify: `igz_steel/_grid.py` (append after `fmt_length`)
- Test: `tests/test_grid_names.py`

**Interfaces:**
- Produces: `LETTERS`, `name_scheme(start) -> "letters" | "numbers"`, `letter_sequence(start, count)`, `number_sequence(start, count)`, `name_sequence(start, count)`, `next_name(name)`, `reconcile_names(start, count, existing) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_names.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_names.py -q`
Expected: FAIL with `ImportError: cannot import name 'letter_sequence'`.

- [ ] **Step 3: Append the naming code to `_grid.py`**

```python
# ------------------------------------------------------------ names

LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"          # drafting alphabet: no I, no O
_RE_LEAD_LETTERS = re.compile(r"^([A-Za-z]+)")
_RE_LEAD_DIGITS = re.compile(r"^(\d+)")


def _letter_index(token):
    t = token.upper()
    if t and t[0] in "IO" and len(set(t)) == 1:
        raise GridError("I and O are not used for grid names")
    if not t or len(set(t)) != 1 or t[0] not in LETTERS:
        raise GridError(f'"{token}" is not a grid letter: use A to Z, then AA, BB …')
    return (len(t) - 1) * len(LETTERS) + LETTERS.index(t[0])


def _letter_name(index):
    reps, i = divmod(index, len(LETTERS))
    return LETTERS[i] * (reps + 1)


def name_scheme(start):
    s = str(start).strip()
    if _RE_LEAD_DIGITS.match(s):
        return "numbers"
    if _RE_LEAD_LETTERS.match(s):
        return "letters"
    raise GridError(f'"{start}" must start with a letter or a number')


def letter_sequence(start, count):
    m = _RE_LEAD_LETTERS.match(str(start).strip())
    if not m:
        raise GridError(f'"{start}" must start with a letter')
    first = _letter_index(m.group(1))
    return [_letter_name(first + k) for k in range(int(count))]


def number_sequence(start, count):
    m = _RE_LEAD_DIGITS.match(str(start).strip())
    if not m:
        raise GridError(f'"{start}" must start with a number')
    first = int(m.group(1))
    return [str(first + k) for k in range(int(count))]


def name_sequence(start, count):
    if name_scheme(start) == "letters":
        return letter_sequence(start, count)
    return number_sequence(start, count)


def next_name(name):
    return name_sequence(name, 2)[1]


def reconcile_names(start, count, existing):
    """Names for ``count`` lines. Regenerated from ``start`` when ``existing``
    is empty or is itself the generated sequence (nothing was renamed);
    otherwise the existing names are kept, extended with ``next_name`` of the
    last one, or truncated."""
    count = int(count)
    if not existing:
        return name_sequence(start, count)
    existing = [str(n) for n in existing]
    try:
        if existing == name_sequence(start, len(existing)):
            return name_sequence(start, count)
    except GridError:
        pass
    names = existing[:count]
    while len(names) < count:
        try:
            names.append(next_name(names[-1]))
        except GridError:
            names.append(str(len(names) + 1))
    return names
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_names.py tests/test_grid_parse.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid.py tests/test_grid_names.py
git commit -m "feat(grid): drafting letter and number sequences with rename reconciliation"
```

---

### Task 3: Rectangular grid geometry

**Files:**
- Modify: `igz_steel/_grid.py` (append)
- Test: `tests/test_grid_rect.py`

**Interfaces:**
- Produces: dataclasses `Level(name, z)`, `Bubble(name, at, toward)`, `GridLine(name, direction, index, points, bubbles)`, `Node(names, at)`; helpers `cumulative(spacings) -> list[float]`, `rotate_xy(x, y, deg)`, `sorted_levels(levels)`; class `RectGrid` with fields in the code below and methods `level(index=None)`, `to_world(u, v, z)`, `direction(du, dv)`, `lines(level_index=None)`, `intersections(level_index=None)`, `corner_marks(level_index=None)`, `nearest(point, level_index=None) -> (Node, Level, float) | None`, `rename_line(direction, index, new_name)`, `set_spacings(direction, spacings, text)`, `set_start(direction, start)`, `set_levels(levels)`, `to_dict()`, `RectGrid.from_dict(d)`. `kind == "rect"`. Directions are `"x"` (lines spaced along X, named with `x_names`) and `"y"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_rect.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import math

import pytest

from igz_steel._grid import GridError, Level, RectGrid


def grid(**kw):
    base = dict(id="g1", name="Main", x_spacings=[7.62, 9.144], y_spacings=[6.096],
                extend={"x_neg": 1.0, "x_pos": 2.0, "y_neg": 3.0, "y_pos": 4.0},
                levels=[Level("EL 112", 34.1376), Level("EL 100", 30.48)])
    base.update(kw)
    return RectGrid(**base)


def by(lines, direction, index):
    return next(l for l in lines if l.direction == direction and l.index == index)


def test_names_and_levels_normalised():
    g = grid()
    assert g.x_names == ["A", "B", "C"] and g.y_names == ["1", "2"]
    assert [lv.name for lv in g.levels] == ["EL 100", "EL 112"]      # sorted by z
    assert g.level().z == 30.48 and g.kind == "rect"


def test_line_endpoints_with_extend():
    lines = grid().lines()
    a, b = by(lines, "x", 1).points
    assert a == pytest.approx((7.62, -3.0, 30.48)) and b == pytest.approx((7.62, 10.096, 30.48))
    a, b = by(lines, "y", 0).points
    assert a == pytest.approx((-1.0, 0.0, 30.48)) and b == pytest.approx((18.764, 0.0, 30.48))
    assert by(lines, "x", 1).name == "B" and by(lines, "y", 1).name == "2"


def test_bubbles_top_left_and_all():
    g = grid()
    xl = by(g.lines(), "x", 0)
    assert len(xl.bubbles) == 1
    assert xl.bubbles[0].at == pytest.approx((0.0, 10.096, 30.48))
    assert xl.bubbles[0].toward == pytest.approx((0.0, 1.0))
    yl = by(g.lines(), "y", 0)
    assert yl.bubbles[0].at == pytest.approx((-1.0, 0.0, 30.48))
    assert yl.bubbles[0].toward == pytest.approx((-1.0, 0.0))
    assert all(len(l.bubbles) == 2 for l in grid(bubbles="all").lines())


def test_rotation_turns_everything_as_a_unit():
    g = grid(rotation_deg=90.0, origin=(10.0, 5.0, 0.0), levels=[Level("L", 0.0)])
    nodes = {n.names: n.at for n in g.intersections()}
    assert nodes[("A", "1")] == pytest.approx((10.0, 5.0, 0.0))
    assert nodes[("B", "1")] == pytest.approx((10.0, 12.62, 0.0))      # local +X -> world +Y
    assert nodes[("A", "2")] == pytest.approx((3.904, 5.0, 0.0))       # local +Y -> world -X
    assert by(g.lines(), "x", 0).bubbles[0].toward == pytest.approx((-1.0, 0.0))
    assert g.corner_marks()[1] == pytest.approx((10.0, 21.764, 0.0))


def test_intersections_levels_and_corners():
    g = grid()
    assert len(g.intersections()) == 6
    assert {round(n.at[2], 4) for n in g.intersections(1)} == {34.1376}
    assert g.corner_marks(1)[2] == pytest.approx((16.764, 6.096, 34.1376))
    assert len(g.corner_marks()) == 4


def test_nearest_across_levels():
    g = grid()
    node, level, d = g.nearest((7.7, 6.0, 34.0))
    assert node.names == ("B", "2") and level.name == "EL 112" and d < 0.3
    _node, level, _d = g.nearest((7.7, 6.0, 34.0), level_index=0)
    assert level.name == "EL 100"


def test_rename_set_spacings_and_set_start():
    g = grid()
    g.rename_line("x", 1, "B.5")
    g.set_spacings("x", [7.62, 9.144, 3.0], "25', 30', 10'")
    assert g.x_names == ["A", "B.5", "C", "D"] and g.x_text == "25', 30', 10'"
    g.set_spacings("y", [6.096, 6.096], "2@20'")
    assert g.y_names == ["1", "2", "3"]
    g.set_start("x", "C")
    assert g.x_names == ["C", "D", "E", "F"] and g.x_start == "C"
    with pytest.raises(GridError):
        g.set_start("y", "I")


def test_set_levels_keeps_active_in_range():
    g = grid(active_level=1)
    g.set_levels([Level("only", 1.0)])
    assert g.active_level == 0 and g.level().name == "only"


def test_round_trip_json():
    g = grid(rotation_deg=15.0, bubbles="all", active_level=1, visible=False,
             x_text="25', 30'", y_text="20'")
    g.rename_line("y", 0, "1A")
    d = g.to_dict()
    json.dumps(d)
    g2 = RectGrid.from_dict(d)
    assert g2.to_dict() == d and g2.y_names[0] == "1A" and g2.visible is False


@pytest.mark.parametrize("patch", [
    {"x": {"spacings": [], "names": [], "start": "A", "text": ""}},
    {"origin": [0, 0]},
    {"x": {"spacings": [-1.0], "start": "A", "text": ""}},
    {"levels": "nope"},
    {"rotation_deg": "fast"}])
def test_from_dict_rejects_bad_blocks(patch):
    d = grid().to_dict()
    d.update(patch)
    with pytest.raises(GridError):
        RectGrid.from_dict(d)


def test_from_dict_fills_defaults():
    d = grid().to_dict()
    d["x"]["names"] = ["A", "B"]            # wrong length -> regenerated
    del d["levels"]
    d.pop("bubbles")
    g = RectGrid.from_dict(d)
    assert g.x_names == ["A", "B", "C"] and g.bubbles == "top_left"
    assert len(g.levels) == 1 and g.levels[0].z == pytest.approx(d["origin"][2])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_rect.py -q`
Expected: FAIL with `ImportError: cannot import name 'Level'`.

- [ ] **Step 3: Append the geometry base and `RectGrid` to `_grid.py`**

```python
# ------------------------------------------------------------ geometry

@dataclass
class Level:
    name: str
    z: float


@dataclass
class Bubble:
    name: str
    at: tuple              # (x, y, z) world
    toward: tuple          # unit (dx, dy) pointing away from the line end


@dataclass
class GridLine:
    name: str
    direction: str         # "x" | "y" | "radii" | "angles"
    index: int
    points: list           # [(x, y, z), ...] world, a polyline
    bubbles: list          # [Bubble]


@dataclass
class Node:
    names: tuple           # (first name, second name), e.g. ("B", "3")
    at: tuple              # (x, y, z) world


def cumulative(spacings):
    out = [0.0]
    for s in spacings:
        out.append(out[-1] + float(s))
    return out


def rotate_xy(x, y, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c)


def sorted_levels(levels):
    return sorted((Level(str(lv.name), float(lv.z)) for lv in levels), key=lambda lv: lv.z)


def _xyz(seq):
    vals = [float(c) for c in seq]
    if len(vals) != 3:
        raise GridError("origin needs three coordinates")
    return tuple(vals)


def _levels_from(raw, fallback_z):
    if raw is None:
        return [Level("Level 1", float(fallback_z))]
    levels = [Level(str(lv["name"]), float(lv["z"])) for lv in raw]
    return levels or [Level("Level 1", float(fallback_z))]


def _extend_from(raw, keys):
    raw = raw or {}
    return {k: float(raw.get(k, 0.0)) for k in keys}


def _bubbles_mode(raw):
    return raw if raw in ("top_left", "all") else "top_left"


class _GridMixin:
    """Behaviour shared by both grid kinds; fields live in the dataclasses."""

    def _finish_init(self):
        self.levels = sorted_levels(self.levels) or [Level("Level 1", float(self.origin[2]))]
        self.active_level = min(max(0, int(self.active_level)), len(self.levels) - 1)
        self.origin = tuple(float(c) for c in self.origin)

    def level(self, index=None):
        return self.levels[self.active_level if index is None else int(index)]

    def to_world(self, u, v, z):
        x, y = rotate_xy(u, v, self.rotation_deg)
        return (self.origin[0] + x, self.origin[1] + y, float(z))

    def direction(self, du, dv):
        return rotate_xy(du, dv, self.rotation_deg)

    def set_levels(self, levels):
        self.levels = sorted_levels(levels) or [Level("Level 1", float(self.origin[2]))]
        self.active_level = min(max(0, int(self.active_level)), len(self.levels) - 1)

    def nearest(self, point, level_index=None):
        best = None
        indices = range(len(self.levels)) if level_index is None else [int(level_index)]
        for li in indices:
            for node in self.intersections(li):
                d = math.dist(node.at, point)
                if best is None or d < best[2]:
                    best = (node, self.levels[li], d)
        return best

    def _levels_dicts(self):
        return [{"name": lv.name, "z": float(lv.z)} for lv in self.levels]


@dataclass
class RectGrid(_GridMixin):
    id: str
    name: str
    origin: tuple = (0.0, 0.0, 0.0)
    rotation_deg: float = 0.0
    x_text: str = ""
    x_spacings: list = field(default_factory=list)
    x_names: list = field(default_factory=list)
    x_start: str = "A"
    y_text: str = ""
    y_spacings: list = field(default_factory=list)
    y_names: list = field(default_factory=list)
    y_start: str = "1"
    extend: dict = field(default_factory=lambda: {"x_neg": 0.0, "x_pos": 0.0,
                                                  "y_neg": 0.0, "y_pos": 0.0})
    bubbles: str = "top_left"
    levels: list = field(default_factory=list)
    active_level: int = 0
    visible: bool = True
    kind = "rect"

    def __post_init__(self):
        self.x_names = reconcile_names(self.x_start, len(self.x_spacings) + 1, self.x_names)
        self.y_names = reconcile_names(self.y_start, len(self.y_spacings) + 1, self.y_names)
        self._finish_init()

    # -- editing
    def set_spacings(self, direction, spacings, text):
        spacings = [float(s) for s in spacings]
        if direction == "x":
            self.x_names = reconcile_names(self.x_start, len(spacings) + 1, self.x_names)
            self.x_spacings, self.x_text = spacings, str(text)
        else:
            self.y_names = reconcile_names(self.y_start, len(spacings) + 1, self.y_names)
            self.y_spacings, self.y_text = spacings, str(text)

    def set_start(self, direction, start):
        if direction == "x":
            self.x_names = name_sequence(start, len(self.x_spacings) + 1)
            self.x_start = str(start).strip()
        else:
            self.y_names = name_sequence(start, len(self.y_spacings) + 1)
            self.y_start = str(start).strip()

    def rename_line(self, direction, index, new_name):
        names = self.x_names if direction == "x" else self.y_names
        text = str(new_name).strip()
        if text:
            names[int(index)] = text

    # -- geometry
    def lines(self, level_index=None):
        z = self.level(level_index).z
        xs, ys = cumulative(self.x_spacings), cumulative(self.y_spacings)
        e = self.extend
        out = []
        for i, (u, name) in enumerate(zip(xs, self.x_names)):
            a = self.to_world(u, -e["y_neg"], z)
            b = self.to_world(u, ys[-1] + e["y_pos"], z)
            bubbles = [Bubble(name, b, self.direction(0.0, 1.0))]
            if self.bubbles == "all":
                bubbles.append(Bubble(name, a, self.direction(0.0, -1.0)))
            out.append(GridLine(name, "x", i, [a, b], bubbles))
        for j, (v, name) in enumerate(zip(ys, self.y_names)):
            a = self.to_world(-e["x_neg"], v, z)
            b = self.to_world(xs[-1] + e["x_pos"], v, z)
            bubbles = [Bubble(name, a, self.direction(-1.0, 0.0))]
            if self.bubbles == "all":
                bubbles.append(Bubble(name, b, self.direction(1.0, 0.0)))
            out.append(GridLine(name, "y", j, [a, b], bubbles))
        return out

    def intersections(self, level_index=None):
        z = self.level(level_index).z
        xs, ys = cumulative(self.x_spacings), cumulative(self.y_spacings)
        return [Node((xn, yn), self.to_world(u, v, z))
                for u, xn in zip(xs, self.x_names) for v, yn in zip(ys, self.y_names)]

    def corner_marks(self, level_index=None):
        z = self.level(level_index).z
        X, Y = cumulative(self.x_spacings)[-1], cumulative(self.y_spacings)[-1]
        return [self.to_world(u, v, z) for u, v in ((0.0, 0.0), (X, 0.0), (X, Y), (0.0, Y))]

    # -- block
    def to_dict(self):
        return {"id": self.id, "name": self.name, "kind": "rect", "visible": bool(self.visible),
                "origin": [float(c) for c in self.origin],
                "rotation_deg": float(self.rotation_deg),
                "x": {"text": self.x_text, "spacings": [float(s) for s in self.x_spacings],
                      "names": list(self.x_names), "start": self.x_start},
                "y": {"text": self.y_text, "spacings": [float(s) for s in self.y_spacings],
                      "names": list(self.y_names), "start": self.y_start},
                "extend": {k: float(self.extend.get(k, 0.0))
                           for k in ("x_neg", "x_pos", "y_neg", "y_pos")},
                "bubbles": self.bubbles, "levels": self._levels_dicts(),
                "active_level": int(self.active_level)}

    @classmethod
    def from_dict(cls, d):
        try:
            x, y = d["x"], d["y"]
            xs = [float(s) for s in x["spacings"]]
            ys = [float(s) for s in y["spacings"]]
            if not xs or not ys:
                raise GridError("a direction has no spacings")
            if any(s <= 0 for s in xs + ys):
                raise GridError("a spacing is not positive")
            origin = _xyz(d.get("origin", (0.0, 0.0, 0.0)))
            return cls(id=str(d["id"]), name=str(d.get("name", d["id"])), origin=origin,
                       rotation_deg=float(d.get("rotation_deg", 0.0)),
                       x_text=str(x.get("text", "")), x_spacings=xs,
                       x_names=[str(n) for n in x.get("names", [])], x_start=str(x.get("start", "A")),
                       y_text=str(y.get("text", "")), y_spacings=ys,
                       y_names=[str(n) for n in y.get("names", [])], y_start=str(y.get("start", "1")),
                       extend=_extend_from(d.get("extend"), ("x_neg", "x_pos", "y_neg", "y_pos")),
                       bubbles=_bubbles_mode(d.get("bubbles")),
                       levels=_levels_from(d.get("levels"), origin[2]),
                       active_level=int(d.get("active_level", 0)),
                       visible=bool(d.get("visible", True)))
        except (KeyError, TypeError, ValueError) as exc:
            raise GridError(f"bad rectangular grid: {exc}") from None
```

Note: `GridError` is a `ValueError`, so the `except` clause re-wraps it with the context prefix. `reconcile_names` receives a wrong-length `names` list from a file: it is not the generated sequence, so it is kept and extended or truncated. For the "wrong length" test the names `["A", "B"]` are exactly the generated prefix, so they regenerate; a renamed list of the wrong length is truncated or extended, which is the spec's "regenerated from start" only when nothing was renamed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_rect.py -q`
Expected: all pass. The value `18.764` is `7.62 + 9.144 + 2.0`; `3.904` is `10 - 6.096`.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid.py tests/test_grid_rect.py
git commit -m "feat(grid): rectangular grid geometry with levels, rotation, bubbles and nearest node"
```

---

### Task 4: Radial grid geometry

**Files:**
- Modify: `igz_steel/_grid.py` (append)
- Test: `tests/test_grid_radial.py`

**Interfaces:**
- Produces: class `RadialGrid(_GridMixin)` with fields in the code below, `kind == "radial"`, properties `closed`, methods `radius_values()`, `angle_values()`, `lines()`, `intersections()`, `corner_marks()`, `rename_line(direction, index, name)` with directions `"radii"` and `"angles"`, `set_radii(spacings, text)`, `set_angles(steps, text)`, `set_start(direction, start)`, `to_dict()`, `from_dict(d)`. Tangent-leg nodes are named `(arc_name, "T1")` at the start angle and `(arc_name, "T2")` at the end angle.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_radial.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from igz_steel._grid import GridError, Level, RadialGrid

C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))
C60, S60 = math.cos(math.radians(60)), math.sin(math.radians(60))


def rg(**kw):
    base = dict(id="g2", name="Tank", radii=[3.0, 2.0], steps_deg=[30.0, 30.0, 30.0],
                start_deg=0.0, tangent=0.0,
                extend={"radial_in": 0.5, "radial_out": 1.0, "arc": 0.0},
                levels=[Level("L", 0.0)])
    base.update(kw)
    return RadialGrid(**base)


def of(lines, direction):
    return [l for l in lines if l.direction == direction]


def test_radii_angles_and_names():
    g = rg()
    assert g.radius_values() == [3.0, 5.0]
    assert g.angle_values() == [0.0, 30.0, 60.0, 90.0]
    assert g.radii_names == ["A", "B"] and g.angle_names == ["1", "2", "3", "4"]
    assert g.kind == "radial" and not g.closed


def test_radial_line_endpoints_and_bubble():
    line = of(rg().lines(), "angles")[1]
    a, b = line.points
    assert a == pytest.approx((2.5 * C30, 2.5 * S30, 0.0))
    assert b == pytest.approx((6.0 * C30, 6.0 * S30, 0.0))
    assert line.name == "2" and len(line.bubbles) == 1
    assert line.bubbles[0].at == pytest.approx(b)
    assert line.bubbles[0].toward == pytest.approx((C30, S30))
    assert len(of(rg(bubbles="all").lines(), "angles")[1].bubbles) == 2


def test_arc_passes_through_every_radial_line():
    arc = of(rg().lines(), "radii")[1]
    assert arc.name == "B"
    for deg in (0.0, 30.0, 60.0, 90.0):
        p = (5.0 * math.cos(math.radians(deg)), 5.0 * math.sin(math.radians(deg)), 0.0)
        assert any(math.dist(p, q) < 1e-9 for q in arc.points)
    assert all(abs(math.hypot(x, y) - 5.0) < 1e-9 for x, y, _ in arc.points)
    assert len(arc.points) >= 23


def test_tangent_legs():
    g = rg(tangent=2.0, extend={"radial_in": 0.0, "radial_out": 0.0, "arc": 0.5})
    arc = of(g.lines(), "radii")[0]                       # r = 3
    first, second, last = arc.points[0], arc.points[1], arc.points[-1]
    assert second == pytest.approx((3.0, 0.0, 0.0))
    assert math.dist(first, second) == pytest.approx(2.5)
    assert first == pytest.approx((3.0, -2.5, 0.0))      # tangent at 0° toward smaller angles
    assert last == pytest.approx((-2.5, 3.0, 0.0))       # tangent at 90° toward larger angles
    assert (first[0] - second[0]) * second[0] + (first[1] - second[1]) * second[1] == pytest.approx(0.0)
    assert arc.bubbles[0].at == pytest.approx(first) and arc.bubbles[0].toward == pytest.approx((0.0, -1.0))
    nodes = {n.names: n.at for n in g.intersections()}
    assert nodes[("A", "T1")] == pytest.approx(first) and nodes[("A", "T2")] == pytest.approx(last)
    assert nodes[("B", "3")] == pytest.approx((5.0 * C60, 5.0 * S60, 0.0))
    assert len(nodes) == 2 * 4 + 4


def test_arc_extension_without_tangent():
    g = rg(extend={"radial_in": 0.0, "radial_out": 0.0, "arc": 1.5})
    arc = of(g.lines(), "radii")[0]                       # r = 3: 1.5 m of arc = 28.65°
    x, y, _ = arc.points[0]
    assert math.degrees(math.atan2(y, x)) == pytest.approx(-math.degrees(1.5 / 3.0))
    x, y, _ = arc.points[-1]
    assert math.degrees(math.atan2(y, x)) == pytest.approx(90.0 + math.degrees(1.5 / 3.0))
    assert ("A", "T1") not in {n.names for n in g.intersections()}


def test_closed_circle_has_no_duplicate_line_and_no_legs():
    g = rg(steps_deg=[90.0] * 4, tangent=2.0)
    assert g.closed
    assert len(of(g.lines(), "angles")) == 4
    assert len(g.intersections()) == 8
    arc = of(g.lines(), "radii")[0]
    assert math.dist(arc.points[0], arc.points[-1]) < 1e-9
    assert all(abs(math.hypot(x, y) - 3.0) < 1e-9 for x, y, _ in arc.points)


def test_corner_marks_rotation_and_round_trip():
    g = rg(rotation_deg=90.0, origin=(1.0, 1.0, 2.0), tangent=1.0)
    nodes = {n.names: n.at for n in g.intersections()}
    assert nodes[("A", "1")] == pytest.approx((1.0, 4.0, 2.0))      # 0° turned to world +Y
    marks = g.corner_marks()
    assert len(marks) == 5 and marks[-1] == pytest.approx((1.0, 1.0, 2.0))
    d = g.to_dict()
    assert RadialGrid.from_dict(d).to_dict() == d


def test_editing_and_names():
    g = rg()
    g.rename_line("radii", 0, "A.5")
    g.set_radii([3.0, 2.0, 2.0], "10', 2@6.5'")
    assert g.radii_names == ["A.5", "B", "C"] and g.radii_text == "10', 2@6.5'"
    g.set_angles([45.0, 45.0], "2@45")
    assert g.angle_names == ["1", "2", "3"] and g.angle_values() == [0.0, 45.0, 90.0]
    g.set_start("angles", "10")
    assert g.angle_names == ["10", "11", "12"]
    with pytest.raises(GridError):
        RadialGrid.from_dict({"id": "x", "kind": "radial", "radii": {"spacings": []},
                              "angles": {"steps_deg": [30]}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_radial.py -q`
Expected: FAIL with `ImportError: cannot import name 'RadialGrid'`.

- [ ] **Step 3: Append `RadialGrid` to `_grid.py`**

```python
def _arc_degrees(start, end, through):
    """Vertex angles from ``start`` to ``end`` every ``ARC_STEP_DEG``, plus
    every angle in ``through`` that lies inside, sorted and deduplicated."""
    span = end - start
    n = max(1, int(math.ceil(abs(span) / ARC_STEP_DEG)))
    degs = [start + span * k / n for k in range(n + 1)]
    degs += [a for a in through if start - 1e-9 <= a <= end + 1e-9]
    degs.sort()
    out = []
    for d in degs:
        if not out or d - out[-1] > 1e-9:
            out.append(d)
    return out


@dataclass
class RadialGrid(_GridMixin):
    id: str
    name: str
    origin: tuple = (0.0, 0.0, 0.0)
    rotation_deg: float = 0.0
    radii_text: str = ""
    radii: list = field(default_factory=list)        # first radius, then the spacing to each next arc
    radii_names: list = field(default_factory=list)
    radii_start: str = "A"
    angles_text: str = ""
    start_deg: float = 0.0
    steps_deg: list = field(default_factory=list)
    angle_names: list = field(default_factory=list)
    angles_start: str = "1"
    tangent: float = 0.0
    extend: dict = field(default_factory=lambda: {"radial_in": 0.0, "radial_out": 0.0, "arc": 0.0})
    bubbles: str = "top_left"
    levels: list = field(default_factory=list)
    active_level: int = 0
    visible: bool = True
    kind = "radial"

    def __post_init__(self):
        self.radii_names = reconcile_names(self.radii_start, len(self.radii), self.radii_names)
        self.angle_names = reconcile_names(self.angles_start, len(self.steps_deg) + 1, self.angle_names)
        self._finish_init()

    @property
    def closed(self):
        return abs(sum(self.steps_deg) - 360.0) < 1e-6

    def radius_values(self):
        return cumulative(self.radii)[1:]

    def angle_values(self):
        return [self.start_deg + a for a in cumulative(self.steps_deg)]

    def _radial_count(self):
        return len(self.steps_deg) if self.closed else len(self.steps_deg) + 1

    def _polar(self, r, deg, z):
        a = math.radians(deg)
        return self.to_world(r * math.cos(a), r * math.sin(a), z)

    def _tangent(self, deg, forward):
        """World unit vector tangent to a circle at ``deg``, toward increasing
        angles when ``forward`` else decreasing."""
        a = math.radians(deg)
        return self.direction(-math.sin(a), math.cos(a)) if forward else self.direction(math.sin(a), -math.cos(a))

    # -- editing
    def set_radii(self, spacings, text):
        spacings = [float(s) for s in spacings]
        self.radii_names = reconcile_names(self.radii_start, len(spacings), self.radii_names)
        self.radii, self.radii_text = spacings, str(text)

    def set_angles(self, steps, text):
        steps = [float(s) for s in steps]
        self.angle_names = reconcile_names(self.angles_start, len(steps) + 1, self.angle_names)
        self.steps_deg, self.angles_text = steps, str(text)

    def set_start(self, direction, start):
        if direction == "radii":
            self.radii_names = name_sequence(start, len(self.radii))
            self.radii_start = str(start).strip()
        else:
            self.angle_names = name_sequence(start, len(self.steps_deg) + 1)
            self.angles_start = str(start).strip()

    def rename_line(self, direction, index, new_name):
        names = self.radii_names if direction == "radii" else self.angle_names
        text = str(new_name).strip()
        if text:
            names[int(index)] = text

    # -- geometry
    def lines(self, level_index=None):
        z = self.level(level_index).z
        rs, angs = self.radius_values(), self.angle_values()
        e = self.extend
        r_in = max(rs[0] - e["radial_in"], 0.0)
        r_out = rs[-1] + e["radial_out"]
        out = []
        for k in range(self._radial_count()):
            deg, name = angs[k], self.angle_names[k]
            a, b = self._polar(r_in, deg, z), self._polar(r_out, deg, z)
            rad = math.radians(deg)
            outward = self.direction(math.cos(rad), math.sin(rad))
            bubbles = [Bubble(name, b, outward)]
            if self.bubbles == "all" and r_in > 0.0:
                bubbles.append(Bubble(name, a, (-outward[0], -outward[1])))
            out.append(GridLine(name, "angles", k, [a, b], bubbles))
        for j, (r, name) in enumerate(zip(rs, self.radii_names)):
            pts, bubbles = self._arc(name, r, angs, z)
            out.append(GridLine(name, "radii", j, pts, bubbles))
        return out

    def _arc(self, name, r, angs, z):
        start, end = angs[0], angs[-1]
        if self.closed:
            pts = [self._polar(r, d, z) for d in _arc_degrees(start, start + 360.0, angs)]
            return pts, [Bubble(name, pts[0], self._tangent(start, False))]
        e_arc = self.extend["arc"]
        if self.tangent > 0.0:
            leg = self.tangent + e_arc
            p0, p1 = self._polar(r, start, z), self._polar(r, end, z)
            t0, t1 = self._tangent(start, False), self._tangent(end, True)
            a = (p0[0] + t0[0] * leg, p0[1] + t0[1] * leg, z)
            b = (p1[0] + t1[0] * leg, p1[1] + t1[1] * leg, z)
            pts = [a] + [self._polar(r, d, z) for d in _arc_degrees(start, end, angs)] + [b]
        else:
            ext = math.degrees(e_arc / r) if r > 0.0 else 0.0
            degs = _arc_degrees(start - ext, end + ext, angs)
            pts = [self._polar(r, d, z) for d in degs]
            t0, t1 = self._tangent(degs[0], False), self._tangent(degs[-1], True)
        bubbles = [Bubble(name, pts[0], t0)]
        if self.bubbles == "all":
            bubbles.append(Bubble(name, pts[-1], t1))
        return pts, bubbles

    def intersections(self, level_index=None):
        z = self.level(level_index).z
        rs, angs = self.radius_values(), self.angle_values()
        n = self._radial_count()
        nodes = [Node((rn, self.angle_names[k]), self._polar(r, angs[k], z))
                 for r, rn in zip(rs, self.radii_names) for k in range(n)]
        if self.tangent > 0.0 and not self.closed:
            for line in self.lines(level_index):
                if line.direction == "radii":
                    nodes.append(Node((line.name, "T1"), line.points[0]))
                    nodes.append(Node((line.name, "T2"), line.points[-1]))
        return nodes

    def corner_marks(self, level_index=None):
        z = self.level(level_index).z
        rs, angs = self.radius_values(), self.angle_values()
        return [self._polar(rs[0], angs[0], z), self._polar(rs[-1], angs[0], z),
                self._polar(rs[-1], angs[-1], z), self._polar(rs[0], angs[-1], z),
                self.to_world(0.0, 0.0, z)]

    # -- block
    def to_dict(self):
        return {"id": self.id, "name": self.name, "kind": "radial", "visible": bool(self.visible),
                "origin": [float(c) for c in self.origin],
                "rotation_deg": float(self.rotation_deg),
                "radii": {"text": self.radii_text, "spacings": [float(s) for s in self.radii],
                          "names": list(self.radii_names), "start": self.radii_start},
                "angles": {"text": self.angles_text, "start_deg": float(self.start_deg),
                           "steps_deg": [float(s) for s in self.steps_deg],
                           "names": list(self.angle_names), "start": self.angles_start},
                "tangent": float(self.tangent),
                "extend": {k: float(self.extend.get(k, 0.0))
                           for k in ("radial_in", "radial_out", "arc")},
                "bubbles": self.bubbles, "levels": self._levels_dicts(),
                "active_level": int(self.active_level)}

    @classmethod
    def from_dict(cls, d):
        try:
            rd, an = d["radii"], d["angles"]
            radii = [float(s) for s in rd["spacings"]]
            steps = [float(s) for s in an["steps_deg"]]
            if not radii or not steps:
                raise GridError("radii or angles are empty")
            if any(s <= 0 for s in radii + steps):
                raise GridError("a radius spacing or angle step is not positive")
            if sum(steps) > 360.0 + 1e-9:
                raise GridError("angle steps sweep more than 360°")
            origin = _xyz(d.get("origin", (0.0, 0.0, 0.0)))
            return cls(id=str(d["id"]), name=str(d.get("name", d["id"])), origin=origin,
                       rotation_deg=float(d.get("rotation_deg", 0.0)),
                       radii_text=str(rd.get("text", "")), radii=radii,
                       radii_names=[str(n) for n in rd.get("names", [])],
                       radii_start=str(rd.get("start", "A")),
                       angles_text=str(an.get("text", "")), start_deg=float(an.get("start_deg", 0.0)),
                       steps_deg=steps, angle_names=[str(n) for n in an.get("names", [])],
                       angles_start=str(an.get("start", "1")),
                       tangent=max(0.0, float(d.get("tangent", 0.0))),
                       extend=_extend_from(d.get("extend"), ("radial_in", "radial_out", "arc")),
                       bubbles=_bubbles_mode(d.get("bubbles")),
                       levels=_levels_from(d.get("levels"), origin[2]),
                       active_level=int(d.get("active_level", 0)),
                       visible=bool(d.get("visible", True)))
        except (KeyError, TypeError, ValueError) as exc:
            raise GridError(f"bad radial grid: {exc}") from None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_radial.py tests/test_grid_rect.py -q`
Expected: all pass. In `test_tangent_legs` the node count is 2 arcs × 4 radial lines + 2 arcs × 2 leg ends = 12.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid.py tests/test_grid_radial.py
git commit -m "feat(grid): radial grids with arcs, radial lines, tangent legs and closed circles"
```

---

### Task 5: Document block helpers and level generation

**Files:**
- Modify: `igz_steel/_grid.py` (append)
- Test: `tests/test_grid_store.py`

**Interfaces:**
- Produces: `grid_from_dict(d) -> RectGrid | RadialGrid`, `parse_block(raw) -> (grids, meta, errors)` with `meta = {"active_grid": str | None, "units": str}` (never raises), `dump_block(grids, active_grid=None, units="imperial") -> dict`, `new_grid_id(grids) -> str`, `unique_name(grids, base) -> str`, `add_levels(levels, count, spacing, direction, pattern="EL {el}", units="imperial") -> list[Level]`, `default_rect_grid(gid, name, units="imperial") -> RectGrid`, `LEVEL_PATTERNS`.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_store.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from igz_steel._grid import (FT_M, GridError, Level, RectGrid, add_levels, default_rect_grid,
                             dump_block, grid_from_dict, new_grid_id, parse_block, unique_name)


def good(gid="g1", name="Main"):
    return RectGrid(id=gid, name=name, x_spacings=[7.62], y_spacings=[6.096],
                    levels=[Level("EL 100'-0\"", 30.48)]).to_dict()


def test_parse_block_skips_bad_grids_and_keeps_good_ones():
    raw = {"version": 1, "grids": [good(), {"id": "g2", "kind": "rect", "x": {}},
                                   {"id": "g3", "kind": "cube"}, "junk"],
           "active_grid": "g3", "units": "metric"}
    grids, meta, errors = parse_block(raw)
    assert [g.id for g in grids] == ["g1"]
    assert len(errors) == 3 and "grid 2" in errors[0]
    assert meta == {"active_grid": "g1", "units": "metric"}    # g3 is gone, so the first grid


def test_parse_block_tolerates_garbage_and_newer_versions():
    assert parse_block(None) == ([], {"active_grid": None, "units": "imperial"}, [])
    assert parse_block({}) == ([], {"active_grid": None, "units": "imperial"}, [])
    grids, _meta, errors = parse_block("nope")
    assert grids == [] and errors
    grids, meta, _ = parse_block({"version": 7, "grids": [good()], "future_key": 1, "units": "cubits"})
    assert len(grids) == 1 and meta["units"] == "imperial"
    grids, _meta, errors = parse_block({"grids": "not a list"})
    assert grids == [] and errors


def test_duplicate_ids_are_renumbered():
    grids, _, _ = parse_block({"grids": [good("g1"), good("g1", "Other")]})
    assert [g.id for g in grids] == ["g1", "g2"]


def test_dump_round_trip_and_ids():
    grids, meta, _ = parse_block({"grids": [good()], "active_grid": "g1", "units": "metric"})
    block = dump_block(grids, meta["active_grid"], meta["units"])
    assert block["version"] == 1 and block["grids"][0] == good() and block["units"] == "metric"
    assert dump_block([], None, "cubits")["units"] == "imperial"
    assert new_grid_id(grids) == "g2"
    assert unique_name(grids, "Main") == "Main 2" and unique_name(grids, "Rack") == "Rack"
    assert grid_from_dict(good()).kind == "rect"
    with pytest.raises(GridError):
        grid_from_dict({"id": "x", "kind": "hex"})


def test_add_levels_up_and_down_with_patterns():
    base = [Level("EL 100'-0\"", 30.48)]
    up = add_levels(base, 2, 12 * FT_M, "up", "T.O.S. EL {el}", "imperial")
    assert [lv.name for lv in up] == ["EL 100'-0\"", "T.O.S. EL 112'-0\"", "T.O.S. EL 124'-0\""]
    assert up[-1].z == pytest.approx(30.48 + 24 * FT_M)
    down = add_levels(base, 1, 3.0, "down", "Level {n}", "metric")
    assert [lv.name for lv in down] == ["Level 2", "EL 100'-0\""]
    assert down[0].z == pytest.approx(27.48)
    assert add_levels(base, 1, 1.0, "up", "EL {el}", "metric")[-1].name == "EL 31.480 m"


def test_add_levels_refuses_bad_input():
    base = [Level("a", 0.0), Level("b", 6.0)]
    with pytest.raises(GridError, match="at least one"):
        add_levels(base, 0, 3.0, "up")
    with pytest.raises(GridError, match="greater than zero"):
        add_levels(base, 1, 0.0, "up")
    with pytest.raises(GridError, match="pattern"):
        add_levels(base, 1, 3.0, "up", "EL {elevation}")
    with pytest.raises(GridError, match="At most"):
        add_levels(base, 99, 1.0, "up")


def test_default_grid():
    g = default_rect_grid("g1", "Grid 1", "imperial")
    assert g.x_text == "3@25'" and g.y_text == "2@20'" and g.x_names == ["A", "B", "C", "D"]
    assert g.levels[0].name == "EL 0'-0\"" and g.extend["x_neg"] == pytest.approx(5 * FT_M)
    m = default_rect_grid("g1", "Grid 1", "metric")
    assert m.x_text == "3@8" and m.levels[0].name == "EL 0.000 m"
```

The duplicate-elevation guard in `add_levels` cannot be reached from a sorted
list (new levels always lie above the top or below the bottom), so it has no
test; it stays as a guard for callers that pass unsorted or hand-built lists.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_store.py -q`
Expected: FAIL with `ImportError: cannot import name 'add_levels'`.

- [ ] **Step 3: Append the block helpers to `_grid.py`**

```python
# ------------------------------------------------------------ document block

LEVEL_PATTERNS = ("EL {el}", "T.O.S. EL {el}", "Level {n}")


def grid_from_dict(d):
    kind = d.get("kind") if isinstance(d, dict) else None
    if kind == "rect":
        return RectGrid.from_dict(d)
    if kind == "radial":
        return RadialGrid.from_dict(d)
    raise GridError(f"unknown grid kind {kind!r}")


def new_grid_id(grids):
    used = {g.id for g in grids}
    n = 1
    while f"g{n}" in used:
        n += 1
    return f"g{n}"


def unique_name(grids, base):
    names = {g.name for g in grids}
    if base not in names:
        return base
    n = 2
    while f"{base} {n}" in names:
        n += 1
    return f"{base} {n}"


def parse_block(raw):
    """``(grids, meta, errors)`` from the document value. Never raises: a bad
    grid is reported in ``errors`` and skipped, the rest load."""
    grids, errors = [], []
    meta = {"active_grid": None, "units": "imperial"}
    if raw is None or raw == {}:
        return grids, meta, errors
    if not isinstance(raw, dict):
        errors.append("grid data is not an object")
        return grids, meta, errors
    items = raw.get("grids", []) or []
    if not isinstance(items, list):
        errors.append("grids is not a list")
        items = []
    for i, d in enumerate(items):
        try:
            g = grid_from_dict(d)
        except GridError as exc:
            errors.append(f"grid {i + 1}: {exc}")
            continue
        if any(x.id == g.id for x in grids):
            g.id = new_grid_id(grids)
        grids.append(g)
    if raw.get("units") in UNITS:
        meta["units"] = raw["units"]
    act = raw.get("active_grid")
    if any(g.id == act for g in grids):
        meta["active_grid"] = act
    elif grids:
        meta["active_grid"] = grids[0].id
    return grids, meta, errors


def dump_block(grids, active_grid=None, units="imperial"):
    return {"version": BLOCK_VERSION, "grids": [g.to_dict() for g in grids],
            "active_grid": active_grid, "units": units if units in UNITS else "imperial"}


def add_levels(levels, count, spacing, direction, pattern="EL {el}", units="imperial"):
    """``count`` new levels every ``spacing`` metres above the top (``"up"``)
    or below the bottom (``"down"``), named by ``pattern`` with ``{el}`` the
    formatted elevation and ``{n}`` the running number."""
    count, spacing = int(count), float(spacing)
    if count < 1:
        raise GridError("Add at least one level")
    if spacing <= 0.0:
        raise GridError("The level spacing must be greater than zero")
    out = sorted_levels(list(levels))
    if len(out) + count > MAX_LEVELS:
        raise GridError(f"At most {MAX_LEVELS} levels")
    base = out[-1].z if direction == "up" else out[0].z
    step = spacing if direction == "up" else -spacing
    new = []
    for k in range(1, count + 1):
        z = base + step * k
        if any(abs(z - lv.z) < LEVEL_TOL for lv in out):
            raise GridError(f"A level already exists at {fmt_length(z, units)}")
        try:
            name = str(pattern).format(el=fmt_length(z, units), n=len(out) + k)
        except (KeyError, IndexError, ValueError):
            raise GridError("The name pattern may use {el} and {n} only") from None
        new.append(Level(name, z))
    return sorted_levels(out + new)


def default_rect_grid(gid, name, units="imperial"):
    if units == "metric":
        xt, yt, ext = "3@8", "2@6", 1.5
    else:
        xt, yt, ext = "3@25'", "2@20'", 5 * FT_M
    return RectGrid(id=gid, name=name, x_text=xt, x_spacings=parse_spacing_list(xt, units),
                    y_text=yt, y_spacings=parse_spacing_list(yt, units),
                    extend={k: ext for k in ("x_neg", "x_pos", "y_neg", "y_pos")},
                    levels=[Level("EL " + fmt_length(0.0, units), 0.0)])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_store.py tests/test_grid_parse.py tests/test_grid_names.py tests/test_grid_rect.py tests/test_grid_radial.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid.py tests/test_grid_store.py
git commit -m "feat(grid): document block parsing and dumping, level generation, default grid"
```

---

### Task 6: Host glue: `GridStore` with overlay, snap provider and pickables

**Files:**
- Create: `igz_steel/_grid_host.py`
- Create: `tests/stubs/core/snap.py`
- Test: `tests/test_grid_host.py`

**Interfaces:**
- Consumes: `_grid.parse_block`, `_grid.dump_block`, grid methods `lines`, `intersections`, `corner_marks`, `level`, `levels`, `active_level`, `visible`, `id`, `name`.
- Produces: `GridStore(app)` with attributes `grids`, `meta`, `errors`, `selected_id`, `confirm` (callable `(grid) -> bool` or `None`), `on_edit_request` (callable `(grid_id)` or `None`); methods `reload()`, `raw_block() -> dict`, `save_block(block)`, `find(gid)`, `visible_grids()`, `invalidate()`, `nodes_px(viewport) -> list[(px, py, grid, level, node)]`, `tip(grid, level, node) -> str`, `paint(viewport, painter)`, `snap(viewport, snap, px, py)`, `pick(viewport, px, py)`, `on_select(item)`, `delete(item)`, `register()`. Module constants `COLOR`, `BUBBLE_PX`, `MARK_PX`, `DEFAULT_SNAP_PX`; helper `project(app, viewport, points) -> list[(px, py) | None]`.

- [ ] **Step 1: Add the snap stub**

`tests/stubs/core/snap.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
class SnapResult:
    """Just enough of core.snap.SnapResult for the grid snap provider."""
    def __init__(self, point, kind, color, label=None):
        self.point, self.kind, self.color, self.label = point, kind, color, label
```

- [ ] **Step 2: Write the failing tests**

`tests/test_grid_host.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
import math
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage, QPainter, QPalette, QVector3D

from igz_steel._grid import Level, RectGrid, dump_block

FT = 0.3048


class FakeViewport:
    snap_threshold_px = 10.0

    def __init__(self):
        self.scene = SimpleNamespace(edit_group=None, version=0)
        self.camera = SimpleNamespace(yaw=0.0, pitch=0.0, distance=10.0, perspective=False,
                                      target=QVector3D(0, 0, 0))
        self.updates = 0

    def _world_to_pixel(self, v):           # crude oblique projection, enough for pixels
        return (100.0 + v.x() * 10.0, 300.0 - v.y() * 10.0 - v.z() * 10.0)

    def width(self):
        return 800

    def height(self):
        return 600

    def update(self):
        self.updates += 1

    def palette(self):
        return QPalette()

    def backgroundRole(self):
        return QPalette.Window


class FakeApp:
    def __init__(self, raw=None):
        self._raw = raw
        self.viewport = FakeViewport()
        self.registered = {}
        self.sets = []

    def document_data(self, default=None):
        return self._raw if self._raw is not None else default

    def set_document_data(self, value):
        self.sets.append(value)
        self._raw = value

    def add_overlay(self, fn):
        self.registered["overlay"] = fn

    def add_snap_provider(self, fn):
        self.registered["snap"] = fn

    def add_pickable(self, pick, on_select=None, delete=None):
        self.registered["pick"] = (pick, on_select, delete)


def block(*grids, active="g1", units="imperial"):
    return dump_block(list(grids), active, units)


def main_grid(**kw):
    base = dict(id="g1", name="Main", x_spacings=[7.62], y_spacings=[6.096],
                extend={"x_neg": 1.0, "x_pos": 1.0, "y_neg": 1.0, "y_pos": 1.0},
                levels=[Level("EL 100", 0.0), Level("EL 112", 12 * FT)])
    base.update(kw)
    return RectGrid(**base)


def world_px(vp, p):
    return vp._world_to_pixel(QVector3D(*p))


@pytest.fixture
def store():
    from igz_steel._grid_host import GridStore
    app = FakeApp(block(main_grid()))
    return GridStore(app), app


def test_reload_reads_block_and_skips_bad_grids():
    from igz_steel._grid_host import GridStore
    raw = block(main_grid())
    raw["grids"].append({"id": "g2", "kind": "rect", "x": {}})
    s = GridStore(FakeApp(raw))
    assert [g.id for g in s.grids] == ["g1"] and len(s.errors) == 1
    assert s.raw_block()["grids"][0]["id"] == "g1"
    assert GridStore(FakeApp(None)).grids == []


def test_snap_hits_nearest_node_on_any_level(store):
    s, app = store
    vp = app.viewport
    target = (7.62, 6.096, 12 * FT)                    # B-2 on the upper level
    px, py = world_px(vp, target)
    res = s.snap(vp, SimpleNamespace(point=QVector3D(0, 0, 0)), px + 3, py - 2)
    assert res is not None and res.label == "B-2 · EL 112" and res.kind == "reference"
    assert (res.point.x(), res.point.y(), res.point.z()) == pytest.approx(target)
    assert s.snap(vp, SimpleNamespace(point=QVector3D(0, 0, 0)), px + 40, py) is None


def test_snap_tip_names_grid_when_several_exist():
    from igz_steel._grid_host import GridStore
    other = main_grid(id="g2", name="Rack", origin=(50.0, 0.0, 0.0))
    s = GridStore(FakeApp(block(main_grid(), other)))
    vp = s.app.viewport
    px, py = world_px(vp, (0.0, 0.0, 0.0))
    res = s.snap(vp, SimpleNamespace(point=QVector3D(0, 0, 0)), px, py)
    assert res.label == "Main A-1 · EL 100"


def test_snap_is_silent_while_editing_or_hidden(store):
    s, app = store
    vp = app.viewport
    px, py = world_px(vp, (0.0, 0.0, 0.0))
    vp.scene.edit_group = object()
    assert s.snap(vp, SimpleNamespace(point=QVector3D()), px, py) is None
    vp.scene.edit_group = None
    s.grids[0].visible = False
    s.invalidate()
    assert s.snap(vp, SimpleNamespace(point=QVector3D()), px, py) is None


def test_snap_never_raises(store):
    s, app = store
    assert s.snap(None, None, None, None) is None


def test_projection_cache_follows_camera_and_data(store):
    s, app = store
    vp = app.viewport
    first = s.nodes_px(vp)
    assert len(first) == 8 and s.nodes_px(vp) is first
    vp.camera.yaw = 0.5
    assert s.nodes_px(vp) is not first
    again = s.nodes_px(vp)
    s.invalidate()
    assert s.nodes_px(vp) is not again


def test_paint_runs_offscreen_with_and_without_batch_projection(qapp, store):
    s, app = store
    vp = app.viewport
    img = QImage(800, 600, QImage.Format_ARGB32)
    painter = QPainter(img)
    s.paint(vp, painter)
    painter.end()
    assert not s._overlay_failed

    def world_to_pixels(points):
        px = [100.0 + p[0] * 10.0 for p in points]
        py = [300.0 - p[1] * 10.0 - p[2] * 10.0 for p in points]
        return px, py, [True] * len(points)
    app.world_to_pixels = world_to_pixels
    s.invalidate()
    painter = QPainter(img)
    s.paint(vp, painter)
    painter.end()
    assert not s._overlay_failed

    app.world_to_pixels = lambda pts: (_ for _ in ()).throw(RuntimeError("boom"))
    s.invalidate()
    assert len(s.nodes_px(vp)) == 8                   # fell back to the per-point helper


def test_paint_error_disables_overlay_once(qapp, store):
    s, app = store
    s.grids[0].lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad"))
    img = QImage(80, 60, QImage.Format_ARGB32)
    painter = QPainter(img)
    s.paint(app.viewport, painter)
    s.paint(app.viewport, painter)
    painter.end()
    assert s._overlay_failed


def test_pick_select_and_delete(qapp, store):
    s, app = store
    vp = app.viewport
    g = s.grids[0]
    cx, cy, _bubble = s.bubble_centres(vp, g)[0]
    assert s.pick(vp, cx + 2, cy - 2) == "g1"
    assert s.pick(vp, cx + 60, cy) is None
    s.on_select("g1")
    assert s.selected_id == "g1" and vp.updates >= 1
    s.on_select(None)
    assert s.selected_id is None
    s.confirm = lambda grid: False
    s.delete("g1")
    assert app.sets == []
    s.confirm = lambda grid: True
    s.delete("g1")
    assert app.sets[-1]["grids"] == [] and app.sets[-1]["active_grid"] is None
    assert s.grids == []


def test_double_pick_requests_edit(store):
    s, app = store
    got = []
    s.on_edit_request = got.append
    s.on_select("g1")
    s.on_select("g1")
    assert got == ["g1"]


def test_register_guards_missing_api():
    from igz_steel._grid_host import GridStore
    app = FakeApp(block(main_grid()))
    del FakeApp.add_pickable
    try:
        s = GridStore(app)
        s.register()
        assert "overlay" in app.registered and "snap" in app.registered and "pick" not in app.registered
    finally:
        FakeApp.add_pickable = lambda self, pick, on_select=None, delete=None: self.registered.__setitem__("pick", (pick, on_select, delete))
    app = FakeApp(block(main_grid()))
    GridStore(app).register()
    assert "pick" in app.registered
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_host.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'igz_steel._grid_host'`.

- [ ] **Step 4: Write `_grid_host.py`**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grids in the host: document data, the viewport overlay, the snap provider
and pickable bubbles. Geometry comes from ``_grid``; this module projects,
paints and talks to ``ExtensionApp``. Nothing here may raise into the host."""
from __future__ import annotations

import logging
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QVector3D

from ._grid import dump_block, parse_block

log = logging.getLogger("ingetrazo.plugins.igz_steel")

COLOR = (0.95, 0.45, 0.16)             # IngeTrazo's accent, as the Levels example uses
BUBBLE_PX = 10.0
MARK_PX = 6.0
DEFAULT_SNAP_PX = 12.0
DOUBLE_CLICK_S = 0.4


def _qcolor(alpha=1.0):
    return QColor.fromRgbF(COLOR[0], COLOR[1], COLOR[2], alpha)


def project(app, viewport, points):
    """``[(px, py) | None]`` for world points: through ``app.world_to_pixels``
    when the host has it (one batch), else one by one through the viewport."""
    if not points:
        return []
    batch = getattr(app, "world_to_pixels", None)
    if callable(batch):
        try:
            px, py, front = batch([list(p) for p in points])
            return [(float(px[i]), float(py[i])) if bool(front[i]) else None
                    for i in range(len(points))]
        except Exception:
            log.debug("igz_steel grids: world_to_pixels failed, using the per-point helper",
                      exc_info=True)
    single = getattr(viewport, "_world_to_pixel", None)
    out = []
    for p in points:
        r = None
        if callable(single):
            try:
                r = single(QVector3D(float(p[0]), float(p[1]), float(p[2])))
            except Exception:
                r = None
        out.append((float(r[0]), float(r[1])) if r is not None else None)
    return out


def _camera_key(viewport):
    cam = getattr(viewport, "camera", None)
    parts = []
    for attr in ("yaw", "pitch", "distance", "perspective", "target", "zoom", "ortho_scale"):
        v = getattr(cam, attr, None)
        if isinstance(v, QVector3D):
            v = (round(v.x(), 6), round(v.y(), 6), round(v.z(), 6))
        elif isinstance(v, float):
            v = round(v, 9)
        parts.append(v)
    for fn in ("width", "height"):
        try:
            parts.append(getattr(viewport, fn)())
        except Exception:
            parts.append(None)
    return tuple(parts)


class GridStore:
    """The grids of the open document and everything the viewport needs."""

    def __init__(self, app):
        self.app = app
        self.grids = []
        self.meta = {"active_grid": None, "units": "imperial"}
        self.errors = []
        self.selected_id = None
        self.confirm = None               # callable(grid) -> bool, set by _core
        self.on_edit_request = None       # callable(grid_id), set by _core
        self._version = 0
        self._cache_key = None
        self._cache = []
        self._overlay_failed = False
        self._last_pick = (None, 0.0)
        self.reload()

    # -- data -----------------------------------------------------------------
    def reload(self):
        try:
            raw = self.app.document_data({})
        except Exception:
            raw = {}
        self.grids, self.meta, self.errors = parse_block(raw)
        for e in self.errors:
            log.warning("igz_steel grids: %s", e)
        if self.selected_id and self.find(self.selected_id) is None:
            self.selected_id = None
        self.invalidate()

    def raw_block(self):
        return dump_block(self.grids, self.meta["active_grid"], self.meta["units"])

    def save_block(self, block):
        """One undo step; the host's document-changed hook reloads us too."""
        self.app.set_document_data(block)
        self.reload()

    def find(self, gid):
        for g in self.grids:
            if g.id == gid:
                return g
        return None

    def visible_grids(self):
        return [g for g in self.grids if g.visible]

    def invalidate(self):
        self._version += 1
        self._cache_key = None

    def _editing(self):
        scene = getattr(getattr(self.app, "viewport", None), "scene", None)
        return getattr(scene, "edit_group", None) is not None

    # -- projection -----------------------------------------------------------
    def nodes_px(self, viewport):
        key = (self._version, _camera_key(viewport))
        if key == self._cache_key:
            return self._cache
        entries, pts = [], []
        for g in self.visible_grids():
            for li, level in enumerate(g.levels):
                for node in g.intersections(li):
                    entries.append((g, level, node))
                    pts.append(node.at)
        px = project(self.app, viewport, pts)
        self._cache = [(p[0], p[1], g, level, node)
                       for p, (g, level, node) in zip(px, entries) if p is not None]
        self._cache_key = key
        return self._cache

    def bubble_centres(self, viewport, grid):
        """``[(cx, cy, Bubble)]`` for the grid's active level, pushed out from
        the line end by the bubble radius in screen space."""
        bubbles = [b for ln in grid.lines() for b in ln.bubbles]
        at = project(self.app, viewport, [b.at for b in bubbles])
        out = project(self.app, viewport,
                      [(b.at[0] + b.toward[0], b.at[1] + b.toward[1], b.at[2]) for b in bubbles])
        centres = []
        for b, p, q in zip(bubbles, at, out):
            if p is None:
                continue
            dx, dy = (q[0] - p[0], q[1] - p[1]) if q is not None else (0.0, -1.0)
            n = math.hypot(dx, dy) or 1.0
            centres.append((p[0] + dx / n * BUBBLE_PX, p[1] + dy / n * BUBBLE_PX, b))
        return centres

    def tip(self, grid, level, node):
        text = f"{node.names[0]}-{node.names[1]} · {level.name}"
        return f"{grid.name} {text}" if len(self.grids) > 1 else text

    # -- overlay --------------------------------------------------------------
    def paint(self, viewport, painter):
        if self._overlay_failed:
            return
        try:
            self._paint(viewport, painter)
        except Exception:
            self._overlay_failed = True
            log.exception("igz_steel grids: overlay disabled after an error")

    def _paint(self, viewport, painter):
        grids = self.visible_grids()
        if not grids or self._editing():
            return
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        try:
            bg = QColor(viewport.palette().color(viewport.backgroundRole()))
        except Exception:
            bg = QColor(32, 32, 32)
        clip = getattr(viewport, "_clip_pixel_line", None)
        for g in grids:
            lines = g.lines()
            px = project(self.app, viewport, [p for ln in lines for p in ln.points])
            selected = g.id == self.selected_id
            painter.setPen(QPen(_qcolor(0.9), 2.0 if selected else 1.2,
                                Qt.SolidLine if selected else Qt.DashLine))
            k = 0
            for ln in lines:
                seg = px[k:k + len(ln.points)]
                k += len(ln.points)
                for a, b in zip(seg, seg[1:]):
                    if a is None or b is None:
                        continue
                    if callable(clip):
                        c = clip(a, b, margin=0.0)
                        if c is None:
                            continue
                        a, b = c
                    painter.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            painter.setBrush(QBrush(bg))
            for cx, cy, b in self.bubble_centres(viewport, g):
                painter.setPen(QPen(_qcolor(1.0), 1.2))
                painter.drawEllipse(QPointF(cx, cy), BUBBLE_PX, BUBBLE_PX)
                painter.drawText(QRectF(cx - BUBBLE_PX, cy - BUBBLE_PX, 2 * BUBBLE_PX, 2 * BUBBLE_PX),
                                 Qt.AlignCenter, b.name)
            painter.setBrush(Qt.NoBrush)
            o = project(self.app, viewport, [g.to_world(0.0, 0.0, g.level().z)])[0]
            if o is not None:
                painter.setPen(QPen(_qcolor(1.0)))
                painter.drawText(QPointF(o[0] + 8, o[1] + 14), f"{g.name} · {g.level().name}")
            marks, labels = [], []
            for li, level in enumerate(g.levels):
                if li == g.active_level:
                    continue
                cm = g.corner_marks(li)
                labels.append((len(marks), level.name))
                marks += cm
            mpx = project(self.app, viewport, marks)
            painter.setPen(QPen(_qcolor(0.4), 1.0))
            for p in mpx:
                if p is None:
                    continue
                painter.drawLine(QPointF(p[0] - MARK_PX, p[1]), QPointF(p[0] + MARK_PX, p[1]))
                painter.drawLine(QPointF(p[0], p[1] - MARK_PX), QPointF(p[0], p[1] + MARK_PX))
            for idx, name in labels:
                p = mpx[idx] if idx < len(mpx) else None
                if p is not None:
                    painter.drawText(QPointF(p[0] + 8, p[1] - 4), name)

    # -- snapping -------------------------------------------------------------
    def snap(self, viewport, snap, px, py):
        try:
            if not self.visible_grids() or self._editing():
                return None
            if px is None or py is None:
                point = getattr(snap, "point", None)
                if not isinstance(point, QVector3D):
                    return None
                here = project(self.app, viewport, [(point.x(), point.y(), point.z())])[0]
                if here is None:
                    return None
                px, py = here
            threshold = float(getattr(viewport, "snap_threshold_px", DEFAULT_SNAP_PX)) * 1.5
            best = None
            for x, y, g, level, node in self.nodes_px(viewport):
                d = math.hypot(x - px, y - py)
                if d <= threshold and (best is None or d < best[0]):
                    best = (d, g, level, node)
            if best is None:
                return None
            from core.snap import SnapResult
            _d, g, level, node = best
            return SnapResult(QVector3D(*node.at), "reference", COLOR,
                              label=self.tip(g, level, node))
        except Exception:
            log.exception("igz_steel grids: snap provider error")
            return None

    # -- pickables ------------------------------------------------------------
    def pick(self, viewport, px, py):
        try:
            if self._editing():
                return None
            for g in self.visible_grids():
                for cx, cy, _b in self.bubble_centres(viewport, g):
                    if math.hypot(cx - px, cy - py) <= BUBBLE_PX:
                        return g.id
        except Exception:
            log.exception("igz_steel grids: pick error")
        return None

    def on_select(self, item):
        now = time.monotonic()
        last_id, last_t = self._last_pick
        if item is not None and item == last_id and now - last_t < DOUBLE_CLICK_S \
                and callable(self.on_edit_request):
            self.on_edit_request(item)
        self._last_pick = (item, now)
        self.selected_id = item
        vp = getattr(self.app, "viewport", None)
        g = self.find(item) if item else None
        if g is not None:
            flash = getattr(vp, "flash_status", None)
            if callable(flash):
                try:
                    flash(f"Grid {g.name}: {len(g.levels)} level(s). Delete removes it.", 3000)
                except Exception:
                    pass
        if vp is not None:
            try:
                vp.update()
            except Exception:
                pass

    def delete(self, item):
        g = self.find(item)
        if g is None:
            return
        if callable(self.confirm) and not self.confirm(g):
            return
        grids = [x for x in self.grids if x.id != item]
        active = self.meta["active_grid"]
        if active == item:
            active = grids[0].id if grids else None
        self.selected_id = None
        self.save_block(dump_block(grids, active, self.meta["units"]))

    def register(self):
        app = self.app
        for name, fn in (("add_overlay", self.paint), ("add_snap_provider", self.snap)):
            reg = getattr(app, name, None)
            if callable(reg):
                try:
                    reg(fn)
                except Exception:
                    log.exception("igz_steel grids: %s failed", name)
        reg = getattr(app, "add_pickable", None)
        if callable(reg):
            try:
                reg(pick=self.pick, on_select=self.on_select, delete=self.delete)
            except Exception:
                log.exception("igz_steel grids: add_pickable failed")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_host.py -q`
Expected: all pass. `test_double_pick_requests_edit` relies on the two calls happening within 0.4 s, which they do.

- [ ] **Step 6: Commit**

```bash
git add igz_steel/_grid_host.py tests/stubs/core/snap.py tests/test_grid_host.py
git commit -m "feat(grid): GridStore with document block IO, overlay painter, snap provider and pickables"
```

---

### Task 7: `GridPreview` widget and `GridDialog` (rectangular path)

**Files:**
- Create: `igz_steel/_grid_dialog.py`
- Test: `tests/test_grid_dialog.py`

**Interfaces:**
- Consumes: everything from `_grid.py` (Tasks 1–5).
- Produces: `GridPreview(parent=None, units="imperial")` with `set_grid(grid, level_index=None, fit=False)`, `set_units(units)`, `set_error(text)`, `fit()`, `bubble_at(px, py)`, signal `renamed(str, int, str)`; `GridDialog(parent=None, units=None, persist=True)` with signals `applied(object)`, `pick_origin_requested()`, `pick_direction_requested()`, methods `load_block(raw, notice=None)`, `block() -> dict`, `select_grid(gid)`, `current_grid()`, `set_origin(xyz)`, `set_rotation(deg)`, `units()`, attributes `confirm` and `ask_text` (overridable callables), and the widgets named in the code. `RadialDialog`, `AddLevelsDialog`, `PickPointTool` and `PickDirectionTool` are added in Task 8; this task leaves the two buttons that need them (`new_radial_button`, `edit_radial_button`, `add_levels_button`) connected to methods that Task 8 completes, as marked.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_dialog.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_dialog.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'igz_steel._grid_dialog'`.

- [ ] **Step 3: Write `_grid_dialog.py` with the preview and the main dialog**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Grid Creator: a plan-view preview, the main dialog, the radial and
add-levels sub-dialogs, and two small pick tools."""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ._grid import (MAX_GRIDS, UNITS, GridError, Level, RadialGrid, RectGrid, add_levels,
                    cumulative, default_rect_grid, dump_block, fmt_length, LEVEL_PATTERNS,
                    new_grid_id, parse_angle_list, parse_block, parse_length,
                    parse_spacing_list, sorted_levels, unique_name)

ACCENT = QColor.fromRgbF(0.95, 0.45, 0.16)
BUBBLE_R = 11.0
ERROR_STYLE = "border: 1px solid #c83c3c;"


def _settings():
    return QSettings("igz_steel", "igz_steel")


def _settings_units():
    try:
        v = _settings().value("grid_units", "imperial")
        return v if v in UNITS else "imperial"
    except Exception:
        return "imperial"


# ---------------------------------------------------------------- preview

class GridPreview(QWidget):
    renamed = Signal(str, int, str)          # direction, index, new name

    def __init__(self, parent=None, units="imperial"):
        super().__init__(parent)
        self.setMinimumSize(320, 300)
        self._grid = None
        self._level = 0
        self._units = units
        self._scale = 20.0                   # pixels per metre
        self._center = (0.0, 0.0)            # world XY at the widget centre
        self._fit_pending = True
        self._bubbles_px = []                # (cx, cy, direction, index, name)
        self._drag = None
        self._editor = None
        self._error = None

    def set_units(self, units):
        self._units = units
        self.update()

    def set_grid(self, grid, level_index=None, fit=False):
        self._grid = grid
        if level_index is not None:
            self._level = int(level_index)
        if fit:
            self._fit_pending = True
        self.update()

    def set_error(self, text):
        self._error = text or None
        self.update()

    def fit(self):
        self._fit_pending = True
        self.update()

    # -- mapping
    def _to_px(self, x, y):
        return (self.width() / 2 + (x - self._center[0]) * self._scale,
                self.height() / 2 - (y - self._center[1]) * self._scale)

    def _from_px(self, px, py):
        return (self._center[0] + (px - self.width() / 2) / self._scale,
                self._center[1] - (py - self.height() / 2) / self._scale)

    def _do_fit(self, pts):
        if not pts:
            return
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self._center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        w, h = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
        margin = 70.0
        self._scale = max(1e-3, min((self.width() - 2 * margin) / w, (self.height() - 2 * margin) / h))
        self._fit_pending = False

    # -- painting
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.palette().base())
        self._bubbles_px = []
        g = self._grid
        text_color = self.palette().text().color()
        if g is None:
            p.setPen(text_color)
            p.drawText(self.rect(), Qt.AlignCenter, "No grid")
            p.end()
            return
        try:
            level = min(self._level, len(g.levels) - 1)
            lines = g.lines(level)
        except Exception as exc:
            p.setPen(QColor(200, 60, 60))
            p.drawText(self.rect(), Qt.AlignCenter, f"Cannot draw: {exc}")
            p.end()
            return
        pts = [q for ln in lines for q in ln.points]
        if self._fit_pending:
            self._do_fit(pts)
        p.setPen(QPen(ACCENT, 1.0, Qt.DashLine))
        for ln in lines:
            p.drawPolyline(QPolygonF([QPointF(*self._to_px(q[0], q[1])) for q in ln.points]))
        p.setBrush(QBrush(self.palette().base()))
        for ln in lines:
            for b in ln.bubbles:
                bx, by = self._to_px(b.at[0], b.at[1])
                cx, cy = bx + b.toward[0] * BUBBLE_R, by - b.toward[1] * BUBBLE_R
                p.setPen(QPen(ACCENT, 1.2))
                p.drawEllipse(QPointF(cx, cy), BUBBLE_R, BUBBLE_R)
                p.setPen(text_color)
                p.drawText(QRectF(cx - BUBBLE_R, cy - BUBBLE_R, 2 * BUBBLE_R, 2 * BUBBLE_R),
                           Qt.AlignCenter, b.name)
                self._bubbles_px.append((cx, cy, ln.direction, ln.index, b.name))
        p.setBrush(Qt.NoBrush)
        self._draw_dimensions(p, g, level, text_color)
        self._draw_origin(p, g, level)
        self._draw_north(p, text_color)
        if self._error:
            p.fillRect(QRectF(0, 0, self.width(), 22), QColor(200, 60, 60, 210))
            p.setPen(Qt.white)
            p.drawText(QRectF(6, 0, self.width() - 12, 22), Qt.AlignVCenter | Qt.AlignLeft, self._error)
        p.end()

    def _dim_string(self, p, pts, labels):
        px = [self._to_px(q[0], q[1]) for q in pts]
        for a, b in zip(px, px[1:]):
            p.drawLine(QPointF(*a), QPointF(*b))
        for x, y in px:
            p.drawEllipse(QPointF(x, y), 1.5, 1.5)
        for a, b, text in zip(px, px[1:], labels):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            p.drawText(QRectF(mx - 44, my - 16, 88, 14), Qt.AlignCenter, text)

    def _draw_dimensions(self, p, g, level, color):
        p.setPen(QPen(color, 0.8))
        font = QFont()
        font.setPointSize(8)
        p.setFont(font)
        off = 34.0 / self._scale
        z = g.levels[level].z
        if g.kind == "rect":
            xs, ys = cumulative(g.x_spacings), cumulative(g.y_spacings)
            e = g.extend
            row = [g.to_world(u, -e["y_neg"] - off, z) for u in xs]
            self._dim_string(p, row, [fmt_length(s, self._units) for s in g.x_spacings])
            col = [g.to_world(xs[-1] + e["x_pos"] + off, v, z) for v in ys]
            self._dim_string(p, col, [fmt_length(s, self._units) for s in g.y_spacings])
        else:
            rs, angs = g.radius_values(), g.angle_values()
            a0 = math.radians(angs[0])
            tx, ty = math.sin(a0) * off, -math.cos(a0) * off
            row = [g.to_world(r * math.cos(a0) + tx, r * math.sin(a0) + ty, z) for r in [0.0] + rs]
            self._dim_string(p, row, [fmt_length(s, self._units) for s in g.radii])
            r_lab = rs[-1] + g.extend["radial_out"] + off
            for a, b, step in zip(angs, angs[1:], g.steps_deg):
                m = math.radians((a + b) / 2)
                x, y = self._to_px(*g.to_world(r_lab * math.cos(m), r_lab * math.sin(m), z)[:2])
                p.drawText(QRectF(x - 30, y - 8, 60, 16), Qt.AlignCenter, f"{step:g}°")

    def _draw_origin(self, p, g, level):
        z = g.levels[level].z
        o = self._to_px(*g.to_world(0.0, 0.0, z)[:2])
        p.setPen(QPen(QColor(216, 90, 48), 1.2))
        p.drawEllipse(QPointF(*o), 3.0, 3.0)
        for du, dv, label in ((1.0, 0.0, "x"), (0.0, 1.0, "y")):
            dx, dy = g.direction(du, dv)
            end = (o[0] + dx * 18.0, o[1] - dy * 18.0)
            p.drawLine(QPointF(*o), QPointF(*end))
            p.drawText(QPointF(end[0] + dx * 6 - 3, end[1] - dy * 6 + 4), label)

    def _draw_north(self, p, color):
        x, y = self.width() - 22.0, 30.0
        p.setPen(QPen(color, 0.8))
        p.drawLine(QPointF(x, y + 14), QPointF(x, y - 10))
        p.drawLine(QPointF(x - 4, y - 4), QPointF(x, y - 10))
        p.drawLine(QPointF(x + 4, y - 4), QPointF(x, y - 10))
        p.drawText(QPointF(x - 4, y - 14), "N")

    # -- mouse
    def wheelEvent(self, ev):
        pos = ev.position()
        wx, wy = self._from_px(pos.x(), pos.y())
        self._scale *= 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        nx, ny = self._from_px(pos.x(), pos.y())
        self._center = (self._center[0] + (wx - nx), self._center[1] + (wy - ny))
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = (ev.position().x(), ev.position().y(), self._center)

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            x0, y0, c0 = self._drag
            dx = (ev.position().x() - x0) / self._scale
            dy = (ev.position().y() - y0) / self._scale
            self._center = (c0[0] - dx, c0[1] + dy)
            self.update()

    def mouseReleaseEvent(self, _ev):
        self._drag = None

    def mouseDoubleClickEvent(self, ev):
        hit = self.bubble_at(ev.position().x(), ev.position().y())
        if hit is not None:
            self.begin_rename(*hit)

    def bubble_at(self, px, py):
        for cx, cy, direction, index, name in self._bubbles_px:
            if math.hypot(cx - px, cy - py) <= BUBBLE_R:
                return (direction, index, name, cx, cy)
        return None

    def begin_rename(self, direction, index, name, cx, cy):
        if self._editor is not None:
            self._editor.deleteLater()
        ed = QLineEdit(name, self)
        ed.setGeometry(int(cx - 26), int(cy - 11), 52, 22)
        ed.selectAll()
        ed.show()
        ed.setFocus()
        ed.installEventFilter(self)
        self._editor = ed

        def done():
            if self._editor is not ed:
                return
            text = ed.text().strip()
            self._editor = None
            ed.hide()
            ed.deleteLater()
            if text and text != name:
                self.renamed.emit(direction, int(index), text)
        ed.editingFinished.connect(done)

    def eventFilter(self, obj, ev):
        if obj is self._editor and ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            self._editor = None
            obj.hide()
            obj.deleteLater()
            return True
        return super().eventFilter(obj, ev)


# ---------------------------------------------------------------- main dialog

def _line(text="", width=None):
    e = QLineEdit(text)
    if width:
        e.setMaximumWidth(width)
    return e


class GridDialog(QDialog):
    applied = Signal(object)                 # the document block (dict)
    pick_origin_requested = Signal()
    pick_direction_requested = Signal()

    def __init__(self, parent=None, units=None, persist=True):
        super().__init__(parent)
        self.setWindowTitle("Steel grids")
        self.setModal(False)
        self._persist = persist
        self._units = units or _settings_units()
        self._grids = []                     # the dialog's copy of every grid (working state)
        self._active = None
        self._loading = False
        self._errors = {}                    # widget -> message
        self.confirm = lambda title, text: QMessageBox.question(self, title, text) == QMessageBox.Yes
        self.ask_text = lambda title, label, default: QInputDialog.getText(self, title, label, text=default)
        self._radial_dialog = None
        self._build()
        self.load_block({})

    # -- construction -----------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Grid"))
        self.grid_combo = QComboBox()
        self.grid_combo.setMinimumWidth(150)
        self.grid_combo.currentIndexChanged.connect(self._on_grid_combo)
        top.addWidget(self.grid_combo)
        self.new_rect_button = QPushButton("New rect")
        self.new_radial_button = QPushButton("New radial…")
        self.dup_button = QPushButton("Duplicate")
        self.rename_button = QPushButton("Rename")
        self.delete_button = QPushButton("Delete")
        for b, fn in ((self.new_rect_button, self._new_rect), (self.new_radial_button, self._new_radial),
                      (self.dup_button, self._duplicate), (self.rename_button, self._rename),
                      (self.delete_button, self._delete)):
            b.clicked.connect(fn)
            top.addWidget(b)
        top.addStretch(1)
        self.visible_check = QCheckBox("Visible")
        self.visible_check.toggled.connect(self._on_visible)
        top.addWidget(self.visible_check)
        self.imperial_radio = QRadioButton("Imperial")
        self.metric_radio = QRadioButton("Metric")
        (self.imperial_radio if self._units == "imperial" else self.metric_radio).setChecked(True)
        self.imperial_radio.toggled.connect(self._on_units)
        top.addWidget(self.imperial_radio)
        top.addWidget(self.metric_radio)
        root.addLayout(top)

        body = QHBoxLayout()
        left = QVBoxLayout()
        body.addLayout(left, 0)

        # origin and rotation
        self.origin_box = QGroupBox("Origin and rotation")
        og = QGridLayout(self.origin_box)
        self.origin_x, self.origin_y, self.origin_z = _line("0", 90), _line("0", 90), _line("0", 90)
        for col, (lab, w) in enumerate((("X", self.origin_x), ("Y", self.origin_y), ("Z", self.origin_z))):
            og.addWidget(QLabel(lab), 0, 2 * col)
            og.addWidget(w, 0, 2 * col + 1)
            w.editingFinished.connect(self._on_fields)
        self.pick_origin_button = QPushButton("Pick origin")
        self.pick_origin_button.clicked.connect(self.pick_origin_requested)
        og.addWidget(self.pick_origin_button, 1, 0, 1, 2)
        og.addWidget(QLabel("Rotation °"), 1, 2)
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360.0, 360.0)
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.valueChanged.connect(self._on_fields)
        og.addWidget(self.rotation_spin, 1, 3)
        self.pick_dir_button = QPushButton("Pick dir.")
        self.pick_dir_button.clicked.connect(self.pick_direction_requested)
        og.addWidget(self.pick_dir_button, 1, 4, 1, 2)
        left.addWidget(self.origin_box)

        # rectangular lines
        self.rect_box = QGroupBox("Grid lines")
        rg = QGridLayout(self.rect_box)
        rg.addWidget(QLabel("X spacing"), 0, 0)
        self.x_spacing = _line("")
        self.x_spacing.textChanged.connect(self._on_fields)
        rg.addWidget(self.x_spacing, 0, 1)
        self.x_start = _line("A", 48)
        self.x_start.editingFinished.connect(lambda: self._on_start("x"))
        rg.addWidget(self.x_start, 0, 2)
        rg.addWidget(QLabel("Y spacing"), 1, 0)
        self.y_spacing = _line("")
        self.y_spacing.textChanged.connect(self._on_fields)
        rg.addWidget(self.y_spacing, 1, 1)
        self.y_start = _line("1", 48)
        self.y_start.editingFinished.connect(lambda: self._on_start("y"))
        rg.addWidget(self.y_start, 1, 2)
        hint = QLabel("spacing list, e.g. 25', 3@30', 25'")
        hint.setStyleSheet("color: gray;")
        rg.addWidget(hint, 2, 1)
        rg.addWidget(QLabel("start"), 2, 2)
        self.swap_button = QPushButton("Swap letters and numbers")
        self.swap_button.clicked.connect(self._swap)
        rg.addWidget(self.swap_button, 3, 0, 1, 3)
        rg.addWidget(QLabel("Extend"), 4, 0)
        self.extend_edit = _line("0")
        self.extend_edit.editingFinished.connect(self._on_fields)
        rg.addWidget(self.extend_edit, 4, 1)
        self.extend_all = QCheckBox("all sides")
        self.extend_all.setChecked(True)
        self.extend_all.toggled.connect(self._on_extend_mode)
        rg.addWidget(self.extend_all, 4, 2)
        self.extend_row = QWidget()
        eg = QHBoxLayout(self.extend_row)
        eg.setContentsMargins(0, 0, 0, 0)
        self.extend_edits = {}
        for key, lab in (("x_neg", "X−"), ("x_pos", "X+"), ("y_neg", "Y−"), ("y_pos", "Y+")):
            eg.addWidget(QLabel(lab))
            e = _line("0", 70)
            e.editingFinished.connect(self._on_fields)
            self.extend_edits[key] = e
            eg.addWidget(e)
        self.extend_row.setVisible(False)
        rg.addWidget(self.extend_row, 5, 0, 1, 3)
        rg.addWidget(QLabel("Bubbles"), 6, 0)
        self.bubbles_combo = QComboBox()
        self.bubbles_combo.addItems(["Top and left", "All ends"])
        self.bubbles_combo.currentIndexChanged.connect(self._on_fields)
        rg.addWidget(self.bubbles_combo, 6, 1, 1, 2)
        left.addWidget(self.rect_box)

        # radial summary
        self.radial_box = QGroupBox("Radial layout")
        rl = QVBoxLayout(self.radial_box)
        self.radial_summary = QLabel("")
        self.radial_summary.setWordWrap(True)
        rl.addWidget(self.radial_summary)
        self.edit_radial_button = QPushButton("Edit radial…")
        self.edit_radial_button.clicked.connect(self._edit_radial)
        rl.addWidget(self.edit_radial_button)
        self.radial_box.setVisible(False)
        left.addWidget(self.radial_box)

        # levels
        lv_box = QGroupBox("Levels")
        lvl = QVBoxLayout(lv_box)
        self.levels_table = QTableWidget(0, 2)
        self.levels_table.setHorizontalHeaderLabels(["Name", "Elevation"])
        self.levels_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.levels_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.levels_table.horizontalHeader().setStretchLastSection(True)
        self.levels_table.verticalHeader().setVisible(False)
        self.levels_table.itemChanged.connect(self._on_level_item)
        self.levels_table.itemSelectionChanged.connect(self._on_level_row)
        lvl.addWidget(self.levels_table)
        lb = QHBoxLayout()
        self.add_level_button = QPushButton("Add")
        self.add_levels_button = QPushButton("Add levels…")
        self.remove_level_button = QPushButton("Remove")
        for b, fn in ((self.add_level_button, self._add_level), (self.add_levels_button, self._add_levels),
                      (self.remove_level_button, self._remove_level)):
            b.clicked.connect(fn)
            lb.addWidget(b)
        lvl.addLayout(lb)
        left.addWidget(lv_box, 1)

        # preview
        right = QVBoxLayout()
        head = QHBoxLayout()
        self.preview_label = QLabel("Preview")
        head.addWidget(self.preview_label)
        head.addStretch(1)
        self.fit_button = QPushButton("Fit")
        head.addWidget(self.fit_button)
        hint2 = QLabel("double-click a bubble to rename")
        hint2.setStyleSheet("color: gray;")
        head.addWidget(hint2)
        right.addLayout(head)
        self.preview = GridPreview(self, self._units)
        self.preview.renamed.connect(self._on_renamed)
        self.fit_button.clicked.connect(self.preview.fit)
        right.addWidget(self.preview, 1)
        self.count_label = QLabel("")
        right.addWidget(self.count_label)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #c83c3c;")
        bottom.addWidget(self.status_label, 1)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        bottom.addWidget(self.apply_button)
        bottom.addWidget(self.close_button)
        root.addLayout(bottom)

    # -- document in/out -------------------------------------------------------
    def units(self):
        return self._units

    def load_block(self, raw, notice=None):
        grids, meta, _errors = parse_block(raw)
        if grids and meta["units"] in UNITS:
            self._set_units(meta["units"], store=False)
        if not grids:
            gid = "g1"
            grids = [default_rect_grid(gid, "Grid 1", self._units)]
            meta["active_grid"] = gid
        self._grids = grids
        self._active = meta["active_grid"] or grids[0].id
        self._errors = {}
        self._refresh_combo()
        self._fill_fields(fit=True)
        self._set_status(notice or "")

    def block(self):
        return dump_block(self._grids, self._active, self._units)

    def current_grid(self):
        for g in self._grids:
            if g.id == self._active:
                return g
        return self._grids[0] if self._grids else None

    def select_grid(self, gid):
        if any(g.id == gid for g in self._grids):
            self._active = gid
            self._refresh_combo()
            self._fill_fields(fit=True)

    def set_origin(self, xyz):
        g = self.current_grid()
        old_z = g.origin[2]
        g.origin = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
        self._follow_origin_z(g, old_z)
        self._fill_fields(fit=True)
        self.show()
        self.raise_()
        self.activateWindow()

    def set_rotation(self, deg):
        self.rotation_spin.setValue(float(deg))
        self.show()
        self.raise_()
        self.activateWindow()

    # -- helpers ---------------------------------------------------------------
    def _set_status(self, text):
        self.status_label.setText(text)

    def _set_units(self, units, store=True):
        self._units = units
        self._loading = True
        (self.imperial_radio if units == "imperial" else self.metric_radio).setChecked(True)
        self._loading = False
        self.preview.set_units(units)
        if store and self._persist:
            try:
                _settings().setValue("grid_units", units)
            except Exception:
                pass

    def _fmt(self, metres):
        return fmt_length(metres, self._units)

    def _mark(self, widget, message=None):
        if message:
            self._errors[widget] = message
            widget.setStyleSheet(ERROR_STYLE)
            widget.setToolTip(message)
        else:
            self._errors.pop(widget, None)
            widget.setStyleSheet("")
            widget.setToolTip("")

    def _finish_edit(self):
        """After any field change: status, Apply state, preview, counts."""
        g = self.current_grid()
        first = next(iter(self._errors.values()), "")
        self._set_status(first)
        self.apply_button.setEnabled(not self._errors)
        self.preview.set_error(first)
        self.preview.set_grid(g, g.active_level)
        try:
            n_lines = len(g.lines())
            n_nodes = len(g.intersections())
        except Exception:
            n_lines = n_nodes = 0
        self.count_label.setText(f"{n_lines} lines · {n_nodes} intersections · {len(g.levels)} levels")
        self.preview_label.setText(f"Preview · {g.level().name}")

    def _follow_origin_z(self, g, old_z):
        """A grid with a single level keeps that level at the origin's Z."""
        if len(g.levels) == 1 and abs(g.levels[0].z - old_z) < 1e-9:
            g.levels[0].z = g.origin[2]

    # -- filling widgets from the grid ----------------------------------------
    def _refresh_combo(self):
        self._loading = True
        self.grid_combo.clear()
        for g in self._grids:
            self.grid_combo.addItem(g.name, g.id)
        idx = next((i for i, g in enumerate(self._grids) if g.id == self._active), 0)
        self.grid_combo.setCurrentIndex(idx)
        self._loading = False

    def _fill_fields(self, fit=False):
        g = self.current_grid()
        if g is None:
            return
        self._loading = True
        for w in list(self._errors):
            self._mark(w, None)
        self.visible_check.setChecked(bool(g.visible))
        self.origin_x.setText(self._fmt(g.origin[0]))
        self.origin_y.setText(self._fmt(g.origin[1]))
        self.origin_z.setText(self._fmt(g.origin[2]))
        self.rotation_spin.setValue(float(g.rotation_deg))
        is_rect = g.kind == "rect"
        self.rect_box.setVisible(is_rect)
        self.radial_box.setVisible(not is_rect)
        if is_rect:
            self.x_spacing.setText(g.x_text)
            self.y_spacing.setText(g.y_text)
            self.x_start.setText(g.x_start)
            self.y_start.setText(g.y_start)
            vals = [g.extend[k] for k in ("x_neg", "x_pos", "y_neg", "y_pos")]
            same = all(abs(v - vals[0]) < 1e-9 for v in vals)
            self.extend_all.setChecked(same)
            self.extend_row.setVisible(not same)
            self.extend_edit.setText(self._fmt(vals[0]))
            for k, e in self.extend_edits.items():
                e.setText(self._fmt(g.extend[k]))
            self.bubbles_combo.setCurrentIndex(1 if g.bubbles == "all" else 0)
        else:
            self.radial_summary.setText(
                f"Radii: {g.radii_text or ', '.join(self._fmt(r) for r in g.radii)}\n"
                f"Angles: {g.angles_text or ', '.join(f'{a:g}' for a in g.steps_deg)} from {g.start_deg:g}°\n"
                f"Tangent: {self._fmt(g.tangent)} · bubbles: {g.bubbles}")
        self._fill_levels()
        self._loading = False
        if fit:
            self.preview.set_grid(g, g.active_level, fit=True)
        self._finish_edit()

    def _fill_levels(self):
        g = self.current_grid()
        was = self._loading
        self._loading = True
        self.levels_table.setRowCount(len(g.levels))
        for row, lv in enumerate(g.levels):
            self.levels_table.setItem(row, 0, QTableWidgetItem(lv.name))
            item = QTableWidgetItem(self._fmt(lv.z))
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.levels_table.setItem(row, 1, item)
        self.levels_table.selectRow(g.active_level)
        self._loading = was

    # -- reading widgets into the grid -----------------------------------------
    def _parse_into(self, widget, fn):
        try:
            value = fn(widget.text())
        except GridError as exc:
            self._mark(widget, str(exc))
            return None
        self._mark(widget, None)
        return value

    def _on_fields(self, *_args):
        if self._loading:
            return
        g = self.current_grid()
        if g is None:
            return
        length = lambda s: parse_length(s, self._units)
        ox, oy, oz = (self._parse_into(w, length) for w in (self.origin_x, self.origin_y, self.origin_z))
        if None not in (ox, oy, oz):
            old_z = g.origin[2]
            g.origin = (ox, oy, oz)
            self._follow_origin_z(g, old_z)
            if len(g.levels) == 1:
                self._fill_levels()
        g.rotation_deg = float(self.rotation_spin.value())
        if g.kind == "rect":
            xs = self._parse_into(self.x_spacing, lambda s: parse_spacing_list(s, self._units))
            if xs is not None:
                g.set_spacings("x", xs, self.x_spacing.text())
            ys = self._parse_into(self.y_spacing, lambda s: parse_spacing_list(s, self._units))
            if ys is not None:
                g.set_spacings("y", ys, self.y_spacing.text())
            if self.extend_all.isChecked():
                v = self._parse_into(self.extend_edit, length)
                if v is not None:
                    g.extend = {k: max(0.0, v) for k in ("x_neg", "x_pos", "y_neg", "y_pos")}
            else:
                for k, e in self.extend_edits.items():
                    v = self._parse_into(e, length)
                    if v is not None:
                        g.extend[k] = max(0.0, v)
            g.bubbles = "all" if self.bubbles_combo.currentIndex() == 1 else "top_left"
        self._finish_edit()

    def _on_start(self, direction):
        if self._loading:
            return
        g = self.current_grid()
        widget = self.x_start if direction == "x" else self.y_start
        try:
            g.set_start(direction, widget.text())
        except GridError as exc:
            self._mark(widget, str(exc))
        else:
            self._mark(widget, None)
        self._finish_edit()

    def _on_extend_mode(self, same):
        self.extend_row.setVisible(not same)
        self._on_fields()

    def _on_visible(self, on):
        if self._loading:
            return
        self.current_grid().visible = bool(on)
        self._finish_edit()

    def _on_units(self, *_args):
        if self._loading:
            return
        self._set_units("imperial" if self.imperial_radio.isChecked() else "metric")
        self._fill_fields()

    def _on_renamed(self, direction, index, name):
        g = self.current_grid()
        try:
            g.rename_line(direction, index, name)
        except (IndexError, GridError):
            return
        self._finish_edit()

    def _swap(self):
        g = self.current_grid()
        if g.kind != "rect":
            return
        from ._grid import name_sequence
        try:
            touched = (g.x_names != name_sequence(g.x_start, len(g.x_names))
                       or g.y_names != name_sequence(g.y_start, len(g.y_names)))
        except GridError:
            touched = True
        if touched and not self.confirm("Swap names", "Renamed lines will be regenerated. Continue?"):
            return
        xs, ys = g.x_start, g.y_start
        try:
            g.set_start("x", ys)
            g.set_start("y", xs)
        except GridError as exc:
            self._set_status(str(exc))
            return
        self._fill_fields()

    # -- levels ------------------------------------------------------------------
    def _on_level_row(self):
        if self._loading:
            return
        rows = self.levels_table.selectionModel().selectedRows()
        if rows:
            self.current_grid().active_level = rows[0].row()
            self._finish_edit()

    def _on_level_item(self, item):
        if self._loading:
            return
        g = self.current_grid()
        row, col = item.row(), item.column()
        if row >= len(g.levels):
            return
        if col == 0:
            g.levels[row].name = item.text().strip() or g.levels[row].name
            self._set_status("")
        else:
            try:
                z = parse_length(item.text(), self._units)
            except GridError as exc:
                self._set_status(str(exc))
                self._fill_levels()
                return
            if any(abs(z - lv.z) < 1e-3 for i, lv in enumerate(g.levels) if i != row):
                self._set_status("A level already exists at that elevation")
                self._fill_levels()
                return
            g.levels[row].z = z
            self._set_status("")
        current = g.levels[row]
        g.set_levels(g.levels)
        g.active_level = g.levels.index(current)
        self._fill_levels()
        self._finish_edit()

    def _add_level(self):
        g = self.current_grid()
        if len(g.levels) >= 2:
            step = g.levels[-1].z - g.levels[-2].z
        else:
            step = 12 * 0.3048 if self._units == "imperial" else 3.6
        try:
            levels = add_levels(g.levels, 1, step, "up", "EL {el}", self._units)
        except GridError as exc:
            self._set_status(str(exc))
            return
        g.set_levels(levels)
        g.active_level = len(levels) - 1
        self._fill_levels()
        self._finish_edit()

    def _add_levels(self):
        """Completed in Task 8 (AddLevelsDialog)."""
        g = self.current_grid()
        dlg = AddLevelsDialog(self, g.levels, self._units)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            levels = dlg.result_levels()
        except GridError as exc:
            self._set_status(str(exc))
            return
        g.set_levels(levels)
        self._fill_levels()
        self._finish_edit()

    def _remove_level(self):
        g = self.current_grid()
        if len(g.levels) <= 1:
            self._set_status("A grid keeps at least one level")
            return
        rows = self.levels_table.selectionModel().selectedRows()
        row = rows[0].row() if rows else g.active_level
        levels = [lv for i, lv in enumerate(g.levels) if i != row]
        g.set_levels(levels)
        g.active_level = min(row, len(levels) - 1)
        self._fill_levels()
        self._finish_edit()

    # -- grid list ---------------------------------------------------------------
    def _on_grid_combo(self, index):
        if self._loading or index < 0:
            return
        self._active = self.grid_combo.itemData(index)
        self._fill_fields(fit=True)

    def _add_grid(self, grid):
        if len(self._grids) >= MAX_GRIDS:
            self._set_status(f"At most {MAX_GRIDS} grids")
            return
        self._grids.append(grid)
        self._active = grid.id
        self._refresh_combo()
        self._fill_fields(fit=True)

    def _new_rect(self):
        name, ok = self.ask_text("New grid", "Name:", unique_name(self._grids, "Grid"))
        if not ok or not name.strip():
            return
        self._add_grid(default_rect_grid(new_grid_id(self._grids),
                                         unique_name(self._grids, name.strip()), self._units))

    def _new_radial(self):
        """Completed in Task 8 (RadialDialog)."""
        self._open_radial(None)

    def _edit_radial(self):
        """Completed in Task 8 (RadialDialog)."""
        g = self.current_grid()
        if g is not None and g.kind == "radial":
            self._open_radial(g)

    def _duplicate(self):
        g = self.current_grid()
        twin = copy.deepcopy(g)
        twin.id = new_grid_id(self._grids)
        twin.name = unique_name(self._grids, g.name)
        self._add_grid(twin)

    def _rename(self):
        g = self.current_grid()
        name, ok = self.ask_text("Rename grid", "Name:", g.name)
        if not ok or not name.strip():
            return
        g.name = unique_name([x for x in self._grids if x is not g], name.strip())
        self._refresh_combo()

    def _delete(self):
        g = self.current_grid()
        if len(self._grids) <= 1:
            self._set_status("The last grid cannot be deleted here; clear its spacings or hide it instead")
            return
        if not self.confirm("Delete grid", f"Delete grid {g.name} with {len(g.levels)} level(s)?"):
            return
        self._grids = [x for x in self._grids if x is not g]
        self._active = self._grids[0].id
        self._refresh_combo()
        self._fill_fields(fit=True)

    def _apply(self):
        if self._errors:
            return
        self.applied.emit(self.block())
```

Then append, at the end of the file, the two placeholders Task 8 replaces with real classes (so this task's tests run):

```python
class AddLevelsDialog(QDialog):            # replaced in Task 8
    def __init__(self, parent, levels, units):
        super().__init__(parent)
        self._levels, self._units = list(levels), units

    def result_levels(self):
        return self._levels


def _open_radial_stub(self, grid):            # replaced in Task 8
    self._set_status("Radial grids arrive in Task 8")


GridDialog._open_radial = _open_radial_stub
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_dialog.py -q`
Expected: all pass. In `test_pick_signals_and_setters` the imperial text for 1.0 m is `3'-3 3/8"` (39.37 in rounds to 39 6/16). If `test_levels_table_edits_and_buttons` fails on the "same spacing" assertion, check `_add_level` reads the two top levels after sorting.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid_dialog.py tests/test_grid_dialog.py
git commit -m "feat(grid): Grid Creator dialog with live plan preview, levels table and grid list"
```

---

### Task 8: `RadialDialog`, `AddLevelsDialog` and the pick tools

**Files:**
- Modify: `igz_steel/_grid_dialog.py` (replace the two placeholders at the end of the file; add the classes below)
- Test: `tests/test_grid_subdialogs.py`

**Interfaces:**
- Consumes: `GridPreview`, `GridDialog` (Task 7), `_grid.RadialGrid`, `parse_angle_list`, `add_levels`, `LEVEL_PATTERNS`, `_tools._flash`, `_tools.xyz`, `tools.base.Tool`.
- Produces: `RadialDialog(parent, units, grid=None, grid_id="g1", name="Radial")` with widgets named below, `result_grid() -> RadialGrid` (raises `GridError`), signal `pick_center_requested()`, method `set_center(xyz)`; `AddLevelsDialog(parent, levels, units)` with `count_spin`, `spacing_edit`, `direction_combo` ("Up from the top" / "Down from the bottom"), `pattern_combo`, `result_levels() -> list[Level]`; `PickPointTool(on_point, previous=None, prompt=...)`; `PickDirectionTool(on_angle, previous=None)`; `GridDialog._open_radial(grid)` wired so New radial… creates and Edit radial… edits, and `GridDialog.pick_center_requested` re-emitted as `pick_origin_requested` while the radial dialog is open (the session routes the picked point to `set_origin`, which forwards to the radial dialog when it is open).

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_subdialogs.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest
from PySide6.QtGui import QImage, QVector3D
from PySide6.QtWidgets import QDialog

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_subdialogs.py -q`
Expected: FAIL with `ImportError: cannot import name 'RadialDialog'`.

- [ ] **Step 3: Replace the placeholders at the end of `_grid_dialog.py`**

Delete the `AddLevelsDialog` placeholder, `_open_radial_stub` and the `GridDialog._open_radial = …` line. Add these imports at the top of the file:

```python
from tools.base import Tool

from ._tools import _flash, xyz
```

Append:

```python
# ---------------------------------------------------------------- sub-dialogs

class AddLevelsDialog(QDialog):
    """Count, spacing, direction and name pattern for a run of new levels."""

    def __init__(self, parent, levels, units):
        super().__init__(parent)
        self.setWindowTitle("Add levels")
        self._levels, self._units = list(levels), units
        form = QFormLayout(self)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setValue(5)
        form.addRow("Count", self.count_spin)
        self.spacing_edit = QLineEdit("12'" if units == "imperial" else "3.6")
        form.addRow("Spacing", self.spacing_edit)
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Up from the top", "Down from the bottom"])
        form.addRow("Direction", self.direction_combo)
        self.pattern_combo = QComboBox()
        self.pattern_combo.setEditable(True)
        self.pattern_combo.addItems(list(LEVEL_PATTERNS))
        form.addRow("Name pattern", self.pattern_combo)
        hint = QLabel("{el} is the elevation, {n} the running number")
        hint.setStyleSheet("color: gray;")
        form.addRow(hint)
        buttons = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        form.addRow(buttons)

    def result_levels(self):
        spacing = parse_length(self.spacing_edit.text(), self._units)
        direction = "up" if self.direction_combo.currentIndex() == 0 else "down"
        return add_levels(self._levels, self.count_spin.value(), spacing, direction,
                          self.pattern_combo.currentText() or "EL {el}", self._units)


class RadialDialog(QDialog):
    """Center, radii, angles, tangent legs and extents of a radial grid, with
    its own preview. Shown with ``show()``; the main dialog disables itself
    while this one is open so a pick in the viewport can still run."""
    pick_center_requested = Signal()

    def __init__(self, parent, units, grid=None, grid_id="g1", name="Radial"):
        super().__init__(parent)
        self.setWindowTitle("Radial layout")
        self.setModal(False)
        self._units = units
        self._errors = {}
        if grid is None:
            grid = RadialGrid(id=grid_id, name=name,
                              radii_text="20', 2@15'" if units == "imperial" else "6, 2@4.5",
                              radii=parse_spacing_list("20', 2@15'" if units == "imperial" else "6, 2@4.5", units),
                              angles_text="6@30", steps_deg=[30.0] * 6,
                              extend={"radial_in": 5 * 0.3048, "radial_out": 5 * 0.3048, "arc": 0.0},
                              levels=[Level("EL " + fmt_length(0.0, units), 0.0)])
        self._grid = copy.deepcopy(grid)
        self._build()
        self._fill()

    def _build(self):
        root = QHBoxLayout(self)
        form = QFormLayout()
        row = QHBoxLayout()
        self.center_x, self.center_y, self.center_z = QLineEdit(), QLineEdit(), QLineEdit()
        for lab, w in (("X", self.center_x), ("Y", self.center_y), ("Z", self.center_z)):
            row.addWidget(QLabel(lab))
            row.addWidget(w)
            w.editingFinished.connect(self._on_fields)
        self.pick_center_button = QPushButton("Pick")
        self.pick_center_button.clicked.connect(self.pick_center_requested)
        row.addWidget(self.pick_center_button)
        form.addRow("Center", row)
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360.0, 360.0)
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.valueChanged.connect(self._on_fields)
        form.addRow("Rotation °", self.rotation_spin)
        r = QHBoxLayout()
        self.radii_edit = QLineEdit()
        self.radii_start = QLineEdit()
        self.radii_start.setMaximumWidth(48)
        r.addWidget(self.radii_edit)
        r.addWidget(self.radii_start)
        form.addRow("Radii (first, then spacings)", r)
        a = QHBoxLayout()
        self.angles_edit = QLineEdit()
        self.angles_start = QLineEdit()
        self.angles_start.setMaximumWidth(48)
        a.addWidget(self.angles_edit)
        a.addWidget(self.angles_start)
        form.addRow("Angle steps °", a)
        self.start_angle_spin = QDoubleSpinBox()
        self.start_angle_spin.setRange(-360.0, 360.0)
        self.start_angle_spin.setDecimals(1)
        self.start_angle_spin.valueChanged.connect(self._on_fields)
        form.addRow("Start angle °", self.start_angle_spin)
        self.tangent_edit = QLineEdit()
        form.addRow("Tangent length", self.tangent_edit)
        self.ext_in_edit, self.ext_out_edit, self.ext_arc_edit = QLineEdit(), QLineEdit(), QLineEdit()
        form.addRow("Extend radial lines inward", self.ext_in_edit)
        form.addRow("Extend radial lines outward", self.ext_out_edit)
        form.addRow("Extend arcs / legs", self.ext_arc_edit)
        self.bubbles_combo = QComboBox()
        self.bubbles_combo.addItems(["Outer ends and start", "All ends"])
        self.bubbles_combo.currentIndexChanged.connect(self._on_fields)
        form.addRow("Bubbles", self.bubbles_combo)
        for w in (self.radii_edit, self.radii_start, self.angles_edit, self.angles_start,
                  self.tangent_edit, self.ext_in_edit, self.ext_out_edit, self.ext_arc_edit):
            w.editingFinished.connect(self._on_fields)
        for w in (self.radii_edit, self.angles_edit):
            w.textChanged.connect(self._on_fields)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #c83c3c;")
        self.status_label.setWordWrap(True)
        form.addRow(self.status_label)
        buttons = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        form.addRow(buttons)
        root.addLayout(form, 0)
        self.preview = GridPreview(self, self._units)
        self.preview.renamed.connect(self._on_renamed)
        root.addWidget(self.preview, 1)

    def _fmt(self, metres):
        return fmt_length(metres, self._units)

    def _fill(self):
        g = self._grid
        self._loading = True
        self.center_x.setText(self._fmt(g.origin[0]))
        self.center_y.setText(self._fmt(g.origin[1]))
        self.center_z.setText(self._fmt(g.origin[2]))
        self.rotation_spin.setValue(g.rotation_deg)
        self.radii_edit.setText(g.radii_text or ", ".join(self._fmt(r) for r in g.radii))
        self.radii_start.setText(g.radii_start)
        self.angles_edit.setText(g.angles_text or ", ".join(f"{s:g}" for s in g.steps_deg))
        self.angles_start.setText(g.angles_start)
        self.start_angle_spin.setValue(g.start_deg)
        self.tangent_edit.setText(self._fmt(g.tangent))
        self.ext_in_edit.setText(self._fmt(g.extend["radial_in"]))
        self.ext_out_edit.setText(self._fmt(g.extend["radial_out"]))
        self.ext_arc_edit.setText(self._fmt(g.extend["arc"]))
        self.bubbles_combo.setCurrentIndex(1 if g.bubbles == "all" else 0)
        self._loading = False
        self.preview.set_grid(g, g.active_level, fit=True)
        self._finish()

    def _mark(self, widget, message):
        if message:
            self._errors[widget] = message
            widget.setStyleSheet(ERROR_STYLE)
            widget.setToolTip(message)
        else:
            self._errors.pop(widget, None)
            widget.setStyleSheet("")
            widget.setToolTip("")

    def _parse_into(self, widget, fn):
        try:
            value = fn(widget.text())
        except GridError as exc:
            self._mark(widget, str(exc))
            return None
        self._mark(widget, None)
        return value

    def _on_fields(self, *_args):
        if getattr(self, "_loading", False):
            return
        g = self._grid
        length = lambda s: parse_length(s, self._units)
        c = [self._parse_into(w, length) for w in (self.center_x, self.center_y, self.center_z)]
        if None not in c:
            old_z = g.origin[2]
            g.origin = tuple(c)
            if len(g.levels) == 1 and abs(g.levels[0].z - old_z) < 1e-9:
                g.levels[0].z = g.origin[2]
        g.rotation_deg = float(self.rotation_spin.value())
        g.start_deg = float(self.start_angle_spin.value())
        radii = self._parse_into(self.radii_edit, lambda s: parse_spacing_list(s, self._units))
        if radii is not None:
            g.set_radii(radii, self.radii_edit.text())
        steps = self._parse_into(self.angles_edit, parse_angle_list)
        if steps is not None:
            g.set_angles(steps, self.angles_edit.text())
        for direction, w in (("radii", self.radii_start), ("angles", self.angles_start)):
            try:
                if w.text().strip() != (g.radii_start if direction == "radii" else g.angles_start):
                    g.set_start(direction, w.text())
                self._mark(w, None)
            except GridError as exc:
                self._mark(w, str(exc))
        t = self._parse_into(self.tangent_edit, length)
        if t is not None:
            g.tangent = max(0.0, t)
        for key, w in (("radial_in", self.ext_in_edit), ("radial_out", self.ext_out_edit),
                       ("arc", self.ext_arc_edit)):
            v = self._parse_into(w, length)
            if v is not None:
                g.extend[key] = max(0.0, v)
        g.bubbles = "all" if self.bubbles_combo.currentIndex() == 1 else "top_left"
        self._finish()

    def _finish(self):
        first = next(iter(self._errors.values()), "")
        self.status_label.setText(first)
        self.ok_button.setEnabled(not self._errors)
        self.preview.set_error(first)
        self.preview.set_grid(self._grid, self._grid.active_level)

    def _on_renamed(self, direction, index, name):
        try:
            self._grid.rename_line(direction, index, name)
        except (IndexError, GridError):
            return
        self._finish()

    def set_center(self, xyz):
        g = self._grid
        old_z = g.origin[2]
        g.origin = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
        if len(g.levels) == 1 and abs(g.levels[0].z - old_z) < 1e-9:
            g.levels[0].z = g.origin[2]
        self._fill()
        self.show()
        self.raise_()
        self.activateWindow()

    def result_grid(self):
        if self._errors:
            raise GridError(next(iter(self._errors.values())))
        return copy.deepcopy(self._grid)


# ---------------------------------------------------------------- pick tools

class PickPointTool(Tool):
    """One click hands a world point to the dialog and restores the previous tool."""
    name = "Pick a grid point"
    description = "Click a point for the grid dialog."
    uses_snap = True

    def __init__(self, on_point, previous=None, prompt="Click the grid origin  •  Esc cancels"):
        self.on_point, self.previous, self.prompt = on_point, previous, prompt

    def on_activate(self, viewport):
        _flash(viewport, self.prompt, 3500)

    def on_deactivate(self, viewport):
        pass

    def on_click(self, ctx):
        p = xyz(ctx.world)
        self._finish(ctx.viewport)
        self.on_point(p)

    def on_cancel(self, viewport):
        self._finish(viewport)

    def status_clause(self):
        return self.prompt

    def _finish(self, viewport):
        try:
            viewport.set_active_tool(self.previous)
        except Exception:
            pass


class PickDirectionTool(Tool):
    """Two clicks give the bearing of the second point from the first, in the
    XY plane, degrees counter-clockwise from world +X."""
    name = "Pick a grid direction"
    description = "Click two points for the grid rotation."
    uses_snap = True

    def __init__(self, on_angle, previous=None):
        self.on_angle, self.previous = on_angle, previous
        self.start_point = None
        self.hover = None

    def on_activate(self, viewport):
        self.start_point = None
        _flash(viewport, "Click the first point of the grid X direction  •  Esc cancels", 3500)

    def on_deactivate(self, viewport):
        self.start_point = None
        self.hover = None

    def on_hover(self, ctx):
        self.hover = xyz(ctx.world)
        ctx.viewport.update()

    def on_click(self, ctx):
        p = xyz(ctx.world)
        if self.start_point is None:
            from PySide6.QtGui import QVector3D
            self.start_point = QVector3D(*p)
            _flash(ctx.viewport, "Click the second point  •  Esc cancels", 3500)
            return
        s = xyz(self.start_point)
        dx, dy = p[0] - s[0], p[1] - s[1]
        if math.hypot(dx, dy) < 1e-6:
            return
        self._finish(ctx.viewport)
        self.on_angle(math.degrees(math.atan2(dy, dx)))

    def on_cancel(self, viewport):
        self.start_point = None
        self._finish(viewport)

    def status_clause(self):
        if self.start_point is None:
            return "Grid direction: click  first point  •  Esc  cancel"
        return "Grid direction: click  second point  •  Esc  cancel"

    def rubber_band_lines(self):
        if self.start_point is None or self.hover is None:
            return []
        from PySide6.QtGui import QVector3D
        return [(QVector3D(self.start_point), QVector3D(*self.hover))]

    def _finish(self, viewport):
        try:
            viewport.set_active_tool(self.previous)
        except Exception:
            pass
```

Then add these methods to `GridDialog` (replacing the Task 7 stubs `_new_radial` and `_edit_radial`, which already call `_open_radial`):

```python
    def _open_radial(self, grid):
        if self._radial_dialog is not None:
            self._radial_dialog.close()
            self._radial_dialog.deleteLater()
            self._radial_dialog = None
        if grid is None:
            name, ok = self.ask_text("New radial grid", "Name:", unique_name(self._grids, "Radial"))
            if not ok or not name.strip():
                return
            dlg = RadialDialog(self, self._units, grid_id=new_grid_id(self._grids),
                               name=unique_name(self._grids, name.strip()))
            editing = None
        else:
            dlg = RadialDialog(self, self._units, grid=grid)
            editing = grid.id
        dlg.pick_center_requested.connect(self.pick_origin_requested)
        dlg.finished.connect(lambda result, d=dlg, e=editing: self._radial_done(d, e, result))
        self._radial_dialog = dlg
        self.setEnabled(False)
        dlg.show()

    def _radial_done(self, dlg, editing, result):
        self.setEnabled(True)
        if self._radial_dialog is dlg:
            self._radial_dialog = None
        if result != QDialog.Accepted:
            dlg.deleteLater()
            return
        try:
            grid = dlg.result_grid()
        except GridError as exc:
            self._set_status(str(exc))
            dlg.deleteLater()
            return
        dlg.deleteLater()
        if editing is None:
            self._add_grid(grid)
        else:
            self._grids = [grid if g.id == editing else g for g in self._grids]
            self._active = grid.id
            self._refresh_combo()
            self._fill_fields(fit=True)
```

and change `set_origin` so a pick made while the radial dialog is open goes there:

```python
    def set_origin(self, xyz):
        if self._radial_dialog is not None:
            self._radial_dialog.set_center(xyz)
            return
        g = self.current_grid()
        old_z = g.origin[2]
        g.origin = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
        self._follow_origin_z(g, old_z)
        self._fill_fields(fit=True)
        self.show()
        self.raise_()
        self.activateWindow()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_grid_subdialogs.py tests/test_grid_dialog.py -q`
Expected: all pass. If `test_main_dialog_creates_and_edits_radial_grids` fails on `rd.isVisible()`, the radial dialog has no parent window shown; `show()` on a top-level dialog still reports visible offscreen, so check that `_open_radial` calls `dlg.show()` before returning.

- [ ] **Step 5: Commit**

```bash
git add igz_steel/_grid_dialog.py tests/test_grid_subdialogs.py
git commit -m "feat(grid): radial layout dialog, add-levels dialog and viewport pick tools"
```

---

### Task 9: Wiring, icons, README and version 1.1.0

**Files:**
- Modify: `igz_steel/_core.py` (session fields, dialogs, actions, `setup`)
- Modify: `igz_steel/__init__.py` (`__version__ = "1.1.0"`)
- Create: `igz_steel/icons/tb_grid.svg`, `igz_steel/icons/tb_grid_light.svg`
- Modify: `igz_steel/README.md` (version line, Grids section)
- Modify: `tests/test_package.py`, `tests/test_package_zip.py`
- Test: `tests/test_grid_wiring.py`

**Interfaces:**
- Consumes: `GridStore` (Task 6), `GridDialog`, `PickPointTool`, `PickDirectionTool` (Tasks 7–8).
- Produces: `SteelSession.grids` (a `GridStore`), `SteelSession.open_grids(grid_id=None)`, `on_grids_applied(block)`, `pick_origin()`, `pick_direction()`, `delete_selected_grid()`; toolbar action "Steel grids…", menu entry "Grids…", context-menu entries.

- [ ] **Step 1: Write the failing tests**

`tests/test_grid_wiring.py`:

```python
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
```

Also edit `tests/test_package_zip.py` to add, after the `tb_place.svg` assertion:

```python
    assert "igz_steel/icons/tb_grid.svg" in names
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_grid_wiring.py tests/test_package_zip.py -q`
Expected: FAIL with `AttributeError: 'SteelSession' object has no attribute 'open_grids'` (and the icon and version assertions fail).

- [ ] **Step 3: Wire the session in `_core.py`**

Add to the imports:

```python
from ._grid_host import GridStore
```

In `SteelSession.__init__`, after `self._edit_target = None`:

```python
        self.grid_dialog_ = None
        self.grids = GridStore(app)
        self.grids.confirm = self._confirm_grid_delete
        self.grids.on_edit_request = lambda gid: QTimer.singleShot(0, lambda: self.open_grids(gid))
```

Add these methods to `SteelSession` (after `open_bom`):

```python
    # -- grids ----------------------------------------------------------------
    def _confirm_grid_delete(self, grid):
        return QMessageBox.question(
            self.app.window, "Steel grids",
            f"Delete grid {grid.name} with {len(grid.levels)} level(s)?") == QMessageBox.Yes

    def grid_dialog(self):
        if self.grid_dialog_ is None:
            from ._grid_dialog import GridDialog
            d = GridDialog(self.app.window)
            d.load_block(self.grids.raw_block())
            d.applied.connect(self.on_grids_applied)
            d.pick_origin_requested.connect(self.pick_origin)
            d.pick_direction_requested.connect(self.pick_direction)
            self.grid_dialog_ = d
        return self.grid_dialog_

    def open_grids(self, grid_id=None):
        d = self.grid_dialog()
        if grid_id:
            d.select_grid(grid_id)
        self._show(d)
        return d

    def on_grids_applied(self, block):
        if not self._guard():
            return
        try:
            self.grids.save_block(block)
        except Exception as exc:
            log.exception("igz_steel: saving grids failed")
            QMessageBox.critical(self.app.window, "Steel grids", f"Could not save the grids: {exc}")
            return
        self.app.viewport.update()

    def delete_selected_grid(self):
        gid = self.grids.selected_id
        if gid:
            self.grids.delete(gid)
            self.app.viewport.update()

    def _previous_tool(self):
        vp = self.app.viewport
        for attr in ("active_tool", "tool", "_tool"):
            t = getattr(vp, attr, None)
            if t is not None and not callable(t):
                return t
        return None

    def pick_origin(self):
        from ._grid_dialog import PickPointTool
        d = self.grid_dialog()

        def on_point(p):
            d.set_origin(p)
            self.app.viewport.update()
        self.app.viewport.set_active_tool(PickPointTool(on_point, previous=self._previous_tool()))

    def pick_direction(self):
        from ._grid_dialog import PickDirectionTool
        d = self.grid_dialog()

        def on_angle(deg):
            d.set_rotation(deg)
            self.app.viewport.update()
        self.app.viewport.set_active_tool(PickDirectionTool(on_angle, previous=self._previous_tool()))
```

Extend `on_document_changed`:

```python
    def on_document_changed(self):
        self._refresh_bom()
        if self.dialog is not None and self.dialog.isVisible():
            self.dialog.set_layers(self.layer_names())
        self.grids.reload()
        if self.grid_dialog_ is not None:
            self.grid_dialog_.load_block(self.grids.raw_block(), notice="Reloaded from the document")
        try:
            self.app.viewport.update()
        except Exception:
            pass
```

Extend `context_menu` so the grid entries come first and do not depend on a steel selection:

```python
    def context_menu(self, menu, selection):
        menu.addSeparator()
        grids = menu.addAction("Steel grids…")
        grids.triggered.connect(_deferred(self.open_grids))
        if self.grids.selected_id:
            edit = menu.addAction("Edit grid…")
            edit.triggered.connect(_deferred(lambda: self.open_grids(self.grids.selected_id)))
            delete = menu.addAction("Delete grid")
            delete.triggered.connect(_deferred(self.delete_selected_grid))
        steel = []
        for item in selection:
            g = getattr(item, "owner", None) or item
            if is_steel_group(g) and g not in steel:
                steel.append(g)
        if len(steel) != 1:
            return
        edit = menu.addAction("Edit steel member…")
        edit.triggered.connect(_deferred(self.open_edit))
        stretch = menu.addAction("Stretch steel member")
        stretch.triggered.connect(_deferred(self.open_stretch))
```

In `_install_toolbar`, add a fifth entry:

```python
               ("tb_grid", "Steel grids…", session.open_grids)]
```

In `setup`, add `("Grids…", session.open_grids)` after the Bill of Materials entry in the menu loop, and register the grid hooks right after `_SESSIONS[id(app)] = session`:

```python
    session.grids.register()
```

- [ ] **Step 4: Icons, version, README**

`igz_steel/icons/tb_grid.svg` (light strokes for a dark palette):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="#e6e6e6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 7v14M16 7v14M4 11h17M4 17h17"/><circle cx="9" cy="4" r="1.6"/><circle cx="16" cy="4" r="1.6"/></svg>
```

`igz_steel/icons/tb_grid_light.svg`: the same with `stroke="#222222"`.

`igz_steel/__init__.py`: `__version__ = "1.1.0"`.

`igz_steel/README.md`: change the Version line to `1.1.0` and add before "## Notes and limits":

````markdown
## Grids

**Steel grids…** (toolbar, Extensions ▸ Steel ▸ Grids…, or the right-click
menu) opens the Grid Creator. A document can hold several named grids;
each is drawn over the viewport with dashed lines and lettered or numbered
bubbles, and the cursor snaps to every intersection on every level with
the grid point on the tip (`B-3 · EL 112'-0"`). Grids are reference
geometry only: they are saved in the document, never appear in the
Browser or the Bill of Materials, and each change is one undo step.

Spacings are lists with repeats; the dialog works in feet-inches by
default and in metres with the Metric switch:

| You type | Meaning |
|---|---|
| `25', 3@30', 25'` | five bays: 25 ft, three of 30 ft, 25 ft |
| `25'-6"`, `25' 6"`, `306"`, `6 1/2"` | feet-inches, inches, fractions |
| `25` | 25 ft (imperial) or 25 m (metric) |
| `7.62`, `7620mm`, `762cm` | metres, millimetres, centimetres |
| `6@30`, `30, 30, 45` | angle steps in degrees (radial grids) |

Lines spaced along X are lettered (A, B, C … skipping I and O, then AA,
BB …) and lines along Y are numbered; Swap exchanges the two, and
double-clicking a bubble in the preview renames one line (`B.5`). Extend
sets how far lines run past the outer grids. Levels copy the grid to
other elevations: add them one by one or with Add levels… (count, spacing,
up or down, name pattern). Only the active level is drawn in full; the
others show corner ticks, and all of them snap. Radial grids take a
center, radii, angle steps, a tangent length (straight legs continuing
each arc past the end radial lines, snappable as `A-T1` / `A-T2`) and
extents. Clicking a bubble with Select selects the grid; Delete removes it.
````

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (the earlier 90 plus the new grid tests). If `tests/test_host.py` or others construct a `SteelSession` with an app lacking `document_data`, `GridStore.reload` already swallows that and starts empty.

- [ ] **Step 6: Commit**

```bash
git add igz_steel/_core.py igz_steel/__init__.py igz_steel/icons/tb_grid.svg igz_steel/icons/tb_grid_light.svg igz_steel/README.md tests/test_grid_wiring.py tests/test_package_zip.py
git commit -m "feat(grid): toolbar, menu and context entries, session wiring, icons, README, version 1.1.0"
```

---

### Task 10: In-app verification and release checklist

**Files:**
- Modify: `catalog/igz_steel.toml` (version, download, sha256 after the release exists)
- Modify: `docs/SUBMISSION.md` (note the 1.1.0 release)

The release itself (GitHub release, catalog PR) publishes outward and needs the user's go-ahead; the steps are listed so they can be run when the user confirms.

- [ ] **Step 1: Install into the running IngeTrazo and verify with the user**

```bash
bash devtools/install.sh
```

Then restart IngeTrazo and walk the spec's verification list with the user: create a rectangular grid from the mockup values (`25', 3@30', 25'` by `4@20'`, origin Z `100'`), place a W12X26 column at B-1 by snapping, add three levels with Add levels… (12' up), place a beam at the second level between B-3 and C-3 by snapping, rotate the grid 30° and confirm lines and snap points turn together, build a radial grid with a tangent and snap to `A-T1`, select a grid by its bubble and delete it, undo back to an empty document, save, reopen and confirm the grids return. Record anything that fails as a bug to fix before release.

- [ ] **Step 2: Build the package**

```bash
.venv/Scripts/python devtools/package.py && certutil -hashfile dist/igz_steel.zip SHA256
```

Expected: `wrote dist/igz_steel.zip (… KB)` and a SHA-256 line.

- [ ] **Step 3: Release (after the user confirms)**

```bash
git tag v1.1.0 && git push origin main --tags && gh release create v1.1.0 dist/igz_steel.zip --title "igz_steel 1.1.0" --notes "Layout grids: rectangular and radial grids with levels, viewport bubbles and snapping."
```

- [ ] **Step 4: Catalog entry**

Edit `catalog/igz_steel.toml`: `version = "1.1.0"`, `download = ".../releases/download/v1.1.0/igz_steel.zip"`, `sha256 = "<from Step 2>"`, and append to each `[summary]` and `[description]` language a sentence on grids (en: "Layout grids with lettered and numbered bubbles, levels and radial layouts; members snap to grid points."). Commit, then update the fork branch `add-igz-steel` and the catalog PR (ingelibre/ingetrazo-extensions#81) with the same three fields, as recorded in the project memory.

```bash
git add catalog/igz_steel.toml docs/SUBMISSION.md && git commit -m "docs: catalog entry for 1.1.0"
```
