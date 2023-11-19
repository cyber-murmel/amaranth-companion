from .graphics_item import SocketGraphicsItem


class Socket:
    def __init__(self, node, socket_type):
        self._node = node
        self._type = socket_type

        self._edges = []

        self._graphics_item = SocketGraphicsItem(self)

    @property
    def graphics_item(self):
        return self._graphics_item

    @property
    def node(self):
        return self._node

    @property
    def scene_pos(self):
        return self.node.graphics_item.pos() + self.graphics_item.pos()

    def add_edge(self, edge):
        self._edges.append(edge)

    def remove_edge(self, edge):
        self._edges.remove(edge)

    def update_edges(self):
        for edge in self._edges:
            edge.update_path()
