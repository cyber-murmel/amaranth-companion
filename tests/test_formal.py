"""Formal verification: the prover, formal blocks, and what gets generated.

The checks that actually run SymbiYosys are skipped when it is not installed,
so the suite stays green without it -- but they are the only ones that prove
the replacement for Amaranth's removed ``assertFormal`` works, so they are
worth having when it is.
"""

import ast
import os
import subprocess
import sys

import pytest

from amaranth import Elaboratable, Module, Signal
from amaranth.hdl import Assert, Cover

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.examples import find, open_example
from amaranth_companion.generate import DesignGenerator, generate_files, generate_tests
from amaranth_companion.module.instantiate import instantiate
from amaranth_companion.verify import formal_tools_available, run_formal
from amaranth_companion.verify.formal import DEFAULT_MODES, declared_modes
from amaranth_companion.verify.sby import (
    DEFAULT_DEPTH,
    MODES,
    FormalToolsMissing,
    assert_formal,
    build_rtlil,
    design_ports,
)

needs_tools = pytest.mark.skipif(
    not formal_tools_available(), reason="needs sby and yosys on PATH"
)


class Counter(Elaboratable):
    """A counter that wraps at ``limit``, for proving things about."""

    def __init__(self, limit=8):
        self.limit = limit
        self.count_out = Signal(range(limit + 1))

    @property
    def ports(self):
        return [self.count_out]

    def elaborate(self, platform):
        m = Module()
        with m.If(self.count_out == self.limit - 1):
            m.d.sync += self.count_out.eq(0)
        with m.Else():
            m.d.sync += self.count_out.eq(self.count_out + 1)
        return m


def in_range(m, dut):
    m.d.comb += Assert(dut.count_out < dut.limit)


def out_of_range(m, dut):
    """Deliberately false: the counter definitely reaches zero."""
    m.d.comb += Assert(dut.count_out > 0)


def reachable(m, dut):
    m.d.comb += Cover(dut.count_out == 3)


def unreachable(m, dut):
    m.d.comb += Cover(dut.count_out == 99)


@pytest.fixture
def design(qapp):
    return Design()


# --- building the rtlil -----------------------------------------------------


def test_ports_come_from_the_declared_list():
    counter = Counter()

    assert design_ports(counter) == [counter.count_out]


def test_ports_fall_back_to_the_naming_convention():
    class Bare(Elaboratable):
        def __init__(self):
            self.a_in = Signal(1)
            self.o_out = Signal(1)
            self.internal = Signal(1)

        def elaborate(self, platform):
            return Module()

    names = {signal.name for signal in design_ports(Bare())}

    assert names == {"a_in", "o_out"}


def test_properties_reach_the_rtlil():
    """A proof over a design with no property cells would prove nothing."""
    text = build_rtlil(Counter(), in_range)

    # modern amaranth emits `$check` cells with a flavour, not `$assert`
    assert text.count("$check") == 1
    assert 'parameter \\FLAVOR "assert"' in text


def test_a_design_without_a_spec_still_builds():
    assert build_rtlil(Counter(), None)


def test_the_clock_and_reset_are_exposed():
    """The solver has to be able to drive them."""
    text = build_rtlil(Counter(), in_range)

    assert "clk" in text and "rst" in text


def test_an_unknown_mode_is_refused():
    from amaranth_companion.verify.sby import run_sby

    with pytest.raises(ValueError):
        run_sby("", mode="nonsense")


# --- actually proving things ------------------------------------------------


@needs_tools
@pytest.mark.parametrize("mode", ["bmc", "prove"])
def test_a_true_property_holds(mode):
    assert_formal(Counter(), in_range, mode=mode, depth=12)


@needs_tools
def test_a_false_property_fails_with_a_trace():
    """A pass is only meaningful if red is reachable."""
    with pytest.raises(AssertionError) as caught:
        assert_formal(Counter(), out_of_range, mode="bmc", depth=12)

    assert "counterexample trace:" in str(caught.value)


@needs_tools
def test_a_reachable_cover_passes():
    assert_formal(Counter(), reachable, mode="cover", depth=12)


@needs_tools
def test_an_unreachable_cover_fails():
    with pytest.raises(AssertionError) as caught:
        assert_formal(Counter(), unreachable, mode="cover", depth=12)

    assert "cover" in str(caught.value).lower()


def test_missing_tools_are_reported_clearly(monkeypatch):
    import amaranth_companion.verify.sby as sby

    monkeypatch.setattr(sby, "formal_tools_available", lambda: False)

    with pytest.raises(FormalToolsMissing):
        sby.run_sby("", mode="bmc")


# --- what a formal block declares -------------------------------------------


def test_a_block_without_declarations_gets_the_defaults():
    assert declared_modes("def formal(m, dut):\n    pass\n") == (
        DEFAULT_MODES,
        DEFAULT_DEPTH,
    )


