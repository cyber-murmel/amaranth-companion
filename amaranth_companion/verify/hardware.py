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
import asyncio
import importlib
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

#: how a platform is named: ``module:ClassName``
PLATFORM_SEPARATOR = ":"

DEFAULT_BUILD_DIR = "build"


class PlatformMissing(RuntimeError):
    """The named platform is not installed."""


class ToolchainMissing(RuntimeError):
    """The programs needed to build for this platform are not installed."""


class ProgrammingFailed(RuntimeError):
    """The bitstream was built, but could not be loaded onto a board.

    Kept apart from a build failure because the two want different things of
    the user: one is a design to fix, the other a board to plug in. The
    bitstream is carried along so it can still be reported.
    """

    def __init__(self, message: str, bitstream: str = ""):
        super().__init__(message)
        self.bitstream = bitstream


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

    # built first and loaded on second, rather than asking the platform to do
    # both in one call: a board that cannot be reached must not cost the
    # bitstream, which took minutes and is perfectly good
    products = platform.build(top, name=name, do_program=False, build_dir=build_dir)
    bitstream = str(Path(build_dir) / _bitstream_name(platform, name))

    if program:
        program_board(platform, products, name, bitstream=bitstream)

    return bitstream


def program_board(
    platform, products, name: str = "top", *, bitstream: str = ""
) -> None:
    """Load built products onto an attached board.

    Raises :class:`ProgrammingFailed` for anything that goes wrong, so the
    caller can tell a board problem from a design problem.
    """
    try:
        with _event_loop():
            _program(platform, products, name)
    except Exception as error:
        raise ProgrammingFailed(
            f"{type(error).__name__}: {error}", bitstream
        ) from error


@contextmanager
def _event_loop():
    """Give ``asyncio.get_event_loop()`` something to find.

    A board programmed over USB is often reached through asyncio, and such a
    platform asks for the current event loop. Python used to make one on
    demand; since 3.12 asking without one raises instead, which is not
    something the platform can be expected to have known. Platforms that
    shell out to a flashing program are unaffected.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        yield  # already inside a loop; there is nothing to arrange
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def _program(platform, products, name: str) -> None:
    """Call the platform's programmer, once more if it forgot an import."""
    try:
        platform.toolchain_program(products, name)
    except NameError as error:
        if not _supply_missing_import(platform, error):
            raise
        platform.toolchain_program(products, name)


def _supply_missing_import(platform, error: NameError) -> bool:
    """Supply a module the platform uses but does not import; did it work?

    Not a bug of ours to fix, and not one worth being stopped by either: at
    the time of writing Glasgow's platform calls ``asyncio.get_event_loop``
    in a module that never imports ``asyncio``, so programming a board raises
    ``NameError`` before it reaches the hardware. The name is only supplied
    when the module really is missing it and it really is importable, and it
    is said out loud, because the honest fix belongs upstream.
    """
    missing = getattr(error, "name", "")
    owner = next(
        (
            klass
            for klass in type(platform).__mro__
            if "toolchain_program" in vars(klass)
        ),
        None,
    )
    module = sys.modules.get(owner.__module__) if owner is not None else None

    if not missing or module is None or hasattr(module, missing):
        return False

    try:
        setattr(module, missing, importlib.import_module(missing))
    except ImportError:
        return False

    print(
        f"warning: {module.__name__} uses {missing!r} without importing it; "
        f"supplying it so the board can be programmed",
        file=sys.stderr,
    )
    return True


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
    except ProgrammingFailed as error:
        # the bitstream is there either way, and worth saying so
        print(f"built {error.bitstream}")
        print(f"could not program the board: {error}", file=sys.stderr)
        return 1

    print(f"built {bitstream}")
    if args.program:
        print("programmed the attached board")
    return 0
