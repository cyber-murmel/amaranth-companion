from .graphics_item import NodeGraphicsItem
from .content_widget import NodeContentWidget
from ..socket import Socket
from enum import Enum


class SocketPosition(Enum):
    TOP = 1
    LEFT = 2
    BOTTOM = 3
    RIGHT = 4


class Node:
    def __init__(
        self,
        title: str,
        content_widget: NodeContentWidget,
        input_types: [],
        output_types: [],
    ):
        self._inputs = []
        self._outputs = []

        self._content_widget = content_widget

        self._graphics_item = NodeGraphicsItem(self._content_widget, title)

        self.socket_spacing = 20

        i = 0
        for input_type in input_types:
            socket = Socket(input_type)
            self._inputs.append(socket)
            socket.graphics_item.setParentItem(self._graphics_item)
            socket.graphics_item.setPos(
                *self.get_socket_position(i, SocketPosition.LEFT)
            )
            i += 1
        i = 0
        for output_type in output_types:
            socket = Socket(output_type)
            self._outputs.append(socket)
            socket.graphics_item.setParentItem(self._graphics_item)
            socket.graphics_item.setPos(
                *self.get_socket_position(i, SocketPosition.RIGHT)
            )
            i += 1

    @property
    def graphics_item(self):
        return self._graphics_item

    @property
    def content_widget(self):
        return self._graphics_item

    @property
    def pos(self):
        pos = self._graphics_item.pos()  # QPointF
        return pos.x(), pos.y()

    @pos.setter
    def pos(self, coordinates):
        self._graphics_item.setPos(coordinates[0], coordinates[1])

    def get_socket_position(self, index, position: SocketPosition):
        x = 0 if (position in (SocketPosition.LEFT,)) else self._graphics_item.width

        # if position in (LEFT_BOTTOM, RIGHT_BOTTOM):
        #     # start from bottom
        #     y = (
        #         self._graphics_item.height
        #         - self._graphics_item.edge_size
        #         - self._graphics_item._padding
        #         - index * self.socket_spacing
        #     )
        # else:
        # start from top
        y = (2 + index) * self.socket_spacing

        return x, y