def test_declared_modes_and_depth_are_read():
    source = 'MODES = ("bmc", "prove")\nDEPTH = 42\n\ndef formal(m, dut):\n    pass\n'

    assert declared_modes(source) == (("bmc", "prove"), 42)


def test_an_unknown_mode_is_dropped():
    modes, _depth = declared_modes('MODES = ("bmc", "nonsense")\n')

    assert modes == ("bmc",)


def test_declarations_are_read_without_running_the_block():
    """The editor labels the checks before anything has been proved."""
    modes, depth = declared_modes('MODES = ("cover",)\nraise RuntimeError("boom")\n')

    assert modes == ("cover",)


def test_a_block_that_does_not_parse_falls_back():
    assert declared_modes("def formal(:\n") == (DEFAULT_MODES, DEFAULT_DEPTH)


# --- formal blocks in a design ----------------------------------------------


def formal_block(design, text, title="Properties"):
    return instantiate(
        design.current_module,
        library().require("builtin.formal"),
        text=text,
        title=title,
        pos=(300, 300),
    )


def test_running_a_non_formal_block_is_refused(design):
    node = design.instantiate(library().require("logic.and2"))

    results = run_formal(design, node)

    assert not results[0].ok
    assert "not a formal block" in results[0].error


def test_a_spec_that_does_not_define_formal_is_reported(design):
    design.instantiate(library().require("logic.and2"))
    node = formal_block(design, "MODES = ('bmc',)\nx = 1\n")

    results = run_formal(design, node)

    assert not results[0].ok


def test_a_spec_with_a_syntax_error_reports_its_line(design):
    design.instantiate(library().require("logic.and2"))
    node = formal_block(design, "MODES = ('bmc',)\n\n\ndef formal(:\n")

    results = run_formal(design, node)

    assert not results[0].ok
    assert results[0].line == 4


def test_one_result_per_declared_mode(design):
    design.instantiate(library().require("logic.and2"))
    node = formal_block(
        design, 'MODES = ("bmc", "cover", "prove")\n\ndef formal(m, dut):\n    pass\n'
    )

    results = run_formal(design, node)

    assert [result.mode for result in results] == ["bmc", "cover", "prove"]


def test_blocks_are_skipped_rather_than_failed_without_tools(design, monkeypatch):
    import amaranth_companion.verify.sby as sby

    monkeypatch.setattr(sby, "formal_tools_available", lambda: False)
    design.instantiate(library().require("logic.and2"))
    node = formal_block(design, 'MODES = ("bmc",)\n\ndef formal(m, dut):\n    pass\n')

    results = run_formal(design, node)

    assert all(result.skipped for result in results)
    assert not any(result.ok for result in results)


# --- the blinker example ----------------------------------------------------


def test_the_blinker_example_ships_a_formal_spec(qapp):
    from amaranth_companion.verify.formal import formal_nodes

    nodes = formal_nodes(open_example(find("blinker")))

    assert len(nodes) == 1

    # Ported off the helpers amaranth removed. Checked against the parsed
    # code rather than the text, because the spec's docstring explains the
    # port and so mentions them by name.
    tree = ast.parse(nodes[0].text)
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert not {"Past", "Rose", "Fell", "Stable"} & (used | imported)


@needs_tools
def test_the_blinker_example_proves(qapp):
    """The whole point: blink's spec, recreated in the editor, holds."""
    from amaranth_companion.verify import run_all_formal

    results = run_all_formal(open_example(find("blinker")))

    assert results
    assert all(result.ok for result in results), [
        result.summary for result in results if not result.ok
    ]
    assert {result.mode for result in results} == set(MODES)


# --- generated tests --------------------------------------------------------


def test_formal_blocks_become_skippable_tests(qapp):
    design = open_example(find("blinker"))
    generator = DesignGenerator(design)
    generator.source()

    source = generate_tests(design, generator, "blink")

    assert "assert_formal(Top(), formal," in source
    assert "skipif" in source
    assert source.count("def test_") == 4  # one simulation, three modes


def test_the_prover_is_copied_into_the_package(qapp):
    """The generated tests must not need amaranth-companion installed."""
    files = generate_files(open_example(find("blinker")), "blink")

    assert "blink/tests/_formal.py" in files
    assert "amaranth_companion" not in "".join(files.values())


def test_a_design_without_formal_gets_no_prover(qapp):
    files = generate_files(open_example(find("nand")), "nand")

    assert not any(name.endswith("_formal.py") for name in files)


@needs_tools
def test_the_generated_blink_package_passes_pytest(qapp, tmp_path):
    """Canvas -> package -> green pytest run, simulation and proof."""
    for name, content in generate_files(open_example(find("blinker")), "blink").items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "blink"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=900,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "4 passed" in completed.stdout
