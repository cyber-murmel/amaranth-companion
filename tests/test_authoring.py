"""Ports as types, blocks as modules, and turning a module into one."""

import json

import pytest

from amaranth_companion.blocks.authoring import (
    BlockWriteError,
    block_id_for,
    describe_ports,
    write_block,
)
from amaranth_companion.blocks.definition import (
    BlockKind,
    PortRole,
    bare_port_name,
    port_name,
)
from amaranth_companion.blocks.library import (
    block_directories,
    library,
    load_library,
    user_block_dir,
)
from amaranth_companion.design import Design
from amaranth_companion.module import Module
from amaranth_companion.module.instantiate import instantiate, refresh_node_ports
from amaranth_companion.module.serialization import FORMAT_VERSION


@pytest.fixture
def design(qapp):
    return Design()


def port(module, kind, name, **kwargs):
    node = instantiate(
        module, library().require(f"builtin.{kind}"), text=name, **kwargs
    )
    refresh_node_ports(node)
    return node


# --- the port role is the kind, not the name --------------------------------


@pytest.mark.parametrize(
    "kind, role",
    [
        (BlockKind.PORT_IN, PortRole.INPUT),
        (BlockKind.PORT_OUT, PortRole.OUTPUT),
        (BlockKind.PORT_PARAM, PortRole.PARAM),
    ],
)
def test_each_port_kind_carries_its_role(kind, role):
    assert kind.port_role is role
    assert kind.is_port


def test_other_kinds_are_not_ports():
    assert BlockKind.CODE.port_role is None
    assert not BlockKind.HIERARCHICAL.is_port


@pytest.mark.parametrize(
    "name, role, expected",
    [
        ("a", PortRole.INPUT, "a_in"),
        ("result", PortRole.OUTPUT, "result_out"),
        ("width", PortRole.PARAM, "width_param"),
        ("a_in", PortRole.INPUT, "a_in"),
    ],
)
def test_the_suffix_is_generated_not_parsed(name, role, expected):
    assert port_name(name, role) == expected
    assert bare_port_name(expected) == bare_port_name(name)


def test_renaming_a_port_cannot_move_it(design):
    """The whole point: `a_in` -> `a_out` used to flip the port's side."""
    node = port(design.current_module, "port_in", "a")
    assert list(node.output_sockets) == ["a_in"]

    node.text = "a_out"
    refresh_node_ports(node)

    # still an input port; the name is just a name
    assert node.kind is BlockKind.PORT_IN
    assert [spec.role for spec in node.port_specs] == [PortRole.INPUT]


def test_a_port_node_stores_a_bare_name(design):
    node = port(design.current_module, "port_out", "result")

    assert node.text == "result"
    assert list(node.input_sockets) == ["result_out"]


def test_a_ports_title_follows_its_name(design):
    """`in_a` used to title a port called `a_in`."""
    node = port(design.current_module, "port_in", "enable")

    assert node.title == "enable"

    node.text = "ready"
    refresh_node_ports(node)
    assert node.title == "ready"


def test_an_unnamed_port_asks_for_a_name(design):
    node = port(design.current_module, "port_in", "")

    assert "name" in node.error
    assert not list(node.sockets)


def test_the_displayed_label_drops_the_suffix(design):
    node = port(design.current_module, "port_param", "width")

    socket = next(iter(node.output_sockets.values()))
    assert socket.name == "width_param"
    assert socket.label == "width"


# --- a block's implementation is a module -----------------------------------


def test_a_shipped_gate_points_at_a_module_file():
    definition = library().require("logic.and2")

    assert definition.implementation == "and2.json"
    assert definition.implementation_path.is_file()


def test_a_gates_implementation_is_an_ordinary_module():
    """It must be openable and diffable like any design."""
    definition = library().require("logic.and2")
    data = json.loads(definition.implementation_path.read_text())

    assert data["version"] == FORMAT_VERSION
    assert set(data) >= {"nodes", "edges"}
    assert any(node["kind"] == "port_in" for node in data["nodes"].values())


def test_a_gate_loads_through_the_normal_reader(design):
    gate = design.instantiate(library().require("logic.and2"))

    kinds = sorted(node.kind.value for node in gate.child_module.nodes.values())
    assert kinds == ["code", "port_in", "port_in", "port_out", "port_param"]
    assert len(list(gate.child_module.edges)) == 4


def test_two_instances_share_no_identity(design):
    first = design.instantiate(library().require("logic.and2"))
    second = design.instantiate(library().require("logic.and2"), pos=(600, 0))

    assert {n.uuid for n in first.child_module.nodes.values()}.isdisjoint(
        {n.uuid for n in second.child_module.nodes.values()}
    )


