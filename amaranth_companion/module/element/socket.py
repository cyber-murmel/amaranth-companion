from typing import TYPE_CHECKING
from enum import Enum

from PyQt5.QtCore import QPointF

from .graphics_item import SocketGraphicsItem

if TYPE_CHECKING:
    from . import Edge
    from . import Node
    from .. import Module


class SocketType(Enum):
    BIT = 1


class Socket:
    def __init__(self, node: "Node", name: str, socket_type: SocketType):
        self._node: "Node" = node
        self._name = name
        self._type: SocketType = socket_type

        self._edges: "[Edge]" = []

        self._graphics_item: SocketGraphicsItem = SocketGraphicsItem(self)

    @property
    def module(self) -> "Module":
        return self.node.module

    @property
    def node(self) -> "Node":
        return self._node

    @property
    def name(self):
        return self._name

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
