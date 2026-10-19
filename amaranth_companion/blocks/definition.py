"""What a *kind of block* is, as opposed to one placed on a canvas.

A :class:`BlockDefinition` is the reusable thing: "an AND gate", "a counter".
A :class:`~amaranth_companion.module.element.Node` is one instance of it, with
its own position, parameter values and edges -- the same split GNU Radio
Companion makes between a block definition and a block in a flowgraph.

Port roles come from a **name suffix**, so the Amaranth source stays the single
source of truth for a block's interface:

====================  ==============================================
``<name>_in``         input signal port
``<name>_out``        output signal port
``<name>_param``      parameter port, an elaboration-time Python value
anything else         internal to the block, not a port
====================  ==============================================

That convention is not invented here: ``Blinker`` in the amaranth-examples
repository already declares ``self.blink_out = Signal(1)`` alongside an
internal ``self.counter``.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

#: suffix -> role, longest first so that ``_param`` is tested before ``_in``
PORT_SUFFIXES = ("_param", "_out", "_in")


class BlockKind(Enum):
    """What a block *is*, which decides how it is edited and generated."""

    #: Amaranth source; its ports are introspected from the code
    CODE = "code"
    #: a port of the enclosing hierarchical block. Which way it faces is the
    #: kind, not something read out of its name: a port is placed as an input,
    #: an output or a parameter, and renaming it cannot move it.
    PORT_IN = "port_in"
    PORT_OUT = "port_out"
    PORT_PARAM = "port_param"
    #: declares and sets a value, exposed as a parameter output
    VARIABLE = "variable"
    #: contains a child graph; its ports are the port blocks inside it
    HIERARCHICAL = "hierarchical"
    #: a simulation testbench over the implementation beside it
    TESTBENCH = "testbench"
    #: formal properties over the implementation beside it
    FORMAL = "formal"
    #: binds a design port to an IO on the board being built for
    RESOURCE = "resource"

    @property
    def has_child_module(self) -> bool:
        return self is BlockKind.HIERARCHICAL

    @property
    def port_role(self) -> "PortRole | None":
        """The role this kind exposes, or ``None`` if it is not a port."""
        return PORT_KINDS.get(self)

    @property
    def is_port(self) -> bool:
        return self in PORT_KINDS


class PortRole(Enum):
    """The role a port name's suffix puts it in."""

    INPUT = "in"
    OUTPUT = "out"
    PARAM = "param"

    @property
    def suffix(self) -> str:
        return f"_{self.value}"

    @property
    def is_param(self) -> bool:
        return self is PortRole.PARAM

    @property
    def is_output(self) -> bool:
        return self is PortRole.OUTPUT


#: the three kinds that stand for a port, and what each one means. This is
#: the whole of the role mapping: nothing else decides which way a port faces.
PORT_KINDS: dict["BlockKind", "PortRole"] = {}


def port_name(name: str, role: "PortRole") -> str:
    """The full signal name for a port called ``name`` in ``role``.

    A port node stores a bare name; the suffix is *generated* from its kind.
    That way one spelling reaches the socket, the generated Amaranth and the
    label, and there is nothing to keep in sync.
    """
    cleaned = name.strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith(role.suffix) else f"{cleaned}{role.suffix}"


def bare_port_name(name: str, role: "PortRole | None" = None) -> str:
    """``"a_in"`` -> ``"a"``; what a port node stores and shows."""
    split = split_port_name(name)
    if split is None:
        return name.strip()
    label, found = split
    return label if role is None or found is role else name.strip()


def split_port_name(name: str) -> tuple[str, PortRole] | None:
    """Split ``"blink_out"`` into ``("blink", PortRole.OUTPUT)``.

    Returns ``None`` for a name with no port suffix, which is how internal
    signals such as ``counter`` are kept off the block's interface. A name that
    is *only* a suffix (``"_in"``) has no label left and is rejected too.
    """
    for role in (PortRole.PARAM, PortRole.OUTPUT, PortRole.INPUT):
        if name.endswith(role.suffix) and len(name) > len(role.suffix):
            return name[: -len(role.suffix)], role
    return None


@dataclass(frozen=True)
class Shape:
    """An Amaranth signal shape, as plain data.

    Mirrors ``amaranth.hdl.Shape`` without importing it: this module is loaded
    by the editor, which must stay usable when a block's code -- or Amaranth
    itself -- cannot be imported.
    """

    width: int = 1
    signed: bool = False

    def __str__(self) -> str:
        return f"{'s' if self.signed else 'u'}{self.width}"

    def to_dict(self) -> dict:
        return {"width": self.width, "signed": self.signed}

    @classmethod
    def from_dict(cls, data: Mapping | None) -> "Shape":
        if not data:
            return cls()
        return cls(width=int(data.get("width", 1)), signed=bool(data.get("signed")))


