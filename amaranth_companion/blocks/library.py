"""Discovery of block definitions.

Definitions are ``*.block.yml`` files, the way GNU Radio Companion keeps its
blocks in ``*.block.yml``: a block is data on disk, not a Python class, so a
user can add one without touching the editor.

YAML rather than the JSON the documents use, because a definition embeds
Amaranth source. A block scalar keeps that source readable and diffable; the
same text in JSON is one ``\\n``-escaped line.
"""

from logging import getLogger
from pathlib import Path
from typing import Iterable, Iterator, Mapping

import yaml

from .definition import BlockDefinition, BlockDefinitionError, BlockKind

log = getLogger(__name__)

SUFFIX = ".block.yml"

#: definitions shipped with the application
BUILTIN_DIR = Path(__file__).parent / "builtin"

#: blocks a design carries with it, beside its own file
PROJECT_BLOCK_DIRNAME = "blocks"


def user_block_dir() -> Path:
    """Where blocks go when they are not tied to one project."""
    import os

    root = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(root) / "amaranth-companion" / "blocks"


def project_block_dir(design) -> Path | None:
    """The block directory beside ``design``'s file, if it has one."""
    path = getattr(design, "path", None)
    return Path(path).parent / PROJECT_BLOCK_DIRNAME if path else None


def block_directories(design=None) -> list[Path]:
    """Where to look for blocks, nearest first.

    A project's own blocks shadow the shared ones, so a design can carry a
    changed copy of a block without editing everybody else's.
    """
    directories = []
    project = project_block_dir(design) if design is not None else None
    if project is not None:
        directories.append(project)
    directories.append(user_block_dir())
    return directories


#: kinds whose behaviour is built into the editor rather than described by a
#: file. They still get a definition so that a node always has an id to
#: serialise and a kind to dispatch on.
BUILTIN_KINDS: dict[BlockKind, tuple[str, str]] = {
    BlockKind.CODE: ("builtin.code", "Code"),
    BlockKind.PORT_IN: ("builtin.port_in", "Input"),
    BlockKind.PORT_OUT: ("builtin.port_out", "Output"),
    BlockKind.PORT_PARAM: ("builtin.port_param", "Parameter"),
    BlockKind.VARIABLE: ("builtin.variable", "Variable"),
    BlockKind.TESTBENCH: ("builtin.testbench", "Testbench"),
    BlockKind.FORMAL: ("builtin.formal", "Formal"),
    BlockKind.RESOURCE: ("builtin.resource", "I/O"),
}

#: the category built-in blocks appear under in the Insert menu
BUILTIN_CATEGORY = ("Blocks",)

#: what a freshly inserted code block starts as. Valid on arrival, so a new
#: block sits there with real ports instead of reporting that it defines no
#: Elaboratable, and shaped to show the naming convention by example.
CODE_TEMPLATE = """\
from amaranth import *


class Block(Elaboratable):
    \"\"\"A new block.

    The ports come from the names below: `_in` and `_out` make signal
    ports, `_param` makes a parameter port, and a name with no suffix --
    `state` here -- stays internal to the block.
    \"\"\"

    def __init__(self, width_param=1):
        self.a_in = Signal(width_param)
        self.o_out = Signal(width_param)
        self.state = Signal(width_param)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o_out.eq(self.a_in)
        return m
"""

#: a testbench block defines this coroutine; the runner calls it with the
#: simulator context and the block the testbench sits inside
TESTBENCH_TEMPLATE = """\
async def testbench(ctx, dut):
    # drive the inputs of the block this testbench sits in, then check
    # its outputs. `ctx.set`, `ctx.get` and `await ctx.tick()` are the
    # amaranth simulator api.
    pass
"""

#: starting point for a formal block. `MODES` and `DEPTH` are read by the
#: checker, so the block states how it wants to be checked.
FORMAL_TEMPLATE = """\
from amaranth.hdl import Assert, Assume, Cover

MODES = ("bmc", "cover")
DEPTH = 20


def formal(m, dut):
    # State what must always hold, rather than what happens for one
    # stimulus. `m` is a wrapper around the block, so properties go in
    # `m.d.comb` and reach the design through `dut`.
    m.d.comb += Assert(dut.o_out == dut.o_out)
"""

