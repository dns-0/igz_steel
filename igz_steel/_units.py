# SPDX-License-Identifier: GPL-3.0-or-later
"""Thin wrapper over IngeTrazo's core.units with safe fallbacks."""
from __future__ import annotations

IMPERIAL_UNITS = {"in", "ft", "ft-in", "in-frac", "ft-in-frac"}
KG_TO_LB = 2.2046226218


def model_unit_code() -> str:
    try:
        from core.units import model_unit
        return str(model_unit())
    except Exception:
        return "m"


def is_imperial() -> bool:
    return model_unit_code() in IMPERIAL_UNITS


def fmt_len(metres: float) -> str:
    try:
        from core.units import fmt_len as host_fmt
        return host_fmt(float(metres))
    except Exception:
        return f"{float(metres):.3f} m"


def fmt_weight(kg: float) -> str:
    if is_imperial():
        return f"{float(kg) * KG_TO_LB:,.1f} lb"
    return f"{float(kg):,.1f} kg"


def fmt_dim(value: float, unit_system: str) -> str:
    """A tabulated dimension for the dialog: inches or millimetres."""
    if unit_system == "metric":
        return f"{float(value):.1f} mm"
    return f"{float(value):.3f} in"
