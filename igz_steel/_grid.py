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
    if count > MAX_LINES:
        raise GridError(f"At most {MAX_LINES} lines in one direction")
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
