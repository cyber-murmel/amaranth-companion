from .graphics_item import EdgeGraphicsItem
from ..socket import Socket


class Edge:
    def __init__(self, start_socket: Socket, end_socket: Socket, parent=None):
        self._start_socket = start_socket
        self._end_socket = end_socket

        self._start_socket.add_edge(self)
        self._end_socket.add_edge(self)

        self._graphics_item = EdgeGraphicsItem(self)

        self.update_path()

    def update_path(self):
        self.graphics_item.start_point = self.start_point
        self.graphics_item.end_point = self.end_point
        self.graphics_item.update_path()

    @property
    def graphics_item(self):
        return self._graphics_item

    @property
    def start_point(self):
        return self._start_socket.scene_pos

    @property
    def end_point(self):
        return self._end_socket.scene_pos

    @property
    def start_socket(self):
        return self._start_socket

    @start_socket.setter
    def start_socket(self, val):
        self._start_socket = val

    @property
    def end_socket(self):
        return self._end_socket

    @end_socket.setter
    def end_socket(self, val):
        self._end_socket = val

    def remove_from_sockets(self):
        self.start_socket.remove_edge(self)
        self.end_socket.remove_edge(self)
