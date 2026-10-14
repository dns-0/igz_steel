# SPDX-License-Identifier: GPL-3.0-or-later
"""The Grid Creator: a plan-view preview, the main dialog, the radial and
add-levels sub-dialogs, and two small pick tools."""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF, QVector3D
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from tools.base import Tool

from ._grid import (LEVEL_PATTERNS, MAX_GRIDS, UNITS, GridError, Level, RadialGrid, add_levels,
                    cumulative, default_rect_grid, dump_block, fmt_length, new_grid_id,
                    parse_angle_list, parse_block, parse_length, parse_spacing_list,
                    unique_name)
from ._tools import _flash, xyz

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


def retext_spacings(text, spacings, units):
    """The spacing text to show after a unit switch: ``text`` itself when it
    still means the same lengths in ``units``, else the lengths spelled out."""
    try:
        parsed = parse_spacing_list(text, units)
        if len(parsed) == len(spacings) and all(abs(a - b) < 1e-9 for a, b in zip(parsed, spacings)):
            return text
    except GridError:
        pass
    return ", ".join(fmt_length(s, units) for s in spacings)


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
        self.rotation_spin.setDecimals(3)
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

    def set_rotation(self, deg):
        g = self.current_grid()
        g.rotation_deg = float(deg)
        self._loading = True
        self.rotation_spin.setValue(g.rotation_deg)
        self._loading = False
        self._finish_edit()
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

    def _read_length(self, widget, current):
        """A length field's value; text that still shows ``current`` (to display
        precision) leaves the stored, unrounded value alone."""
        if widget.text() == self._fmt(current):
            self._mark(widget, None)
            return current
        return self._parse_into(widget, lambda s: parse_length(s, self._units))

    def _on_fields(self, *_args):
        if self._loading:
            return
        g = self.current_grid()
        if g is None:
            return
        length = lambda s: parse_length(s, self._units)
        ox, oy, oz = (self._read_length(w, cur) for w, cur in
                      zip((self.origin_x, self.origin_y, self.origin_z), g.origin))
        if None not in (ox, oy, oz):
            old_z = g.origin[2]
            g.origin = (ox, oy, oz)
            self._follow_origin_z(g, old_z)
            if len(g.levels) == 1:
                self._fill_levels()
        if abs(self.rotation_spin.value() - round(g.rotation_deg, self.rotation_spin.decimals())) > 1e-9:
            g.rotation_deg = float(self.rotation_spin.value())
        if g.kind == "rect":
            xs = self._parse_into(self.x_spacing, lambda s: parse_spacing_list(s, self._units))
            if xs is not None:
                g.set_spacings("x", xs, self.x_spacing.text())
            ys = self._parse_into(self.y_spacing, lambda s: parse_spacing_list(s, self._units))
            if ys is not None:
                g.set_spacings("y", ys, self.y_spacing.text())
            if self.extend_all.isChecked():
                v = self._read_length(self.extend_edit, g.extend["x_neg"])
                if v is not None:
                    g.extend = {k: max(0.0, v) for k in ("x_neg", "x_pos", "y_neg", "y_pos")}
            else:
                for k, e in self.extend_edits.items():
                    v = self._read_length(e, g.extend[k])
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
        g = self.current_grid()
        was = self._loading
        self._loading = True
        if g is not None and g.kind == "rect":
            hidden = list(self.extend_edits.values()) if same else [self.extend_edit]
            for w in hidden:
                self._mark(w, None)
            if same:
                self.extend_edit.setText(self._fmt(g.extend["x_neg"]))
            else:
                for k, e in self.extend_edits.items():
                    e.setText(self._fmt(g.extend[k]))
        self._loading = was
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
        for g in self._grids:
            if g.kind == "rect":
                g.x_text = retext_spacings(g.x_text, g.x_spacings, self._units)
                g.y_text = retext_spacings(g.y_text, g.y_spacings, self._units)
            else:
                g.radii_text = retext_spacings(g.radii_text, g.radii, self._units)
        self._fill_fields()

    def _on_renamed(self, direction, index, name):
        g = self.current_grid()
        if not name.strip():
            self._set_status("Enter a name for the line")
            return
        try:
            g.rename_line(direction, index, name)
        except (IndexError, GridError) as exc:
            self._set_status(str(exc) or "That line no longer exists")
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
        """Prepend or append a run of new levels chosen in AddLevelsDialog."""
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
        self._open_radial(None)

    def _edit_radial(self):
        g = self.current_grid()
        if g is not None and g.kind == "radial":
            self._open_radial(g)

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
        dlg.setEnabled(True)                 # a child window inherits the disabled state
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
        self._loading = False
        if grid is None:
            radii_text = "20', 2@15'" if units == "imperial" else "6, 2@4.5"
            grid = RadialGrid(id=grid_id, name=name,
                              radii_text=radii_text,
                              radii=parse_spacing_list(radii_text, units),
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
        self.rotation_spin.setDecimals(3)
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
        self.start_angle_spin.setDecimals(3)
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

    def _read_length(self, widget, current):
        """A length field's value; text that still shows ``current`` (to display
        precision) leaves the stored, unrounded value alone."""
        if widget.text() == self._fmt(current):
            self._mark(widget, None)
            return current
        return self._parse_into(widget, lambda s: parse_length(s, self._units))

    @staticmethod
    def _spin_changed(spin, current):
        """True when ``spin`` shows something other than ``current`` rounded to the
        spin's precision, so an untouched spin never rewrites the stored value."""
        return abs(spin.value() - round(current, spin.decimals())) > 1e-9

    def _on_fields(self, *_args):
        if self._loading:
            return
        g = self._grid
        c = [self._read_length(w, cur) for w, cur in
             zip((self.center_x, self.center_y, self.center_z), g.origin)]
        if None not in c:
            old_z = g.origin[2]
            g.origin = tuple(c)
            if len(g.levels) == 1 and abs(g.levels[0].z - old_z) < 1e-9:
                g.levels[0].z = g.origin[2]
        if self._spin_changed(self.rotation_spin, g.rotation_deg):
            g.rotation_deg = float(self.rotation_spin.value())
        if self._spin_changed(self.start_angle_spin, g.start_deg):
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
        t = self._read_length(self.tangent_edit, g.tangent)
        if t is not None:
            g.tangent = max(0.0, t)
        for key, w in (("radial_in", self.ext_in_edit), ("radial_out", self.ext_out_edit),
                       ("arc", self.ext_arc_edit)):
            v = self._read_length(w, g.extend[key])
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
        return [(QVector3D(self.start_point), QVector3D(*self.hover))]

    def _finish(self, viewport):
        try:
            viewport.set_active_tool(self.previous)
        except Exception:
            pass
