"""Running a testbench block against the design around it.

A testbench block sits in the same graph as the implementation it exercises,
and drives the block that graph *is*: put one inside a Blinker and it drives
the Blinker. The block defines one coroutine::

    async def testbench(ctx, dut):
        ctx.set(dut.a_in, 1)
        await ctx.tick()
        assert ctx.get(dut.o_out) == 0

``ctx`` is the Amaranth simulator context and ``dut`` the elaborated block, so
there are no magic globals to learn -- and a testbench copied out of the editor
is still valid Python.

Simulations run in a worker process for the same reason introspection does: a
testbench that never returns, or that fails an assertion deep inside Amaranth,
must cost a subprocess rather than the user's unsaved design.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Mapping, TYPE_CHECKING

from ..blocks.definition import BlockKind
from ..errors import locate

if TYPE_CHECKING:
    from ..design import Design
    from ..module.element import Node

log = getLogger(__name__)

#: the coroutine a testbench block is expected to define
ENTRY_POINT = "testbench"

#: the filename the testbench is compiled under, which is what makes its own
#: frames findable when an assertion fires deep inside the simulator
TESTBENCH_FILENAME = "<testbench>"

#: simulated clock period, when the design has a synchronous domain
DEFAULT_CLOCK_PERIOD = 1e-6

#: a testbench that never returns must not wedge the editor
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class SimulationResult:
    """How a testbench run went."""

    ok: bool
    name: str = ""
    error: str = ""
    traceback: str = ""
    vcd_path: str = ""
    #: line in the testbench block the failure came from
    line: int | None = None

    @property
    def summary(self) -> str:
        if self.ok:
            return f"{self.name}: passed"
        if self.line:
            return f"{self.name}: line {self.line}: {self.error}"
        return f"{self.name}: {self.error}"

    @classmethod
    def from_dict(cls, data: Mapping, name: str = "") -> "SimulationResult":
        return cls(
            ok=bool(data.get("ok")),
            name=name or data.get("name", ""),
            error=data.get("error", ""),
            traceback=data.get("traceback", ""),
            vcd_path=data.get("vcd_path", ""),
            line=data.get("line"),
        )

    @classmethod
    def failed(
        cls, error: str, name: str = "", line: int | None = None
    ) -> "SimulationResult":
        return cls(ok=False, name=name, error=error, line=line)


# --- client -----------------------------------------------------------------


def run_testbench(
    design: "Design",
    node: "Node",
    *,
    vcd_path: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> SimulationResult:
    """Generate the design, then run ``node``'s testbench against it."""
    from ..generate.python import DesignGenerator, GenerationError

    if node.kind is not BlockKind.TESTBENCH:
        return SimulationResult.failed("not a testbench block", node.title)

    generator = DesignGenerator(design)
    try:
        source = generator.source()
    except GenerationError as error:
        return SimulationResult.failed(str(error), node.title)

    target = generator.class_for(node.module)
    if target is None:
        return SimulationResult.failed(
            "could not work out what this testbench drives", node.title
        )

    request = {
        "source": source,
        "target": target,
        "testbench": node.text,
        "vcd_path": vcd_path,
    }
    return _run_worker(request, node.title, timeout)


def _run_worker(
    request: Mapping[str, Any], name: str, timeout: float
) -> SimulationResult:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", __name__],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SimulationResult.failed(f"did not finish within {timeout:g}s", name)
    except OSError as error:
        return SimulationResult.failed(f"could not start the simulator: {error}", name)

    if not completed.stdout.strip():
        detail = completed.stderr.strip().splitlines()
        return SimulationResult.failed(
            detail[-1] if detail else f"simulator exited with {completed.returncode}",
            name,
        )

    try:
        return SimulationResult.from_dict(json.loads(completed.stdout), name)
    except ValueError as error:
        return SimulationResult.failed(f"malformed worker response: {error}", name)


def run_all(design: "Design", **kwargs) -> list[SimulationResult]:
    """Run every testbench block anywhere in the design."""
    results = []
    for module in design.walk():
        for node in module.nodes.values():
            if node.kind is BlockKind.TESTBENCH:
                results.append(run_testbench(design, node, **kwargs))
    return results


# --- worker -----------------------------------------------------------------


def simulate(
    source: str,
    target: str,
    testbench: str,
    vcd_path: str | None = None,
) -> dict:
    """Elaborate ``target`` out of ``source`` and run ``testbench`` on it.

    Runs in the worker process; returns the response dict rather than printing
    it, so the logic can be tested without spawning anything.
    """
    from amaranth.sim import Simulator

    namespace: dict[str, Any] = {"__name__": "_amaranth_companion_design"}

    try:
        exec(compile(source, "<design>", "exec"), namespace)
    except Exception as error:
        return _failure(error, "generated design: ")

    cls = namespace.get(target)
    if cls is None:
        return {"ok": False, "error": f"generated design has no {target!r}"}

    try:
        exec(compile(testbench, TESTBENCH_FILENAME, "exec"), namespace)
    except Exception as error:
        return _failure(error)

    body = namespace.get(ENTRY_POINT)
    if body is None:
        return {
            "ok": False,
            "error": f"testbench block defines no `async def {ENTRY_POINT}(ctx, dut)`",
        }

    try:
        dut = cls()
        simulator = Simulator(dut)
        _add_clock(simulator)

        # a real coroutine function, not a lambda: the simulator inspects what
        # it is handed and rejects anything that is not async
        async def entry(ctx):
            await body(ctx, dut)

        simulator.add_testbench(entry)

        if vcd_path:
            with simulator.write_vcd(vcd_path):
                simulator.run()
        else:
            simulator.run()
    except Exception as error:
        return _failure(error)

    return {"ok": True, "vcd_path": vcd_path or ""}


def _add_clock(simulator) -> None:
    """Drive ``sync`` if the design has one.

    Asked for rather than inspected: a fragment reports no domains until the
    simulator has elaborated it, so the simulator is the only thing that
    actually knows. A purely combinational design raises here, and has no
    clock to drive.
    """
    try:
        simulator.add_clock(DEFAULT_CLOCK_PERIOD)
    except NameError:
        log.debug("design has no sync domain; running without a clock")


def _failure(error: BaseException, prefix: str = "") -> dict:
    located = locate(error, TESTBENCH_FILENAME, prefix)
    return {
        "ok": False,
        "error": located.message,
        "line": located.line,
        "traceback": located.traceback,
    }


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
    except ValueError as error:
        json.dump({"ok": False, "error": f"malformed request: {error}"}, sys.stdout)
        return 1

    json.dump(
        simulate(
            request.get("source", ""),
            request.get("target", ""),
            request.get("testbench", ""),
            request.get("vcd_path"),
        ),
        sys.stdout,
    )
    return 0


if "__main__" == __name__:
    sys.exit(main())
