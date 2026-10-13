# SPDX-License-Identifier: GPL-3.0-or-later
from PySide6.QtGui import QVector3D


def test_stub_mesh_welds_and_links_edges():
    from core.mesh import Mesh
    m = Mesh()
    a, b, c, d = (QVector3D(0, 0, 0), QVector3D(1, 0, 0),
                  QVector3D(1, 1, 0), QVector3D(0, 1, 0))
    f1 = m.add_face([a, b, c, d])
    f2 = m.add_face([a, d, QVector3D(0, 1, 1), QVector3D(0, 0, 1)])
    shared = [e for e in m.edges if len(e.faces) == 2]
    assert len(shared) == 1 and f1 in shared[0].faces and f2 in shared[0].faces
    assert shared[0].soft is False


def test_stub_history_and_layers():
    from core.scene import Scene
    from core.group import Group
    from core.history import History, InsertGroupCommand, AssignLayerCommand, CompoundCommand
    s = Scene()
    h = History(s)
    g = Group(name="x")
    h.execute(CompoundCommand([InsertGroupCommand(g), AssignLayerCommand([g], "Steel")]))
    assert g in s.groups and g.layer == "Steel" and s.layer("Steel") is not None
    assert h.last_error is None
    h.undo()
    assert g not in s.groups and s.layer("Steel") is None
