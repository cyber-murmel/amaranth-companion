"""Testbench blocks: running them, and emitting them as a pytest file."""

import os
import subprocess
import sys

import pytest

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.generate import (
    DesignGenerator,
    generate_files,
    generate_tests,
)

# aliased: pytest would otherwise collect the imported helper as a test
from amaranth_companion.generate import testbench_nodes as find_testbenches
from amaranth_companion.module.instantiate import instantiate
from amaranth_companion.verify import run_all, run_testbench

PASSING = """
async def testbench(ctx, dut):
    for a, b in ((1, 1), (1, 0), (0, 1), (0, 0)):
        ctx.set(dut.a_in, a)
        ctx.set(dut.b_in, b)
        await ctx.delay(1e-6)
        assert ctx.get(dut.o_out) == (a & b)
"""

FAILING = """
async def testbench(ctx, dut):
    ctx.set(dut.a_in, 1)
    ctx.set(dut.b_in, 1)
    await ctx.delay(1e-6)
    assert ctx.get(dut.o_out) == 0, "deliberately wrong"
"""


@pytest.fixture
def design(qapp):
    return Design()


@pytest.fixture
def gate_with_testbench(design):
    """An AND gate with a testbench block inside its implementation."""
    gate = design.instantiate(library().require("logic.and2"))
    design.enter(gate)
    node = instantiate(
        design.current_module,
        library().require("builtin.testbench"),
        pos=(100, 600),
        text=PASSING,
    )
    design.leave()
    return design, node


# --- running ----------------------------------------------------------------


def test_a_passing_testbench_passes(gate_with_testbench):
    design, node = gate_with_testbench

    result = run_testbench(design, node)

    assert result.ok, result.error
    assert result.summary.endswith("passed")


def test_a_failing_testbench_reports_the_assertion(gate_with_testbench):
    design, node = gate_with_testbench
    node.text = FAILING

    result = run_testbench(design, node)

    assert not result.ok
    assert "deliberately wrong" in result.error


def test_a_hanging_testbench_is_killed(gate_with_testbench):
    """A runaway testbench must cost a worker, not the editor."""
    design, node = gate_with_testbench
    node.text = "async def testbench(ctx, dut):\n    while True:\n        pass\n"

    result = run_testbench(design, node, timeout=5.0)

    assert not result.ok
    assert "did not finish" in result.error


def test_a_testbench_with_a_syntax_error_is_reported(gate_with_testbench):
    design, node = gate_with_testbench
    node.text = "async def testbench(:\n"

    result = run_testbench(design, node)

    assert not result.ok
    assert "SyntaxError" in result.error


def test_a_testbench_without_the_entry_point_is_reported(gate_with_testbench):
    design, node = gate_with_testbench
    node.text = "x = 1\n"

    result = run_testbench(design, node)

    assert not result.ok
    assert "testbench" in result.error


def test_a_testbench_drives_the_block_it_sits_in(gate_with_testbench):
    """The dut is the implementation around it, not the whole design."""
    design, node = gate_with_testbench
    node.text = """
async def testbench(ctx, dut):
    assert hasattr(dut, "a_in") and hasattr(dut, "o_out")
"""

    assert run_testbench(design, node).ok


def test_a_vcd_is_written_when_asked(gate_with_testbench, tmp_path):
    design, node = gate_with_testbench
    path = tmp_path / "trace.vcd"

    result = run_testbench(design, node, vcd_path=str(path))

    assert result.ok, result.error
    assert path.stat().st_size > 0


def test_running_a_non_testbench_block_is_refused(design):
    node = design.instantiate(library().require("logic.and2"))

    result = run_testbench(design, node)

    assert not result.ok
    assert "not a testbench" in result.error


def test_run_all_finds_testbenches_at_any_depth(gate_with_testbench):
    design, _node = gate_with_testbench

    results = run_all(design)

    assert len(results) == 1
    assert results[0].ok


def test_a_design_with_a_broken_block_reports_rather_than_running(
    gate_with_testbench,
):
    design, node = gate_with_testbench
    instantiate(design.root, library().require("builtin.code"), text="class X(:\n")

    result = run_testbench(design, node)

    assert not result.ok


# --- emitting ---------------------------------------------------------------


