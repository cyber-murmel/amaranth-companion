from .socket import Socket

from amaranth_companion.module.gui.node_graphics_item import NodeGraphicsItem
from amaranth_companion.module.gui.node_content_widget import NodeContentWidget
from enum import Enum


class SocketPosition(Enum):
    TOP = 1
    LEFT = 2
    BOTTOM = 3
    RIGHT = 4


class Node():
    SOCKET_SPACING = 20

    def __init__(
        self,
        module,
        title: str,
        content_widget: NodeContentWidget,
        input_types: [],
        output_types: [],
    ):
        self._module = module
        self._content_widget = content_widget
        self._graphics_item = NodeGraphicsItem(self, title)

        self._inputs = []
        self._outputs = []
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
    def module(self):
        return self._module

    @property
    def graphics_item(self):
        return self._graphics_item

    @property
    def content_widget(self):
        return self._content_widget

    @property
    def pos(self):
        pos = self._graphics_item.pos()  # QPointF
        return pos.x(), pos.y()

    @pos.setter
    def pos(self, coordinates):
        self._graphics_item.setPos(coordinates[0], coordinates[1])

    def get_socket_position(self, index, position: SocketPosition):
        x = 0 if (position in (SocketPosition.LEFT,)) else self._graphics_item.width
        y = (2 + index) * self.SOCKET_SPACING
        return x, y

    def update_edges(self):
        for socket in self._inputs:
            socket.update_edges()
        for socket in self._outputs:
            socket.update_edges()
