"""Running a design for a while and looking at the waveform.

This is the "what does it actually do" counterpart to the testbench and formal
blocks: no assertions, just run the thing for a given number of clocks, write
the trace, and open a viewer at it.

Like :mod:`.sby`, this module is **deliberately standalone** -- stdlib and
Amaranth only. The code generator copies its source into every exported
package so that ``python -m <package>`` simulates and writes a waveform
without amaranth-companion installed. Keep it that way: an import from a
sibling module here becomes a broken generated file.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_CLOCKS = 100
DEFAULT_PERIOD = 1e-6

#: how deep into submodules to go looking for signals worth plotting
DEFAULT_TRACE_DEPTH = 3

#: shown above everything else, because a clocked waveform is unreadable
#: without them. They cannot be passed as traces -- ``ClockSignal`` is not a
#: concrete signal until the design is elaborated -- so they are added to the
#: viewer's save file afterwards, using the paths the VCD itself reports.
CLOCK_SIGNALS = ("clk", "rst")

VIEWER = "gtkwave"

#: GTKWave converter, shipped alongside it. The VCD loader in some GTKWave
#: builds overflows on perfectly valid files, and FST is its native format
#: anyway -- smaller, faster, and the path that actually works.
CONVERTER = "vcd2fst"

#: ``splash_disable`` suppresses the mascot; ``do_initial_zoom_fit`` frames
#: the whole trace on open. Both are plain rc variables, which avoids
#: GTKWave's Tcl scripting path entirely.
VIEWER_RCVARS = ("splash_disable on", "do_initial_zoom_fit on")


class ViewerMissing(RuntimeError):
    """No waveform viewer is installed."""


# --- simulating -------------------------------------------------------------


def waveform_traces(dut, depth: int = DEFAULT_TRACE_DEPTH) -> list:
    """The signals worth plotting: the design's, and its submodules'.

    Internal state is included deliberately -- a blinker's ``counter`` is the
    thing you want to see next to its output, and the blink example's own
    ``ports`` list says as much by including it.
    """
    from amaranth.hdl import Signal

    traces: list = []
    seen: set[int] = set()

    def visit(obj, level: int) -> None:
        if level > depth or id(obj) in seen:
            return
        seen.add(id(obj))

        for value in vars(obj).values():
            if isinstance(value, Signal):
                if not any(value is trace for trace in traces):
                    traces.append(value)
            elif hasattr(value, "elaborate"):
                visit(value, level + 1)

    visit(dut, 0)
    return traces


def _add_clock(simulator, period: float) -> bool:
    """Drive ``sync`` if the design has one; returns whether it does.

    A fragment reports no domains until the simulator has elaborated it, so
    asking is the only reliable check.
    """
    try:
        simulator.add_clock(period)
    except NameError:
        return False
    return True


def simulate(
    dut,
    *,
    clocks: int = DEFAULT_CLOCKS,
    period: float = DEFAULT_PERIOD,
    vcd_path="design.vcd",
    gtkw_path=None,
    traces=None,
) -> str:
    """Run ``dut`` for ``clocks`` cycles, writing a VCD and a viewer save file.

    Returns the VCD path. The save file is what makes the viewer open on the
    signals that matter rather than on nothing at all.

    ``clocks`` only means anything for a design with a clock domain; a purely
    combinational one is settled once and produces a single-instant trace.
    """
    from amaranth.sim import Simulator

    vcd_path = str(vcd_path)
    Path(vcd_path).parent.mkdir(parents=True, exist_ok=True)

    simulator = Simulator(dut)
    clocked = _add_clock(simulator, period)

    chosen = list(traces) if traces is not None else waveform_traces(dut)

    with simulator.write_vcd(
        vcd_path, gtkw_file=str(gtkw_path) if gtkw_path else None, traces=chosen
    ):
        if clocked:
            simulator.run_until(clocks * period)
        else:
            # a combinational design has no events to advance through, and
            # `run_until` would wait forever for one; it settles and that is
            # the whole waveform. Use a testbench block to drive one.
            simulator.run()

    if gtkw_path:
        add_clock_to_save(vcd_path, gtkw_path)

    return vcd_path


def vcd_signal_paths(vcd_path, names) -> list:
    """Dotted paths of ``names`` in a VCD header, shallowest occurrence only.

    The clock appears in every scope that uses it; only the outermost one is
    wanted, and guessing the scope prefix instead of reading it would break
    the moment the generated hierarchy changed.
    """
    scope: list[str] = []
    found: dict[str, str] = {}

    with open(vcd_path) as handle:
        for line in handle:
            line = line.strip()
            parts = line.split()

            if line.startswith("$scope") and len(parts) >= 3:
                scope.append(parts[2])
            elif line.startswith("$upscope"):
                if scope:
                    scope.pop()
            elif line.startswith("$var") and len(parts) >= 5:
                name = parts[4]
                if name in names and name not in found:
                    found[name] = ".".join(scope + [name])
            elif line.startswith("$enddefinitions"):
                break

    return [found[name] for name in names if name in found]


def add_clock_to_save(vcd_path, gtkw_path, names=CLOCK_SIGNALS) -> int:
    """Put the clock and reset at the top of the viewer's signal list.

    Returns how many were added, which is zero for a design with no clock.
    """
    gtkw = Path(gtkw_path)
    if not gtkw.is_file():
        return 0

    paths = vcd_signal_paths(vcd_path, names)
    if not paths:
        return 0

    lines = gtkw.read_text().splitlines()
    existing = set(lines)
    paths = [path for path in paths if path not in existing]
    if not paths:
        return 0

    # after the first format directive, which is where the signal list starts
    insert_at = next(
        (index + 1 for index, line in enumerate(lines) if line.startswith("@")),
        len(lines),
    )
    lines[insert_at:insert_at] = paths
    gtkw.write_text("\n".join(lines) + "\n")

    return len(paths)


# --- viewing ----------------------------------------------------------------


def viewer_available() -> bool:
    return bool(shutil.which(VIEWER))


def to_fst(vcd_path) -> str:
    """Convert to GTKWave's native format, or hand back the VCD unchanged."""
    if not shutil.which(CONVERTER):
        return str(vcd_path)

    fst_path = str(Path(vcd_path).with_suffix(".fst"))
    try:
        subprocess.run(
            [CONVERTER, str(vcd_path), fst_path],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return str(vcd_path)

    return fst_path


def viewer_command(vcd_path, gtkw_path=None, *, zoom_fit: bool = True) -> list:
    """The command line that opens ``vcd_path`` the way we want it."""
    command = [VIEWER]
    for variable in VIEWER_RCVARS:
        if variable.startswith("do_initial_zoom_fit") and not zoom_fit:
            continue
        command += ["--rcvar", variable]

    if gtkw_path and Path(gtkw_path).is_file():
        command += ["--save", str(gtkw_path)]

    command.append(to_fst(vcd_path))
    return command


def open_viewer(vcd_path, gtkw_path=None, *, zoom_fit: bool = True, wait=False):
    """Open the waveform viewer on ``vcd_path``.

    Detached by default: the viewer is something the user keeps open and
    pokes at, so neither the editor nor ``python -m <package>`` should sit
    waiting for them to close it.
    """
    if not viewer_available():
        raise ViewerMissing(f"{VIEWER} is not on PATH")

    command = viewer_command(vcd_path, gtkw_path, zoom_fit=zoom_fit)

    if wait:
        return subprocess.run(command)

    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# --- command line -----------------------------------------------------------


def build_parser(name: str = "design") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"python -m {name}",
        description="Simulate the design and write a waveform.",
    )
    parser.add_argument(
        "-c",
        "--clocks",
        type=int,
        default=DEFAULT_CLOCKS,
        help="how many clock cycles to run (default: %(default)s)",
    )
    parser.add_argument(
        "-p",
        "--period",
        type=float,
        default=DEFAULT_PERIOD,
        help="clock period in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--vcd-file",
        default=f"{name}.vcd",
        help="where to write the waveform (default: %(default)s)",
    )
    parser.add_argument(
        "--gtkw-file",
        default=f"{name}.gtkw",
        help="where to write the viewer save file (default: %(default)s)",
    )
    parser.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="open the waveform viewer when the run finishes",
    )
    return parser


def main(build, name: str = "design", argv=None) -> int:
    """Entry point for a generated package's ``__main__``.

    ``build`` is called with no arguments and must return the design to run --
    normally the generated ``Top``.
    """
    args = build_parser(name).parse_args(argv)

    vcd_path = simulate(
        build(),
        clocks=args.clocks,
        period=args.period,
        vcd_path=args.vcd_file,
        gtkw_path=args.gtkw_file,
    )
    print(f"wrote {vcd_path} ({args.clocks} clocks)")

    if not args.open:
        return 0

    try:
        open_viewer(vcd_path, args.gtkw_file)
    except ViewerMissing as error:
        print(f"not opening a viewer: {error}", file=sys.stderr)
        return 0

    return 0
