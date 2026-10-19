"""Running a design for a waveform, from the editor.

The simulation itself lives in :mod:`.waveform`, which is standalone so it can
be copied into generated packages. This is the editor's side of it: generate
the design, run it in a worker, and hand back where the trace landed.

The viewer is *not* launched from the worker. It outlives the run, so it has
to be started by the editor itself or it would die with the subprocess.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, Mapping, TYPE_CHECKING

from ..errors import locate
from .waveform import DEFAULT_CLOCKS, DEFAULT_PERIOD

if TYPE_CHECKING:
    from ..design import Design

log = getLogger(__name__)

#: a design that will not settle must not wedge the editor
DEFAULT_TIMEOUT = 120.0


@dataclass(frozen=True)
class WaveformResult:
    """Where a run put its trace, or why there is not one."""

    ok: bool
    vcd_path: str = ""
    gtkw_path: str = ""
    clocks: int = 0
    error: str = ""
    traceback: str = ""

    @property
    def summary(self) -> str:
        if not self.ok:
            return f"Simulation failed: {self.error}"
        return f"Simulated {self.clocks} clocks to {Path(self.vcd_path).name}"

    @classmethod
    def failed(cls, error: str) -> "WaveformResult":
        return cls(ok=False, error=error)


def output_paths(design: "Design", directory=None) -> tuple[str, str]:
    """Where to write the trace and its save file.

    Beside the design file when there is one, so a trace is easy to find
    again; otherwise somewhere temporary, because an unsaved design has no
    obvious home.
    """
    if directory is not None:
        root, stem = Path(directory), design.name
    elif design.path:
        root, stem = Path(design.path).parent, Path(design.path).stem
    else:
        root, stem = Path(mkdtemp(prefix="amaranth-companion-")), design.name

    return str(root / f"{stem}.vcd"), str(root / f"{stem}.gtkw")


def run_waveform(
    design: "Design",
    *,
    clocks: int = DEFAULT_CLOCKS,
    period: float = DEFAULT_PERIOD,
    directory=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> WaveformResult:
    """Generate the design, run it, and write a waveform."""
    from ..generate.python import DesignGenerator, GenerationError

    generator = DesignGenerator(design)
    try:
        source = generator.source()
    except GenerationError as error:
        return WaveformResult.failed(str(error))

    vcd_path, gtkw_path = output_paths(design, directory)
    request = {
        "source": source,
        "target": generator.top_name,
        "clocks": clocks,
        "period": period,
        "vcd_path": vcd_path,
        "gtkw_path": gtkw_path,
    }

    return _run_worker(request, clocks, timeout)


def _run_worker(
    request: Mapping[str, Any], clocks: int, timeout: float
) -> WaveformResult:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", __name__],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return WaveformResult.failed(f"did not finish within {timeout:g}s")
    except OSError as error:
        return WaveformResult.failed(f"could not start the simulator: {error}")

    if not completed.stdout.strip():
        detail = completed.stderr.strip().splitlines()
        return WaveformResult.failed(
            detail[-1] if detail else f"simulator exited with {completed.returncode}"
        )

    try:
        data = json.loads(completed.stdout)
    except ValueError as error:
        return WaveformResult.failed(f"malformed worker response: {error}")

    if not data.get("ok"):
        return WaveformResult(
            ok=False,
            error=data.get("error", "simulation failed"),
            traceback=data.get("traceback", ""),
        )

    return WaveformResult(
        ok=True,
        vcd_path=data.get("vcd_path", ""),
        gtkw_path=data.get("gtkw_path", ""),
        clocks=clocks,
    )


# --- worker -----------------------------------------------------------------


def run(
    source: str,
    target: str,
    clocks: int,
    period: float,
    vcd_path: str,
    gtkw_path: str,
) -> dict:
    """Elaborate ``target`` out of ``source`` and trace it."""
    from .waveform import simulate

    namespace: dict[str, Any] = {"__name__": "_amaranth_companion_design"}

    try:
        exec(compile(source, "<design>", "exec"), namespace)
    except Exception as error:
        located = locate(error, "<design>", "generated design: ")
        return {"ok": False, "error": located.message, "traceback": located.traceback}

    cls = namespace.get(target)
    if cls is None:
        return {"ok": False, "error": f"generated design has no {target!r}"}

    try:
        simulate(
            cls(),
            clocks=clocks,
            period=period,
            vcd_path=vcd_path,
            gtkw_path=gtkw_path,
        )
    except Exception as error:
        located = locate(error, "<design>")
        return {"ok": False, "error": located.message, "traceback": located.traceback}

    return {"ok": True, "vcd_path": vcd_path, "gtkw_path": gtkw_path}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
    except ValueError as error:
        json.dump({"ok": False, "error": f"malformed request: {error}"}, sys.stdout)
        return 1

    json.dump(
        run(
            request.get("source", ""),
            request.get("target", "Top"),
            request.get("clocks", DEFAULT_CLOCKS),
            request.get("period", DEFAULT_PERIOD),
            request.get("vcd_path", "design.vcd"),
            request.get("gtkw_path", "design.gtkw"),
        ),
        sys.stdout,
    )
    return 0


if "__main__" == __name__:
    sys.exit(main())
