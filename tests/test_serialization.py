import json
import os

import pytest

from amaranth_companion.module import Module
from amaranth_companion.module.element import Edge, SocketType
from amaranth_companion.module.serialization import (
    FORMAT_VERSION,
    LEGACY_INPUTS,
    LEGACY_OUTPUTS,
    dumps,
    internal_edges,
    loads,
    selection_to_dict,
)

from conftest import DATA_DIR


def test_round_trip_preserves_everything(chain):
    module, nodes = chain
    nodes[0].text = "some content\nover two lines"
    nodes[0].title = "renamed"

    data = module.to_dict()
    restored = Module()
    restored.load(data)

    assert restored.to_dict() == data


def test_round_trip_preserves_custom_socket_layout(module, make_node):
    """The whole point of format 2: sockets used to be reset on every load."""
    make_node(
        module,
        title="custom",
        inputs={"enable": SocketType.BIT, "data": SocketType.BIT},
        outputs={"result": SocketType.BIT},
    )

    data = module.to_dict()
    restored = Module()
    restored.load(data)

    node = next(iter(restored.nodes.values()))
    assert list(node.input_sockets) == ["enable", "data"]
    assert list(node.output_sockets) == ["result"]
    assert restored.to_dict() == data


def test_to_dict_reports_the_current_format_version(module):
    assert module.to_dict()["version"] == FORMAT_VERSION


def test_load_replaces_previous_content(chain, make_node):
    module, _ = chain
    other = Module()
    make_node(other, title="only")

    module.load(other.to_dict())

    assert [node.title for node in module.nodes.values()] == ["only"]
    assert list(module.edges) == []


def test_format_1_payload_falls_back_to_the_hardcoded_sockets(module):
    """Files written before sockets were persisted must still open."""
    legacy = {
        "version": 1,
        "nodes": {"deadbeef": {"pos": [20.0, 40.0], "text": "kept"}},
        "edges": [],
    }

    module.load(legacy)

    node = module.nodes["deadbeef"]
    assert list(node.input_sockets) == list(LEGACY_INPUTS)
    assert list(node.output_sockets) == list(LEGACY_OUTPUTS)
    assert node.text == "kept"
    assert node.pos == (20.0, 40.0)


def test_load_drops_an_edge_with_an_unknown_endpoint(module, caplog):
    data = {
        "version": FORMAT_VERSION,
        "nodes": {},
        "edges": [
            {
                "start": {"node_uuid": "missing", "socket_name": "o"},
                "end": {"node_uuid": "gone", "socket_name": "a"},
            }
        ],
    }

    module.load(data)

    assert list(module.edges) == []
    assert "dropping edge" in caplog.text


def test_internal_edges_keeps_only_fully_selected_edges(chain):
    module, nodes = chain

    kept = internal_edges(nodes[:2], module.edges)

    assert len(kept) == 1
    assert kept[0].start_socket.node is nodes[0]


def test_selection_to_dict_omits_half_selected_edges(chain):
    module, nodes = chain

    payload = selection_to_dict(nodes[:2], module.edges)

    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1


def test_paste_remaps_uuids_and_keeps_the_originals(chain):
    module, nodes = chain
    payload = selection_to_dict(nodes, module.edges)
    original_uuids = set(module.nodes)

    mapping = module.paste(payload)

    assert len(module.nodes) == 6
    assert len(list(module.edges)) == 4
    assert set(mapping.values()).isdisjoint(original_uuids)
    assert original_uuids <= set(module.nodes)


def test_paste_reproduces_the_internal_edges(chain):
    module, nodes = chain
    payload = selection_to_dict(nodes[:2], module.edges)

    mapping = module.paste(payload)

    pasted = {module.nodes[uuid] for uuid in mapping.values()}
    pasted_edges = [
        edge
        for edge in module.edges
        if edge.start_socket.node in pasted and edge.end_socket.node in pasted
    ]
    assert len(pasted_edges) == 1


def test_loads_rejects_a_non_object_payload():
    with pytest.raises(ValueError):
        loads("[1, 2, 3]")


def test_dumps_is_valid_json(chain):
    module, _ = chain

    assert loads(dumps(module.to_dict())) == module.to_dict()


def test_save_and_from_file(chain, tmp_path):
    module, _ = chain
    path = tmp_path / "saved.json"

    module.save(path)

    assert module.path == str(path)
    reopened = Module.from_file(path)
    assert reopened.to_dict() == module.to_dict()
    assert reopened.path == str(path)


def test_save_without_a_path_is_an_error(module):
    with pytest.raises(ValueError):
        module.save()


def test_save_reuses_the_stored_path(chain, tmp_path):
    module, nodes = chain
    path = tmp_path / "saved.json"
    module.save(path)

    nodes[0].title = "changed"
    module.save()

    assert json.loads(path.read_text())["nodes"][nodes[0].uuid]["title"] == "changed"


def test_from_file_starts_history_at_the_loaded_state(chain, tmp_path):
    module, _ = chain
    path = tmp_path / "saved.json"
    module.save(path)

    reopened = Module.from_file(path)

    assert not reopened.history.is_undoable
    assert len(reopened.nodes) == 3


def test_example_fixture_loads(qapp):
    module = Module.from_file(os.path.join(DATA_DIR, "example.json"))

    assert len(module.nodes) == 3
    assert len(list(module.edges)) == 2
    titles = sorted(node.title for node in module.nodes.values())
    assert titles == ["middle", "sink", "source"]
    sink = next(n for n in module.nodes.values() if n.title == "sink")
    assert list(sink.input_sockets) == ["in", "enable"]


def test_example_fixture_is_in_the_current_format(qapp):
    path = os.path.join(DATA_DIR, "example.json")

    assert json.loads(open(path).read())["version"] == FORMAT_VERSION
