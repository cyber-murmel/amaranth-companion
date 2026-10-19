"""Turning a :class:`BlockDefinition` into a node on a canvas.

This is where a definition stops being data and becomes something the user can
drag around. For a code block that means running the source to find its ports;
for a hierarchical block it means building the child graph the definition
describes, and then reading the block's own interface back off the port blocks
inside it.

The two directions matter and are easy to confuse:

* a **code** block's ports come from its Amaranth source
* a **hierarchical** block's ports come from the port blocks in its child graph
* a **port** block's single socket faces the *opposite* way to its name, since
  an ``a_in`` port of a block is where a value arrives from, seen from inside
"""

from logging import getLogger
from typing import Any, Mapping, Sequence, TYPE_CHECKING

from dataclasses import dataclass, field, replace

from ..blocks.definition import (
    BlockDefinition,
    BlockKind,
    PortRole,
    PortSpec,
    Shape,
    port_name,
)
from ..blocks.introspect import introspect_cached
from ..blocks.library import builtin_definition, library
from .element import Edge, Node
from .element.graphics_item import content_widget_for
from .naming import disambiguate
from .parameters import resolve_params, variable_port_name

if TYPE_CHECKING:
    from .module import Module

log = getLogger(__name__)

#: where a newly inserted node lands when nothing says otherwise
DEFAULT_POSITION = (0.0, 0.0)


@dataclass(frozen=True)
class PortResult:
    """The ports a node should have, and why it could not work them out."""

    ports: list[PortSpec] = field(default_factory=list)
    error: str = ""
    #: line in the block's own source the failure came from, if any
    line: int | None = None


# --- ports ------------------------------------------------------------------


def code_ports(source: str, params: Mapping[str, Any] | None = None) -> PortResult:
    """The ports a code block declares, and the error if it could not be read."""
    result = introspect_cached(source, params)
    if not result.ok:
        log.debug("introspection failed: %s", result.summary)
        return PortResult([], result.error, result.line)
    return PortResult(list(result.ports))


def hierarchical_ports(child: "Module") -> list[PortSpec]:
    """A hierarchical block's interface: the port blocks inside it.

    Ordered inputs first, then parameters, then outputs, and within each group
    by vertical position -- so dragging a port block up the canvas moves that
    port up the parent, which is the only ordering rule a user can see.
    """
    specs: list[tuple[int, float, PortSpec]] = []
    group = {PortRole.INPUT: 0, PortRole.PARAM: 1, PortRole.OUTPUT: 2}

    for node in child.nodes.values():
        if not node.kind.is_port:
            continue
        spec = port_block_spec(node)
        if spec is not None:
            specs.append((group[spec.role], node.pos[1], spec))

    return [spec for _group, _y, spec in sorted(specs, key=lambda item: item[:2])]


def port_block_spec(node: Node) -> PortSpec | None:
    """The port a port block stands for.

    The *role* is the block's kind -- an input port is an input however it is
    named. The *name* is whatever the user typed, with the suffix added for
    them. The *shape* comes from whatever the block is wired to inside the
    implementation: an ``a`` feeding an 8-bit signal is an 8-bit port, and
    making the user restate that would be a second place for it to be wrong.
    """
    role = node.kind.port_role
    if role is None:
        return None

    name = port_name(node.text.strip(), role)
    if not name:
        return None

    peer = connected_shape(node)
    spec = PortSpec(name=name, role=role)
    return replace(spec, shape=peer) if peer is not None else spec


def connected_shape(node: Node) -> Shape | None:
    """The shape of the signal on the other end of a port block's edge."""
    for socket in node.sockets:
        if socket.is_param:
            continue
        for edge in socket.edges:
            other = (
                edge.end_socket if edge.start_socket is socket else edge.start_socket
            )
            if other is not None and other is not socket:
                return other.shape
    return None


