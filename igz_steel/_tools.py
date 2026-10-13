# SPDX-License-Identifier: GPL-3.0-or-later
"""The viewport tools: place a member, stretch a member.

Both expose ``start_point`` (a QVector3D) once a first point exists, because
the host's inference engine reads that attribute to build the work plane and
the axis magnet. Typed values arrive through ``on_value`` already in metres.
"""
from __future__ import annotations

from PySide6.QtGui import QVector3D

from tools.base import Tool

from ._geometry import (MAX_LENGTH, MIN_LENGTH, add, direction_and_length, dot,
                        preview_segments, scale, sub)
from ._host import insertion_uv, member_endpoints, profile_for
from ._units import fmt_len


def xyz(p):
    if isinstance(p, QVector3D):
        return (float(p.x()), float(p.y()), float(p.z()))
    return (float(p[0]), float(p[1]), float(p[2]))


def _flash(viewport, text, msec=3000):
    fn = getattr(viewport, "flash_status", None)
    if callable(fn):
        try:
            fn(text, msec)
        except Exception:
            pass


def _leave(viewport):
    try:
        viewport.set_active_tool(None)
    except Exception:
        pass


def _as_vectors(segments):
    return [(QVector3D(*a), QVector3D(*b)) for a, b in segments]


def _valid_length(length):
    return MIN_LENGTH <= length <= MAX_LENGTH


class PlaceMemberTool(Tool):
    name = "Place steel member"
    description = "Place an AISC steel member: click the start, then click the end or type a length."
    uses_snap = True
    vcb_label = "Length"
    magnetic_axis_deg = 3.0
    screen_axis_px = 9.0

    def __init__(self, shape, params, on_member, on_profile):
        self.shape = shape
        self.params = dict(params)
        self.profile = profile_for(shape, self.params)
        self.uv = insertion_uv(self.profile, self.params.get("insertion", "centroid"))
        self.roll = float(self.params.get("roll", 0.0))
        self.on_member = on_member
        self.on_profile = on_profile
        self.start_point = None
        self.hover = None

    # -- protocol -----------------------------------------------------------
    def on_activate(self, viewport):
        self.start_point = None
        _flash(viewport, f"{self.shape.label}: click to place the profile  •  Esc exits", 3500)

    def on_deactivate(self, viewport):
        self.start_point = None
        self.hover = None

    def on_hover(self, ctx):
        self.hover = xyz(ctx.world)
        ctx.viewport.update()

    def on_click(self, ctx):
        p = xyz(ctx.world)
        if self.start_point is None:
            self.start_point = QVector3D(*p)
            self.hover = p
            _flash(ctx.viewport, f"{self.shape.label}: click the end point or type a length"
                                 "  •  Esc places the profile only", 3500)
            ctx.viewport.update()
            return
        d, length = direction_and_length(xyz(self.start_point), p)
        if d is None or not _valid_length(length):
            return
        self._commit(ctx.viewport, d, length)

    def on_value(self, viewport, value):
        if self.start_point is None:
            return False
        start = xyz(self.start_point)
        if isinstance(value, tuple):
            if len(value) != 3:
                return False
            try:
                d, length = direction_and_length((0.0, 0.0, 0.0), xyz(value))
            except (TypeError, ValueError):
                return False
        else:
            try:
                v = float(value)
            except (TypeError, ValueError):
                return False
            if v == 0.0 or self.hover is None:
                return False
            d, along = direction_and_length(start, self.hover)
            if d is None or along < MIN_LENGTH:
                return False
            length = abs(v)
            if v < 0:
                d = scale(d, -1.0)
        if d is None or not _valid_length(length):
            return False
        return self._commit(viewport, d, length)

    def on_cancel(self, viewport):
        if self.start_point is not None:
            start = xyz(self.start_point)
            self.start_point = None
            if self.on_profile(start):
                _flash(viewport, f"{self.shape.label}: profile placed. Stretch it later.", 3000)
            viewport.update()
            return
        _leave(viewport)

    def status_clause(self):
        if self.start_point is None:
            return f"{self.shape.label}: click  start  •  Esc  exit"
        if self.hover is not None:
            d, length = direction_and_length(xyz(self.start_point), self.hover)
            if d is not None and length >= MIN_LENGTH:
                return (f"{self.shape.label}: {fmt_len(length)}  •  click  end  "
                        f"•  type a length  •  Esc  profile only")
        return f"{self.shape.label}: click  end  •  type a length  •  Esc  profile only"

    def rubber_band_lines(self):
        if self.start_point is None:
            if self.hover is None:
                return []
            return _as_vectors(preview_segments(self.profile, self.uv, self.hover,
                                                (1.0, 0.0, 0.0), 0.0, self.roll))
        start = xyz(self.start_point)
        d, length = (None, 0.0)
        if self.hover is not None:
            d, length = direction_and_length(start, self.hover)
        if d is None or length < MIN_LENGTH:
            return _as_vectors(preview_segments(self.profile, self.uv, start,
                                                (1.0, 0.0, 0.0), 0.0, self.roll))
        return _as_vectors(preview_segments(self.profile, self.uv, start, d, length, self.roll))

    # -- internals ----------------------------------------------------------
    def _commit(self, viewport, direction, length):
        start = xyz(self.start_point)
        ok = bool(self.on_member(start, direction, length))
        if ok:
            self.start_point = None
            _flash(viewport, f"{self.shape.label}: member created ({fmt_len(length)}). "
                             "Click to place another, Esc to exit.", 3000)
        viewport.update()
        return ok


