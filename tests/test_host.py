# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from PySide6.QtGui import QVector3D

from igz_steel import _db, _host, KEY


class FakeViewport:
    def __init__(self, scene, history):
        self.scene, self.history = scene, history
        self.updated = self.notified = 0

    def notify_scene_changed(self):
        self.notified += 1

    def update(self):
        self.updated += 1


@pytest.fixture
def scene_history():
    from core.scene import Scene
    from core.history import History
    s = Scene()
    return s, History(s)


def _w12():
    return _db.load().find("W12X26")


def test_params_and_parts_for_a_beam():
    shape = _w12()
    params = _host.new_params("W12X26", "imperial", "top", 0.0, True, 24)
    parts = _host.member_parts(shape, params, (1.0, 2.0, 3.0), (1.0, 0.0, 0.0), 3.0)
    assert parts["name"] == "W12X26"
    assert parts["ifc"] == {"class": "IfcBeam", "name": "W12X26"}
    ext = parts["ext"][KEY]
    assert ext["version"] == 1 and ext["label"] == "W12X26" and ext["insertion"] == "top"
    assert ext["start"] == [1.0, 2.0, 3.0] and ext["direction"] == [1.0, 0.0, 0.0]
    assert ext["length"] == 3.0 and ext["fillets"] is True and ext["segments"] == 24
    end = parts["xform"].map(QVector3D(3.0, 0.0, 0.0))
    assert (end.x(), end.y(), end.z()) == pytest.approx((4.0, 2.0, 3.0))
    mesh = parts["mesh"]
    assert len(mesh.faces) == 2 + 12 + 16
    assert sum(1 for e in mesh.edges if e.soft) == 20          # 4 fillets x 5 lines
    # top of steel is on the axis: no vertex above z = 0 in local space
    assert max(v.position.z() for f in mesh.faces for v in f.loop) == pytest.approx(0.0)


def test_sharp_member_has_no_soft_edges_and_column_is_tagged():
    shape = _w12()
    params = _host.new_params("W12X26", "imperial", "centroid", 0.0, False, 24)
    parts = _host.member_parts(shape, params, (0, 0, 0), (0, 0, 1), 4.0)
    assert not any(e.soft for e in parts["mesh"].edges)
    assert parts["ifc"]["class"] == "IfcColumn"
    profile = _host.member_parts(shape, params, (0, 0, 0), (1, 0, 0), 0.0)
    assert profile["name"] == "W12X26 (profile)" and len(profile["mesh"].faces) == 1


def test_make_group_insert_rebuild_undo(scene_history):
    scene, history = scene_history
    vp = FakeViewport(scene, history)
    shape = _w12()
    params = _host.new_params("W12X26", "imperial", "centroid", 0.0, True, 24)
    parts = _host.member_parts(shape, params, (1, 2, 3), (1, 0, 0), 3.0)
    g = _host.make_group(parts)
    assert g.component is False and _host.is_steel_group(g)
    assert _host.run(vp, _host.insert_command(g, "Steel")) is None
    assert g in scene.groups and g.layer == "Steel" and scene.layer("Steel") is not None
    assert _host.member_endpoints(g) == (pytest.approx((1, 2, 3)), pytest.approx((4, 2, 3)))
    longer = _host.member_parts(shape, params, (1, 2, 3), (1, 0, 0), 5.0)
    assert _host.run(vp, _host.rebuild_command(g, longer, "Beams")) is None
    assert _host.member_endpoints(g)[1] == pytest.approx((6, 2, 3))
    assert g.layer == "Beams" and _host.member_params(g)["length"] == 5.0
    assert scene.selection == {g}
    history.undo()
    assert _host.member_endpoints(g)[1] == pytest.approx((4, 2, 3)) and g.layer == "Steel"
    history.undo()
    assert g not in scene.groups and scene.layer("Steel") is None
    assert vp.notified == 2 and vp.updated == 2


def test_is_steel_group_rejects_exploded_and_foreign_groups():
    from core.group import Group
    assert _host.is_steel_group(Group(name="plain")) is False
    assert _host.member_params(Group(name="plain")) is None
    shape = _w12()
    params = _host.new_params("W12X26", "imperial", "centroid", 0.0, True, 24)
    g = _host.make_group(_host.member_parts(shape, params, (0, 0, 0), (1, 0, 0), 2.0))
    g.xform = None                                     # exploded / made unique
    assert _host.is_steel_group(g) is False
    foreign = Group(name="other")
    foreign.ext = {"windowizer": {"rows": 2}}
    assert _host.is_steel_group(foreign) is False


def test_run_reports_errors(scene_history):
    scene, history = scene_history
    vp = FakeViewport(scene, history)
    from core.history import Command

    class Boom(Command):
        def do(self, scene):
            raise RuntimeError("nope")

        def undo(self, scene):
            pass
    err = _host.run(vp, Boom())
    assert err and "nope" in err


def test_member_record_and_iter_groups(scene_history):
    scene, _ = scene_history
    from core.group import Group
    db = _db.load()
    shape = db.find("HSS6X6X1/2")
    params = _host.new_params("HSS6X6X1/2", "imperial", "centroid", 0.0, True, 24)
    g = _host.make_group(_host.member_parts(shape, params, (0, 0, 0), (0, 0, 1), 2.0), layer="Cols")
    container = Group(name="box")
    container.children.append(g)
    scene.groups.append(container)
    found = [x for x in _host.iter_groups(scene) if _host.is_steel_group(x)]
    assert found == [g]
    rec = _host.member_record(g, db)
    assert rec["label"] == "HSS6X6X1/2" and rec["family"] == "HSS"
    assert rec["length_m"] == 2.0 and rec["weight_per_m"] == pytest.approx(shape.weight_per_m())
    assert rec["layer"] == "Cols" and rec["ifc_class"] == "IfcColumn" and rec["uid"] == g.uid
    assert _host.member_record(Group(name="plain"), db) is None


def test_profile_cache_and_insertion_fallback():
    shape = _w12()
    p1 = _host.profile_for(shape, {"fillets": True, "segments": 24})
    p2 = _host.profile_for(shape, {"fillets": True, "segments": 24})
    assert p1 is p2
    assert _host.insertion_uv(p1, "does-not-exist") == (0.0, 0.0)
    assert _host.insertion_uv(p1, "top")[1] > 0
