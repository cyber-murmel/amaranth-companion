"""Block definitions, the library, and deriving ports from Amaranth source."""

import pytest

from amaranth_companion.blocks.definition import (
    BlockDefinition,
    BlockDefinitionError,
    BlockKind,
    PortRole,
    PortSpec,
    Shape,
    split_port_name,
)
from amaranth_companion.blocks.introspect import analyse, introspect
from amaranth_companion.blocks.library import BUILTIN_DIR, BlockLibrary, load_library

GATE_SOURCE = """
from amaranth import *


class And2(Elaboratable):
    def __init__(self, width_param=4):
        self.a_in = Signal(width_param)
        self.b_in = Signal(width_param)
        self.o_out = Signal(width_param)
        self.counter = Signal(range(width_param))

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o_out.eq(self.a_in & self.b_in)
        return m
"""


# --- the naming convention --------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("a_in", ("a", PortRole.INPUT)),
        ("blink_out", ("blink", PortRole.OUTPUT)),
        ("width_param", ("width", PortRole.PARAM)),
        ("data_valid_in", ("data_valid", PortRole.INPUT)),
    ],
)
def test_suffix_decides_the_port_role(name, expected):
    assert split_port_name(name) == expected


@pytest.mark.parametrize("name", ["counter", "half_period", "m", "_in", "_param"])
def test_names_without_a_role_suffix_are_internal(name):
    """``Blinker.counter`` is a signal but not a port; it must stay off the edge."""
    assert split_port_name(name) is None


def test_param_is_matched_before_in():
    """``_param`` ends in no other suffix, but the order still has to be right."""
    assert PortSpec.from_name("width_param").role is PortRole.PARAM


# --- introspection ----------------------------------------------------------


def test_ports_come_from_the_source_with_real_shapes():
    result = introspect(GATE_SOURCE, {"width_param": 8})

    assert result.ok
    assert result.class_name == "And2"
    assert [port.name for port in result.signal_ports] == ["a_in", "b_in", "o_out"]
    assert all(port.shape == Shape(8, False) for port in result.signal_ports)


def test_parameters_are_read_from_the_constructor():
    result = introspect(GATE_SOURCE)

    assert [port.name for port in result.param_ports] == ["width_param"]
    assert result.params[0].default == 4


def test_a_width_that_depends_on_a_parameter_follows_it():
    """The reason ports are introspected rather than parsed."""
    narrow = introspect(GATE_SOURCE, {"width_param": 2})
    wide = introspect(GATE_SOURCE, {"width_param": 16})

    assert narrow.signal_ports[0].shape == Shape(2, False)
    assert wide.signal_ports[0].shape == Shape(16, False)


def test_internal_signals_are_not_ports():
    result = introspect(GATE_SOURCE, {"width_param": 8})

    assert "counter" not in [port.name for port in result.ports]


def test_signedness_is_carried_through():
    source = GATE_SOURCE.replace(
        "self.o_out = Signal(width_param)",
        "self.o_out = Signal(signed(width_param))",
    )
    result = introspect(source, {"width_param": 8})

    output = next(port for port in result.signal_ports if port.name == "o_out")
    assert output.shape == Shape(8, True)


def test_an_imported_elaboratable_is_not_mistaken_for_the_block():
    """``from amaranth import *`` binds ``Module``, itself an ``Elaboratable``."""
    result = introspect(GATE_SOURCE)

    assert result.class_name == "And2"


def test_the_last_defined_class_wins():
    source = GATE_SOURCE + """

class Wrapper(Elaboratable):
    def __init__(self):
        self.q_out = Signal(1)

    def elaborate(self, platform):
        return Module()
"""
    result = introspect(source)

    assert result.class_name == "Wrapper"
    assert [port.name for port in result.signal_ports] == ["q_out"]


# --- introspection failures -------------------------------------------------


def test_a_syntax_error_is_reported_not_raised():
    result = introspect("class Broken(:\n")

    assert not result.ok
    assert "SyntaxError" in result.error


def test_source_without_an_elaboratable_is_reported():
    result = introspect("x = 1")

    assert not result.ok
    assert "Elaboratable" in result.error


def test_code_that_raises_is_reported():
    result = introspect("raise RuntimeError('boom')")

    assert not result.ok
    assert "boom" in result.error


def test_a_block_that_never_returns_is_killed():
    """A runaway loop must cost a worker, not the editor."""
    result = introspect("while True: pass", timeout=2.0)

    assert not result.ok
    assert "did not finish" in result.error


