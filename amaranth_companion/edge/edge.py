from .graphics_item import EdgeGraphicsItem
from ..socket import Socket


class Edge:
    def __init__(self, start_socket: Socket, end_socket: Socket, parent=None):
        self._start_socket = start_socket
        self._end_socket = end_socket

        print(self.start_point.x())
        print(self.end_point)

        self._graphics_item = EdgeGraphicsItem(self.start_point, self.end_point, parent)

    def update_path(self):
        self._graphics_item.start_point = self.start_point
        self._graphics_item.end_point = self.end_point

    @property
    def graphics_item(self):
        return self._graphics_item

    @property
    def start_point(self):
        return (
            self._start_socket.graphics_item.parentItem().pos()
            + self._start_socket.graphics_item.pos()
        )

    @property
    def end_point(self):
        return (
            self._end_socket.graphics_item.parentItem().pos()
            + self._end_socket.graphics_item.pos()
        )

    @property
    def start_socket(self):
        return self._start_socket

    @property
    def end_socket(self):
        return self._end_socket
