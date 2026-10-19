from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence, TYPE_CHECKING
from uuid import uuid4

from PyQt5.QtCore import QPointF

from ...blocks.definition import BlockDefinition, BlockKind, PortSpec
from ..grid import snap
from .element import ModuleElement
from .graphics_item.node_content_widget import NodeContentWidget
from .graphics_item.node_graphics_item import NodeGraphicsItem
from .socket import ROLE_TO_SOCKET, Socket, SocketDirection, SocketKind

if TYPE_CHECKING:
    from .. import Module
    from .edge import Edge

log = getLogger(__name__)


class SocketSide(Enum):
    LEFT = 1
    RIGHT = 2


@dataclass
class PortDiff:
    """What :meth:`Node.refresh_ports` changed.

    Returned rather than logged alone so the window can tell the user that
    recompiling their block cost them a connection.
    """

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    reshaped: list[str] = field(default_factory=list)
    dropped_edges: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.reshaped)

    def describe(self) -> str:
        parts = []
        if self.added:
            parts.append(f"added {', '.join(sorted(self.added))}")
        if self.removed:
            parts.append(f"removed {', '.join(sorted(self.removed))}")
        if self.reshaped:
            parts.append(f"resized {', '.join(sorted(self.reshaped))}")
        if self.dropped_edges:
            parts.append(
                f"dropped {self.dropped_edges} "
                f"connection{'s' if self.dropped_edges != 1 else ''}"
            )
        return "; ".join(parts)


