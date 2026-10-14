# SPDX-License-Identifier: GPL-3.0-or-later
"""Extension wiring: toolbar, menus, context menu, Browser kind, and the
session object that owns the dialogs and turns tool callbacks into commands."""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPalette
from PySide6.QtWidgets import QMessageBox, QToolBar

from . import KEY
from ._bom import collect
from ._db import load as load_db
from ._geometry import MIN_LENGTH
from ._grid_host import GridStore
from ._host import (insert_command, is_steel_group, iter_groups, make_group, member_frame,
                    member_params, member_parts, member_record, new_params, rebuild_command, run)
from ._tools import PlaceMemberTool, StretchMemberTool
from ._units import fmt_len, fmt_weight

log = logging.getLogger("ingetrazo.plugins.igz_steel")
_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
_SESSIONS = {}
TOOLBAR_NAME = "igz_steel_toolbar"


def _deferred(fn):
    """A slot that runs ``fn`` on the next event-loop turn and ignores the
    ``checked`` bool Qt may pass to a triggered handler."""
    return lambda _checked=False, f=fn: QTimer.singleShot(0, f)


def load_icon(name, window):
    """icons/<name>.svg (light strokes) for a dark palette, <name>_light.svg
    for a light one; either file serves as the fallback for the other."""
    dark = True
    try:
        bg = window.palette().color(QPalette.Window)
        dark = bg.lightness() < 128
    except Exception:
        pass
    order = [f"{name}.svg", f"{name}_light.svg"] if dark else [f"{name}_light.svg", f"{name}.svg"]
    for fn in order:
        path = os.path.join(_ICONS, fn)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


class SteelSession:
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.dialog = None
        self.bom_dialog = None
        self._edit_target = None
        self.grid_dialog_ = None
        self.grids = GridStore(app)
        self.grids.confirm = self._confirm_grid_delete
        self.grids.on_edit_request = lambda gid: QTimer.singleShot(0, lambda: self.open_grids(gid))

    # -- helpers ------------------------------------------------------------
    @property
    def scene(self):
        return self.app.viewport.scene

    def layer_names(self):
        return [ly.name for ly in getattr(self.scene, "layers", []) or []]

    def _guard(self):
        if getattr(self.scene, "edit_group", None) is not None:
            QMessageBox.information(self.app.window, "Steel",
                                    "Close the group you are editing before placing or "
                                    "changing steel members.")
            return False
        return True

    def single_selected(self):
        found = []
        for item in getattr(self.scene, "selection", ()) or ():
            g = getattr(item, "owner", None) or item
            if is_steel_group(g) and g not in found:
                found.append(g)
        if len(found) != 1:
            QMessageBox.information(self.app.window, "Steel",
                                    "Select exactly one steel member created with this extension.")
            return None
        return found[0]

    # -- dialogs ------------------------------------------------------------
    def member_dialog(self):
        if self.dialog is None:
            from ._dialog import MemberDialog
            self.dialog = MemberDialog(self.db, self.app.window)
            self.dialog.place_requested.connect(self.on_place)
            self.dialog.update_requested.connect(self.on_update)
        self.dialog.set_layers(self.layer_names())
        return self.dialog

    def _show(self, dialog):
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_place(self):
        d = self.member_dialog()
        d.set_mode("place")
        self._show(d)

    def open_edit(self):
        g = self.single_selected()
        if g is None:
            return
        params = member_params(g)
        _start, _direction, length, roll = member_frame(g)
        params["roll"] = roll
        from core.layers import layer_of
        d = self.member_dialog()
        d.set_mode("edit")
        d.load(params, layer_of(g), length)
        self._edit_target = g
        self._show(d)

    def open_stretch(self):
        g = self.single_selected()
        if g is None:
            return
        params = member_params(g)
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            QMessageBox.warning(self.app.window, "Steel",
                                f"Unknown shape {params.get('label')!r} in this member.")
            return
        from core.layers import layer_of
        layer = layer_of(g)
        params["roll"] = member_frame(g)[3]

        def on_commit(fixed, direction, length):
            return self.rebuild(g, params, fixed, direction, length, layer)
        self.app.viewport.set_active_tool(StretchMemberTool(g, shape, params, on_commit))

    def open_bom(self):
        if self.bom_dialog is None:
            from ._dialog import BomDialog
            self.bom_dialog = BomDialog(self.app.window, self.collect_bom, self.select_uid,
                                        fmt_len, fmt_weight)
        self.bom_dialog.refresh()
        self._show(self.bom_dialog)

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

    # -- actions ------------------------------------------------------------
    def on_place(self, p):
        shape = self.db.find(p.get("label", ""))
        if shape is None:
            return
        params = new_params(shape.label, p.get("unit_system", "imperial"),
                            p.get("insertion", "centroid"), p.get("roll", 0.0),
                            p.get("fillets", True), p.get("segments", 24))
        layer = (p.get("layer") or "").strip() or None

        def on_member(start, direction, length):
            return self.insert(shape, params, start, direction, length, layer)

        def on_profile(start):
            return self.insert(shape, params, start, (1.0, 0.0, 0.0), 0.0, layer)
        self.app.viewport.set_active_tool(PlaceMemberTool(shape, params, on_member, on_profile))

    def on_update(self, p):
        g = self._edit_target
        if g is None or not is_steel_group(g) or g not in list(iter_groups(self.scene)):
            QMessageBox.information(self.app.window, "Steel",
                                    "The member is no longer in the document. Select it again.")
            return
        shape = self.db.find(p.get("label", ""))
        if shape is None:
            return
        old = member_params(g)
        params = new_params(shape.label, p.get("unit_system", "imperial"),
                            p.get("insertion", "centroid"), p.get("roll", 0.0),
                            p.get("fillets", True), p.get("segments", 24))
        length = float(p.get("length", old.get("length", 0.0)))
        if length < MIN_LENGTH:
            length = 0.0
        layer = (p.get("layer") or "").strip() or None
        start, direction, _length, _roll = member_frame(g)
        if self.rebuild(g, params, start, direction, length, layer) and self.dialog is not None:
            self.dialog.close()

    def insert(self, shape, params, start, direction, length, layer):
        if not self._guard():
            return False
        try:
            parts = member_parts(shape, params, start, direction, length)
            group = make_group(parts)
        except Exception as exc:
            log.exception("igz_steel: building a member failed")
            QMessageBox.critical(self.app.window, "Steel", f"Could not build the member: {exc}")
            return False
        err = run(self.app.viewport, insert_command(group, layer))
        if err:
            QMessageBox.critical(self.app.window, "Steel", err)
            return False
        self._refresh_bom()
        return True

    def rebuild(self, group, params, start, direction, length, layer):
        if not self._guard():
            return False
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return False
        try:
            parts = member_parts(shape, params, start, direction, length)
        except Exception as exc:
            log.exception("igz_steel: rebuilding a member failed")
            QMessageBox.critical(self.app.window, "Steel", f"Could not rebuild the member: {exc}")
            return False
        err = run(self.app.viewport, rebuild_command(group, parts, layer))
        if err:
            QMessageBox.critical(self.app.window, "Steel", err)
            return False
        self._refresh_bom()
        return True

    # -- queries ------------------------------------------------------------
    def collect_bom(self):
        records = [member_record(g, self.db) for g in iter_groups(self.scene) if is_steel_group(g)]
        return collect([r for r in records if r is not None])

    def select_uid(self, uid):
        for g in iter_groups(self.scene):
            if getattr(g, "uid", None) == uid:
                self.scene.selection.clear()
                self.scene.selection.add(g)
                self.app.viewport.update()
                return

    def _refresh_bom(self):
        d = self.bom_dialog
        if d is not None and d.isVisible():
            d.refresh()

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

    # -- host hooks ---------------------------------------------------------
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

    def outliner_kind(self, group):
        if not is_steel_group(group):
            return None
        p = member_params(group) or {}
        shape = self.db.find(p.get("label", ""))
        length = float(p.get("length", 0.0))
        weight = length * (shape.weight_per_m() if shape else 0.0)
        from core.layers import layer_of
        return {"type": "Steel profile" if length < MIN_LENGTH else "Steel member",
                "props": [("Shape", p.get("label", "")), ("Length", fmt_len(length)),
                          ("Weight", fmt_weight(weight)), ("Layer", layer_of(group))]}


