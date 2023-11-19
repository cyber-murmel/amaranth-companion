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

    #
    # @end_point.setter
    # def end_point(self, val):
    #     self._end_point = val

    @property
    def start_socket(self):
        return self._start_socket

    @start_socket.setter
    def start_socket(self, val):
        self._start_socket = val
        # self._graphics_item.start_point = (
        #     self._start_socket.graphics_item.parentItem().pos()
        #     + self._start_socket.graphics_item.pos()
        # )

    @property
    def end_socket(self):
        return self._end_socket

    @end_socket.setter
    def end_socket(self, val):
        self._end_socket = val
        # self._graphics_item.start_point = (
        #     self._end_socket.graphics_item.parentItem().pos()
        #     + self._end_socket.graphics_item.pos()
        # )
