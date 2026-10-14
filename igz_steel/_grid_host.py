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
from PySide6.QtWidgets import QApplication

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


def _bubble_points(bubbles):
    """Anchors then anchor + toward, so one projection covers both."""
    return ([b.at for b in bubbles]
            + [(b.at[0] + b.toward[0], b.at[1] + b.toward[1], b.at[2]) for b in bubbles])


def _double_click_s():
    try:
        if QApplication.instance() is not None:
            return QApplication.doubleClickInterval() / 1000.0
    except Exception:
        pass
    return DOUBLE_CLICK_S


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
        self._snap_failed = False
        self._pick_failed = False
        self._last_pick = (None, 0.0)
        self.reload()

    # -- data -----------------------------------------------------------------
    def reload(self):
        try:
            raw = self.app.document_data({})
        except Exception:
            raw = {}
        self._overlay_failed = False        # a corrected document may draw again
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

    def bubble_centres(self, viewport, grid, lines=None, projected=None):
        """``[(cx, cy, Bubble)]`` for the grid's active level, pushed out from
        the line end by the bubble radius in screen space. ``_paint`` passes the
        ``lines`` it already has and ``projected`` (the anchors' and the
        toward-points' pixels, in bubble order) from its single projection."""
        if lines is None:
            lines = grid.lines()
        bubbles = [b for ln in lines for b in ln.bubbles]
        if projected is None:
            both = project(self.app, viewport, _bubble_points(bubbles))
            at, out = both[:len(bubbles)], both[len(bubbles):]
        else:
            at, out = projected
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
            bubbles = [b for ln in lines for b in ln.bubbles]
            line_pts = [p for ln in lines for p in ln.points]
            marks, labels = [], []
            for li, level in enumerate(g.levels):
                if li == g.active_level:
                    continue
                labels.append((len(marks), level.name))
                marks += g.corner_marks(li)
            # one projection for everything this grid draws, sliced back by offsets
            n_line, n_bub = len(line_pts), len(bubbles)
            px = project(self.app, viewport,
                         line_pts + _bubble_points(bubbles)
                         + [g.to_world(0.0, 0.0, g.level().z)] + marks)
            line_px = px[:n_line]
            at_px = px[n_line:n_line + n_bub]
            out_px = px[n_line + n_bub:n_line + 2 * n_bub]
            o = px[n_line + 2 * n_bub]
            mpx = px[n_line + 2 * n_bub + 1:]
            selected = g.id == self.selected_id
            painter.setPen(QPen(_qcolor(0.9), 2.0 if selected else 1.2,
                                Qt.SolidLine if selected else Qt.DashLine))
            k = 0
            for ln in lines:
                seg = line_px[k:k + len(ln.points)]
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
            for cx, cy, b in self.bubble_centres(viewport, g, lines, (at_px, out_px)):
                painter.setPen(QPen(_qcolor(1.0), 1.2))
                painter.drawEllipse(QPointF(cx, cy), BUBBLE_PX, BUBBLE_PX)
                painter.drawText(QRectF(cx - BUBBLE_PX, cy - BUBBLE_PX, 2 * BUBBLE_PX, 2 * BUBBLE_PX),
                                 Qt.AlignCenter, b.name)
            painter.setBrush(Qt.NoBrush)
            if o is not None:
                painter.setPen(QPen(_qcolor(1.0)))
                painter.drawText(QPointF(o[0] + 8, o[1] + 14), f"{g.name} · {g.level().name}")
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

    def _log_once(self, flag, what):
        """First failure is logged in full, repeats at debug level (mouse-move rate)."""
        if getattr(self, flag):
            log.debug("igz_steel grids: %s", what, exc_info=True)
        else:
            setattr(self, flag, True)
            log.exception("igz_steel grids: %s", what)

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
                if d > threshold:
                    continue
                active = g.levels[g.active_level] is level
                # in plan view every level projects to one pixel: prefer the active level
                if best is None or d < best[0] - 1e-6 or (d <= best[0] + 1e-6 and active and not best[4]):
                    best = (d, g, level, node, active)
            if best is None:
                return None
            from core.snap import SnapResult
            _d, g, level, node, _active = best
            return SnapResult(QVector3D(*node.at), "reference", COLOR,
                              label=self.tip(g, level, node))
        except Exception:
            self._log_once("_snap_failed", "snap provider error")
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
            self._log_once("_pick_failed", "pick error")
        return None

    def on_select(self, item):
        now = time.monotonic()
        last_id, last_t = self._last_pick
        fired = False
        if item is not None and item == last_id and now - last_t < _double_click_s()                 and callable(self.on_edit_request):
            fired = True
            try:
                self.on_edit_request(item)
            except Exception:
                log.exception("igz_steel grids: edit request failed")
        self._last_pick = (None, 0.0) if fired else (item, now)   # a triple click fires once
        self.selected_id = item
        vp = getattr(self.app, "viewport", None)
        g = self.find(item) if item else None
        if g is not None:
            self._flash(f"Grid {g.name}: {len(g.levels)} level(s). Delete removes it.")
        if vp is not None:
            try:
                vp.update()
            except Exception:
                pass

    def _flash(self, text):
        flash = getattr(getattr(self.app, "viewport", None), "flash_status", None)
        if callable(flash):
            try:
                flash(text, 3000)
            except Exception:
                pass

    def delete(self, item):
        g = self.find(item)
        if g is None:
            return
        try:
            if callable(self.confirm) and not self.confirm(g):
                return
        except Exception:
            log.exception("igz_steel grids: delete confirmation failed")
            return
        grids = [x for x in self.grids if x.id != item]
        active = self.meta["active_grid"]
        if active == item:
            active = grids[0].id if grids else None
        try:
            self.save_block(dump_block(grids, active, self.meta["units"]))
        except Exception:
            log.exception("igz_steel grids: could not delete the grid")
            self._flash("Could not delete the grid")
            return
        self.selected_id = None

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