def ports_for(
    definition: BlockDefinition,
    params: Mapping[str, Any] | None = None,
    child: "Module | None" = None,
    text: str = "",
    node_variable_port: str = "value_param",
) -> PortResult:
    """The ports a node should have, and any error to show on it."""
    if definition.kind is BlockKind.CODE:
        return code_ports(text or definition.source, params)

    if definition.kind is BlockKind.HIERARCHICAL and child is not None:
        return PortResult(hierarchical_ports(child))

    if definition.kind.is_port:
        name = port_name(text.strip(), definition.kind.port_role)
        return PortResult(
            [PortSpec(name=name, role=definition.kind.port_role)] if name else [],
            "" if name else "give this port a name",
        )

    if definition.kind is BlockKind.RESOURCE:
        # the real answer needs the design's platform, which `ports_for` has
        # no way to reach; `refresh_node_ports` settles it
        return PortResult([], "")

    if definition.kind is BlockKind.VARIABLE:
        # a variable hands its value out as a parameter, named after whatever
        # it declares -- the port follows the name the user typed
        return PortResult([PortSpec(name=node_variable_port, role=PortRole.PARAM)])

    return PortResult(list(definition.ports))


# --- instantiation ----------------------------------------------------------


def build_child_module(definition: BlockDefinition) -> "Module | None":
    """Build the graph a hierarchical definition is made of.

    The implementation is an ordinary module file, so this is the same read
    that opens a design -- ``load_into`` is already the single reader for
    files, the clipboard and undo, and adding a second one here is what made
    a block's insides impossible to open or diff.

    ``remap_uuids`` gives every instance fresh identity, so two AND gates in
    one design share nothing.
    """
    if definition.kind is not BlockKind.HIERARCHICAL:
        return None

    from .module import Module as ModuleType
    from .serialization import load_into

    child = ModuleType()
    load_into(child, definition.load_implementation(), clear=False, remap_uuids=True)
    refresh_port_blocks(child)
    return child


def instantiate(
    module: "Module",
    definition: BlockDefinition,
    *,
    params: Mapping[str, Any] | None = None,
    pos: Sequence[float] = DEFAULT_POSITION,
    text: str | None = None,
    title: str = "",
) -> Node:
    """Place a new node for ``definition`` on ``module``.

    Builds the child graph for a hierarchical block and derives the ports, so
    the node arrives on the canvas already wired up to its own definition.
    """
    values = dict(definition.default_params)
    values.update(params or {})

    content = definition.source if text is None else text
    child = build_child_module(definition)

    node = Node(
        module,
        definition=definition,
        params=params,
        content_widget=content_widget_for(definition, text=content),
        title=title or definition.label,
        child_module=child,
    )
    node.pos = tuple(pos)
    if child is not None:
        child.owner = node

    result = ports_for(definition, values, child, content, variable_port_name(node))
    node.refresh_ports(result.ports)
    node.set_error(result.error, result.line)

    module.add_node(node)
    if not node.kind.is_port:
        # a port's title is its name, so it is the name that has to be unique
        disambiguate(module, node)
    return node


def refresh_implementation(module: "Module") -> None:
    """Bring a block's insides up to date, innermost first.

    Code blocks are re-read before the port blocks, because a port block takes
    its width from the code block it is wired to.
    """
    for node in module.nodes.values():
        if node.kind is BlockKind.CODE:
            refresh_node_ports(node)

    refresh_port_blocks(module)


