"""Simulating a design to a waveform, and opening a viewer at it."""

import os
import shutil
import subprocess
import sys

import pytest

from amaranth_companion.examples import find, open_example
from amaranth_companion.generate import generate_files, generate_source
from amaranth_companion.verify import run_waveform, viewer_available
from amaranth_companion.verify.waveform import (
    CLOCK_SIGNALS,
    DEFAULT_CLOCKS,
    VIEWER,
    ViewerMissing,
    add_clock_to_save,
    build_parser,
    open_viewer,
    simulate,
    vcd_signal_paths,
    viewer_command,
    waveform_traces,
)

needs_viewer = pytest.mark.skipif(
    not viewer_available(), reason=f"needs {VIEWER} on PATH"
)


def build(name: str):
    """The generated ``Top`` of a shipped example."""
    namespace: dict = {}
    source = generate_source(open_example(find(name)))
    exec(compile(source, "<generated>", "exec"), namespace)
    return namespace["Top"]()


def save_file_signals(path) -> list[str]:
    return [
        line.strip()
        for line in open(path)
        if line.strip() and not line.startswith(("[", "@"))
    ]


@pytest.fixture
def blinker(qapp):
    return build("blinker")


# --- choosing what to show --------------------------------------------------


def test_traces_include_internal_state(blinker):
    """A blinker's counter is exactly what you want next to its output."""
    names = [signal.name for signal in waveform_traces(blinker)]

    assert "counter" in names
    assert "blink_out" in names


def test_traces_reach_into_submodules(blinker):
    """The counter belongs to the Blinker, not to Top."""
    assert "counter" not in vars(blinker)
    assert "counter" in [signal.name for signal in waveform_traces(blinker)]


def test_trace_depth_is_respected(blinker):
    shallow = waveform_traces(blinker, depth=0)

    assert "counter" not in [signal.name for signal in shallow]


def test_a_signal_is_not_traced_twice(blinker):
    traces = waveform_traces(blinker)

    assert len({id(signal) for signal in traces}) == len(traces)


# --- simulating -------------------------------------------------------------


def test_a_clocked_design_runs_for_the_requested_clocks(blinker, tmp_path):
    vcd = tmp_path / "b.vcd"

    simulate(blinker, clocks=20, period=1e-6, vcd_path=vcd)

    assert vcd.stat().st_size > 0
    # the last timestamp the trace reaches, in femtoseconds
    stamps = [int(line[1:]) for line in vcd.read_text().splitlines() if line[:1] == "#"]
    assert max(stamps) >= 19 * 1_000_000_000


def test_a_longer_run_produces_a_longer_trace(qapp, tmp_path):
    short, long = tmp_path / "s.vcd", tmp_path / "l.vcd"

    simulate(build("blinker"), clocks=10, vcd_path=short)
    simulate(build("blinker"), clocks=100, vcd_path=long)

    assert long.stat().st_size > short.stat().st_size


def test_a_combinational_design_does_not_hang(qapp, tmp_path):
    """`run_until` waits forever for an event a comb design never produces."""
    vcd = tmp_path / "n.vcd"

    simulate(build("nand"), clocks=50, vcd_path=vcd)

    assert vcd.stat().st_size > 0


def test_the_save_file_lists_the_traces(blinker, tmp_path):
    vcd, gtkw = tmp_path / "b.vcd", tmp_path / "b.gtkw"

    simulate(blinker, clocks=20, vcd_path=vcd, gtkw_path=gtkw)
    signals = save_file_signals(gtkw)

    assert any(name.endswith("counter[2:0]") for name in signals)
    assert any(name.endswith("blink_out") for name in signals)


def test_the_clock_is_at_the_top_of_the_save_file(blinker, tmp_path):
    """A clocked waveform is unreadable without the clock."""
    vcd, gtkw = tmp_path / "b.vcd", tmp_path / "b.gtkw"

    simulate(blinker, clocks=20, vcd_path=vcd, gtkw_path=gtkw)
    signals = save_file_signals(gtkw)

    assert signals[0].endswith(".clk")
    assert signals[1].endswith(".rst")


def test_the_output_directory_is_created(blinker, tmp_path):
    vcd = tmp_path / "nested" / "deeper" / "b.vcd"

    simulate(blinker, clocks=5, vcd_path=vcd)

    assert vcd.is_file()


# --- reading the vcd header -------------------------------------------------


def test_signal_paths_come_from_the_vcd(blinker, tmp_path):
    vcd = tmp_path / "b.vcd"
    simulate(blinker, clocks=5, vcd_path=vcd)

    paths = vcd_signal_paths(vcd, CLOCK_SIGNALS)

    assert paths == ["bench.top.clk", "bench.top.rst"]


def test_only_the_shallowest_occurrence_is_used(blinker, tmp_path):
    """The clock appears in every scope that uses it."""
    vcd = tmp_path / "b.vcd"
    simulate(blinker, clocks=5, vcd_path=vcd)

    paths = vcd_signal_paths(vcd, ("clk",))

    assert paths == ["bench.top.clk"]
    assert "blinker" not in paths[0]


def test_a_missing_signal_is_simply_absent(blinker, tmp_path):
    vcd = tmp_path / "b.vcd"
    simulate(blinker, clocks=5, vcd_path=vcd)

    assert vcd_signal_paths(vcd, ("nonexistent",)) == []


