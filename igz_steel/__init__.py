# SPDX-License-Identifier: GPL-3.0-or-later
"""igz_steel — AISC structural steel members for IngeTrazo.

Entry point only. IngeTrazo instantiates every ``Tool`` subclass defined in
this module with no arguments, so no Tool lives here: the tools are in
``_tools.py`` and the wiring in ``_core.py``.
"""
from __future__ import annotations

KEY = "igz_steel"
EXT_VERSION = 1
__version__ = "1.1.0"


def setup(app):
    """Extension API v2 entry point, called once when the main window exists."""
    from ._core import setup as _setup
    _setup(app)
