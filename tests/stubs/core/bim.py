# SPDX-License-Identifier: GPL-3.0-or-later
IFC_CLASSES = ["IfcColumn", "IfcBeam", "IfcMember"]


def tag_group(group, ifc_class, name):
    group.ifc = {"class": ifc_class, "name": name}
