# SPDX-License-Identifier: GPL-3.0-or-later
from abc import ABC, abstractmethod


class CommandRejected(Exception):
    pass


class Command(ABC):
    @abstractmethod
    def do(self, scene): ...

    @abstractmethod
    def undo(self, scene): ...


class History:
    def __init__(self, scene):
        self.scene = scene
        self.undo_stack = []
        self.redo_stack = []
        self.last_error = None

    def execute(self, cmd):
        try:
            cmd.do(self.scene)
        except Exception as exc:  # the host also swallows and reports
            self.last_error = f"{type(exc).__name__}: {exc}"
            return
        self.last_error = None
        self.undo_stack.append(cmd)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return False
        cmd = self.undo_stack.pop()
        cmd.undo(self.scene)
        self.redo_stack.append(cmd)
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        cmd = self.redo_stack.pop()
        cmd.do(self.scene)
        self.undo_stack.append(cmd)
        return True


class InsertGroupCommand(Command):
    def __init__(self, group):
        self.group = group

    def do(self, scene):
        scene.groups.append(self.group)
        scene.selection.clear()
        scene.selection.add(self.group)
        scene.version += 1

    def undo(self, scene):
        if self.group in scene.groups:
            scene.groups.remove(self.group)
        scene.selection.discard(self.group)
        scene.version += 1


class CompoundCommand(Command):
    def __init__(self, commands):
        self.commands = list(commands)

    def do(self, scene):
        done = []
        try:
            for c in self.commands:
                c.do(scene)
                done.append(c)
        except CommandRejected:
            for c in reversed(done):
                c.undo(scene)
            raise

    def undo(self, scene):
        for c in reversed(self.commands):
            c.undo(scene)


class AssignLayerCommand(Command):
    def __init__(self, entities, layer):
        self._entities = list(entities)
        self._layer = layer
        self._prev = []
        self._created = False

    def do(self, scene):
        from core.layers import Layer, assign_layer, layer_of
        if scene.layer(self._layer) is None:
            scene.layers.append(Layer(self._layer))
            self._created = True
        self._prev = [layer_of(e) for e in self._entities]
        for e in self._entities:
            assign_layer(e, self._layer)
        scene.version += 1

    def undo(self, scene):
        from core.layers import assign_layer
        for e, prev in zip(self._entities, self._prev):
            assign_layer(e, prev)
        if self._created:
            ly = scene.layer(self._layer)
            if ly is not None:
                scene.layers.remove(ly)
        scene.version += 1
