from enum import Enum
from typing import TYPE_CHECKING

from PyQt5.QtCore import QPointF

from ...blocks.definition import PortRole, PortSpec, Shape, split_port_name
from .element import ModuleElement
from .graphics_item import SocketGraphicsItem

if TYPE_CHECKING:
    from . import Edge
    from . import Node
    from .. import Module


class SocketKind(Enum):
    """What travels along the edges attached to a socket.

    ``SIGNAL`` sockets are wires: they become Amaranth ``Signal``s and carry
    values at run time. ``PARAM`` sockets carry a Python value consumed while
    the design is being elaborated -- a bit width, a counter reset value --
    so the two can never be connected to each other.
    """

    SIGNAL = "signal"
    PARAM = "param"

    @property
    def is_param(self) -> bool:
        return self is SocketKind.PARAM


class SocketDirection(Enum):
    INPUT = 1
    OUTPUT = 2

    @property
    def opposite(self) -> "SocketDirection":
        return (
            SocketDirection.OUTPUT
            if self is SocketDirection.INPUT
            else SocketDirection.INPUT
        )


#: how a port's name suffix maps onto a socket, for a block that *consumes*
#: the port. Port blocks flip the direction -- see :meth:`Socket.from_spec`.
ROLE_TO_SOCKET: dict[PortRole, tuple[SocketDirection, SocketKind]] = {
    PortRole.INPUT: (SocketDirection.INPUT, SocketKind.SIGNAL),
    PortRole.OUTPUT: (SocketDirection.OUTPUT, SocketKind.SIGNAL),
    PortRole.PARAM: (SocketDirection.INPUT, SocketKind.PARAM),
}


class Socket(ModuleElement):
    def __init__(
        self,
        node: "Node",
        name: str,
        direction: SocketDirection,
        kind: SocketKind = SocketKind.SIGNAL,
        shape: Shape | None = None,
        default=None,
    ):
        self._node: "Node" = node
        self._name = name
        self._direction: SocketDirection = direction
        self._kind: SocketKind = kind
        self._shape: Shape = shape if shape is not None else Shape()
        self._default = default

        self._edges: list["Edge"] = []

        self._graphics_item: SocketGraphicsItem = SocketGraphicsItem(self)

    @classmethod
    def from_spec(cls, node: "Node", spec: PortSpec, *, flip: bool = False) -> "Socket":
        """Build a socket for ``spec``.

        ``flip`` inverts the direction, which is what a port block needs: an
        ``a_in`` port of a hierarchical block is an input *on the block*, but
        inside the implementation it is where the value comes *from*, so the
        port block carries an output socket.
        """
        direction, kind = ROLE_TO_SOCKET[spec.role]
        return cls(
            node,
            spec.name,
            direction.opposite if flip else direction,
            kind,
            spec.shape,
            spec.default,
        )

    def to_spec(self) -> PortSpec:
        """The port this socket represents, independent of which side it is on."""
        split = split_port_name(self._name)
        role = (
            split[1]
            if split
            else (
                PortRole.OUTPUT
                if self._direction is SocketDirection.OUTPUT
                else PortRole.INPUT
            )
        )
        return PortSpec(
            name=self._name, role=role, shape=self._shape, default=self._default
        )

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
    def label(self) -> str:
        """The name without its port suffix, which is what the canvas shows."""
        split = split_port_name(self._name)
        return split[0] if split else self._name

    @property
    def kind(self) -> SocketKind:
        return self._kind

    @property
    def shape(self) -> Shape:
        return self._shape

    @shape.setter
    def shape(self, value: Shape) -> None:
        self._shape = value
        self._graphics_item.update()

    @property
    def default(self):
        """Parameter sockets: the value used when nothing is connected."""
        return self._default

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
    def is_param(self) -> bool:
        return self._kind.is_param

    @property
    def key(self) -> tuple[str, SocketDirection]:
        """What identifies a socket across a port refresh.

        A socket keeping its name *and* side is the same socket, so its edges
        survive the block's code being recompiled; anything else is a new one.
        """
        return self._name, self._direction

    @property
    def edges(self) -> list["Edge"]:
        return self._edges

    @property
    def graphics_item(self) -> SocketGraphicsItem:
        return self._graphics_item

    @property
    def scene_pos(self) -> QPointF:
        return self.node.graphics_item.pos() + self.graphics_item.pos()

    def can_connect_to(self, other: "Socket") -> bool:
        """Whether an edge between these two sockets is meaningful.

        Signals and parameters live in different worlds -- one is a wire, the
        other a value read while elaborating -- so they never connect. Width
        mismatches are deliberately *not* rejected: Amaranth truncates or
        extends, and refusing the edge would be stricter than the language.
        """
        if other is None or other.node is self.node:
            return False
        if self._kind is not other.kind:
            return False
        return self._direction is not other.direction

    def add_edge(self, edge: "Edge") -> None:
        self._edges.append(edge)

    def remove_edge(self, edge: "Edge") -> None:
        self._edges.remove(edge)

    def __repr__(self) -> str:
        return (
            f"<Socket {self._name} {self._direction.name.lower()} "
            f"{self._kind.value} {self._shape}>"
        )
