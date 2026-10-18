from enum import Enum
from typing import TYPE_CHECKING

from PyQt5.QtCore import QPointF

from .element import ModuleElement
from .graphics_item import SocketGraphicsItem

if TYPE_CHECKING:
    from . import Edge
    from . import Node
    from .. import Module


class SocketType(Enum):
    BIT = 1


class SocketDirection(Enum):
    INPUT = 1
    OUTPUT = 2


class Socket(ModuleElement):
    def __init__(
        self,
        node: "Node",
        name: str,
        socket_type: SocketType,
        direction: SocketDirection,
    ):
        self._node: "Node" = node
        self._name = name
        self._type: SocketType = socket_type
        self._direction: SocketDirection = direction

        self._edges: list["Edge"] = []

        self._graphics_item: SocketGraphicsItem = SocketGraphicsItem(self)

    @property
    def module(self) -> "Module":
        return self.node.module

    @property
    def node(self) -> "Node":
        return self._node

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> SocketType:
        return self._type

    @property
    def direction(self) -> SocketDirection:
        return self._direction

    @property
    def is_input(self) -> bool:
        return self._direction is SocketDirection.INPUT

    @property
    def is_output(self) -> bool:
        return self._direction is SocketDirection.OUTPUT

    @property
    def edges(self) -> list["Edge"]:
        return self._edges

    @property
    def graphics_item(self) -> SocketGraphicsItem:
        return self._graphics_item

    @property
    def scene_pos(self) -> QPointF:
        return self.node.graphics_item.pos() + self.graphics_item.pos()

    def add_edge(self, edge: "Edge") -> None:
        self._edges.append(edge)

    def remove_edge(self, edge: "Edge") -> None:
        self._edges.remove(edge)
