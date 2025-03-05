import json

from .scene.module_scene import ModuleScene
from .scene.module_scene_view import ModuleSceneView

from .element import ModuleElementEncoder
from .element import Node, Edge, SocketType
from .element.graphics_item import NodeContentWidget


from amaranth_companion import __version__


class Module:
    def __init__(self, file=None):
        self._path = None
        self._nodes = {}

        self._scene = ModuleScene()

        if file:
            self.deserialize(file)

    @property
    def scene(self):
        return self._scene

    @property
    def scene_view(self):
        return self._scene_view

    def addNode(self, node):
        self._nodes[node.uuid] = node
        self.scene.addItem(node.graphics_item)

    def addEdge(self, edge):
        if (edge.start_socket.name in edge.start_socket.node._output_sockets) and (
            edge.end_socket.name in edge.end_socket.node._input_sockets
        ):
            self.scene.addItem(edge.graphics_item)
            return True

        edge.remove_from_sockets()

        return False

    def removeNode(self, node):
        del self._nodes[node.uuid]

        for socket in list(node._input_sockets.values()) + list(
            node._output_sockets.values()
        ):
            for edge in socket.edges:
                self.removeEdge(edge)

        self.scene.removeItem(node.graphics_item)

    def removeEdge(self, edge):
        # self._edges.remove(edge)

        edge.remove_from_sockets()

        self.scene.removeItem(edge.graphics_item)

    def to_json(self):
        scene = {
            "width": self.scene.scene_width,
            "height": self.scene.scene_height,
        }

        edges = list(
            {
                edge
                for node in self._nodes.values()
                for socket in list(node._output_sockets.values())
                for edge in socket._edges
            }
        )

        module_dict = {
            "version": __version__,
            "scene": scene,
            "nodes": self._nodes,
            "edges": edges,
        }

        return json.dumps(module_dict, cls=ModuleElementEncoder, indent=2)

    def serialize(self, file):
        self._path = file.name
        return file.write(self.to_json())

    def clear(self):
        for node in list(self._nodes.values()):
        # while self._nodes:
            self.removeNode(node)

    def from_json(self, text):
        data = json.loads(text)
        self.clear()

        for uuid, node_data in data["nodes"].items():
            inputs = {
                "a": SocketType.BIT,
                "b": SocketType.BIT,
            }
            outputs = {
                "o": SocketType.BIT,
            }
            text = node_data["text"] if "text" in node_data else ""
            node = Node(
                self, NodeContentWidget(text=text), inputs, outputs, uuid
            )
            node.pos = node_data["pos"]
            self.addNode(node)

        for edge_data in data["edges"]:
            start_node = self._nodes[edge_data["start"]["node_uuid"]]
            end_node = self._nodes[edge_data["end"]["node_uuid"]]
            edge = Edge(
                start_node._output_sockets[edge_data["start"]["socket_name"]],
                end_node._input_sockets[edge_data["end"]["socket_name"]],
            )
            self.addEdge(edge)

    def deserialize(self, file):
        self._path = file.name
        text = file.read()
        self.from_json(text)