def _dist2(a, b):
    d = sub(a, b)
    return dot(d, d)


def _grip_segments(p, size):
    x, y, z = p
    return [((x - size, y, z), (x + size, y, z)),
            ((x, y - size, z), (x, y + size, z)),
            ((x, y, z - size), (x, y, z + size))]


class StretchMemberTool(Tool):
    name = "Stretch steel member"
    description = "Stretch a steel member: click the end to move, then click or type the new length."
    uses_snap = True
    vcb_label = "Length"
    magnetic_axis_deg = 3.0
    screen_axis_px = 9.0

    def __init__(self, group, shape, params, on_commit):
        self.group = group
        self.shape = shape
        self.params = dict(params)
        self.profile = profile_for(shape, self.params)
        self.uv = insertion_uv(self.profile, self.params.get("insertion", "centroid"))
        self.roll = float(self.params.get("roll", 0.0))
        self.on_commit = on_commit
        self.start_point = None          # the fixed end, once a grip is chosen
        self.free = None                 # the end being moved
        self.hover = None
        self.refresh()

    def refresh(self):
        """Re-read the member's ends (after a rebuild, or on construction)."""
        self.p0, self.p1 = member_endpoints(self.group)
        self.axis, self.length = direction_and_length(self.p0, self.p1)
        if self.length < MIN_LENGTH:
            self.axis = None

    # -- protocol -----------------------------------------------------------
    def on_activate(self, viewport):
        self.start_point = None
        _flash(viewport, f"{self.shape.label}: click the end to stretch  •  Esc exits", 3500)

    def on_deactivate(self, viewport):
        self.start_point = None
        self.hover = None

    def on_hover(self, ctx):
        self.hover = xyz(ctx.world)
        ctx.viewport.update()

    def on_click(self, ctx):
        p = xyz(ctx.world)
        if self.start_point is None:
            if self.axis is None:
                fixed, free = self.p0, self.p0
            elif _dist2(p, self.p0) < _dist2(p, self.p1):
                fixed, free = self.p1, self.p0
            else:
                fixed, free = self.p0, self.p1
            self.start_point = QVector3D(*fixed)
            self.free = free
            self.hover = p
            _flash(ctx.viewport, f"{self.shape.label}: click the new end or type a length", 3500)
            ctx.viewport.update()
            return
        d, length = direction_and_length(xyz(self.start_point), self._target(p))
        if d is None or not _valid_length(length):
            return
        self._commit(ctx.viewport, d, length)

    def on_value(self, viewport, value):
        if self.start_point is None or isinstance(value, tuple):
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if v == 0.0:
            return False
        d = self._axis_from_fixed()
        if d is None:
            if self.hover is None:
                return False
            d, along = direction_and_length(xyz(self.start_point), self.hover)
            if d is None or along < MIN_LENGTH:
                return False
        length = abs(v)
        if v < 0:
            d = scale(d, -1.0)
        if not _valid_length(length):
            return False
        return self._commit(viewport, d, length)

    def on_cancel(self, viewport):
        if self.start_point is not None:
            self.start_point = None
            viewport.update()
            return
        _leave(viewport)

    def status_clause(self):
        if self.start_point is None:
            return f"{self.shape.label}: click  an end to stretch  •  Esc  exit"
        if self.hover is not None:
            d, length = direction_and_length(xyz(self.start_point), self._target(self.hover))
            if d is not None and length >= MIN_LENGTH:
                return f"{self.shape.label}: {fmt_len(length)}  •  click  end  •  type a length"
        return f"{self.shape.label}: click  end  •  type a length  •  Esc  cancel"

    def rubber_band_lines(self):
        size = max(0.05, 0.02 * self.length)
        segs = _grip_segments(self.p0, size)
        if self.length >= MIN_LENGTH:
            segs += _grip_segments(self.p1, size)
        if self.start_point is not None and self.hover is not None:
            fixed = xyz(self.start_point)
            d, length = direction_and_length(fixed, self._target(self.hover))
            if d is not None and length >= MIN_LENGTH:
                segs += preview_segments(self.profile, self.uv, fixed, d, length, self.roll)
        return _as_vectors(segs)

    # -- internals ----------------------------------------------------------
    def _axis_from_fixed(self):
        if self.axis is None or self.start_point is None:
            return None
        d, _ = direction_and_length(xyz(self.start_point), self.free)
        return d or self.axis

    def _target(self, p):
        a = self._axis_from_fixed()
        if a is None:
            return p
        fixed = xyz(self.start_point)
        return add(fixed, scale(a, dot(sub(p, fixed), a)))

    def _commit(self, viewport, direction, length):
        fixed = xyz(self.start_point)
        ok = bool(self.on_commit(fixed, direction, length))
        if ok:
            self.start_point = None
            self.refresh()
            _flash(viewport, f"{self.shape.label}: now {fmt_len(length)}", 3000)
        viewport.update()
        return ok
