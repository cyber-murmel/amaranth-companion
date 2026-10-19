"""Generating Amaranth from a design.

The interesting assertions here are not about the text that comes out: they
elaborate it and simulate it, because a generator that produces plausible code
which does the wrong thing is the failure mode that matters.
"""

import pytest

from amaranth.back import rtlil
from amaranth.sim import Simulator

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.generate import (
    GenerationError,
    NameAllocator,
    class_name,
    generate_files,
    generate_source,
    identifier,
)
from amaranth_companion.module.element import Edge
from amaranth_companion.module.naming import family_name
from amaranth_companion.module.instantiate import instantiate, refresh_node_ports


@pytest.fixture
def design(qapp):
    return Design()


def build(design, text, **kwargs):
    return instantiate(
        design.current_module, library().require("builtin.code"), text=text, **kwargs
    )


def load(source: str) -> dict:
    """Execute generated source and hand back what it defined."""
    namespace: dict = {}
    exec(compile(source, "<generated>", "exec"), namespace)
    return namespace


def simulate(dut, body):
    sim = Simulator(dut)
    sim.add_testbench(body)
    sim.run()


# --- names ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("AND", "and_"),
        ("half adder", "half_adder"),
        ("2nd stage", "n2nd_stage"),
        ("", "block"),
        ("---", "block"),
        ("class", "class_"),
    ],
)
def test_identifiers_are_legal_python(text, expected):
    assert identifier(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("logic.and2", "LogicAnd2"), ("half adder", "HalfAdder"), ("", "Block")],
)
def test_class_names_are_camel_case(text, expected):
    assert class_name(text) == expected


def test_allocated_names_are_unique():
    allocator = NameAllocator()

    assert [allocator.take("gate") for _ in range(3)] == ["gate", "gate_2", "gate_3"]


def test_reserved_names_are_avoided():
    assert NameAllocator(reserved={"Signal"}).take("Signal") == "Signal_2"


# --- generating -------------------------------------------------------------


def test_an_empty_design_still_generates_a_top(design):
    source = generate_source(design)

    assert "class Top(Elaboratable):" in source
    assert load(source)["Top"]() is not None


def test_the_top_class_keeps_its_name(design):
    """``Top`` must not be suffixed by a collision with a reserved word."""
    design.instantiate(library().require("logic.and2"))

    assert "class Top(Elaboratable):" in generate_source(design)


def test_a_gate_generates_an_elaboratable(design):
    design.instantiate(library().require("logic.and2"))
    namespace = load(generate_source(design))

    assert "AND" in namespace
    assert "And2" in namespace  # the code block's own class, emitted verbatim


def test_a_code_block_is_emitted_verbatim(design):
    design.instantiate(library().require("logic.and2"))
    source = generate_source(design)

    assert "m.d.comb += self.o_out.eq(self.a_in & self.b_in)" in source


def test_the_amaranth_import_is_not_repeated(design):
    """A star import before every class would shadow what came above it."""
    design.instantiate(library().require("logic.and2"))

    assert generate_source(design).count("from amaranth import *") == 1


def test_identical_blocks_share_one_class(design):
    """Counting the name is not enough: the duplicate used to be AND_2."""
    design.instantiate(library().require("logic.and2"))
    design.instantiate(library().require("logic.and2"), pos=(400, 0))

    source = generate_source(design)
    classes = [line for line in source.splitlines() if line.startswith("class ")]

    assert source.count("class AND(Elaboratable):") == 1
    # the gate, the code block inside it, and Top
    assert len(classes) == 3


def test_an_edited_block_gets_its_own_class(design):
    """Two AND gates are one class, until one of them is changed."""
    first = design.instantiate(library().require("logic.and2"))
    second = design.instantiate(library().require("logic.and2"), pos=(400, 0))

    port = next(n for n in second.child_module.nodes.values() if n.text == "a")
    port.text = "enable"
    refresh_node_ports(second)

    source = generate_source(design)
    assert source.count("(Elaboratable):") > source.count("class AND(Elaboratable):")
    # the same kind of block either way; it is the insides that differ
    assert family_name(first) == family_name(second) == "AND"


def test_an_empty_code_block_is_an_error(design):
    build(design, "")

    with pytest.raises(GenerationError):
        generate_source(design)


def test_a_broken_code_block_is_an_error(design):
    build(design, "class Broken(:\n")

    with pytest.raises(GenerationError):
        generate_source(design)


def test_files_are_laid_out_as_a_package(design):
    files = generate_files(design, "blink")

    assert set(files) == {
        "blink/__init__.py",
        "blink/__main__.py",
        "blink/_hardware.py",
        "blink/_waveform.py",
        "blink/blink.py",
    }
    assert "from .blink import *" in files["blink/__init__.py"]


# --- parameters survive generation ------------------------------------------


def test_a_port_width_keeps_its_parameter(design):
    """Emitting `Signal(1)` would freeze a parameterisable block."""
    design.instantiate(library().require("logic.and2"))
    source = generate_source(design)

    assert "self.a_in = Signal(width_param)" in source


