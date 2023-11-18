from .graphics_item import SocketGraphicsItem


class Socket:
    def __init__(self, socket_type, parent=None):
        self._type = socket_type

        self._edges = []

        self._graphics_item = SocketGraphicsItem(parent)

    @property
    def graphics_item(self):
        return self._graphics_item

    def add_edge(self, edge):
        self._edges.append(edge)

    def remove_edge(self, edge):
        self._edges.remove(edge)

    def update_edges(self):
        for edge in self._edges:
            edge.update_path()
