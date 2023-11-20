from amaranth_companion.module.scene.module_scene import ModuleScene
from .scene.module_scene_view import ModuleSceneView


class Module:
    def __init__(self):
        self._nodes = []
        self._edges = []

        self._scene = ModuleScene()
        self._scene_view = ModuleSceneView(self)

    @property
    def scene(self):
        return self._scene

    @property
    def scene_view(self):
        return self._scene_view

    def addNode(self, node):
        self._nodes.append(node)
        self.scene.addItem(node.graphics_item)

    def addEdge(self, edge):
        if (edge.start_socket in edge.start_socket.node._outputs) and (
            edge.end_socket in edge.end_socket.node._inputs
        ):
            self._edges.append(edge)
            self.scene.addItem(edge.graphics_item)
            return True

        edge.remove_from_sockets()

        return False

    def removeNode(self, node):
        self._nodes.remove(node)

    def removeEdge(self, edge):
        self._edges.remove(edge)
        edge.remove_from_sockets()
        self.scene.removeItem(edge.graphics_item)
