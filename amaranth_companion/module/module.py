from .scene import ModuleScene
from ..node import Node


class Module:
    def __init__(self):
        self._nodes = []
        self._edges = []

        self._scene = ModuleScene()

    @property
    def scene(self):
        return self._scene

    def addNode(self, node: Node):
        self._nodes.append(node)
        self.scene.addItem(node.graphics_item)

    def addEdge(self, edge):
        self._edges.append(edge)
        self.scene.addItem(edge.graphics_item)

    def removeNode(self, node: Node):
        self._nodes.remove(node)

    def removeEdge(self, edge):
        self._edges.remove(edge)
