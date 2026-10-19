"""Building a design for a board, and loading it onto one.

Like :mod:`.sby` and :mod:`.waveform`, this module is **standalone** -- stdlib
and Amaranth only -- because the code generator copies its source into every
exported package. ``python -m <package> build`` has to work on a machine that
has never heard of amaranth-companion.

The platform is named rather than imported directly, so a package generated
for a board can still be opened, read and simulated on a machine where that
board's support package is not installed; only ``build`` needs it.
"""

import argparse
import importlib
import shutil
import sys
from pathlib import Path

#: how a platform is named: ``module:ClassName``
PLATFORM_SEPARATOR = ":"

DEFAULT_BUILD_DIR = "build"


class PlatformMissing(RuntimeError):
    """The named platform is not installed."""


class ToolchainMissing(RuntimeError):
    """The programs needed to build for this platform are not installed."""


def load_platform(platform_id: str):
    """The platform class named by ``module:ClassName``."""
    module_name, separator, class_name = platform_id.partition(PLATFORM_SEPARATOR)
    if not separator:
        raise PlatformMissing(
            f"{platform_id!r} is not a platform name (expected module:ClassName)"
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise PlatformMissing(
            f"{platform_id!r} needs the {module_name.split('.')[0]!r} package: {error}"
        ) from error

    try:
        return getattr(module, class_name)
    except AttributeError as error:
        raise PlatformMissing(
            f"{module_name!r} has no platform {class_name!r}"
        ) from error


def required_tools(platform) -> tuple[str, ...]:
    """The toolchain programs ``platform`` will shell out to.

    Asked of the platform rather than kept in a table here: every Amaranth
    platform declares this, and a table would be one more thing to get wrong
    for each new FPGA family.
    """
    return tuple(getattr(platform, "required_tools", ()) or ())


def missing_tools(platform) -> list[str]:
    """Which of them are not installed.

    Checked up front so a missing toolchain is a sentence rather than a wall
    of traceback out of the middle of a build.
    """
    return [tool for tool in required_tools(platform) if not shutil.which(tool)]


def build(
    top,
    platform_id: str,
    *,
    build_dir: str = DEFAULT_BUILD_DIR,
    program: bool = False,
    name: str = "top",
) -> str:
    """Build ``top`` for ``platform_id``; returns the bitstream path.

    ``program`` loads it onto an attached board, which is the one step that
    needs the hardware actually plugged in.
    """
    platform = load_platform(platform_id)()

    absent = missing_tools(platform)
    if absent:
        raise ToolchainMissing(
            f"building for this board needs {', '.join(absent)} on PATH"
        )

    platform.build(top, name=name, do_program=program, build_dir=build_dir)

    bitstream = Path(build_dir) / _bitstream_name(platform, name)
    return str(bitstream)


def _bitstream_name(platform, name: str) -> str:
    """What the platform calls its output, asking it rather than guessing."""
    namer = getattr(platform, "bitstream_filename", None)
    if callable(namer):
        try:
            return namer(name)
        except Exception:
            pass
    return f"{name}.bin"


# --- command line -----------------------------------------------------------


def build_parser(
    name: str = "design", platform_id: str = ""
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"python -m {name} build",
        description="Build the design for a board, and optionally load it on.",
    )
    parser.add_argument(
        "-p",
        "--platform",
        default=platform_id,
        help="board to build for (default: %(default)s)",
    )
    parser.add_argument(
        "--build-dir",
        default=DEFAULT_BUILD_DIR,
        help="where to put the build products (default: %(default)s)",
    )
    parser.add_argument(
        "--program",
        action="store_true",
        help="load the bitstream onto an attached board",
    )
    return parser


def main(construct, name: str = "design", platform_id: str = "", argv=None) -> int:
    """Entry point for a generated package's ``build`` command."""
    args = build_parser(name, platform_id).parse_args(argv)

    if not args.platform:
        print(
            "no board chosen: pass --platform, or set one in the design",
            file=sys.stderr,
        )
        return 2

    try:
        bitstream = build(
            construct(),
            args.platform,
            build_dir=args.build_dir,
            program=args.program,
            name=name,
        )
    except (PlatformMissing, ToolchainMissing) as error:
        print(f"cannot build: {error}", file=sys.stderr)
        return 1

    print(f"built {bitstream}")
    if args.program:
        print("programmed the attached board")
    return 0
