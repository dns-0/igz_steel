# SPDX-License-Identifier: GPL-3.0-or-later
from abc import ABC, abstractmethod
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QVector3D


@dataclass
class ToolContext:
    viewport: object
    world: QVector3D
    screen: QPointF = QPointF(0, 0)
    modifiers: object = Qt.KeyboardModifier.NoModifier
    snap: object = None


class Tool(ABC):
    name = "Unnamed"
    icon = None
    shortcut = None
    description = None
    menu_order = 0
    uses_snap = True
    box_select = False
    wireframe_color = None
    wireframe_depth_tested = False
    vcb_label = None

    @abstractmethod
    def on_activate(self, viewport): ...

    @abstractmethod
    def on_deactivate(self, viewport): ...

    def on_click(self, ctx): ...
    def on_hover(self, ctx): ...
    def on_cancel(self, viewport): ...
    def on_key(self, viewport, key, modifiers): return False
    def on_value(self, viewport, value): return False
    def status_clause(self): return ""
    def rubber_band_lines(self): return []
    def preview_faces(self): return []
