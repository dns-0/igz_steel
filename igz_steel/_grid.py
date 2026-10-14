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
_QUOTES = {"”": '"', "″": '"', "’": "'", "′": "'"}


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
