from enum import Enum
from typing import TYPE_CHECKING
from PyQt5.QtCore import QPointF

from .graphics_item.node_graphics_item import NodeGraphicsItem
from .graphics_item.node_content_widget import NodeContentWidget
from .socket import Socket

if TYPE_CHECKING:
    from .. import Module


class SocketPosition(Enum):
    TOP = 1
    LEFT = 2
    BOTTOM = 3
    RIGHT = 4


class Node:
    SOCKET_SPACING = 20

    def __init__(
        self,
        module: "Module",
        title: str,
        content_widget: NodeContentWidget,
        input_types: [],
        output_types: [],
    ):
        self._module: "Module" = module
        self._content_widget: NodeContentWidget = content_widget
        self._graphics_item: NodeGraphicsItem = NodeGraphicsItem(self, title)

        self._inputs: [Socket] = []
        self._outputs: [Socket] = []
        for i in range(len(input_types)):
            socket = Socket(self, input_types[i])
            self._inputs.append(socket)
            socket.graphics_item.setPos(
                *self.get_socket_position(i, SocketPosition.LEFT)
            )
        for i in range(len(output_types)):
            socket = Socket(self, output_types[i])
            self._outputs.append(socket)
            socket.graphics_item.setPos(
                *self.get_socket_position(i, SocketPosition.RIGHT)
            )

    @property
    def module(self) -> "Module":
        return self._module

    @property
    def graphics_item(self) -> NodeGraphicsItem:
        return self._graphics_item

    @property
    def content_widget(self) -> NodeContentWidget:
        return self._content_widget

    @property
    def pos(self) -> (float, float):
        pos: QPointF = self._graphics_item.pos()
        return pos.x(), pos.y()

    @pos.setter
    def pos(self, coordinates: (float, float)) -> None:
        self._graphics_item.setPos(coordinates[0], coordinates[1])

    def get_socket_position(self, index: int, position: SocketPosition) -> (float, float):
        x = 0 if (position in (SocketPosition.LEFT,)) else self._graphics_item.width
        y = (2 + index) * self.SOCKET_SPACING
        return x, y
