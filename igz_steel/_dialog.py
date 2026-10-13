# SPDX-License-Identifier: GPL-3.0-or-later
"""The member dialog (pick a shape, an insertion point, roll, layer) and the
section preview widget."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QRadioButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ._profiles import (DEFAULT_ROUND_SEGMENTS, MAX_ROUND_SEGMENTS, MIN_ROUND_SEGMENTS,
                        build_profile)
from ._units import fmt_dim

READOUT_KEYS = {
    "W": ["d", "bf", "tw", "tf", "kdes"], "M": ["d", "bf", "tw", "tf", "kdes"],
    "S": ["d", "bf", "tw", "tf", "kdes"], "HP": ["d", "bf", "tw", "tf", "kdes"],
    "C": ["d", "bf", "tw", "tf", "kdes"], "MC": ["d", "bf", "tw", "tf", "kdes"],
    "WT": ["d", "bf", "tw", "tf", "kdes"], "MT": ["d", "bf", "tw", "tf", "kdes"],
    "ST": ["d", "bf", "tw", "tf", "kdes"],
    "L": ["b", "d", "t", "kdes"], "2L": ["b", "d", "t", "gap"],
    "HSS": ["Ht", "B", "OD", "tdes"], "PIPE": ["OD", "tdes"],
}
ROLL_PRESETS = (0.0, 90.0, 180.0, 270.0)


def _length_spinbox(parent):
    try:
        from views.length_field import LengthSpinBox
        return LengthSpinBox(parent, minimum=0.0, maximum=1000.0)
    except Exception:
        box = QDoubleSpinBox(parent)
        box.setRange(0.0, 1000.0)
        box.setDecimals(4)
        box.setSuffix(" m")
        return box


class SectionPreview(QWidget):
    point_picked = Signal(str)
    PICK_PX = 10.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile = None
        self._selected = "centroid"
        self.setMinimumSize(220, 220)

    def set_profile(self, profile):
        self._profile = profile
        if profile is not None and all(p.id != self._selected for p in profile.points):
            self._selected = "centroid"
        self.update()

    def selected(self):
        return self._selected

    def set_selected(self, insertion_id):
        self._selected = insertion_id
        self.update()

    def pick(self, insertion_id):
        self.set_selected(insertion_id)
        self.point_picked.emit(insertion_id)

    def _mapping(self):
        if self._profile is None:
            return None
        umin, vmin, umax, vmax = self._profile.bbox
        w, h = max(umax - umin, 1e-9), max(vmax - vmin, 1e-9)
        margin = 24.0
        sx = (self.width() - 2 * margin) / w
        sy = (self.height() - 2 * margin) / h
        s = min(sx, sy)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        mu, mv = (umin + umax) / 2.0, (vmin + vmax) / 2.0
        return s, cx, cy, mu, mv

    def _to_px(self, uv, mapping):
        s, cx, cy, mu, mv = mapping
        return (cx + (uv[0] - mu) * s, cy - (uv[1] - mv) * s)

    def point_pixel(self, insertion_id):
        mapping = self._mapping()
        return self._to_px(self._profile.point(insertion_id).uv, mapping)

    def pick_at(self, px, py):
        mapping = self._mapping()
        if mapping is None:
            return
        best, best_d = None, self.PICK_PX
        for p in self._profile.points:
            x, y = self._to_px(p.uv, mapping)
            d = math.hypot(x - px, y - py)
            if d <= best_d:
                best, best_d = p.id, d
        if best is not None:
            self.pick(best)

    def mousePressEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.localPos()
        self.pick_at(pos.x(), pos.y())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        mapping = self._mapping()
        if mapping is None:
            painter.end()
            return
        steel = QColor(120, 130, 145)
        painter.setPen(QPen(steel.darker(140), 1.2))
        painter.setBrush(QBrush(steel.lighter(150)))
        for reg in self._profile.regions:
            poly = QPolygonF([QPointF(*self._to_px(p, mapping)) for p in reg.outer.points])
            painter.drawPolygon(poly)
            painter.setBrush(self.palette().base())
            for h in reg.holes:
                painter.drawPolygon(QPolygonF([QPointF(*self._to_px(p, mapping)) for p in h.points]))
            painter.setBrush(QBrush(steel.lighter(150)))
        for p in self._profile.points:
            x, y = self._to_px(p.uv, mapping)
            if p.id == self._selected:
                painter.setPen(QPen(QColor(200, 40, 40), 2))
                painter.setBrush(QBrush(QColor(255, 120, 120)))
                painter.drawEllipse(QPointF(x, y), 6, 6)
            else:
                painter.setPen(QPen(QColor(30, 90, 200), 1))
                painter.setBrush(QBrush(QColor(120, 170, 255)))
                painter.drawEllipse(QPointF(x, y), 3.5, 3.5)
        painter.end()


class MemberDialog(QDialog):
    place_requested = Signal(dict)
    update_requested = Signal(dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.mode = "place"
        self.setWindowTitle("Steel member")
        self.setModal(False)
        self._build()
        self._refill()

    # -- construction -------------------------------------------------------
    def _build(self):
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 1)
        pick = QGroupBox("Shape")
        pv = QVBoxLayout(pick)
        row = QHBoxLayout()
        self.family_combo = QComboBox()
        self.family_combo.addItems(self.db.families())
        self.imperial_radio = QRadioButton("Imperial")
        self.metric_radio = QRadioButton("Metric")
        self.imperial_radio.setChecked(True)
        row.addWidget(QLabel("Family"))
        row.addWidget(self.family_combo, 1)
        row.addWidget(self.imperial_radio)
        row.addWidget(self.metric_radio)
        pv.addLayout(row)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter, e.g. 12X26")
        pv.addWidget(self.filter_edit)
        self.shape_list = QListWidget()
        pv.addWidget(self.shape_list, 1)
        self.readout = QLabel("")
        self.readout.setTextFormat(Qt.PlainText)
        self.readout.setWordWrap(True)
        pv.addWidget(self.readout)
        left.addWidget(pick, 1)

        right = QVBoxLayout()
        root.addLayout(right, 1)
        self.preview = SectionPreview()
        right.addWidget(self.preview, 1)
        self.insertion_label = QLabel("Insertion: Centroid")
        right.addWidget(self.insertion_label)
        form = QFormLayout()
        roll_row = QHBoxLayout()
        self.roll_spin = QDoubleSpinBox()
        self.roll_spin.setRange(-360.0, 360.0)
        self.roll_spin.setSuffix("°")
        roll_row.addWidget(self.roll_spin, 1)
        self.roll_buttons = []
        for preset in ROLL_PRESETS:
            b = QPushButton(f"{preset:g}")
            b.clicked.connect(lambda _c=False, v=preset: self.roll_spin.setValue(v))
            roll_row.addWidget(b)
            self.roll_buttons.append(b)
        form.addRow("Roll", roll_row)
        self.fillets_check = QCheckBox("Rounded fillets")
        self.fillets_check.setChecked(True)
        form.addRow("", self.fillets_check)
        self.segments_spin = QSpinBox()
        self.segments_spin.setRange(MIN_ROUND_SEGMENTS, MAX_ROUND_SEGMENTS)
        self.segments_spin.setValue(DEFAULT_ROUND_SEGMENTS)
        self.segments_spin.setEnabled(False)
        form.addRow("Round segments", self.segments_spin)
        self.layer_combo = QComboBox()
        self.layer_combo.setEditable(True)
        form.addRow("Layer", self.layer_combo)
        self.length_spin = _length_spinbox(self)
        self.length_label = QLabel("Length")
        form.addRow(self.length_label, self.length_spin)
        right.addLayout(form)
        buttons = QHBoxLayout()
        self.place_button = QPushButton("Place")
        self.update_button = QPushButton("Update")
        close = QPushButton("Close")
        buttons.addStretch(1)
        buttons.addWidget(self.place_button)
        buttons.addWidget(self.update_button)
        buttons.addWidget(close)
        right.addLayout(buttons)

        self.family_combo.currentTextChanged.connect(lambda _t: self._refill())
        self.imperial_radio.toggled.connect(lambda _c: self._refill())
        self.filter_edit.textChanged.connect(lambda _t: self._refill())
        self.shape_list.currentRowChanged.connect(lambda _r: self._on_shape_changed())
        self.fillets_check.toggled.connect(lambda _c: self._on_shape_changed())
        self.segments_spin.valueChanged.connect(lambda _v: self._on_shape_changed())
        self.preview.point_picked.connect(self._on_point)
        self.place_button.clicked.connect(self._on_place)
        self.update_button.clicked.connect(self._on_update)
        close.clicked.connect(self.close)
        self.set_mode("place")

    # -- state --------------------------------------------------------------
    def unit_system(self):
        return "metric" if self.metric_radio.isChecked() else "imperial"

    def set_layers(self, names):
        current = self.layer_combo.currentText()
        self.layer_combo.clear()
        self.layer_combo.addItems(list(names))
        if current:
            self.layer_combo.setEditText(current)

    def set_mode(self, mode):
        self.mode = mode
        editing = mode == "edit"
        self.update_button.setVisible(editing)
        self.place_button.setVisible(not editing)
        self.length_spin.setVisible(editing)
        self.length_label.setVisible(editing)
        self.setWindowTitle("Edit steel member" if editing else "Steel member")

    def current_shape(self):
        item = self.shape_list.currentItem()
        if item is None:
            return None
        return self.db.find(item.data(Qt.UserRole))

    def params(self):
        shape = self.current_shape()
        return {"label": shape.label if shape else None,
                "unit_system": self.unit_system(),
                "insertion": self.preview.selected(),
                "roll": float(self.roll_spin.value()),
                "fillets": bool(self.fillets_check.isChecked()),
                "segments": int(self.segments_spin.value()),
                "layer": self.layer_combo.currentText().strip(),
                "length": float(self.length_spin.value())}

    def load(self, params, layer, length_m):
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return
        if params.get("unit_system") == "metric":
            self.metric_radio.setChecked(True)
        else:
            self.imperial_radio.setChecked(True)
        self.family_combo.setCurrentText(shape.family)
        self.filter_edit.setText("")
        self._select_label(shape.label)
        self.fillets_check.setChecked(bool(params.get("fillets", True)))
        self.segments_spin.setValue(int(params.get("segments", DEFAULT_ROUND_SEGMENTS)))
        self.roll_spin.setValue(float(params.get("roll", 0.0)))
        self.preview.set_selected(params.get("insertion", "centroid"))
        self._on_point(self.preview.selected())
        self.layer_combo.setEditText(layer or "")
        self.length_spin.setValue(float(length_m))

    # -- internals ----------------------------------------------------------
    def _select_label(self, label):
        for i in range(self.shape_list.count()):
            if self.shape_list.item(i).data(Qt.UserRole) == label:
                self.shape_list.setCurrentRow(i)
                return

    def _refill(self):
        family = self.family_combo.currentText()
        text = self.filter_edit.text().strip()
        shapes = self.db.search(text, family) if text else self.db.shapes(family)
        keep = self.current_shape().label if self.current_shape() else None
        self.shape_list.blockSignals(True)
        self.shape_list.clear()
        for s in shapes:
            item = QListWidgetItem(s.label_for(self.unit_system()))
            item.setData(Qt.UserRole, s.label)
            self.shape_list.addItem(item)
        self.shape_list.blockSignals(False)
        if keep is not None:
            self._select_label(keep)
        if self.shape_list.currentRow() < 0 and self.shape_list.count() == 1:
            self.shape_list.setCurrentRow(0)
        self._on_shape_changed()

    def _on_shape_changed(self):
        shape = self.current_shape()
        enabled = shape is not None
        self.place_button.setEnabled(enabled)
        self.update_button.setEnabled(enabled)
        if shape is None:
            self.readout.setText("")
            self.preview.set_profile(None)
            self.segments_spin.setEnabled(False)
            return
        self.segments_spin.setEnabled(bool(shape.round))
        units = self.unit_system()
        dims = shape.dims_mm if units == "metric" else shape.dims
        parts = [f"{k} = {fmt_dim(dims[k], units)}" for k in READOUT_KEYS.get(shape.family, [])
                 if k in dims]
        if units == "metric":
            parts.append(f"W = {shape.W_kgm:g} kg/m")
            parts.append(f"A = {shape.A_mm2:g} mm²")
        else:
            parts.append(f"W = {shape.W:g} lb/ft")
            parts.append(f"A = {shape.A:g} in²")
        self.readout.setText("   ".join(parts))
        profile = build_profile(shape.family, shape.dims_m(),
                                fillets=self.fillets_check.isChecked(),
                                segments=self.segments_spin.value())
        self.preview.set_profile(profile)
        self._on_point(self.preview.selected())

    def _on_point(self, insertion_id):
        profile = self.preview._profile
        label = insertion_id
        if profile is not None:
            label = profile.point(insertion_id).label
        self.insertion_label.setText(f"Insertion: {label}")

    def _on_place(self):
        if self.current_shape() is None:
            return
        self.place_requested.emit(self.params())

    def _on_update(self):
        if self.current_shape() is None:
            return
        self.update_requested.emit(self.params())


from PySide6.QtWidgets import QFileDialog, QHeaderView, QTableWidget, QTableWidgetItem  # noqa: E402

from ._bom import to_csv  # noqa: E402

ROW_HEADERS = ["Mark", "Shape", "Family", "Length", "Weight", "Layer", "IFC"]
SUMMARY_HEADERS = ["Shape", "Family", "Count", "Total length", "Total weight"]


class BomDialog(QDialog):
    def __init__(self, parent, fetch_bom, select_uid, fmt_len, fmt_weight):
        super().__init__(parent)
        self.setWindowTitle("Steel Bill of Materials")
        self.setModal(False)
        self.resize(760, 520)
        self._fetch = fetch_bom
        self._select = select_uid
        self._fmt_len = fmt_len
        self._fmt_weight = fmt_weight
        self._bom = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Members"))
        self.rows_table = self._table(ROW_HEADERS)
        self.rows_table.cellDoubleClicked.connect(self._on_row_activated)
        layout.addWidget(self.rows_table, 3)
        layout.addWidget(QLabel("Summary by shape"))
        self.summary_table = self._table(SUMMARY_HEADERS)
        layout.addWidget(self.summary_table, 2)
        self.totals_label = QLabel("")
        layout.addWidget(self.totals_label)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        export = QPushButton("Export CSV…")
        close = QPushButton("Close")
        refresh.clicked.connect(self.refresh)
        export.clicked.connect(lambda _c=False: self.export_csv())
        close.clicked.connect(self.close)
        buttons.addStretch(1)
        for b in (refresh, export, close):
            buttons.addWidget(b)
        layout.addLayout(buttons)

    @staticmethod
    def _table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        return t

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(str(value)))

    def refresh(self):
        self._bom = self._fetch()
        bom = self._bom
        self._fill(self.rows_table, [
            (r.mark, r.label, r.family,
             "profile" if r.is_profile else self._fmt_len(r.length_m),
             self._fmt_weight(r.weight_kg), r.layer, r.ifc_class) for r in bom.rows])
        self._fill(self.summary_table, [
            (s.label, s.family, s.count, self._fmt_len(s.total_length_m),
             self._fmt_weight(s.total_weight_kg)) for s in bom.summary])
        self.totals_label.setText(
            f"{bom.count} members  •  {self._fmt_len(bom.total_length_m)}  •  "
            f"{self._fmt_weight(bom.total_weight_kg)}")

    def _on_row_activated(self, row, _column=0):
        if self._bom is None or row < 0 or row >= len(self._bom.rows):
            return
        self._select(self._bom.rows[row].uid)

    def export_csv(self, path=None):
        if self._bom is None:
            self.refresh()
        if path is None:
            path, _f = QFileDialog.getSaveFileName(self, "Export Bill of Materials", "steel_bom.csv",
                                                   "CSV files (*.csv)")
            if not path:
                return None
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(to_csv(self._bom, self._fmt_len, self._fmt_weight))
        return path
