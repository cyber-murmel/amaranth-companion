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
"""

import json
from logging import getLogger
from typing import Iterable, Mapping, TYPE_CHECKING

from .element import Edge, Node, Socket, SocketType
from .element.graphics_item import NodeContentWidget

if TYPE_CHECKING:
    from .module import Module

log = getLogger(__name__)

FORMAT_VERSION = 2
INDENT = 2

#: The socket layout that format version 1 gave every node implicitly.
LEGACY_INPUTS = {"a": SocketType.BIT, "b": SocketType.BIT}
LEGACY_OUTPUTS = {"o": SocketType.BIT}


# --- json text -------------------------------------------------------------


def dumps(data: dict) -> str:
    return json.dumps(data, indent=INDENT)


def loads(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"expected a json object, got {type(data).__name__}")
    return data


# --- module -> data --------------------------------------------------------


def socket_types_to_dict(sockets: Mapping[str, Socket]) -> dict[str, str]:
    return {name: socket.type.name for name, socket in sockets.items()}


def node_to_dict(node: Node) -> dict:
    return {
        "title": node.title,
        "pos": list(node.pos),
        "text": node.text,
        "inputs": socket_types_to_dict(node.input_sockets),
        "outputs": socket_types_to_dict(node.output_sockets),
    }


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


def module_to_dict(module: "Module") -> dict:
    return {
        "version": FORMAT_VERSION,
        "scene": {
            "width": module.scene.scene_width,
            "height": module.scene.scene_height,
        },
        "nodes": nodes_to_dict(module.nodes.values()),
        "edges": [edge_to_dict(edge) for edge in module.edges],
    }


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


def socket_types_from_dict(
    data: Mapping[str, str] | None, fallback: Mapping[str, SocketType]
) -> dict[str, SocketType]:
    if data is None:
        return dict(fallback)
    return {name: SocketType[type_name] for name, type_name in data.items()}


def node_from_dict(module: "Module", data: Mapping, uuid: str | None = None) -> Node:
    node = Node(
        module,
        NodeContentWidget(text=data.get("text", "")),
        socket_types_from_dict(data.get("inputs"), LEGACY_INPUTS),
        socket_types_from_dict(data.get("outputs"), LEGACY_OUTPUTS),
        title=data.get("title", ""),
        uuid=uuid,
    )
    node.pos = tuple(data["pos"])
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
    return sockets.get(endpoint["socket_name"])


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