def test_a_wired_variable_becomes_a_constant(design):
    module = design.current_module
    var = instantiate(module, library().require("builtin.variable"), text="width = 4")
    gate = design.instantiate(library().require("logic.and2"), pos=(400, 0))
    module.add_edge(
        Edge(var.output_sockets["width_param"], gate.input_sockets["width_param"])
    )
    refresh_node_ports(gate)

    source = generate_source(design)

    assert "width = 4" in source
    assert "AND(width_param=width)" in source


def test_a_parameter_edge_is_not_a_wire(design):
    """It is a constructor argument; emitting it as comb would be wrong."""
    module = design.current_module
    var = instantiate(module, library().require("builtin.variable"), text="width = 4")
    gate = design.instantiate(library().require("logic.and2"), pos=(400, 0))
    module.add_edge(
        Edge(var.output_sockets["width_param"], gate.input_sockets["width_param"])
    )

    assert "width_param.eq(" not in generate_source(design)


# --- the generated code actually works --------------------------------------


def test_a_generated_gate_elaborates(design):
    design.instantiate(library().require("logic.and2"))
    namespace = load(generate_source(design))

    gate = namespace["AND"](width_param=4)

    assert rtlil.convert(gate, ports=gate.ports)


def test_a_generated_and_gate_computes_an_and(design):
    design.instantiate(library().require("logic.and2"))
    dut = load(generate_source(design))["AND"](width_param=4)

    async def body(ctx):
        for a, b in ((0b1100, 0b1010), (0b1111, 0b0001), (0b0000, 0b1111)):
            ctx.set(dut.a_in, a)
            ctx.set(dut.b_in, b)
            await ctx.delay(1e-6)
            assert ctx.get(dut.o_out) == a & b

    simulate(dut, body)


@pytest.mark.parametrize(
    "gate, operation",
    [
        ("logic.or2", lambda a, b: a | b),
        ("logic.xor2", lambda a, b: a ^ b),
    ],
)
def test_every_two_input_gate_computes_its_operation(design, gate, operation):
    node = design.instantiate(library().require(gate))
    dut = load(generate_source(design))[node.title](width_param=4)

    async def body(ctx):
        for a, b in ((0b1100, 0b1010), (0b0101, 0b0011)):
            ctx.set(dut.a_in, a)
            ctx.set(dut.b_in, b)
            await ctx.delay(1e-6)
            assert ctx.get(dut.o_out) == operation(a, b) & 0xF

    simulate(dut, body)


def test_a_wired_design_computes_the_whole_function(design):
    """An AND into a NOT, built on the canvas, must behave as a NAND."""
    module = design.current_module
    lib = library()

    width = instantiate(module, lib.require("builtin.variable"), text="width = 4")
    a = instantiate(module, lib.require("builtin.port_in"), text="a", pos=(0, 200))
    b = instantiate(module, lib.require("builtin.port_in"), text="b", pos=(0, 400))
    q = instantiate(module, lib.require("builtin.port_out"), text="q", pos=(900, 300))
    gate = design.instantiate(lib.require("logic.and2"), pos=(300, 200))
    inverter = design.instantiate(lib.require("logic.not"), pos=(600, 200))

    for edge in (
        Edge(width.output_sockets["width_param"], gate.input_sockets["width_param"]),
        Edge(
            width.output_sockets["width_param"],
            inverter.input_sockets["width_param"],
        ),
        Edge(a.output_sockets["a_in"], gate.input_sockets["a_in"]),
        Edge(b.output_sockets["b_in"], gate.input_sockets["b_in"]),
        Edge(gate.output_sockets["o_out"], inverter.input_sockets["a_in"]),
        Edge(inverter.output_sockets["o_out"], q.input_sockets["q_out"]),
    ):
        assert module.add_edge(edge)

    for node in (gate, inverter, a, b, q):
        refresh_node_ports(node)

    dut = load(generate_source(design, "Nand"))["Nand"]()

    async def body(ctx):
        for left, right in ((0b1100, 0b1010), (0b1111, 0b1111), (0, 0)):
            ctx.set(dut.a_in, left)
            ctx.set(dut.b_in, right)
            await ctx.delay(1e-6)
            assert ctx.get(dut.q_out) == ~(left & right) & 0xF

    simulate(dut, body)


def test_the_generated_ports_follow_the_wired_width(design):
    """A root port takes the width of whatever it is attached to."""
    module = design.current_module
    lib = library()

    width = instantiate(module, lib.require("builtin.variable"), text="width = 7")
    a = instantiate(module, lib.require("builtin.port_in"), text="a", pos=(0, 200))
    gate = design.instantiate(lib.require("logic.and2"), pos=(300, 200))

    module.add_edge(
        Edge(width.output_sockets["width_param"], gate.input_sockets["width_param"])
    )
    refresh_node_ports(gate)
    module.add_edge(Edge(a.output_sockets["a_in"], gate.input_sockets["a_in"]))
    refresh_node_ports(a)

    assert "self.a_in = Signal(7)" in generate_source(design)
