# SPDX-License-Identifier: GPL-3.0-or-later
from PySide6.QtWidgets import QDoubleSpinBox


class LengthSpinBox(QDoubleSpinBox):
    """value() is metres, like the host's."""
    def __init__(self, parent=None, minimum=0.0, maximum=1000.0, unit=None, decimals=None):
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setDecimals(4)
        self._unit = unit or "m"

    def unit(self):
        return self._unit
