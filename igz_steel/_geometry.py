# SPDX-License-Identifier: GPL-3.0-or-later
"""Members from profiles: extrusion along local +X, the world frame, IFC class.

Pure Python on tuples. The profile's (u, v) maps to local (y, z); the member
runs from x = 0 to x = length; the insertion point sits on the local origin.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MIN_LENGTH = 0.001
MAX_LENGTH = 1000.0


@dataclass
class MemberMesh:
    faces: list = field(default_factory=list)
    soft_pairs: set = field(default_factory=set)


# ------------------------------------------------------------ vectors

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return scale(a, 1.0 / n) if n > 0 else (0.0, 0.0, 0.0)


def direction_and_length(a, b):
    d = sub(b, a)
    n = norm(d)
    if n < 1e-12:
        return None, 0.0
    return scale(d, 1.0 / n), n


def member_end(start, direction, length):
    return add(start, scale(unit(direction), length))


# ------------------------------------------------------------ extrusion

def extrude(profile, length, insertion_uv):
    ou, ov = insertion_uv
    L = float(length)

    def P(uv, x):
        return (x, uv[0] - ou, uv[1] - ov)

    faces = []
    soft = set()
    if L < MIN_LENGTH:
        for reg in profile.regions:
            outer = [P(p, 0.0) for p in reg.outer.points]
            holes = [[P(p, 0.0) for p in h.points] for h in reg.holes]
            faces.append((outer, holes) if holes else outer)
        return MemberMesh(faces, soft)
    for reg in profile.regions:
        outer0 = [P(p, 0.0) for p in reversed(reg.outer.points)]
        holes0 = [[P(p, 0.0) for p in reversed(h.points)] for h in reg.holes]
        faces.append((outer0, holes0) if holes0 else outer0)
        outerL = [P(p, L) for p in reg.outer.points]
        holesL = [[P(p, L) for p in h.points] for h in reg.holes]
        faces.append((outerL, holesL) if holesL else outerL)
    for reg in profile.regions:
        for loop in (reg.outer, *reg.holes):
            pts = loop.points
            n = len(pts)
            idx = []
            for i in range(n):
                a, b = pts[i], pts[(i + 1) % n]
                faces.append([P(a, 0.0), P(b, 0.0), P(b, L), P(a, L)])
                idx.append(len(faces) - 1)
            for i in range(n):
                if i in loop.arc_edges or (i - 1) % n in loop.arc_edges:
                    soft.add((idx[(i - 1) % n], idx[i]))
    return MemberMesh(faces, soft)


# ------------------------------------------------------------ frame

def member_matrix(start, direction, roll_deg=0.0):
    x = unit(direction)
    vertical = abs(x[2]) > math.cos(math.radians(1.0))
    ref = (0.0, 1.0, 0.0) if vertical else (0.0, 0.0, 1.0)
    z = unit(sub(ref, scale(x, dot(ref, x))))
    y = cross(z, x)
    if roll_deg:
        a = math.radians(roll_deg)
        c, s = math.cos(a), math.sin(a)
        y, z = add(scale(y, c), scale(z, s)), add(scale(z, c), scale(y, -s))
    return [x[0], y[0], z[0], float(start[0]),
            x[1], y[1], z[1], float(start[1]),
            x[2], y[2], z[2], float(start[2]),
            0.0, 0.0, 0.0, 1.0]


def apply_matrix(m, p):
    return (m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3],
            m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7],
            m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11])


def ifc_class_for(direction, tol_deg=5.0):
    x = unit(direction)
    vz = abs(x[2])
    if vz >= math.cos(math.radians(tol_deg)):
        return "IfcColumn"
    if vz <= math.sin(math.radians(tol_deg)):
        return "IfcBeam"
    return "IfcMember"


# ------------------------------------------------------------ preview

def preview_segments(profile, insertion_uv, start, direction, length, roll_deg=0.0):
    """Wireframe of the member: both end outlines and one longitudinal line per
    vertex (zero length: the single outline). World coordinates."""
    m = member_matrix(start, direction, roll_deg)
    ou, ov = insertion_uv
    L = float(length)
    ends = [0.0] if L < MIN_LENGTH else [0.0, L]
    segs = []
    for reg in profile.regions:
        for loop in (reg.outer, *reg.holes):
            pts = loop.points
            n = len(pts)
            world = {}
            for x in ends:
                world[x] = [apply_matrix(m, (x, p[0] - ou, p[1] - ov)) for p in pts]
                for i in range(n):
                    segs.append((world[x][i], world[x][(i + 1) % n]))
            if len(ends) == 2:
                for i in range(n):
                    segs.append((world[0.0][i], world[L][i]))
    return segs
