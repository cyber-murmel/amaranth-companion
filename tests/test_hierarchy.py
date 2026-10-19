"""Hierarchical blocks: instantiation, port refresh, navigation and undo."""

import pytest

from amaranth_companion.blocks.definition import BlockKind, PortRole, PortSpec, Shape
from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.module import Module
from amaranth_companion.module.element import Edge
from amaranth_companion.module.instantiate import (
    hierarchical_ports,
    instantiate,
    refresh_node_ports,
)

from conftest import ports


@pytest.fixture
def design(qapp):
    return Design()


@pytest.fixture
def and_gate(design):
    return design.instantiate(library().require("logic.and2"))


def code_node(module):
    return next(n for n in module.nodes.values() if n.kind is BlockKind.CODE)


def port_node(module, name):
    return next(n for n in module.nodes.values() if n.kind.is_port and n.text == name)


# --- instantiation ----------------------------------------------------------


def test_a_gate_exposes_the_ports_its_implementation_declares(and_gate):
    assert [socket.name for socket in and_gate.sockets] == [
        "a_in",
        "b_in",
        "width_param",
        "o_out",
    ]


def test_a_gate_builds_its_child_graph(and_gate):
    child = and_gate.child_module

    assert child is not None
    # three signal ports plus the width parameter
    assert sum(1 for n in child.nodes.values() if n.kind.is_port) == 4
    assert len(list(child.edges)) == 4


def test_a_port_block_faces_the_other_way_inside(and_gate):
    """``a_in`` is an input of the gate, but a source inside it."""
    inside = port_node(and_gate.child_module, "a")

    assert list(inside.output_sockets) == ["a_in"]
    assert not inside.input_sockets


def test_the_inner_code_block_gets_the_gate_parameters(and_gate):
    inner = code_node(and_gate.child_module)

    assert "width_param" in inner.input_sockets
    assert inner.input_sockets["width_param"].is_param


def test_two_gates_share_no_identity(design):
    first = design.instantiate(library().require("logic.and2"))
    second = design.instantiate(library().require("logic.and2"))

    first_uuids = {n.uuid for n in first.child_module.nodes.values()}
    second_uuids = {n.uuid for n in second.child_module.nodes.values()}

    assert first_uuids.isdisjoint(second_uuids)


def test_a_one_input_gate_has_one_input(design):
    inverter = design.instantiate(library().require("logic.not"))

    assert [s.name for s in inverter.sockets] == ["a_in", "width_param", "o_out"]


# --- port refresh -----------------------------------------------------------


def test_renaming_a_port_block_renames_the_parent_port(and_gate):
    port_node(and_gate.child_module, "a").text = "enable"
    refresh_node_ports(and_gate)

    assert [s.name for s in and_gate.sockets] == [
        "enable_in",
        "b_in",
        "width_param",
        "o_out",
    ]


def test_moving_a_port_block_reorders_the_parent_ports(and_gate):
    """Vertical position is the only ordering rule a user can see."""
    a, b = port_node(and_gate.child_module, "a"), port_node(and_gate.child_module, "b")
    a.pos, b.pos = (a.pos[0], 500.0), (b.pos[0], -500.0)
    refresh_node_ports(and_gate)

    assert [s.name for s in and_gate.sockets] == [
        "b_in",
        "a_in",
        "width_param",
        "o_out",
    ]


def test_a_surviving_socket_keeps_its_edges(design, make_node):
    """Editing a block's code must not cost the user their wiring."""
    module = design.current_module
    source = make_node(module, title="source", node_ports=ports("o_out"))
    sink = make_node(module, title="sink", node_ports=ports("a_in", "b_in"))
    module.add_edge(Edge(source.output_sockets["o_out"], sink.input_sockets["a_in"]))

    diff = sink.refresh_ports(ports("a_in", "b_in", "c_in"))

    assert diff.added == ["c_in"]
    assert diff.dropped_edges == 0
    assert len(sink.input_sockets["a_in"].edges) == 1


def test_a_vanished_socket_takes_its_edges(design, make_node):
    module = design.current_module
    source = make_node(module, title="source", node_ports=ports("o_out"))
    sink = make_node(module, title="sink", node_ports=ports("a_in", "b_in"))
    module.add_edge(Edge(source.output_sockets["o_out"], sink.input_sockets["a_in"]))

    diff = sink.refresh_ports(ports("b_in"))

    assert diff.removed == ["a_in"]
    assert diff.dropped_edges == 1
    assert source.output_sockets["o_out"].edges == []


def test_a_width_change_keeps_the_edge(design, make_node):
    module = design.current_module
    source = make_node(module, title="source", node_ports=ports("o_out"))
    sink = make_node(module, title="sink", node_ports=ports("a_in"))
    module.add_edge(Edge(source.output_sockets["o_out"], sink.input_sockets["a_in"]))

    diff = sink.refresh_ports([PortSpec("a_in", PortRole.INPUT, Shape(8, False))])

    assert diff.reshaped == ["a_in"]
    assert diff.dropped_edges == 0
    assert sink.input_sockets["a_in"].shape == Shape(8, False)


