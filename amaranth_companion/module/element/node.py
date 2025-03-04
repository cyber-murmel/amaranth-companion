from enum import Enum
from typing import TYPE_CHECKING
from PyQt5.QtCore import QPointF
from uuid import uuid4

from .graphics_item.node_graphics_item import NodeGraphicsItem
from .graphics_item.node_content_widget import NodeContentWidget
from .socket import Socket, SocketType

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
        inputs: dict[str, SocketType],
        outputs: dict[str, SocketType],
        uuid=None,
    ):
        self._module: "Module" = module
        self._content_widget: NodeContentWidget = content_widget
        self._graphics_item: NodeGraphicsItem = NodeGraphicsItem(self, title)
        self._uuid = uuid if uuid else uuid4().hex

        self._input_sockets: dict[str, Socket] = {}
        self._output_sockets: dict[str, Socket] = {}
        for index, name in enumerate(inputs):
            socket = Socket(self, name, inputs[name])
            self._input_sockets.update({name: socket})
            socket.graphics_item.setPos(
                *self.get_socket_position(index, SocketPosition.LEFT)
            )
        for index, name in enumerate(outputs):
            socket = Socket(self, name, outputs[name])
            self._output_sockets.update({name: socket})
            socket.graphics_item.setPos(
                *self.get_socket_position(index, SocketPosition.RIGHT)
            )

    @property
    def uuid(self) -> (float, float):
        return self._uuid

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

    def get_socket_position(
        self, index: int, position: SocketPosition
    ) -> (float, float):
        x = 0 if (position in (SocketPosition.LEFT,)) else self._graphics_item.width
        y = (2 + index) * self.SOCKET_SPACING
        return x, y