class Node(ModuleElement):
    """One block placed on a canvas.

    The reusable half -- the Amaranth source, the parameter declarations, the
    icon -- lives in the node's :class:`BlockDefinition`. The node itself holds
    only what is particular to this placement: position, parameter values,
    sockets and edges.
    """

    SOCKET_SPACING = 20
    FIRST_SOCKET_INDEX = 2  # sockets start below the title bar

    def __init__(
        self,
        module: "Module",
        *,
        definition: BlockDefinition | None = None,
        ports: Sequence[PortSpec] = (),
        params: Mapping[str, Any] | None = None,
        content_widget: NodeContentWidget | None = None,
        title: str = "",
        uuid: str | None = None,
        child_module: "Module | None" = None,
    ):
        self._module: "Module" = module
        self._definition = definition
        self._params: dict[str, Any] = dict(params or {})
        self._child_module: "Module | None" = child_module
        self._content_widget = (
            content_widget if content_widget is not None else NodeContentWidget()
        )
        self._uuid: str = uuid if uuid else uuid4().hex
        self._title: str = title or (definition.label if definition else self._uuid[:8])
        self._graphics_item: NodeGraphicsItem = NodeGraphicsItem(self, self._title)

        self._input_sockets: dict[str, Socket] = {}
        self._output_sockets: dict[str, Socket] = {}
        #: the last error from introspecting this block, shown on the node
        self._error: str = ""
        #: line in this block's source the error came from, if it has one
        self._error_line: int | None = None

        self.refresh_ports(ports or (definition.ports if definition else ()))

    # --- identity ----------------------------------------------------------

    @property
    def uuid(self) -> str:
        return self._uuid

    @property
    def module(self) -> "Module":
        return self._module

    @property
    def definition(self) -> BlockDefinition | None:
        return self._definition

    @property
    def kind(self) -> BlockKind:
        return self._definition.kind if self._definition else BlockKind.CODE

    @property
    def block_id(self) -> str | None:
        return self._definition.id if self._definition else None

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
    def error(self) -> str:
        return self._error

    @error.setter
    def error(self, value: str) -> None:
        self.set_error(value)

    @property
    def error_line(self) -> int | None:
        """Line in this block's own source the error came from."""
        return self._error_line

    def set_error(self, message: str, line: int | None = None) -> None:
        self._error = message
        self._error_line = line if message else None
        self._graphics_item.update()

    # --- parameters --------------------------------------------------------

    @property
    def params(self) -> Mapping[str, Any]:
        return MappingProxyType(self._params)

    def set_param(self, name: str, value: Any) -> None:
        self._params[name] = value

    @property
    def effective_params(self) -> dict[str, Any]:
        """Parameter values to elaborate with: the definition's, overridden."""
        values = self._definition.default_params if self._definition else {}
        values.update(self._params)
        return values

    # --- hierarchy ---------------------------------------------------------

    @property
    def child_module(self) -> "Module | None":
        """The graph inside a hierarchical block, if this is one."""
        return self._child_module

    @child_module.setter
    def child_module(self, value: "Module | None") -> None:
        self._child_module = value

    @property
    def is_hierarchical(self) -> bool:
        return self._child_module is not None

    # --- sockets -----------------------------------------------------------

    @property
    def flips_ports(self) -> bool:
        """Whether this node's sockets face the opposite way to their role.

        A port block does: ``a_in`` is an input *of the enclosing block*, but
        inside the implementation it is the source the value comes from. So
        does a variable: ``width_param`` names a parameter, but the variable
        is what hands the value out rather than something that consumes one.
        """
        return self.kind.is_port or self.kind is BlockKind.VARIABLE

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
    def port_specs(self) -> list[PortSpec]:
        """This node's interface, as the ports a parent block would expose."""
        return [socket.to_spec() for socket in self.sockets]

    def refresh_ports(self, specs: Sequence[PortSpec]) -> PortDiff:
        """Make the sockets match ``specs``, keeping as many edges as possible.

        A socket that keeps both its name and its side is the *same* socket, so
        its edges survive -- which is what makes editing a block's source a
        non-destructive operation. Only a socket that genuinely disappears
        takes its connections with it.
        """
        diff = PortDiff()
        desired = self._desired_sockets(specs)
        existing = {socket.key: socket for socket in self.sockets}

        for key in existing.keys() - desired.keys():
            socket = existing[key]
            diff.removed.append(socket.name)
            diff.dropped_edges += self._detach(socket)

        for key in existing.keys() & desired.keys():
            socket, spec = existing[key], desired[key]
            if socket.shape != spec.shape:
                socket.shape = spec.shape
                diff.reshaped.append(socket.name)

        # in ``desired`` order, not set order: the sockets a block declares
        # have an order, and a node whose sockets came out shuffled would
        # serialise differently on every load
        for key, spec in desired.items():
            if key not in existing:
                socket = Socket.from_spec(self, spec, flip=self.flips_ports)
                self._register(socket)
                diff.added.append(socket.name)

        self._reorder_sockets(desired)
        self.reposition_sockets()

        if diff.changed:
            log.debug("ports of %s: %s", self._title, diff.describe())

        return diff

    def _desired_sockets(
        self, specs: Sequence[PortSpec]
    ) -> dict[tuple[str, SocketDirection], PortSpec]:
        """``specs`` keyed the same way :attr:`Socket.key` is, order preserved."""
        desired: dict[tuple[str, SocketDirection], PortSpec] = {}
        for spec in specs:
            direction, _kind = ROLE_TO_SOCKET[spec.role]
            if self.flips_ports:
                direction = direction.opposite
            desired[(spec.name, direction)] = spec
        return desired

    def _register(self, socket: Socket) -> None:
        bucket = self._input_sockets if socket.is_input else self._output_sockets
        bucket[socket.name] = socket

    def _detach(self, socket: Socket) -> int:
        """Remove ``socket`` and everything attached; returns edges dropped."""
        dropped = 0
        for edge in list(socket.edges):
            self._module.remove_edge(edge)
            dropped += 1

        bucket = self._input_sockets if socket.is_input else self._output_sockets
        bucket.pop(socket.name, None)

        item = socket.graphics_item
        item.setParentItem(None)
        scene = item.scene()
        if scene is not None:
            scene.removeItem(item)

        return dropped

    def _reorder_sockets(
        self, desired: Mapping[tuple[str, SocketDirection], PortSpec]
    ) -> None:
        """Put the socket maps back into the order the specs gave.

        Kept and newly added sockets would otherwise sit in whatever order
        they happened to be touched in, which leaks into serialization.
        """
        self._input_sockets = self._ordered(desired, self._input_sockets)
        self._output_sockets = self._ordered(desired, self._output_sockets)

    @staticmethod
    def _ordered(
        desired: Mapping[tuple[str, SocketDirection], PortSpec],
        sockets: Mapping[str, Socket],
    ) -> dict[str, Socket]:
        """``sockets`` in the order their specs appeared, stragglers last."""
        ordered = {
            name: sockets[name] for name, _direction in desired if name in sockets
        }
        ordered.update(sockets)  # anything the specs did not mention
        return ordered

    def reposition_sockets(self) -> None:
        """Lay the sockets out down the node's edges.

        Signal inputs come first down the left edge, then parameter inputs
        below them, so that the wires and the elaboration-time values do not
        interleave; outputs run down the right edge.
        """
        inputs = list(self._input_sockets.values())
        left = [socket for socket in inputs if not socket.is_param]
        left += [socket for socket in inputs if socket.is_param]
        right = list(self._output_sockets.values())

        for side, sockets in ((SocketSide.LEFT, left), (SocketSide.RIGHT, right)):
            for index, socket in enumerate(sockets):
                socket.graphics_item.setPos(*self.get_socket_position(index, side))

        for edge in self.edges:
            edge.update_path()

    # --- graph -------------------------------------------------------------

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
    def size(self) -> tuple[int, int]:
        """How big the node is drawn; the user can drag this."""
        return self._graphics_item.size

    @size.setter
    def size(self, value: tuple[int, int]) -> None:
        self._graphics_item.resize(*value)

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

    def __repr__(self) -> str:
        return f"<Node {self._title} {self.kind.value} {self._uuid[:8]}>"
