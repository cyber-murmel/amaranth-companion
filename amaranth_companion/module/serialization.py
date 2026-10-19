"""Conversion between modules and plain data.

Everything that needs to turn a module (or part of one) into data and back goes
through here: saving to a file, the clipboard, and the undo history. Keeping the
single reader in :func:`load_into` is what stops those three from drifting
apart, as they previously did.

Format history
--------------
1. ``nodes`` keyed by uuid, ``pos`` and ``text`` per node. Socket layout and
   node titles were *not* stored, so every load reset them.
2. adds ``title``, ``inputs`` and ``outputs`` per node. Files written by
   version 1 still load: the socket layout falls back to the one that version
   hardcoded.
3. blocks. A node gains ``block_id`` (which definition it instantiates),
   ``params``, a ``ports`` list replacing the ``inputs``/``outputs`` maps,
   ``child`` -- a nested module, which is what makes a design hierarchical --
   and an optional ``size``, present only on a node the user has resized.
   Ports carry a role and a shape rather than the single ``BIT`` type.
   Versions 1 and 2 still load: a node with no ``block_id`` is a bare code
   block, and the old ``BIT`` type becomes an unsigned 1-bit signal.
4. explicit port kinds. A port block used to be one ``builtin.port`` whose
   *name* said which way it faced -- ``a_in`` was an input because of the
   suffix, so renaming it moved the port. There are now three kinds, and a
   port node stores a bare name. Version 3 files still load: the suffix on
   the old name picks the kind, and is then stripped off.
"""

import json
from logging import getLogger
from typing import Iterable, Mapping, TYPE_CHECKING

from ..blocks.definition import (
    BlockKind,
    PortRole,
    PortSpec,
    Shape,
    bare_port_name,
    split_port_name,
)
from ..blocks.library import library
from .element import Edge, Node, Socket
from .element.graphics_item import content_widget_for

if TYPE_CHECKING:
    from .module import Module

log = getLogger(__name__)

FORMAT_VERSION = 4
INDENT = 2

#: The socket layout that format version 1 gave every node implicitly.
LEGACY_INPUTS = ("a", "b")
LEGACY_OUTPUTS = ("o",)


# --- json text -------------------------------------------------------------


def dumps(data: dict) -> str:
    return json.dumps(data, indent=INDENT)


def loads(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"expected a json object, got {type(data).__name__}")
    return data


# --- module -> data --------------------------------------------------------


def default_size(node: Node) -> tuple[int, int]:
    """The size this node would get if nobody had resized it."""
    from .element.graphics_item.node_graphics_item import DEFAULT_SIZE, SIZE_BY_KIND

    return SIZE_BY_KIND.get(node.kind, DEFAULT_SIZE)


def ports_to_list(node: Node) -> list[dict]:
    return [socket.to_spec().to_dict() for socket in node.sockets]


def node_to_dict(node: Node) -> dict:
    data: dict = {
        "title": node.title,
        "pos": list(node.pos),
        "text": node.text,
        "kind": node.kind.value,
        "ports": ports_to_list(node),
    }

    # only when the user has dragged it, so an untouched design does not
    # carry a size on every node
    if node.size != default_size(node):
        data["size"] = list(node.size)

    if node.block_id is not None:
        data["block_id"] = node.block_id
    if node.params:
        data["params"] = dict(node.params)
    if node.child_module is not None:
        data["child"] = module_to_dict(node.child_module, versioned=False)

    return data


def edge_to_dict(edge: Edge) -> dict:
    return {
        "start": {
            "node_uuid": edge.start_socket.node.uuid,
            "socket_name": edge.start_socket.name,
        },
        "end": {
            "node_uuid": edge.end_socket.node.uuid,
            "socket_name": edge.end_socket.name,
        },
    }


def nodes_to_dict(nodes: Iterable[Node]) -> dict[str, dict]:
    return {node.uuid: node_to_dict(node) for node in nodes}


def module_to_dict(module: "Module", *, versioned: bool = True) -> dict:
    """``module`` as plain data.

    ``versioned=False`` for a module nested inside a node: the version belongs
    to the document as a whole, not to every level of its hierarchy.
    """
    data: dict = {
        "nodes": nodes_to_dict(module.nodes.values()),
        "edges": [edge_to_dict(edge) for edge in module.edges],
    }

    if versioned:
        data = {
            "version": FORMAT_VERSION,
            "scene": {
                "width": module.scene.scene_width,
                "height": module.scene.scene_height,
            },
            **data,
        }

    return data


def internal_edges(nodes: Iterable[Node], edges: Iterable[Edge]) -> list[Edge]:
    """The edges with *both* endpoints among ``nodes``.

    An edge with one endpoint outside the selection cannot be reproduced on
    paste, so it is not part of the payload.
    """
    uuids = {node.uuid for node in nodes}
    return [
        edge
        for edge in edges
        if edge.start_socket.node.uuid in uuids and edge.end_socket.node.uuid in uuids
    ]


def selection_to_dict(nodes: Iterable[Node], edges: Iterable[Edge]) -> dict:
    """A clipboard payload, in the same node/edge shape as a saved module."""
    nodes = list(nodes)
    return {
        "version": FORMAT_VERSION,
        "nodes": nodes_to_dict(nodes),
        "edges": [edge_to_dict(edge) for edge in internal_edges(nodes, edges)],
    }


# --- data -> module --------------------------------------------------------


