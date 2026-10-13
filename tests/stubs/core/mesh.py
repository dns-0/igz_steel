# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal stand-in for core.mesh: welded vertices, radial edges, faces."""
from PySide6.QtGui import QVector3D


def _key(p):
    return (round(p.x(), 6), round(p.y(), 6), round(p.z(), 6))


class Vertex:
    def __init__(self, position):
        self.position = position
        self.edges = set()


class Edge:
    def __init__(self, v0, v1):
        self.v0, self.v1 = v0, v1
        self.faces = []
        self.soft = False

    @property
    def a(self):
        return self.v0.position

    @property
    def b(self):
        return self.v1.position


class Face:
    def __init__(self, loop, holes):
        self.loop = loop
        self.hole_loops = holes
        self.attrs = {}

    def vertices(self):
        return [v.position for v in self.loop]

    def holes(self):
        return [[v.position for v in h] for h in self.hole_loops]


class Mesh:
    def __init__(self):
        self.faces = []
        self.edges = []
        self._verts = {}
        self._edge_map = {}

    def vertex(self, position):
        k = _key(position)
        v = self._verts.get(k)
        if v is None:
            v = Vertex(QVector3D(position))
            self._verts[k] = v
        return v

    def _link_edge(self, v0, v1):
        k = frozenset((id(v0), id(v1)))
        e = self._edge_map.get(k)
        if e is None:
            e = Edge(v0, v1)
            self._edge_map[k] = e
            self.edges.append(e)
            v0.edges.add(e)
            v1.edges.add(e)
        return e

    def add_face(self, loop_positions, hole_loops=None):
        loop = [self.vertex(p) for p in loop_positions]
        holes = [[self.vertex(p) for p in h] for h in (hole_loops or [])]
        face = Face(loop, holes)
        for lp in (loop, *holes):
            n = len(lp)
            for i in range(n):
                self._link_edge(lp[i], lp[(i + 1) % n]).faces.append(face)
        self.faces.append(face)
        return face
