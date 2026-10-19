"""Running a formal block against the design around it.

A formal block sits beside the implementation it constrains, the way a
testbench does, and states what must always hold rather than what happens for
one stimulus::

    MODES = ("bmc", "cover")
    DEPTH = 20

    def formal(m, dut):
        m.d.comb += Assert(dut.counter < dut.half_period)
        m.d.comb += Cover(dut.blink_out == 1)

Each mode is a separate check and a separate result, which is why the blink
example has three tests for one spec.

Like simulation, this runs in a worker process: a proof can take arbitrarily
long, and the editor has to stay usable while it does.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Mapping, Sequence, TYPE_CHECKING

from ..blocks.definition import BlockKind
from ..errors import locate
from .sby import DEFAULT_DEPTH, MODES

if TYPE_CHECKING:
    from ..design import Design
    from ..module.element import Node

log = getLogger(__name__)

#: the function a formal block is expected to define
ENTRY_POINT = "formal"

#: module-level names a formal block may set to configure its own checking
MODES_NAME = "MODES"
DEPTH_NAME = "DEPTH"

#: modes checked when the block does not say
DEFAULT_MODES = ("bmc", "cover")

#: the filename the spec is compiled under, so its frames are findable
FORMAL_FILENAME = "<formal>"

#: a proof is allowed to be slow, but not unbounded
DEFAULT_TIMEOUT = 600.0


@dataclass(frozen=True)
class FormalResult:
    """How one mode of one formal block came out."""

    ok: bool
    name: str = ""
    mode: str = ""
    error: str = ""
    traceback: str = ""
    trace_path: str = ""
    line: int | None = None
    skipped: bool = False

    @property
    def summary(self) -> str:
        label = f"{self.name} [{self.mode}]" if self.mode else self.name
        if self.skipped:
            return f"{label}: skipped ({self.error})"
        if self.ok:
            return f"{label}: passed"
        if self.line:
            return f"{label}: line {self.line}: {self.error}"
        return f"{label}: {self.error}"

    @classmethod
    def from_dict(cls, data: Mapping, name: str = "") -> "FormalResult":
        return cls(
            ok=bool(data.get("ok")),
            name=name or data.get("name", ""),
            mode=data.get("mode", ""),
            error=data.get("error", ""),
            traceback=data.get("traceback", ""),
            trace_path=data.get("trace_path", ""),
            line=data.get("line"),
            skipped=bool(data.get("skipped")),
        )

    @classmethod
    def failed(
        cls, error: str, name: str = "", mode: str = "", skipped: bool = False
    ) -> "FormalResult":
        return cls(ok=False, name=name, mode=mode, error=error, skipped=skipped)


# --- client -----------------------------------------------------------------


def declared_modes(source: str) -> tuple[Sequence[str], int]:
    """What the block asked to be checked for, read without running it.

    Parsed rather than executed: the editor wants to label the checks before
    anything is proved, and the spec may not even be valid yet.
    """
    import ast

    modes: Sequence[str] = DEFAULT_MODES
    depth = DEFAULT_DEPTH

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return modes, depth

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        try:
            value = ast.literal_eval(node.value)
        except ValueError:
            continue

        if target.id == MODES_NAME and isinstance(value, (list, tuple)):
            chosen = [str(item) for item in value if str(item) in MODES]
            if chosen:
                modes = tuple(chosen)
        elif target.id == DEPTH_NAME and isinstance(value, int):
            depth = value

    return modes, depth


def run_formal(
    design: "Design",
    node: "Node",
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[FormalResult]:
    """Check ``node``'s properties, one result per mode it asks for."""
    from ..generate.python import DesignGenerator, GenerationError
    from .sby import formal_tools_available

    if node.kind is not BlockKind.FORMAL:
        return [FormalResult.failed("not a formal block", node.title)]

    modes, depth = declared_modes(node.text)

    # a spec that does not even compile is the user's typo, and worth saying
    # so whether or not a prover is installed
    try:
        compile(node.text, FORMAL_FILENAME, "exec")
    except SyntaxError as error:
        located = locate(error, FORMAL_FILENAME)
        return [
            FormalResult(
                ok=False,
                name=node.title,
                mode=mode,
                error=located.message,
                line=located.line,
            )
            for mode in modes
        ]

    if not formal_tools_available():
        return [
            FormalResult.failed(
                "`sby` and `yosys` are not on PATH", node.title, mode, skipped=True
            )
            for mode in modes
        ]

    generator = DesignGenerator(design)
    try:
        source = generator.source()
    except GenerationError as error:
        return [FormalResult.failed(str(error), node.title, mode) for mode in modes]

    target = generator.class_for(node.module)
    if target is None:
        return [
            FormalResult.failed(
                "could not work out what this spec constrains", node.title, mode
            )
            for mode in modes
        ]

    results = []
    for mode in modes:
        request = {
            "source": source,
            "target": target,
            "formal": node.text,
            "mode": mode,
            "depth": depth,
        }
        results.append(_run_worker(request, node.title, mode, timeout))

    return results


