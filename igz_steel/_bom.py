# SPDX-License-Identifier: GPL-3.0-or-later
"""Bill of Materials arithmetic. Pure Python; formatting is injected."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from ._db import FAMILIES
from ._geometry import MIN_LENGTH


@dataclass
class Row:
    mark: str
    label: str
    family: str
    length_m: float
    weight_kg: float
    layer: str
    ifc_class: str
    uid: object
    is_profile: bool


@dataclass
class SummaryRow:
    label: str
    family: str
    count: int
    total_length_m: float
    total_weight_kg: float


@dataclass
class BOM:
    rows: list
    summary: list
    count: int
    total_length_m: float
    total_weight_kg: float


def collect(records) -> BOM:
    rows = []
    counters = {}
    totals = {}
    for rec in records:
        label = str(rec["label"])
        counters[label] = counters.get(label, 0) + 1
        length = float(rec.get("length_m") or 0.0)
        is_profile = length < MIN_LENGTH
        weight = 0.0 if is_profile else length * float(rec.get("weight_per_m") or 0.0)
        rows.append(Row(f"{label}-{counters[label]}", label, str(rec.get("family", "")),
                        length, weight, str(rec.get("layer") or "Layer 0"),
                        str(rec.get("ifc_class") or ""), rec.get("uid"), is_profile))
        if not is_profile:
            t = totals.setdefault(label, [rec.get("family", ""), 0, 0.0, 0.0])
            t[1] += 1
            t[2] += length
            t[3] += weight
    order = {f: i for i, f in enumerate(FAMILIES)}
    summary = [SummaryRow(label, fam, n, L, w) for label, (fam, n, L, w) in totals.items()]
    summary.sort(key=lambda s: (order.get(s.family, 99), s.label))
    return BOM(rows, summary, sum(s.count for s in summary),
               sum(s.total_length_m for s in summary), sum(s.total_weight_kg for s in summary))


def to_csv(bom: BOM, fmt_len, fmt_weight) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["mark", "label", "family", "length", "weight", "layer", "ifc_class",
                "length_m", "weight_kg"])
    for r in bom.rows:
        w.writerow([r.mark, r.label, r.family, fmt_len(r.length_m), fmt_weight(r.weight_kg),
                    r.layer, r.ifc_class, round(r.length_m, 4), round(r.weight_kg, 2)])
    w.writerow([])
    w.writerow(["label", "family", "count", "total_length", "total_weight",
                "total_length_m", "total_weight_kg"])
    for s in bom.summary:
        w.writerow([s.label, s.family, s.count, fmt_len(s.total_length_m),
                    fmt_weight(s.total_weight_kg), round(s.total_length_m, 4),
                    round(s.total_weight_kg, 2)])
    w.writerow(["TOTAL", "", bom.count, fmt_len(bom.total_length_m),
                fmt_weight(bom.total_weight_kg), round(bom.total_length_m, 4),
                round(bom.total_weight_kg, 2)])
    return out.getvalue()