def ports_from_dict(data: Mapping) -> list[PortSpec]:
    """The node's ports, migrating the pre-v3 ``inputs``/``outputs`` maps.

    Version 2 stored ``{"a": "BIT"}``; version 1 stored nothing at all and
    relied on every node having the same hardcoded layout.
    """
    if "ports" in data:
        return [PortSpec.from_dict(port) for port in data["ports"]]

    legacy_inputs = data.get("inputs")
    legacy_outputs = data.get("outputs")
    if legacy_inputs is None and legacy_outputs is None:
        legacy_inputs = {name: "BIT" for name in LEGACY_INPUTS}
        legacy_outputs = {name: "BIT" for name in LEGACY_OUTPUTS}

    specs: list[PortSpec] = []
    for names, role in (
        (legacy_inputs or {}, PortRole.INPUT),
        (legacy_outputs or {}, PortRole.OUTPUT),
    ):
        for name in names:
            # pre-v3 names carried no suffix, so give them the one their side
            # implies; everything downstream keys off the suffix
            suffixed = name if name.endswith(role.suffix) else f"{name}{role.suffix}"
            specs.append(PortSpec(name=suffixed, role=role, shape=Shape()))

    return specs


#: the one block id that became three
LEGACY_PORT_BLOCK = "builtin.port"

#: which kind a format-3 port node turns into, by the suffix it carried
PORT_KIND_FOR_ROLE = {
    PortRole.INPUT: BlockKind.PORT_IN,
    PortRole.OUTPUT: BlockKind.PORT_OUT,
    PortRole.PARAM: BlockKind.PORT_PARAM,
}


def migrate_port_node(data: Mapping) -> dict:
    """Turn a format-3 ``builtin.port`` node into one of the three kinds.

    The role used to live in the name's suffix, which is exactly what made it
    worth changing; reading it back out is a one-off, and the name is stored
    bare afterwards.
    """
    if data.get("block_id") != LEGACY_PORT_BLOCK:
        return dict(data)

    split = split_port_name(data.get("text", ""))
    role = split[1] if split else PortRole.INPUT
    kind = PORT_KIND_FOR_ROLE[role]

    migrated = dict(data)
    migrated["block_id"] = f"builtin.{kind.value}"
    migrated["kind"] = kind.value
    migrated["text"] = bare_port_name(data.get("text", ""), role)
    return migrated


def node_from_dict(module: "Module", data: Mapping, uuid: str | None = None) -> Node:
    data = migrate_port_node(data)
    block_id = data.get("block_id")
    definition = library().get(block_id) if block_id else None
    if block_id and definition is None:
        log.warning("node %r refers to unknown block %r", uuid, block_id)

    node = Node(
        module,
        definition=definition,
        ports=ports_from_dict(data),
        params=data.get("params"),
        content_widget=content_widget_for(definition, text=data.get("text", "")),
        title=data.get("title", ""),
        uuid=uuid,
    )
    node.pos = tuple(data["pos"])
    if "size" in data:
        node.size = tuple(data["size"])

    child = data.get("child")
    if child is not None:
        from .module import Module as ModuleType

        node.child_module = ModuleType()
        node.child_module.owner = node
        load_into(node.child_module, child, clear=False, remap_uuids=False)

    return node


def _resolve_socket(
    module: "Module",
    endpoint: Mapping,
    uuid_map: Mapping[str, str],
    *,
    outgoing: bool,
) -> Socket | None:
    uuid = uuid_map.get(endpoint["node_uuid"])
    if uuid is None:
        return None

    node = module.nodes.get(uuid)
    if node is None:
        return None

    sockets = node.output_sockets if outgoing else node.input_sockets
    socket = sockets.get(endpoint["socket_name"])
    if socket is not None:
        return socket

    # pre-v3 names had no suffix; the migration added one, so look again
    for candidate in sockets.values():
        if candidate.label == endpoint["socket_name"]:
            return candidate
    return None


def edge_from_dict(
    module: "Module", data: Mapping, uuid_map: Mapping[str, str]
) -> Edge | None:
    """Rebuild an edge, or return ``None`` if either endpoint is missing."""
    start = _resolve_socket(module, data["start"], uuid_map, outgoing=True)
    end = _resolve_socket(module, data["end"], uuid_map, outgoing=False)

    if start is None or end is None:
        log.warning(
            "dropping edge with unresolved endpoint: %s -> %s",
            data["start"],
            data["end"],
        )
        return None

    return Edge(start, end)


def load_into(
    module: "Module",
    data: Mapping,
    *,
    clear: bool,
    remap_uuids: bool,
) -> dict[str, str]:
    """Rebuild nodes and edges from ``data`` inside ``module``.

    The single reader for all three sources:

    * opening a file, and restoring an undo snapshot -- ``clear=True,
      remap_uuids=False``, so uuids and therefore edge references are preserved.
    * pasting from the clipboard -- ``clear=False, remap_uuids=True``, so the
      pasted nodes are fresh objects that cannot collide with what is already
      in the module.

    Returns the mapping from the uuids in ``data`` to the uuids in ``module``
    (the identity mapping unless ``remap_uuids``).
    """
    if clear:
        module.clear()

    uuid_map: dict[str, str] = {}
    for uuid, node_data in data.get("nodes", {}).items():
        node = node_from_dict(module, node_data, None if remap_uuids else uuid)
        uuid_map[uuid] = node.uuid
        module.add_node(node)

    for edge_data in data.get("edges", []):
        edge = edge_from_dict(module, edge_data, uuid_map)
        if edge is not None:
            module.add_edge(edge)

    return uuid_map