def _run_worker(
    request: Mapping[str, Any], name: str, mode: str, timeout: float
) -> FormalResult:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", __name__],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return FormalResult.failed(f"did not finish within {timeout:g}s", name, mode)
    except OSError as error:
        return FormalResult.failed(f"could not start the prover: {error}", name, mode)

    if not completed.stdout.strip():
        detail = completed.stderr.strip().splitlines()
        return FormalResult.failed(
            detail[-1] if detail else f"prover exited with {completed.returncode}",
            name,
            mode,
        )

    try:
        return FormalResult.from_dict(json.loads(completed.stdout), name)
    except ValueError as error:
        return FormalResult.failed(f"malformed worker response: {error}", name, mode)


def run_all(design: "Design", **kwargs) -> list[FormalResult]:
    """Check every formal block anywhere in the design."""
    results: list[FormalResult] = []
    for module in design.walk():
        for node in module.nodes.values():
            if node.kind is BlockKind.FORMAL:
                results.extend(run_formal(design, node, **kwargs))
    return results


def formal_nodes(design: "Design") -> list["Node"]:
    """Every formal block in the design, outermost first."""
    return [
        node
        for module in design.walk()
        for node in module.nodes.values()
        if node.kind is BlockKind.FORMAL
    ]


# --- worker -----------------------------------------------------------------


def check(
    source: str,
    target: str,
    spec: str,
    mode: str = "bmc",
    depth: int = DEFAULT_DEPTH,
) -> dict:
    """Elaborate ``target`` and prove ``spec`` about it in ``mode``."""
    from .sby import FormalToolsMissing, assert_formal

    namespace: dict[str, Any] = {"__name__": "_amaranth_companion_design"}

    try:
        exec(compile(source, "<design>", "exec"), namespace)
    except Exception as error:
        return _failure(error, mode, "generated design: ")

    cls = namespace.get(target)
    if cls is None:
        return {
            "ok": False,
            "mode": mode,
            "error": f"generated design has no {target!r}",
        }

    try:
        exec(compile(spec, FORMAL_FILENAME, "exec"), namespace)
    except Exception as error:
        return _failure(error, mode)

    body = namespace.get(ENTRY_POINT)
    if body is None:
        return {
            "ok": False,
            "mode": mode,
            "error": f"formal block defines no `def {ENTRY_POINT}(m, dut)`",
        }

    try:
        assert_formal(cls(), body, mode=mode, depth=depth)
    except AssertionError as error:
        message, _, trace = str(error).partition("\ncounterexample trace: ")
        return {
            "ok": False,
            "mode": mode,
            "error": message,
            "trace_path": trace,
            "line": None,
        }
    except FormalToolsMissing as error:
        return {"ok": False, "mode": mode, "error": str(error), "skipped": True}
    except Exception as error:
        return _failure(error, mode)

    return {"ok": True, "mode": mode}


def _failure(error: BaseException, mode: str, prefix: str = "") -> dict:
    located = locate(error, FORMAL_FILENAME, prefix)
    return {
        "ok": False,
        "mode": mode,
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
        check(
            request.get("source", ""),
            request.get("target", ""),
            request.get("formal", ""),
            request.get("mode", "bmc"),
            request.get("depth", DEFAULT_DEPTH),
        ),
        sys.stdout,
    )
    return 0


if "__main__" == __name__:
    sys.exit(main())
