from .scene import ModuleScene


class Module:
    def __init__(self):
        self._nodes = []
        self._edges = []

        self._scene = ModuleScene()

    @property
    def scene(self):
        return self._scene

    def addNode(self, node):
        self._nodes.append(node)

    def addEdge(self, edge):
        self._edges.append(edge)

    def removeNode(self, node):
        self._nodes.remove(node)

    def removeEdge(self, edge):
        self._edges.remove(edge)
