from typing import TYPE_CHECKING

from PyQt5.QtCore import QPointF

from .element import ModuleElement
from .graphics_item import EdgeGraphicsItem
from .socket import Socket

if TYPE_CHECKING:
    from .. import Module


class Edge(ModuleElement):
    def __init__(self, start_socket: Socket, end_socket: Socket):
        self._start_socket: Socket = start_socket
        self._end_socket: Socket = end_socket

        self._graphics_item: EdgeGraphicsItem = EdgeGraphicsItem(self)

        self._start_socket.add_edge(self)
        self._end_socket.add_edge(self)

        self.update_path()

    @property
    def module(self) -> "Module":
        if self._start_socket:
            return self._start_socket.module
        return self._end_socket.module

    @property
    def graphics_item(self) -> EdgeGraphicsItem:
        return self._graphics_item

    @property
    def start_socket(self) -> Socket:
        return self._start_socket

    @start_socket.setter
    def start_socket(self, value: Socket) -> None:
        self._start_socket = value

    @property
    def end_socket(self) -> Socket:
        return self._end_socket

    @end_socket.setter
    def end_socket(self, value: Socket) -> None:
        self._end_socket = value

    @property
    def start_point(self) -> QPointF:
        return self._start_socket.scene_pos

    @property
    def end_point(self) -> QPointF:
        return self._end_socket.scene_pos

    def update_path(self) -> None:
        self._graphics_item.set_points(self.start_point, self.end_point)

    def remove_from_sockets(self) -> None:
        self._start_socket.remove_edge(self)
        self._end_socket.remove_edge(self)