def test_testbenches_become_a_pytest_module(gate_with_testbench):
    design, _node = gate_with_testbench
    generator = DesignGenerator(design)
    generator.source()

    source = generate_tests(design, generator, "gates")

    assert "def test_" in source
    assert "from ..gates import AND" in source
    assert "simulator.run()" in source


def test_a_design_without_testbenches_emits_no_test_file(design):
    design.instantiate(library().require("logic.and2"))
    generator = DesignGenerator(design)
    generator.source()

    assert generate_tests(design, generator, "gates") is None
    assert not any("tests/" in name for name in generate_files(design, "gates"))


def test_the_package_has_the_example_repository_layout(gate_with_testbench):
    design, _node = gate_with_testbench

    files = generate_files(design, "gates")

    assert set(files) == {
        "gates/__init__.py",
        "gates/__main__.py",
        "gates/_hardware.py",
        "gates/_waveform.py",
        "gates/gates.py",
        "gates/tests/__init__.py",
        "gates/tests/test_gates.py",
    }


def test_two_testbenches_do_not_collide(gate_with_testbench):
    """Both blocks define `async def testbench`; nesting keeps them apart."""
    design, node = gate_with_testbench
    design.enter(design.root.nodes[next(iter(design.root.nodes))])
    instantiate(
        design.current_module,
        library().require("builtin.testbench"),
        pos=(600, 600),
        text=PASSING,
    )
    design.leave()

    generator = DesignGenerator(design)
    generator.source()
    source = generate_tests(design, generator, "gates")

    assert source.count("def test_") == 2


def test_testbenches_are_found_at_any_depth(gate_with_testbench):
    design, node = gate_with_testbench

    assert find_testbenches(design) == [node]


def test_the_generated_tests_pass_under_pytest(gate_with_testbench, tmp_path):
    """The end of the whole chain: canvas -> package -> green pytest run."""
    design, _node = gate_with_testbench

    for name, content in generate_files(design, "gates").items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "gates"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "1 passed" in completed.stdout


def test_the_generated_tests_fail_when_the_design_is_wrong(
    gate_with_testbench, tmp_path
):
    """A green run has to mean something, so check red is reachable."""
    design, node = gate_with_testbench
    node.text = FAILING

    for name, content in generate_files(design, "gates").items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "gates"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )

    assert completed.returncode != 0
    assert "deliberately wrong" in completed.stdout


# --- the shipped examples ---------------------------------------------------


def example_names():
    from amaranth_companion.examples import list_examples

    return [example.name for example in list_examples()]


def test_every_indexed_example_has_a_file(qapp):
    from amaranth_companion.examples import list_examples

    examples = list_examples()

    assert examples
    assert all(example.exists for example in examples)


@pytest.mark.parametrize("name", example_names())
def test_an_example_opens_untitled(qapp, name):
    """Saving an example must ask where, not overwrite what ships."""
    from amaranth_companion.examples import find, open_example

    design = open_example(find(name))

    assert design.path is None
    assert design.root.nodes


@pytest.mark.parametrize("name", example_names())
def test_an_example_generates_amaranth(qapp, name):
    from amaranth.back import rtlil

    from amaranth_companion.examples import find, open_example
    from amaranth_companion.generate import generate_source

    design = open_example(find(name))
    namespace: dict = {}
    exec(compile(generate_source(design), "<generated>", "exec"), namespace)

    top = namespace["Top"]()
    assert rtlil.convert(top, ports=getattr(top, "ports", []))


@pytest.mark.parametrize("name", example_names())
def test_an_examples_testbenches_pass(qapp, name):
    """A shipped example with a red testbench would be worse than none."""
    from amaranth_companion.examples import find, open_example

    results = run_all(open_example(find(name)))

    assert all(result.ok for result in results), [
        result.summary for result in results if not result.ok
    ]


def test_the_examples_cover_the_block_kinds(qapp):
    """Between them the examples should demonstrate what the editor can do."""
    from amaranth_companion.blocks.definition import BlockKind
    from amaranth_companion.examples import find, open_example

    kinds = set()
    for name in example_names():
        design = open_example(find(name))
        for module in design.walk():
            kinds.update(node.kind for node in module.nodes.values())

    assert {
        BlockKind.CODE,
        BlockKind.PORT_IN,
        BlockKind.VARIABLE,
        BlockKind.HIERARCHICAL,
        BlockKind.TESTBENCH,
    } <= kinds
