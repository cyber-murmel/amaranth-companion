from enum import Enum
from types import MappingProxyType
from typing import Iterator, Mapping, TYPE_CHECKING
from uuid import uuid4

from PyQt5.QtCore import QPointF

from .element import ModuleElement
from .graphics_item.node_content_widget import NodeContentWidget
from .graphics_item.node_graphics_item import NodeGraphicsItem
from .socket import Socket, SocketDirection, SocketType

if TYPE_CHECKING:
    from .. import Module
    from .edge import Edge


class SocketSide(Enum):
    LEFT = 1
    RIGHT = 2


class Node(ModuleElement):
    SOCKET_SPACING = 20
    FIRST_SOCKET_INDEX = 2  # sockets start below the title bar

    def __init__(
        self,
        module: "Module",
        content_widget: NodeContentWidget,
        inputs: Mapping[str, SocketType],
        outputs: Mapping[str, SocketType],
        title: str = "",
        uuid: str | None = None,
    ):
        self._module: "Module" = module
        self._content_widget: NodeContentWidget = content_widget
        self._uuid: str = uuid if uuid else uuid4().hex
        self._title: str = title if title else self._uuid[:8]
        self._graphics_item: NodeGraphicsItem = NodeGraphicsItem(self, self._title)

        self._input_sockets: dict[str, Socket] = self._create_sockets(
            inputs, SocketDirection.INPUT, SocketSide.LEFT
        )
        self._output_sockets: dict[str, Socket] = self._create_sockets(
            outputs, SocketDirection.OUTPUT, SocketSide.RIGHT
        )

    def _create_sockets(
        self,
        types: Mapping[str, SocketType],
        direction: SocketDirection,
        side: SocketSide,
    ) -> dict[str, Socket]:
        sockets: dict[str, Socket] = {}
        for index, (name, socket_type) in enumerate(types.items()):
            socket = Socket(self, name, socket_type, direction)
            socket.graphics_item.setPos(*self.get_socket_position(index, side))
            sockets[name] = socket
        return sockets

    @property
    def uuid(self) -> str:
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
    def text(self) -> str:
        return self._content_widget.text

    @text.setter
    def text(self, value: str) -> None:
        self._content_widget.text = value

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value
        self._graphics_item.title = value

    @property
    def input_sockets(self) -> Mapping[str, Socket]:
        return MappingProxyType(self._input_sockets)

    @property
    def output_sockets(self) -> Mapping[str, Socket]:
        return MappingProxyType(self._output_sockets)

    @property
    def sockets(self) -> Iterator[Socket]:
        """Every socket of this node, inputs first."""
        yield from self._input_sockets.values()
        yield from self._output_sockets.values()

    @property
    def edges(self) -> Iterator["Edge"]:
        """Every edge attached to any of this node's sockets, each one once."""
        seen: set["Edge"] = set()
        for socket in self.sockets:
            for edge in socket.edges:
                if edge not in seen:
                    seen.add(edge)
                    yield edge

    @property
    def pos(self) -> tuple[float, float]:
        pos: QPointF = self._graphics_item.pos()
        return pos.x(), pos.y()

    @pos.setter
    def pos(self, coordinates: tuple[float, float]) -> None:
        self._graphics_item.setPos(coordinates[0], coordinates[1])

    def get_socket_position(self, index: int, side: SocketSide) -> tuple[float, float]:
        x = 0 if side is SocketSide.LEFT else self._graphics_item.WIDTH
        y = (self.FIRST_SOCKET_INDEX + index) * self.SOCKET_SPACING
        return x, y
