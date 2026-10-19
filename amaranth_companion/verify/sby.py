"""Proving properties about a design with SymbiYosys.

Amaranth used to ship ``FHDLTestCase.assertFormal`` for this; it was removed,
along with ``Past``/``Rose``/``Fell``/``Stable``, so the editor carries its own.

This module is **deliberately standalone** -- stdlib and Amaranth only, nothing
from the rest of amaranth-companion. The code generator emits its source
verbatim into the test file it writes, so a generated design's formal tests run
in CI with the editor nowhere in sight. Keep it that way: an import from a
sibling module here becomes a broken generated file.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

#: the three things SymbiYosys can be asked to do. ``bmc`` looks for a
#: counterexample within ``depth`` cycles, ``cover`` checks the cover
#: statements are reachable, ``prove`` attempts unbounded induction.
MODES = ("bmc", "cover", "prove")

DEFAULT_MODE = "bmc"
DEFAULT_DEPTH = 20
DEFAULT_ENGINE = "smtbmc z3"
DEFAULT_TIMEOUT = 300.0

#: sby's exit code when a property does not hold, as opposed to a tooling error
FAILURE_RETURNCODE = 2

JOB_TEMPLATE = """\
[options]
mode {mode}
depth {depth}

[engines]
{engine}

[script]
read_rtlil design.il
prep -top top

[files]
design.il
"""


class FormalToolsMissing(RuntimeError):
    """SymbiYosys or Yosys is not installed."""


def formal_tools_available() -> bool:
    """Whether a formal check can run at all."""
    return bool(shutil.which("sby") and shutil.which("yosys"))


def design_ports(dut) -> list:
    """The signals to expose to the solver.

    Generated classes carry a ``ports`` property; anything else is scanned for
    the ``_in``/``_out`` attributes the editor's naming convention produces.
    """
    from amaranth.hdl import Signal

    declared = getattr(dut, "ports", None)
    if declared:
        return list(declared)

    return [
        value
        for name, value in vars(dut).items()
        if isinstance(value, Signal) and (name.endswith("_in") or name.endswith("_out"))
    ]


def build_rtlil(dut, formal) -> str:
    """Elaborate ``dut`` with its properties attached, as RTLIL text.

    ``formal(m, dut)`` is called inside a wrapper module, so the properties it
    adds sit alongside the design rather than inside it -- a block's own source
    stays free of the spec that checks it.
    """
    from amaranth.back import rtlil
    from amaranth.hdl import ClockDomain, Elaboratable, Module

    class FormalTop(Elaboratable):
        def elaborate(self, platform):
            m = Module()
            m.submodules.dut = dut
            if formal is not None:
                formal(m, dut)
            return m

    # the solver needs the clock and reset as inputs it can drive, and a
    # design with no sync logic still needs the domain to exist for `prove`
    sync = ClockDomain()
    top = Module()
    top.domains += sync
    top.submodules += FormalTop()

    return rtlil.convert(top, ports=[sync.clk, sync.rst] + design_ports(dut))


def run_sby(
    rtlil_text: str,
    *,
    mode: str = DEFAULT_MODE,
    depth: int = DEFAULT_DEPTH,
    engine: str = DEFAULT_ENGINE,
    timeout: float = DEFAULT_TIMEOUT,
    directory=None,
) -> tuple[bool, str, str]:
    """Run one SymbiYosys job; returns ``(passed, output, trace path)``."""
    if mode not in MODES:
        raise ValueError(f"unknown formal mode {mode!r}, expected one of {MODES}")

    if not formal_tools_available():
        raise FormalToolsMissing("formal verification needs `sby` and `yosys` on PATH")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(directory) if directory else Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        (root / "design.il").write_text(rtlil_text)
        (root / "job.sby").write_text(
            JOB_TEMPLATE.format(mode=mode, depth=depth, engine=engine)
        )

        completed = subprocess.run(
            ["sby", "-f", "job.sby"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = completed.stdout + completed.stderr
        trace = _trace_path(output, root)

        if completed.returncode == 0:
            return True, output, ""
        if completed.returncode == FAILURE_RETURNCODE:
            return False, output, trace

        raise RuntimeError(
            f"sby failed to run (exit {completed.returncode}):\n{output}"
        )


def _trace_path(output: str, root: Path) -> str:
    """The counterexample sby wrote, if it wrote one."""
    for line in output.splitlines():
        marker = "counterexample trace:"
        if marker in line:
            return str(root / line.split(marker, 1)[1].strip())
    return ""


def assert_formal(
    dut,
    formal=None,
    *,
    mode: str = DEFAULT_MODE,
    depth: int = DEFAULT_DEPTH,
    engine: str = DEFAULT_ENGINE,
    timeout: float = DEFAULT_TIMEOUT,
    directory=None,
) -> None:
    """Check ``dut``'s properties, raising ``AssertionError`` if any fail.

    The replacement for the ``assertFormal`` Amaranth used to provide. The
    message names the counterexample trace, because a failed proof without one
    tells you nothing you can act on.
    """
    passed, output, trace = run_sby(
        build_rtlil(dut, formal),
        mode=mode,
        depth=depth,
        engine=engine,
        timeout=timeout,
        directory=directory,
    )

    if passed:
        return

    detail = _failure_detail(output)
    message = f"formal {mode} failed"
    if detail:
        message = f"{message}: {detail}"
    if trace:
        message = f"{message}\ncounterexample trace: {trace}"

    raise AssertionError(message)


def _failure_detail(output: str) -> str:
    """The most useful line sby printed about the failure."""
    for line in output.splitlines():
        for marker in ("Assert failed", "Unreached cover statement", "Assume failed"):
            if marker in line:
                return line.split("]", 1)[-1].strip()
    return ""
