# SPDX-License-Identifier: GPL-3.0-or-later
class SnapResult:
    """Just enough of core.snap.SnapResult for the grid snap provider."""
    def __init__(self, point, kind, color, label=None):
        self.point, self.kind, self.color, self.label = point, kind, color, label