def _install_toolbar(app, session):
    win = app.window
    if win is None or not hasattr(win, "addToolBar"):
        return None
    if win.findChild(QToolBar, TOOLBAR_NAME) is not None:
        return None
    tb = None
    maker = getattr(win, "_new_toolbar", None)
    if callable(maker):
        try:
            tb = maker("Steel", TOOLBAR_NAME)
        except Exception:
            tb = None
    if tb is None:
        tb = QToolBar("Steel", win)
        tb.setObjectName(TOOLBAR_NAME)
        tb.setMovable(True)
        tb.setFloatable(True)
        px = 24
        try:
            from views.icons import toolbar_icon_px
            px = toolbar_icon_px()
        except Exception:
            pass
        tb.setIconSize(QSize(px, px))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        win.addToolBar(Qt.TopToolBarArea, tb)
    entries = [("tb_place", "Place steel member…", session.open_place),
               ("tb_stretch", "Stretch steel member", session.open_stretch),
               ("tb_edit", "Edit steel member…", session.open_edit),
               ("tb_bom", "Steel Bill of Materials…", session.open_bom),
               ("tb_grid", "Steel grids…", session.open_grids)]
    refs = []
    for icon, text, fn in entries:
        act = QAction(load_icon(icon, win), text, win)
        act.setToolTip(text)
        act.setStatusTip(text)
        act.triggered.connect(_deferred(fn))
        tb.addAction(act)
        refs.append(act)
    tb._igz_steel_refs = refs
    return tb


def setup(app):
    db = load_db()                         # a broken JSON surfaces as a load error
    session = SteelSession(app, db)
    _SESSIONS[id(app)] = session
    session.grids.register()
    try:
        toolbar = _install_toolbar(app, session)
    except Exception:
        log.exception("igz_steel: toolbar install failed")
        toolbar = None
    menu = app.add_menu("Steel")
    if menu is not None:
        for text, fn in (("Place member…", session.open_place),
                         ("Stretch member", session.open_stretch),
                         ("Edit member…", session.open_edit),
                         ("Bill of Materials…", session.open_bom),
                         ("Grids…", session.open_grids)):
            menu.addAction(text, _deferred(fn))
        if toolbar is not None:
            menu.addSeparator()
            toggle = toolbar.toggleViewAction()
            toggle.setText("Show steel toolbar")
            menu.addAction(toggle)
    app.add_context_menu(session.context_menu)
    outliner = getattr(app, "add_outliner_kind", None)
    if callable(outliner):
        outliner(session.outliner_kind)
    app.on_document_changed(session.on_document_changed)