TEMPLATES: dict[BlockKind, str] = {
    BlockKind.CODE: CODE_TEMPLATE,
    BlockKind.TESTBENCH: TESTBENCH_TEMPLATE,
    BlockKind.FORMAL: FORMAL_TEMPLATE,
}


def builtin_definitions() -> list[BlockDefinition]:
    return [builtin_definition(kind) for kind in BUILTIN_KINDS]


def builtin_definition(kind: BlockKind) -> BlockDefinition:
    """The definition for a built-in ``kind``, with its starting template."""
    block_id, label = BUILTIN_KINDS[kind]
    return BlockDefinition(
        id=block_id,
        label=label,
        kind=kind,
        category=BUILTIN_CATEGORY,
        source=TEMPLATES.get(kind, ""),
    )


class BlockLibrary:
    """Every block definition the editor knows about, keyed by id."""

    def __init__(self) -> None:
        self._definitions: dict[str, BlockDefinition] = {}

    def __len__(self) -> int:
        return len(self._definitions)

    def __iter__(self) -> Iterator[BlockDefinition]:
        return iter(self._definitions.values())

    def __contains__(self, block_id: str) -> bool:
        return block_id in self._definitions

    @property
    def definitions(self) -> Mapping[str, BlockDefinition]:
        return dict(self._definitions)

    def register(self, definition: BlockDefinition) -> None:
        if definition.id in self._definitions:
            log.debug("block %r redefined, keeping the newer one", definition.id)
        self._definitions[definition.id] = definition

    def get(self, block_id: str) -> BlockDefinition | None:
        return self._definitions.get(block_id)

    def require(self, block_id: str) -> BlockDefinition:
        definition = self.get(block_id)
        if definition is None:
            raise KeyError(f"no block definition {block_id!r}")
        return definition

    # --- loading -----------------------------------------------------------

    def load_file(self, path: Path) -> BlockDefinition:
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, Mapping):
            raise BlockDefinitionError(f"{path} is not a yaml mapping")

        definition = BlockDefinition.from_dict(data, source_path=str(path))
        self.register(definition)
        return definition

    def load_directory(self, directory: Path) -> int:
        """Load every definition under ``directory``; returns how many.

        A broken file is logged and skipped rather than taken as fatal: one bad
        block in a user's library must not stop the editor from starting.
        """
        if not directory.is_dir():
            log.debug("no block directory at %s", directory)
            return 0

        loaded = 0
        for path in sorted(directory.rglob(f"*{SUFFIX}")):
            try:
                self.load_file(path)
            except (BlockDefinitionError, OSError, yaml.YAMLError) as error:
                log.warning("skipping block definition %s: %s", path, error)
                continue
            loaded += 1

        return loaded

    # --- presentation ------------------------------------------------------

    def by_category(self) -> dict[tuple[str, ...], list[BlockDefinition]]:
        """Definitions grouped by category path, for building the Insert menu.

        Uncategorised blocks collect under a single empty path, which the menu
        renders at the top level.
        """
        grouped: dict[tuple[str, ...], list[BlockDefinition]] = {}
        for definition in self._definitions.values():
            grouped.setdefault(tuple(definition.category), []).append(definition)

        for definitions in grouped.values():
            definitions.sort(key=lambda d: d.label)

        return dict(sorted(grouped.items()))

    def of_kind(self, kind: BlockKind) -> list[BlockDefinition]:
        return [d for d in self._definitions.values() if d.kind is kind]


def load_library(extra_directories: Iterable[Path] = ()) -> BlockLibrary:
    """The built-in definitions, then the shipped ones, then ``extra``.

    Later registrations win, so the directories are loaded furthest-first and
    a project's block shadows the shared one of the same id.
    """
    library = BlockLibrary()
    for definition in builtin_definitions():
        library.register(definition)
    library.load_directory(BUILTIN_DIR)
    for directory in extra_directories:
        library.load_directory(Path(directory))
    return library


_library: BlockLibrary | None = None


def library() -> BlockLibrary:
    """The process-wide library, loaded on first use."""
    global _library
    if _library is None:
        _library = load_library()
        log.debug("loaded %d block definitions", len(_library))
    return _library


def reload_library(design=None) -> BlockLibrary:
    """Rebuild the library, picking up blocks written since it was loaded.

    ``design`` supplies the project directory to search; without one only the
    shared blocks are seen.
    """
    global _library
    _library = load_library(reversed(block_directories(design)))
    log.debug("reloaded %d block definitions", len(_library))
    return _library
