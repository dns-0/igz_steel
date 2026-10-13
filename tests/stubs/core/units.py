# SPDX-License-Identifier: GPL-3.0-or-later
"""Just enough of core.units: a settable model unit and two formatters."""
_UNIT = {"length": "m", "precision": 2}
IN_M = 0.0254


def set_model_unit(code, precision=2):
    _UNIT["length"], _UNIT["precision"] = code, precision


def model_unit():
    return _UNIT["length"]


def model_precision():
    return _UNIT["precision"]


def format_length(metres, units="m", decimals=2):
    if units in ("ft-in", "ft-in-frac"):
        inches = metres / IN_M
        feet = int(inches // 12)
        rest = inches - feet * 12
        return f"{feet}' {rest:.{decimals}f}\""
    if units in ("in", "in-frac"):
        return f"{metres / IN_M:.{decimals}f}\""
    if units == "ft":
        return f"{metres / IN_M / 12:.{decimals}f}'"
    if units == "mm":
        return f"{metres * 1000:.{decimals}f} mm"
    if units == "cm":
        return f"{metres * 100:.{decimals}f} cm"
    return f"{metres:.{decimals}f} m"


def fmt_len(metres):
    return format_length(float(metres), model_unit(), model_precision())
