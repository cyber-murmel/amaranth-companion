from logging import getLogger
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Mapping

from .element import Edge, Node
from .history import ModuleHistory
from .scene.module_scene import ModuleScene
from .serialization import dumps, load_into, loads, module_to_dict

log = getLogger(__name__)


class Module:
    """A gateware module: the node graph plus the scene it is drawn on."""

    def __init__(self):
        self._path: str | None = None
        self._nodes: dict[str, Node] = {}
        self._scene = ModuleScene()
        self._design = None
        self._owner = None
        self._history = ModuleHistory(self)
        self._history.reset()

    # --- identity ----------------------------------------------------------

    @property
    def scene(self) -> ModuleScene:
        return self._scene

    @property
    def owner(self):
        """The hierarchical node this module is the inside of, if any."""
        return self._owner

    @owner.setter
    def owner(self, value) -> None:
        self._owner = value

    def inherited_param(self, name: str):
        """The value the enclosing block was given for parameter ``name``.

        This is how a parameter crosses into a block's implementation: a
        parameter port block inside asks the node it belongs to what it was
        handed from the level above.
        """
        if self._owner is None:
            return None

        from .parameters import resolve_params

        values, _error = resolve_params(self._owner)
        return values.get(name)

    @property
    def design(self):
        """The document this module belongs to, if it belongs to one."""
        return self._design

    @design.setter
    def design(self, value) -> None:
        self._design = value

    @property
    def history(self) -> ModuleHistory:
        """The undo stack edits to this module go on.

        A module inside a design shares the design's stack: descending into a
        block and editing it is one editing session to the user, so Ctrl+Z
        must not mean something different depending on the depth on screen.
        """
        if self._design is not None:
            return self._design.history
        return self._history

    @property
    def path(self) -> str | None:
        """Where this module was last loaded from or saved to."""
        return self._path

    # --- graph -------------------------------------------------------------

    @property
    def nodes(self) -> Mapping[str, Node]:
        return MappingProxyType(self._nodes)

    @property
    def edges(self) -> Iterator[Edge]:
        """Every edge in the module, each one once, in a stable order.

        Walking only the *output* sockets is what makes this a deduplication:
        :meth:`add_edge` guarantees an edge starts at an output and ends at an
        input, so each edge is reached from exactly one output socket.
        """
        for node in self._nodes.values():
            for socket in node.output_sockets.values():
                yield from socket.edges

    def add_node(self, node: Node) -> None:
        self._nodes[node.uuid] = node
        self._scene.addItem(node.graphics_item)

    def add_edge(self, edge: Edge) -> bool:
        """Accept an edge if it is meaningful, else detach and reject it.

        An edge must run output -> input, and must join two sockets of the same
        :class:`~.element.SocketKind`: a wire and an elaboration-time parameter
        are not interchangeable. Width mismatches are allowed through, because
        Amaranth itself truncates or extends.
        """
        start, end = edge.start_socket, edge.end_socket

        if not (start.is_output and end.is_input) or not start.can_connect_to(end):
            log.debug("rejecting edge %s -> %s", start, end)
            edge.remove_from_sockets()
            return False

        self._scene.addItem(edge.graphics_item)
        return True

    def remove_node(self, node: Node) -> None:
        del self._nodes[node.uuid]

        # materialise the edges first: remove_edge mutates the socket lists
        # this would otherwise be iterating
        for edge in list(node.edges):
            self.remove_edge(edge)

        self._scene.removeItem(node.graphics_item)

    def remove_edge(self, edge: Edge) -> None:
        edge.remove_from_sockets()
        self._scene.removeItem(edge.graphics_item)

    def clear(self) -> None:
        for node in list(self._nodes.values()):
            self.remove_node(node)

    # --- serialization -----------------------------------------------------

    def to_dict(self, *, versioned: bool = True) -> dict:
        """This module as plain data.

        ``versioned=False`` drops the format version and scene size, which is
        what a caller comparing two modules structurally wants.
        """
        return module_to_dict(self, versioned=versioned)

    def load(self, data: Mapping) -> None:
        """Replace the contents of this module with ``data``."""
        load_into(self, data, clear=True, remap_uuids=False)

    def paste(self, data: Mapping) -> dict[str, str]:
        """Add a copy of ``data`` to this module, with fresh uuids."""
        return load_into(self, data, clear=False, remap_uuids=True)

    @classmethod
    def from_file(cls, path) -> "Module":
        module = cls()
        module.load(loads(Path(path).read_text()))
        module._path = str(path)
        # the loaded state is the baseline, not something to undo back past
        module.history.reset()
        return module

    def save(self, path=None) -> None:
        target = path if path is not None else self._path
        if target is None:
            raise ValueError("module has no path; pass one to save()")

        Path(target).write_text(dumps(self.to_dict()))
        self._path = str(target)
