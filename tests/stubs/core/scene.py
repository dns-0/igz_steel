# SPDX-License-Identifier: GPL-3.0-or-later
from core.layers import Layer, DEFAULT_LAYER


class Scene:
    def __init__(self):
        self.groups = []
        self.selection = set()
        self.layers = [Layer(DEFAULT_LAYER)]
        self.edit_group = None
        self.version = 0
        self.units = {"length": "m", "precision": 2}
        self.plugin_data = {}

    def layer(self, name):
        for ly in self.layers:
            if ly.name == name:
                return ly
        return None
