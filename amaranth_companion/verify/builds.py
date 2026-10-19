"""Building a design for hardware, from the editor.

The build itself lives in :mod:`.hardware`, which is standalone so it can be
copied into generated packages. This is the editor's side: generate the
design, run the toolchain in a worker, and report where the bitstream landed.

A synthesis run takes minutes and prints a great deal; neither belongs in the
editor's process, which is why this goes through a subprocess like the other
long-running jobs.
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
from .hardware import DEFAULT_BUILD_DIR

if TYPE_CHECKING:
    from ..design import Design

log = getLogger(__name__)

#: synthesis and place-and-route are slow, but not unbounded
DEFAULT_TIMEOUT = 1800.0


@dataclass(frozen=True)
class BuildResult:
    """Where a build put its bitstream, or why there is not one."""

    ok: bool
    bitstream: str = ""
    build_dir: str = ""
    programmed: bool = False
    error: str = ""
    traceback: str = ""
    #: a missing toolchain or board package is worth saying differently from
    #: a design that does not build
    unavailable: bool = False

    @property
    def summary(self) -> str:
        if self.unavailable:
            return f"Cannot build: {self.error}"
        if not self.ok:
            return f"Build failed: {self.error}"
        if self.programmed:
            return f"Built and programmed {Path(self.bitstream).name}"
        return f"Built {Path(self.bitstream).name}"

    @classmethod
    def failed(cls, error: str, unavailable: bool = False) -> "BuildResult":
        return cls(ok=False, error=error, unavailable=unavailable)


def output_directory(design: "Design", directory=None) -> str:
    """Where to put build products.

    Beside the design file when there is one -- a bitstream is something you
    go and find afterwards -- and somewhere temporary otherwise.
    """
    if directory is not None:
        return str(directory)
    if design.path:
        return str(Path(design.path).parent / DEFAULT_BUILD_DIR)
    return mkdtemp(prefix="amaranth-companion-build-")


def run_build(
    design: "Design",
    *,
    program: bool = False,
    directory=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> BuildResult:
    """Generate the design and build it for the board it names."""
    from ..generate.python import DesignGenerator, GenerationError

    if not design.platform:
        return BuildResult.failed("this design does not name a board", unavailable=True)

    generator = DesignGenerator(design)
    try:
        source = generator.source()
    except GenerationError as error:
        return BuildResult.failed(str(error))

    build_dir = output_directory(design, directory)
    request = {
        "source": source,
        "target": generator.top_name,
        "platform": design.platform,
        "build_dir": build_dir,
        "program": program,
        "name": design.name,
    }

    return _run_worker(request, build_dir, program, timeout)


def _run_worker(
    request: Mapping[str, Any], build_dir: str, program: bool, timeout: float
) -> BuildResult:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", __name__],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return BuildResult.failed(f"did not finish within {timeout:g}s")
    except OSError as error:
        return BuildResult.failed(f"could not start the build: {error}")

    if not completed.stdout.strip():
        detail = completed.stderr.strip().splitlines()
        return BuildResult.failed(
            detail[-1] if detail else f"build exited with {completed.returncode}"
        )

    try:
        data = json.loads(completed.stdout)
    except ValueError as error:
        return BuildResult.failed(f"malformed worker response: {error}")

    if not data.get("ok"):
        return BuildResult(
            ok=False,
            error=data.get("error", "build failed"),
            traceback=data.get("traceback", ""),
            unavailable=bool(data.get("unavailable")),
            build_dir=build_dir,
        )

    return BuildResult(
        ok=True,
        bitstream=data.get("bitstream", ""),
        build_dir=build_dir,
        programmed=program,
    )


# --- worker -----------------------------------------------------------------


def run(
    source: str,
    target: str,
    platform_id: str,
    build_dir: str,
    program: bool,
    name: str,
) -> dict:
    """Elaborate ``target`` out of ``source`` and build it."""
    from .hardware import PlatformMissing, ToolchainMissing, build

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
        bitstream = build(
            cls(),
            platform_id,
            build_dir=build_dir,
            program=program,
            name=name,
        )
    except (PlatformMissing, ToolchainMissing) as error:
        return {"ok": False, "error": str(error), "unavailable": True}
    except Exception as error:
        located = locate(error, "<design>")
        return {"ok": False, "error": located.message, "traceback": located.traceback}

    return {"ok": True, "bitstream": bitstream}


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
            request.get("platform", ""),
            request.get("build_dir", DEFAULT_BUILD_DIR),
            bool(request.get("program")),
            request.get("name", "top"),
        ),
        sys.stdout,
    )
    return 0


if "__main__" == __name__:
    sys.exit(main())