def test_a_broken_code_block_reports_rather_than_losing_its_ports(design):
    module = design.current_module
    node = instantiate(
        module,
        library().require("builtin.code"),
        text="class Broken(:\n",
    )

    assert node.error
    assert "SyntaxError" in node.error


def test_refresh_is_idempotent(and_gate):
    before = [s.name for s in and_gate.sockets]
    refresh_node_ports(and_gate)
    refresh_node_ports(and_gate)

    assert [s.name for s in and_gate.sockets] == before


# --- connection rules -------------------------------------------------------


def test_a_parameter_cannot_be_wired_to_a_signal(design, make_node):
    module = design.current_module
    source = make_node(module, title="source", node_ports=ports("o_out"))
    sink = make_node(module, title="sink", node_ports=ports("width_param"))

    accepted = module.add_edge(
        Edge(source.output_sockets["o_out"], sink.input_sockets["width_param"])
    )

    assert not accepted
    assert source.output_sockets["o_out"].edges == []


def test_signals_still_connect(design, make_node):
    module = design.current_module
    source = make_node(module, title="source", node_ports=ports("o_out"))
    sink = make_node(module, title="sink", node_ports=ports("a_in"))

    assert module.add_edge(
        Edge(source.output_sockets["o_out"], sink.input_sockets["a_in"])
    )


def test_a_node_cannot_connect_to_itself(design, make_node):
    module = design.current_module
    node = make_node(module, node_ports=ports("a_in", "o_out"))

    assert not module.add_edge(
        Edge(node.output_sockets["o_out"], node.input_sockets["a_in"])
    )


# --- navigation -------------------------------------------------------------


def test_entering_a_block_shows_its_implementation(design, and_gate):
    assert design.enter(and_gate)

    assert design.current_module is and_gate.child_module
    assert design.breadcrumb == ["untitled", "AND"]


def test_a_plain_block_cannot_be_entered(design, make_node):
    node = make_node(design.current_module)

    assert not design.enter(node)
    assert design.depth == 0


def test_leaving_returns_to_the_level_above(design, and_gate):
    design.enter(and_gate)

    assert design.leave()
    assert design.current_module is design.root
    assert not design.leave()


def test_nested_blocks_stack(design, and_gate):
    """A gate inside a gate: the breadcrumb has to track both levels."""
    design.enter(and_gate)
    inner = design.instantiate(library().require("logic.not"))
    design.enter(inner)

    assert design.depth == 2
    assert design.breadcrumb == ["untitled", "AND", "NOT"]

    design.go_to_depth(1)
    assert design.current_module is and_gate.child_module


def test_the_path_truncates_when_a_block_is_deleted(design, and_gate):
    design.enter(and_gate)
    design.root.remove_node(and_gate)

    assert design.depth == 0
    assert design.current_module is design.root


def test_every_module_in_the_tree_shares_the_history(design, and_gate):
    assert and_gate.child_module.history is design.history
    assert design.root.history is design.history


# --- undo across levels -----------------------------------------------------


def test_an_edit_inside_a_block_is_undoable_from_anywhere(design, and_gate):
    design.history.check_in()
    design.enter(and_gate)

    code_node(design.current_module).title = "edited"
    design.history.check_in()

    design.history.undo()

    assert code_node(design.current_module).title != "edited"


def test_undo_keeps_the_user_where_they_were(design, and_gate):
    design.history.check_in()
    design.enter(and_gate)
    code_node(design.current_module).title = "edited"
    design.history.check_in()

    design.history.undo()

    assert design.depth == 1
    assert design.breadcrumb == ["untitled", "AND"]


# --- serialization of a hierarchy -------------------------------------------


def test_a_hierarchy_round_trips(design, and_gate):
    data = design.to_dict()
    restored = Design()
    restored.load(data)

    assert restored.to_dict() == data


def test_a_restored_child_graph_is_intact(design, and_gate):
    restored = Design()
    restored.load(design.to_dict())

    gate = next(iter(restored.root.nodes.values()))
    assert [s.name for s in gate.sockets] == ["a_in", "b_in", "width_param", "o_out"]
    assert len(gate.child_module.nodes) == 5
    assert len(list(gate.child_module.edges)) == 4


def test_a_restored_hierarchy_is_adopted(design, and_gate):
    restored = Design()
    restored.load(design.to_dict())

    gate = next(iter(restored.root.nodes.values()))
    assert gate.child_module.history is restored.history


def test_two_levels_deep_round_trips(design, and_gate):
    design.enter(and_gate)
    design.instantiate(library().require("logic.not"))
    design.go_to_depth(0)

    data = design.to_dict()
    restored = Design()
    restored.load(data)

    assert restored.to_dict() == data


def test_saving_and_reopening_a_hierarchy(design, and_gate, tmp_path):
    path = tmp_path / "hierarchy.json"
    design.save(path)

    reopened = Design.from_file(path)
    gate = next(iter(reopened.root.nodes.values()))

    assert gate.child_module is not None
    assert not reopened.history.is_undoable
    assert reopened.name == "hierarchy"


def test_hierarchical_ports_ignores_unnamed_port_blocks(design):
    """A port block whose name has no suffix contributes nothing."""
    child = Module()
    instantiate(child, library().require("builtin.port_in"), text="")

    assert hierarchical_ports(child) == []
