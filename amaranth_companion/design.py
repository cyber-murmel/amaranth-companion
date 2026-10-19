"""An open document: a hierarchy of modules, and where the user is in it.

A :class:`~amaranth_companion.module.Module` is one graph. A design is the
whole tree of them -- the root graph, plus the child graph inside every
hierarchical block, however deep -- together with the file it came from and a
single undo history spanning all of it.

The history has to live here rather than on the module: descending into a
block and editing it is one continuous editing session to the user, and an
undo stack per level would make Ctrl+Z mean something different depending on
which canvas happened to be showing.
"""

from logging import getLogger
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .blocks.definition import BlockDefinition
from .module import Module
from .module.element import Node
from .module.history import History
from .module.instantiate import instantiate
from .module.serialization import dumps, loads

log = getLogger(__name__)


class Design:
    """A document, open in the editor."""

    def __init__(self) -> None:
        self._root = Module()
        self._path: str | None = None
        #: the board this design is built for, as a platform registry id
        self._platform: str | None = None
        #: uuids of the hierarchical nodes descended into, outermost first.
        #: Uuids rather than nodes, because restoring an undo snapshot
        #: rebuilds every node object but keeps the uuids.
        self._stack: list[str] = []

        self._history = History(self)
        self.adopt()
        self._history.reset()

    # --- identity ----------------------------------------------------------

    @property
    def root(self) -> Module:
        return self._root

    @property
    def history(self) -> History:
        return self._history

    @property
    def path(self) -> str | None:
        """Where this design was last loaded from or saved to."""
        return self._path

    @property
    def name(self) -> str:
        return Path(self._path).stem if self._path else "untitled"

    @property
    def platform(self) -> str | None:
        """The board this design targets, or ``None`` for simulation only."""
        return self._platform

    @platform.setter
    def platform(self, value: str | None) -> None:
        self._platform = value or None

    def detach(self) -> None:
        """Forget where this design came from.

        An example is a starting point, not a file to edit in place: detaching
        it makes Save ask where to put it instead of writing back into the
        installed package.
        """
        self._path = None

    # --- hierarchy ---------------------------------------------------------

    def adopt(self, module: Module | None = None) -> None:
        """Make every module in the tree report *this* design's history.

        Called after anything that builds modules -- opening a file, undoing,
        instantiating a hierarchical block -- so that an edit made three levels
        down still lands on the one undo stack.
        """
        for descendant in self.walk(module if module is not None else self._root):
            descendant.design = self

    def walk(self, module: Module | None = None) -> Iterator[Module]:
        """Every module in the tree, outermost first."""
        module = module if module is not None else self._root
        yield module
        for node in module.nodes.values():
            if node.child_module is not None:
                yield from self.walk(node.child_module)

    @property
    def stack(self) -> list[Node]:
        """The hierarchical nodes currently descended into, outermost first.

        Resolved fresh each time: a uuid that no longer exists -- the block was
        deleted, or undone away -- silently truncates the path rather than
        leaving the editor pointing at nothing.
        """
        nodes: list[Node] = []
        module = self._root

        for uuid in self._stack:
            node = module.nodes.get(uuid)
            if node is None or node.child_module is None:
                break
            nodes.append(node)
            module = node.child_module

        return nodes

    @property
    def current_module(self) -> Module:
        """The graph the user is looking at."""
        stack = self.stack
        return stack[-1].child_module if stack else self._root

    @property
    def depth(self) -> int:
        return len(self.stack)

    @property
    def breadcrumb(self) -> list[str]:
        """Labels for the path from the root to where the user is."""
        return [self.name] + [node.title for node in self.stack]

    def enter(self, node: Node) -> bool:
        """Descend into ``node``; ``False`` if it has nothing to descend into."""
        if node.child_module is None:
            return False

        self._stack = [n.uuid for n in self.stack] + [node.uuid]
        log.debug("entered %s, depth %d", node.title, self.depth)
        return True

    def leave(self) -> bool:
        """Go up one level; ``False`` if already at the root."""
        if not self._stack:
            return False

        self._stack = [node.uuid for node in self.stack][:-1]
        return True

    def go_to_depth(self, depth: int) -> None:
        """Jump to a level of the current path, as the breadcrumb does."""
        self._stack = [node.uuid for node in self.stack][:depth]

    def go_to_path(self, uuids) -> bool:
        """Jump to any module in the tree, named by the path of nodes to it.

        Unlike :meth:`enter`, this does not have to start from where the user
        currently is -- the tree view offers every module at once. A path
        that no longer resolves leaves the location alone.
        """
        wanted = list(uuids)
        module = self._root

        for uuid in wanted:
            node = module.nodes.get(uuid)
            if node is None or node.child_module is None:
                return False
            module = node.child_module

        self._stack = wanted
        return True

    def paths(self):
        """Every module in the tree, as ``(path of uuids, node or None)``.

        The root comes first with an empty path and no node, because it is the
        design rather than a block inside it.
        """

        def walk(module, prefix):
            for node in module.nodes.values():
                if node.child_module is None:
                    continue
                path = prefix + [node.uuid]
                yield path, node
                yield from walk(node.child_module, path)

        yield [], None
        yield from walk(self._root, [])

    # --- editing -----------------------------------------------------------

    def instantiate(
        self,
        definition: BlockDefinition,
        *,
        params: Mapping[str, Any] | None = None,
        pos: Sequence[float] = (0.0, 0.0),
    ) -> Node:
        """Place a block on whichever graph the user is looking at."""
        node = instantiate(self.current_module, definition, params=params, pos=pos)
        if node.child_module is not None:
            self.adopt(node.child_module)
        return node

    # --- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        data = self._root.to_dict()
        # a design-level setting, so it sits beside the graph rather than on
        # any one node; absent until a board has been chosen
        if self._platform:
            data["platform"] = self._platform
        return data

    def load(self, data: Mapping) -> None:
        self._root.load(data)
        self._platform = data.get("platform") or None
        self.adopt()

    @classmethod
    def from_file(cls, path) -> "Design":
        design = cls()
        data = loads(Path(path).read_text())
        design._root.load(data)
        design._platform = data.get("platform") or None
        design.adopt()
        design._path = str(path)
        # the loaded state is the baseline, not something to undo back past
        design._history.reset()
        return design

    def save(self, path=None) -> None:
        target = path if path is not None else self._path
        if target is None:
            raise ValueError("design has no path; pass one to save()")

        Path(target).write_text(dumps(self.to_dict()))
        self._path = str(target)

    def __repr__(self) -> str:
        return f"<Design {self.name} depth={self.depth}>"
