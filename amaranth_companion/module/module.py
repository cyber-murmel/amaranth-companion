import json

from .scene.module_scene import ModuleScene
from .scene.module_scene_view import ModuleSceneView

from .element import ModuleElementEncoder
from .element import Node, Edge, SocketType
from .element.graphics_item import NodeContentWidget


from amaranth_companion import __version__

# import module_pb2


class Module:
    def __init__(self, file=None):
        self._nodes = []

        self._scene = ModuleScene()
        self._scene_view = ModuleSceneView(self)

        if file:
            self.deserialize(file)

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
        if (edge.start_socket.name in edge.start_socket.node._output_sockets) and (
            edge.end_socket.name in edge.end_socket.node._input_sockets
        ):
            # self._edges.append(edge)
            self.scene.addItem(edge.graphics_item)
            return True

        edge.remove_from_sockets()

        return False

    def removeNode(self, node):
        self._nodes.remove(node)

        for socket in node._input_sockets + node._output_sockets:
            for edge in socket.edges:
                self.removeEdge(edge)

        self.scene.removeItem(node.graphics_item)

    def removeEdge(self, edge):
        # self._edges.remove(edge)

        edge.remove_from_sockets()

        self.scene.removeItem(edge.graphics_item)

    def serialize(self, file):
        scene = {
            "width": self.scene.scene_width,
            "height": self.scene.scene_height,
        }

        edges = list(
            {
                edge
                for node in self._nodes
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

        # return file.write(json.dumps(module_dict, cls=ModuleElementEncoder, indent=2))
        return json.dump(module_dict, file, cls=ModuleElementEncoder, indent=2)

    def clear(self):
        while self._nodes:
            self.removeNode(self._nodes[0])

    def deserialize(self, file):
        self.clear()
        data = json.load(file)

        for index, node_data in enumerate(data["nodes"]):
            inputs = {
                "a": SocketType.BIT,
                "b": SocketType.BIT,
            }
            outputs = {
                "o": SocketType.BIT,
            }
            node = Node(self, f"{index}", NodeContentWidget(), inputs, outputs)
            node.pos = node_data["pos"]
            self.addNode(node)

        for edge_data in data["edges"]:
            start_node = self._nodes[edge_data["start"]["node_index"]]
            end_node = self._nodes[edge_data["end"]["node_index"]]
            edge = Edge(
                start_node._output_sockets[edge_data["start"]["socket_name"]],
                end_node._input_sockets[edge_data["end"]["socket_name"]],
            )
            self.addEdge(edge)