def test_a_definition_with_a_missing_module_is_reported(tmp_path):
    (tmp_path / "broken.block.yml").write_text(
        "id: broken\nkind: hierarchical\nimplementation: nowhere.json\n"
    )
    loaded = load_library([tmp_path])

    assert loaded.require("broken").load_implementation() == {}


# --- turning a module into a block ------------------------------------------


@pytest.fixture
def gate_insides(design):
    """The inside of an AND gate: a complete, sensible little module."""
    gate = design.instantiate(library().require("logic.and2"))
    design.enter(gate)
    return design.current_module


@pytest.mark.parametrize(
    "label, category, expected",
    [
        ("Half Adder", ["Math"], "math.half_adder"),
        ("Counter", [], "counter"),
        ("My And", ["Mine"], "mine.my_and"),
    ],
)
def test_block_ids_are_namespaced_by_category(label, category, expected):
    assert block_id_for(label, category) == expected


def test_a_block_needs_a_name():
    with pytest.raises(BlockWriteError):
        block_id_for("   ")


def test_the_ports_come_from_the_module(gate_insides):
    assert describe_ports(gate_insides) == {
        "in": ["a", "b"],
        "out": ["o"],
        "param": ["width"],
    }


def test_writing_a_block_produces_a_definition_and_a_module(gate_insides, tmp_path):
    path = write_block(gate_insides, label="My And", directory=tmp_path)

    assert path.name.endswith(".block.yml")
    assert (tmp_path / "blocks.my_and.json").is_file()


def test_the_written_block_is_what_the_shipped_ones_are(gate_insides, tmp_path):
    """Nothing about a built-in block should be privileged."""
    write_block(gate_insides, label="My And", directory=tmp_path, category=["Mine"])
    written = load_library([tmp_path]).require("mine.my_and")
    shipped = library().require("logic.and2")

    assert written.kind is shipped.kind
    assert written.implementation.endswith(".json")
    assert written.implementation_path.is_file()


def test_a_written_block_can_be_instantiated(qapp, gate_insides, tmp_path):
    write_block(gate_insides, label="My And", directory=tmp_path, category=["Mine"])
    spec = load_library([tmp_path]).require("mine.my_and")

    other = Design()
    node = other.instantiate(spec)

    assert [socket.name for socket in node.sockets] == [
        "a_in",
        "b_in",
        "width_param",
        "o_out",
    ]


def test_a_module_round_trips_through_a_block(qapp, gate_insides, tmp_path):
    before = sorted(
        (node.kind.value, node.text) for node in gate_insides.nodes.values()
    )
    write_block(gate_insides, label="Round Trip", directory=tmp_path)
    spec = load_library([tmp_path]).require("blocks.round_trip")

    rebuilt = Design().instantiate(spec).child_module
    after = sorted((node.kind.value, node.text) for node in rebuilt.nodes.values())

    assert after == before


def test_parameters_are_declared_from_the_param_ports(gate_insides, tmp_path):
    write_block(gate_insides, label="Parameterised", directory=tmp_path)
    spec = load_library([tmp_path]).require("blocks.parameterised")

    assert list(spec.params) == ["width_param"]


def test_an_empty_module_is_refused(qapp, tmp_path):
    with pytest.raises(BlockWriteError):
        write_block(Module(), label="Nothing", directory=tmp_path)


def test_an_existing_block_is_not_clobbered(gate_insides, tmp_path):
    write_block(gate_insides, label="Once", directory=tmp_path)

    with pytest.raises(BlockWriteError):
        write_block(gate_insides, label="Once", directory=tmp_path)

    write_block(gate_insides, label="Once", directory=tmp_path, overwrite=True)


# --- where blocks are looked for --------------------------------------------


def test_a_saved_design_looks_beside_itself_first(design, tmp_path):
    design.save(tmp_path / "thing.json")

    directories = block_directories(design)

    assert directories[0] == tmp_path / "blocks"
    assert directories[-1] == user_block_dir()


def test_an_unsaved_design_only_has_the_shared_directory(design):
    assert block_directories(design) == [user_block_dir()]


def test_a_project_block_shadows_a_shared_one(qapp, gate_insides, tmp_path):
    """A project can carry a changed copy without editing everyone else's."""
    shared, project = tmp_path / "shared", tmp_path / "project"
    write_block(gate_insides, label="Shared One", directory=shared)
    write_block(
        gate_insides, label="Shared One", directory=project, doc="the project copy"
    )

    # furthest first, so the nearest registration wins
    loaded = load_library([shared, project])

    assert loaded.require("blocks.shared_one").doc == "the project copy"
