from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QGraphicsItem
from PyQt5.QtCore import QPointF

from .element import ModuleElement
from .graphics_item import EdgeGraphicsItem
from .socket import Socket
if TYPE_CHECKING:
    from .. import Module


class Edge(ModuleElement):
    def __init__(self, start_socket: Socket, end_socket: Socket, parent=None):
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
        elif self._end_socket:
            return self._end_socket.module

    def update_path(self) -> None:
        self.graphics_item.start_point = self.start_point
        self.graphics_item.end_point = self.end_point
        self.graphics_item.update_path()

    @property
    def graphics_item(self) -> EdgeGraphicsItem:
        return self._graphics_item

    @property
    def start_point(self) -> QPointF:
        return self._start_socket.scene_pos

    @property
    def end_point(self) -> QPointF:
        return self._end_socket.scene_pos

    @property
    def start_socket(self) -> Socket:
        return self._start_socket

    @start_socket.setter
    def start_socket(self, val: Socket) -> None:
        self._start_socket = val

    @property
    def end_socket(self) -> Socket:
        return self._end_socket

    @end_socket.setter
    def end_socket(self, val: Socket) -> None:
        self._end_socket = val

    def remove_from_sockets(self) -> None:
        self.start_socket.remove_edge(self)
        self.end_socket.remove_edge(self)