def test_adding_a_clock_to_a_missing_save_file_is_harmless(tmp_path):
    assert add_clock_to_save(tmp_path / "nope.vcd", tmp_path / "nope.gtkw") == 0


def test_the_clock_is_not_added_twice(blinker, tmp_path):
    vcd, gtkw = tmp_path / "b.vcd", tmp_path / "b.gtkw"
    simulate(blinker, clocks=5, vcd_path=vcd, gtkw_path=gtkw)

    assert add_clock_to_save(vcd, gtkw) == 0


# --- the viewer command -----------------------------------------------------


def test_the_splash_is_suppressed(tmp_path):
    command = viewer_command(tmp_path / "b.vcd")

    assert "splash_disable on" in command


def test_the_view_is_zoomed_to_fit(tmp_path):
    command = viewer_command(tmp_path / "b.vcd")

    assert "do_initial_zoom_fit on" in command


def test_zoom_fit_can_be_turned_off(tmp_path):
    command = viewer_command(tmp_path / "b.vcd", zoom_fit=False)

    assert "do_initial_zoom_fit on" not in command


def test_the_save_file_is_passed_when_it_exists(blinker, tmp_path):
    vcd, gtkw = tmp_path / "b.vcd", tmp_path / "b.gtkw"
    simulate(blinker, clocks=5, vcd_path=vcd, gtkw_path=gtkw)

    command = viewer_command(vcd, gtkw)

    assert "--save" in command
    assert str(gtkw) in command


def test_a_missing_save_file_is_not_passed(tmp_path):
    command = viewer_command(tmp_path / "b.vcd", tmp_path / "absent.gtkw")

    assert "--save" not in command


@pytest.mark.skipif(
    not shutil.which("vcd2fst"), reason="needs vcd2fst, which ships with gtkwave"
)
def test_the_trace_is_converted_to_the_viewers_native_format(blinker, tmp_path):
    """Some GTKWave builds overflow on VCD; FST is its own format anyway."""
    vcd = tmp_path / "b.vcd"
    simulate(blinker, clocks=10, vcd_path=vcd)

    command = viewer_command(vcd)

    assert command[-1].endswith(".fst")
    assert os.path.getsize(command[-1]) > 0


def test_opening_without_a_viewer_is_reported(tmp_path, monkeypatch):
    import amaranth_companion.verify.waveform as waveform

    monkeypatch.setattr(waveform, "viewer_available", lambda: False)

    with pytest.raises(ViewerMissing):
        open_viewer(tmp_path / "b.vcd")


# --- the command line -------------------------------------------------------


def test_the_parser_defaults_are_sensible():
    args = build_parser("blink").parse_args([])

    assert args.clocks == DEFAULT_CLOCKS
    assert args.vcd_file == "blink.vcd"
    assert args.gtkw_file == "blink.gtkw"
    assert args.open is True


def test_the_viewer_can_be_suppressed():
    """So a run in CI writes a trace without trying to open a window."""
    assert build_parser("blink").parse_args(["--no-open"]).open is False


def test_the_clock_count_is_settable():
    assert build_parser("blink").parse_args(["-c", "250"]).clocks == 250


# --- from the editor --------------------------------------------------------


def test_running_a_design_writes_a_trace(qapp, tmp_path):
    design = open_example(find("blinker"))

    result = run_waveform(design, clocks=30, directory=tmp_path)

    assert result.ok, result.error
    assert os.path.getsize(result.vcd_path) > 0
    assert save_file_signals(result.gtkw_path)
    assert "30 clocks" in result.summary


def test_a_broken_design_is_reported_not_raised(qapp, tmp_path):
    from amaranth_companion.blocks.library import library
    from amaranth_companion.design import Design
    from amaranth_companion.module.instantiate import instantiate

    design = Design()
    instantiate(design.root, library().require("builtin.code"), text="class X(:\n")

    result = run_waveform(design, clocks=10, directory=tmp_path)

    assert not result.ok
    assert "Simulation failed" in result.summary


def test_the_trace_lands_beside_a_saved_design(qapp, tmp_path):
    design = open_example(find("blinker"))
    design.save(tmp_path / "mydesign.json")

    result = run_waveform(design, clocks=10)

    assert result.vcd_path == str(tmp_path / "mydesign.vcd")


# --- the generated package --------------------------------------------------


def test_the_package_has_a_main(qapp):
    files = generate_files(open_example(find("blinker")), "blink")

    assert "blink/__main__.py" in files
    assert "blink/_waveform.py" in files
    assert 'simulate_main(Top, "blink", argv)' in files["blink/__main__.py"]


def test_the_simulator_is_copied_into_the_package(qapp):
    """`python -m <package>` must not need amaranth-companion installed."""
    files = generate_files(open_example(find("blinker")), "blink")

    assert "amaranth_companion" not in "".join(files.values())


def test_running_the_generated_main_writes_a_waveform(qapp, tmp_path):
    """The end of the chain: canvas -> package -> `python -m blink` -> trace."""
    for name, content in generate_files(open_example(find("blinker")), "blink").items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    completed = subprocess.run(
        [sys.executable, "-m", "blink", "--clocks", "40", "--no-open"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ""},
        timeout=300,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "40 clocks" in completed.stdout
    assert (tmp_path / "blink.vcd").stat().st_size > 0
    assert save_file_signals(tmp_path / "blink.gtkw")