def resource_port(node: Node) -> tuple[PortSpec | None, str]:
    """The single port a resource block exposes, and any complaint about it.

    An output io -- an LED -- is something the design *drives*, so the block
    takes an input. An input io hands a value to the design, so the block
    gives an output. Getting this backwards would wire every design to the
    wrong side of its own pins.

    A problem with the *board* never removes the port. Opening a design on a
    machine that lacks the board's package would otherwise drop every wire
    into a pin, and saving would make that permanent. The block complains and
    keeps what it had; only an empty block has nothing to offer.
    """
    from ..platforms import effective_direction, find, find_io, list_ios, parse_io

    text = node.text.strip()
    if not text:
        return None, "choose an io to bind to"

    io_id, requested = parse_io(text)
    design = node.module.design
    platform = design.platform if design else None

    if not platform:
        return _resource_spec(node, io_id, requested, None), "no board chosen yet"

    if not list_ios(platform):
        # nothing can be checked against a board that will not load
        missing = "is not installed" if find(platform) is None else "could not be read"
        return (
            _resource_spec(node, io_id, requested, None),
            f"this board's support package {missing}",
        )

    spec = find_io(platform, io_id)
    if spec is None:
        return (
            _resource_spec(node, io_id, requested, None),
            f"{io_id!r} is not an io on this board",
        )

    return _resource_spec(node, io_id, requested, spec), ""


def _resource_spec(node: Node, io_id: str, requested, spec) -> PortSpec:
    """The port for a resource block, preferring the one it already has.

    Keeping the existing socket is what preserves its edges across a refresh,
    which matters most in exactly the cases where the board cannot be
    consulted.
    """
    from ..platforms import effective_direction

    direction = effective_direction(spec, requested)
    label = identifier_for(io_id)
    name = f"{label}_in" if direction == "o" else f"{label}_out"

    if spec is None:
        existing = next(iter(node.sockets), None)
        if existing is not None and existing.name == name:
            return existing.to_spec()

    return PortSpec.from_name(name)


def identifier_for(io_id: str) -> str:
    """``"led 0"`` -> ``"led_0"``, so the socket has a usable name."""
    cleaned = "".join(c if c.isalnum() else "_" for c in io_id.strip().lower())
    return cleaned.strip("_") or "io"


def refresh_port_blocks(module: "Module") -> None:
    """Re-derive the shape of every port block in ``module``.

    Run after the implementation is wired, and again whenever a parameter
    changes: a port block's width follows the signal it is attached to, so it
    is only correct once that signal's own width is known.
    """
    for node in module.nodes.values():
        if not node.kind.is_port:
            continue
        spec = port_block_spec(node)
        if spec is not None:
            node.refresh_ports([spec])


def refresh_node_ports(node: Node) -> tuple:
    """Re-derive ``node``'s ports from whatever it is made of.

    The one entry point for "the user changed something, work out the new
    interface", so editing source, renaming a port block and changing a
    parameter all go down the same path.

    Parameters are resolved *first*: a block's port widths depend on them, so
    a variable feeding ``width_param`` has to be read before the code is run.
    """
    if node.kind is BlockKind.RESOURCE:
        spec, error = resource_port(node)
        diff = node.refresh_ports([spec] if spec is not None else [])
        node.set_error(error)
        return diff, node.error

    if node.kind.is_port:
        # port blocks take their width from what they are wired to, which
        # ``ports_for`` cannot see because it is given a name, not a node
        spec = port_block_spec(node)
        diff = node.refresh_ports([spec] if spec is not None else [])
        node.set_error("" if spec else "give this port a name")

        # a port's title *is* its name; carrying two is how `in_a` ended up
        # titling a port called `a_in`
        label = node.definition.label if node.definition else "Port"
        node.title = node.text.strip() or label

        return diff, node.error

    definition = node.definition or builtin_definition(BlockKind.CODE)
    params, param_error = resolve_params(node)

    if node.child_module is not None:
        # the implementation first: this block's interface is read off its
        # port blocks, whose widths follow the code blocks beside them, whose
        # widths follow the parameters resolved just above
        refresh_implementation(node.child_module)

    result = ports_for(
        definition, params, node.child_module, node.text, variable_port_name(node)
    )

    diff = node.refresh_ports(result.ports)
    node.set_error(
        "; ".join(part for part in (param_error, result.error) if part), result.line
    )
    return diff, node.error