@dataclass(frozen=True)
class PortSpec:
    """One port of a block: what :meth:`Node.refresh_ports` builds a socket from.

    ``name`` is the full signal name including its suffix, because that is what
    generated code has to emit; ``label`` is the stripped form shown on canvas.
    """

    name: str
    role: PortRole
    shape: Shape = field(default_factory=Shape)
    #: parameter ports only: the value to use when nothing is connected
    default: Any = None

    @property
    def label(self) -> str:
        split = split_port_name(self.name)
        return split[0] if split else self.name

    @property
    def is_param(self) -> bool:
        return self.role.is_param

    @property
    def is_output(self) -> bool:
        return self.role.is_output

    def to_dict(self) -> dict:
        data: dict = {"name": self.name, "role": self.role.value}
        if not self.is_param:
            data["shape"] = self.shape.to_dict()
        elif self.default is not None:
            data["default"] = self.default
        return data

    @classmethod
    def from_dict(cls, data: Mapping) -> "PortSpec":
        return cls(
            name=data["name"],
            role=PortRole(data["role"]),
            shape=Shape.from_dict(data.get("shape")),
            default=data.get("default"),
        )

    @classmethod
    def from_name(cls, name: str, **kwargs) -> "PortSpec | None":
        """Build a spec from a suffixed name, or ``None`` if it is internal."""
        split = split_port_name(name)
        if split is None:
            return None
        return cls(name=name, role=split[1], **kwargs)


@dataclass(frozen=True)
class ParamSpec:
    """A declared parameter of a block, with the default from its source."""

    name: str
    default: Any = None
    #: free-form type hint, used by the editor to pick an input widget
    dtype: str = "int"

    def to_dict(self) -> dict:
        return {"name": self.name, "default": self.default, "dtype": self.dtype}

    @classmethod
    def from_dict(cls, name: str, data: Mapping | Any) -> "ParamSpec":
        if not isinstance(data, Mapping):  # `width_param: 4` shorthand
            return cls(name=name, default=data)
        return cls(
            name=name,
            default=data.get("default"),
            dtype=data.get("dtype", "int"),
        )


class BlockDefinitionError(ValueError):
    """A definition file is malformed."""


@dataclass(frozen=True)
class BlockDefinition:
    """A reusable kind of block, loaded from a ``*.block.yml`` file."""

    id: str
    label: str
    kind: BlockKind
    category: Sequence[str] = ()
    #: ``CODE`` blocks: the Amaranth source
    source: str = ""
    #: ``HIERARCHICAL`` blocks: the file holding the child graph, named
    #: relative to this definition. An ordinary module, the same format a
    #: design is saved in -- so a block's insides can be opened, diffed and
    #: edited like anything else, and so that writing one out is just saving.
    implementation: str | None = None
    #: ``HIERARCHICAL`` blocks: an svg drawn on the node, named relative to
    #: the definition file so a block directory stays self-contained
    icon: str | None = None
    #: the file this definition was loaded from; built-in kinds have none
    source_path: str | None = None
    params: Mapping[str, ParamSpec] = field(default_factory=dict)
    #: ports declared up front; ``CODE`` blocks leave this empty and introspect
    ports: Sequence[PortSpec] = ()
    doc: str = ""

    @property
    def default_params(self) -> dict[str, Any]:
        return {name: spec.default for name, spec in self.params.items()}

    @property
    def implementation_path(self) -> Path | None:
        """The module file this block is made of, if it has one."""
        return self._relative(self.implementation)

    def load_implementation(self) -> dict:
        """Read the module this block is made of.

        Returns an empty module rather than raising: a definition whose file
        has gone missing should give an empty block the user can see is
        wrong, not stop the library from loading.
        """
        import json

        path = self.implementation_path
        if path is None:
            return {}

        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise BlockDefinitionError(
                f"{self.id}: cannot read {self.implementation!r}: {error}"
            ) from error

    def _relative(self, name: str | None) -> Path | None:
        """``name`` resolved against the definition file that declared it."""
        if not name:
            return None

        candidate = Path(name)
        if not candidate.is_absolute():
            if self.source_path is None:
                return None
            candidate = Path(self.source_path).parent / candidate

        return candidate if candidate.is_file() else None

    @property
    def icon_path(self) -> str | None:
        """The icon as a path on disk, or ``None`` if there is no usable one.

        Resolved against the definition file rather than the working
        directory, so moving a block directory moves its icons with it.
        """
        resolved = self._relative(self.icon)
        return str(resolved) if resolved is not None else None

    @classmethod
    def from_dict(
        cls, data: Mapping, *, source_path: str | None = None
    ) -> "BlockDefinition":
        where = f" in {source_path}" if source_path else ""

        for required in ("id", "kind"):
            if required not in data:
                raise BlockDefinitionError(f"missing {required!r}{where}")

        try:
            kind = BlockKind(data["kind"])
        except ValueError as error:
            raise BlockDefinitionError(
                f"unknown kind {data['kind']!r}{where}"
            ) from error

        category = data.get("category", ())
        if isinstance(category, str):
            category = (category,)

        return cls(
            id=data["id"],
            label=data.get("label", data["id"]),
            kind=kind,
            category=tuple(category),
            source=data.get("source", ""),
            implementation=data.get("implementation"),
            icon=data.get("icon"),
            params={
                name: ParamSpec.from_dict(name, value)
                for name, value in (data.get("params") or {}).items()
            },
            ports=tuple(PortSpec.from_dict(port) for port in data.get("ports", ())),
            doc=data.get("doc", ""),
            source_path=source_path,
        )


PORT_KINDS.update(
    {
        BlockKind.PORT_IN: PortRole.INPUT,
        BlockKind.PORT_OUT: PortRole.OUTPUT,
        BlockKind.PORT_PARAM: PortRole.PARAM,
    }
)
