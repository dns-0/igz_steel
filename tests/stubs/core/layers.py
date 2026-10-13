# SPDX-License-Identifier: GPL-3.0-or-later
DEFAULT_LAYER = "Layer 0"


class Layer:
    def __init__(self, name, visible=True, locked=False):
        self.name, self.visible, self.locked = name, visible, locked


def layer_of(entity):
    attrs = getattr(entity, "attrs", None)
    if attrs is not None:
        return attrs.get("layer") or DEFAULT_LAYER
    return getattr(entity, "layer", None) or DEFAULT_LAYER


def assign_layer(entity, name):
    value = None if name == DEFAULT_LAYER else name
    attrs = getattr(entity, "attrs", None)
    if attrs is not None:
        if value is None:
            attrs.pop("layer", None)
        else:
            attrs["layer"] = value
    elif hasattr(entity, "layer"):
        entity.layer = value
