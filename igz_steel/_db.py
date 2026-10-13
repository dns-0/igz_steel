# SPDX-License-Identifier: GPL-3.0-or-later
"""The AISC shape table: loaded once from data/aisc_v16.json. Pure Python."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

IN_M = 0.0254
LB_PER_FT_TO_KG_PER_M = 1.48816394
FAMILIES = ["W", "M", "S", "HP", "C", "MC", "L", "WT", "MT", "ST", "2L", "HSS", "PIPE"]
DATA_PATH = Path(__file__).parent / "data" / "aisc_v16.json"


@dataclass(frozen=True)
class Shape:
    family: str
    label: str
    label_metric: str
    edi: str
    round: bool
    llbb: object          # True / False / None
    dims: dict            # inches
    dims_mm: dict         # millimetres
    W: float              # lb/ft
    A: float              # in^2
    W_kgm: float
    A_mm2: float
    notes: str

    def dims_m(self) -> dict:
        out = {k: v * IN_M for k, v in self.dims.items()}
        if self.family == "2L":
            out["llbb"] = True if self.llbb is None else bool(self.llbb)
        return out

    def weight_per_m(self) -> float:
        if self.W_kgm is not None:
            return float(self.W_kgm)
        return float(self.W or 0.0) * LB_PER_FT_TO_KG_PER_M

    def weight_per_ft(self) -> float:
        return float(self.W or 0.0)

    def label_for(self, unit_system: str) -> str:
        return self.label_metric if unit_system == "metric" else self.label


class Database:
    def __init__(self, shapes):
        self._shapes = list(shapes)
        self._by_family = {f: [] for f in FAMILIES}
        self._by_label = {}
        for s in self._shapes:
            self._by_family[s.family].append(s)
            self._by_label[s.label.lower()] = s
            self._by_label.setdefault(s.label_metric.lower(), s)

    def families(self):
        return list(FAMILIES)

    def shapes(self, family):
        return list(self._by_family.get(family, ()))

    def find(self, label):
        return self._by_label.get(str(label).strip().lower())

    def search(self, text, family=None):
        needle = str(text).strip().lower()
        pool = self.shapes(family) if family else self._shapes
        return [s for s in pool
                if needle in s.label.lower() or needle in s.label_metric.lower()]


_DB = None


def load(path=DATA_PATH) -> Database:
    global _DB
    if path != DATA_PATH:
        with open(path, "r", encoding="utf-8") as fh:
            return Database(Shape(**e) for e in json.load(fh)["shapes"])
    if _DB is None:
        with open(DATA_PATH, "r", encoding="utf-8") as fh:
            _DB = Database(Shape(**e) for e in json.load(fh)["shapes"])
    return _DB
