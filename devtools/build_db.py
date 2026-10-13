# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert the AISC Shapes Database v16.0 workbook into igz_steel/data/aisc_v16.json.

Developer tool, needs openpyxl. Usage:
    python devtools/build_db.py "aisc-shapes-database-v160-2.xlsx" igz_steel/data/aisc_v16.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

SHEET = "Database v16.0"
FAMILIES = ["W", "M", "S", "HP", "C", "MC", "L", "WT", "MT", "ST", "2L", "HSS", "PIPE"]
GEOM = ["d", "bf", "tw", "tf", "kdes", "k1", "t", "b", "Ht", "B", "OD", "tdes", "x", "y"]
MISSING = {"–", "-", "—", "", None}

_FRAC = re.compile(r"^(\d+)(?:-(\d+)/(\d+))?$|^(\d+)/(\d+)$")


def frac_to_float(token: str) -> float:
    """'1-3/8' -> 1.375, '3/4' -> 0.75, '12' -> 12.0, '1.5' -> 1.5."""
    token = token.strip()
    try:
        return float(token)
    except ValueError:
        pass
    m = _FRAC.match(token)
    if m is None:
        raise ValueError(f"not a fraction: {token!r}")
    if m.group(1) is not None:
        whole = float(m.group(1))
        if m.group(2):
            whole += float(m.group(2)) / float(m.group(3))
        return whole
    return float(m.group(4)) / float(m.group(5))


def parse_2l(label: str):
    """'2L8X4X1X3/4LLBB' -> (leg1, leg2, t, gap, llbb); llbb is None for equal legs."""
    if not label.startswith("2L"):
        raise ValueError(label)
    s = label[2:]
    llbb = None
    for tok, value in (("LLBB", True), ("SLBB", False)):
        if s.endswith(tok):
            llbb = value
            s = s[: -len(tok)]
    parts = s.split("X")
    if len(parts) not in (3, 4):
        raise ValueError(f"unexpected 2L label {label!r}")
    try:
        leg1, leg2, t = (frac_to_float(p) for p in parts[:3])
        gap = frac_to_float(parts[3]) if len(parts) == 4 else 0.0
    except ValueError as exc:
        raise ValueError(f"unexpected 2L label {label!r}: {exc}") from None
    return leg1, leg2, t, gap, llbb


def _num(value):
    if value in MISSING:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _block(header, start, names):
    """Column index of each name inside one unit block of the header row."""
    idx = {}
    for i in range(start, len(header)):
        h = header[i]
        if h in names and h not in idx:
            idx[h] = i
    missing = [n for n in names if n not in idx]
    if missing:
        raise SystemExit(f"header mismatch, missing {missing} from column {start}")
    return idx


def convert(xlsx: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb[SHEET]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    second = header.index("EDI_Std_Nomenclature", 2)   # start of the metric block
    names = ["Type", "EDI_Std_Nomenclature", "AISC_Manual_Label", "T_F", "W", "A"] + GEOM
    imp = _block(header, 0, names)
    met = _block(header, second, ["EDI_Std_Nomenclature", "AISC_Manual_Label", "W", "A"] + GEOM)
    shapes = []
    for row in rows:
        fam = row[imp["Type"]]
        if fam not in FAMILIES:
            continue
        label = str(row[imp["AISC_Manual_Label"]]).strip()
        dims = {k: _num(row[imp[k]]) for k in GEOM}
        dims_mm = {k: _num(row[met[k]]) for k in GEOM}
        dims = {k: v for k, v in dims.items() if v is not None}
        dims_mm = {k: v for k, v in dims_mm.items() if v is not None}
        llbb = None
        if fam == "2L":
            _l1, _l2, _t, gap, llbb = parse_2l(label)
            dims["gap"] = gap
            dims_mm["gap"] = round(gap * 25.4, 4)
        note = row[imp["T_F"]]
        shapes.append({
            "family": fam,
            "label": label,
            "label_metric": str(row[met["AISC_Manual_Label"]]).strip(),
            "edi": str(row[imp["EDI_Std_Nomenclature"]]).strip(),
            "round": fam in ("HSS", "PIPE") and "OD" in dims,
            "llbb": llbb,
            "dims": dims,
            "dims_mm": dims_mm,
            "W": _num(row[imp["W"]]),
            "A": _num(row[imp["A"]]),
            "W_kgm": _num(row[met["W"]]),
            "A_mm2": _num(row[met["A"]]),
            "notes": "sloped flanges" if (fam in ("M", "MT") and note == "T") else "",
        })
    singles = {s["label"]: s for s in shapes if s["family"] == "L"}
    for s in shapes:
        if s["family"] != "2L":
            continue
        base = s["label"][2:]
        for tok in ("LLBB", "SLBB"):
            base = base.replace(tok, "")
        single = singles.get("L" + "X".join(base.split("X")[:3]))
        if single is not None:
            for key in ("kdes",):
                if key in single["dims"] and key not in s["dims"]:
                    s["dims"][key] = single["dims"][key]
                    s["dims_mm"][key] = single["dims_mm"][key]
    if len(shapes) != 2299:
        raise SystemExit(f"expected 2299 shapes, got {len(shapes)}")
    return {"source": "AISC Shapes Database v16.0 (August 2023)",
            "generated": date.today().isoformat(), "shapes": shapes}


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    out = Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    data = convert(Path(argv[1]))
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(data['shapes'])} shapes)")


if __name__ == "__main__":
    main(sys.argv)