def test_analyse_runs_without_spawning_anything():
    """The worker's own logic, exercised in-process."""
    response = analyse(GATE_SOURCE, {"width_param": 3})

    assert response["ok"]
    assert response["class_name"] == "And2"


def test_a_stale_parameter_does_not_break_instantiation():
    """The editor may still hold a value for a parameter the source dropped."""
    result = introspect(GATE_SOURCE, {"width_param": 2, "removed_param": 9})

    assert result.ok
    assert result.signal_ports[0].shape == Shape(2, False)


# --- the library ------------------------------------------------------------


def test_the_shipped_gates_load():
    loaded = load_library()

    for block_id in ("logic.not", "logic.and2", "logic.or2", "logic.xor2"):
        definition = loaded.require(block_id)
        assert definition.kind is BlockKind.HIERARCHICAL
        assert definition.category == ("Logic",)


def test_builtin_kinds_are_registered():
    loaded = load_library()

    assert loaded.require("builtin.port_in").kind is BlockKind.PORT_IN
    assert loaded.require("builtin.port_out").kind is BlockKind.PORT_OUT
    assert loaded.require("builtin.port_param").kind is BlockKind.PORT_PARAM
    assert loaded.require("builtin.code").kind is BlockKind.CODE


@pytest.mark.parametrize(
    "block_id, inputs",
    [("logic.not", ["a_in"]), ("logic.and2", ["a_in", "b_in"])],
)
def test_a_gate_implementation_agrees_with_its_code(block_id, inputs):
    """The port blocks inside a gate must match what its source declares."""
    definition = load_library().require(block_id)
    nodes = definition.load_implementation()["nodes"].values()

    # the implementation is an ordinary module, so the port nodes carry a
    # bare name and their kind says which way they face
    declared = {
        f"{node['text']}_in" if node["kind"] == "port_in" else f"{node['text']}_out"
        for node in nodes
        if node["kind"] in ("port_in", "port_out")
    }
    source = next(node["text"] for node in nodes if node["kind"] == "code")
    introspected = {port.name for port in introspect(source).signal_ports}

    assert declared == introspected == set(inputs) | {"o_out"}


def test_a_broken_definition_is_skipped_not_fatal(tmp_path, caplog):
    (tmp_path / "bad.block.yml").write_text("id: broken\nkind: nonsense\n")
    (tmp_path / "good.block.yml").write_text("id: fine\nkind: code\n")

    loaded = BlockLibrary()
    count = loaded.load_directory(tmp_path)

    assert count == 1
    assert "fine" in loaded
    assert "broken" not in loaded


def test_definitions_group_by_category():
    grouped = load_library().by_category()

    assert [d.id for d in grouped[("Logic",)]] == [
        "logic.and2",
        "logic.not",
        "logic.or2",
        "logic.xor2",
    ]


def test_a_definition_needs_an_id_and_a_kind():
    with pytest.raises(BlockDefinitionError):
        BlockDefinition.from_dict({"kind": "code"})

    with pytest.raises(BlockDefinitionError):
        BlockDefinition.from_dict({"id": "x"})


def test_every_shipped_definition_file_parses():
    """Nothing in the builtin directory may be silently skipped."""
    paths = sorted(BUILTIN_DIR.rglob("*.block.yml"))
    loaded = BlockLibrary()

    assert loaded.load_directory(BUILTIN_DIR) == len(paths) > 0


# --- starting templates -----------------------------------------------------


@pytest.mark.parametrize(
    "block_id", ["builtin.code", "builtin.testbench", "builtin.formal"]
)
def test_a_new_block_arrives_with_a_skeleton(block_id):
    """An empty editor gives a new user nothing to work from."""
    assert load_library().require(block_id).source.strip()


def test_the_code_skeleton_is_valid_on_arrival():
    """A new code block must not be born reporting an error."""
    result = introspect(load_library().require("builtin.code").source)

    assert result.ok, result.error
    assert [port.name for port in result.signal_ports] == ["a_in", "o_out"]
    assert [port.name for port in result.param_ports] == ["width_param"]


def test_the_code_skeleton_demonstrates_an_internal_signal():
    """It teaches the convention by example, so it must include a non-port."""
    source = load_library().require("builtin.code").source
    result = introspect(source)

    assert "self.state = Signal" in source
    assert "state" not in [port.name for port in result.ports]
