from typing import TYPE_CHECKING

from PyQt5.QtCore import QPointF

from .graphics_item import SocketGraphicsItem
if TYPE_CHECKING:
    from . import Edge
    from . import Node
    from .. import Module


class Socket:
    def __init__(self, node: "Node", socket_type):
        self._node: "Node" = node
        self._type = socket_type

        self._edges: "[Edge]" = []

        self._graphics_item: SocketGraphicsItem = SocketGraphicsItem(self)

    @property
    def module(self) -> "Module":
        return self.node.module

    @property
    def node(self) -> "Node":
        return self._node

    @property
    def edges(self) -> "[Edge]":
        return self._edges

    @property
    def graphics_item(self) -> SocketGraphicsItem:
        return self._graphics_item

    @property
    def scene_pos(self) -> QPointF:
        return self.node.graphics_item.pos() + self.graphics_item.pos()

    def add_edge(self, edge) -> None:
        self._edges.append(edge)

    def remove_edge(self, edge) -> None:
        self._edges.remove(edge)
