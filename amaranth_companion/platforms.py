"""The boards a design can be built for, and the IOs they offer.

Platforms are not bundled: they come from whatever is installed --
``amaranth-boards`` for the common development boards, and the ``glasgow``
package for the Glasgow Interface Explorer. The registry therefore reports
what is *available on this machine*, and a design naming a platform that is
not installed says so rather than failing obscurely.

Two kinds of IO are offered, because real platforms have both:

* **requested** resources -- ``platform.request("led", 0)``, the usual case
* **named ports** -- a mapping the platform exposes directly. Glasgow does
  this: its constructor claims the LED and port pins for itself, so ``led 0``
  cannot be requested, and the pins appear as ``glasgow_pins["LED0"]``
  instead. A block naming ``LED0`` has to generate the other call.
"""

import importlib
import inspect
import pkgutil
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from logging import getLogger
from typing import Any, Iterator

log = getLogger(__name__)

#: packages searched for platform classes, in the order they are offered
PLATFORM_PACKAGES = ("amaranth_boards", "glasgow.hardware.platform")

#: attribute a platform may expose mapping names to ready-made ports
NAMED_PORTS_ATTRIBUTE = "glasgow_pins"

#: modules in those packages that define no boards
SKIP_MODULES = {"test", "resources", "extensions"}


class IOKind(Enum):
    """How the generated code has to reach an IO."""

    #: ``platform.request(name, number, dir="-")``
    REQUEST = "request"
    #: ``platform.<attribute>[name]``
    NAMED = "named"


@dataclass(frozen=True)
class IOSpec:
    """One IO a design can attach to."""

    #: what the user picks, and what a resource block stores
    id: str
    kind: IOKind
    #: ``request`` only
    name: str = ""
    number: int = 0
    #: "i", "o" or "io", taken from the platform rather than guessed
    direction: str = "io"

    @property
    def is_input(self) -> bool:
        return self.direction == "i"

    @property
    def is_output(self) -> bool:
        return self.direction == "o"

    @property
    def label(self) -> str:
        return f"{self.id}  ({self.direction})"


@dataclass(frozen=True)
class PlatformSpec:
    """A board that can be built for."""

    id: str
    label: str
    module: str
    class_name: str

    @property
    def vendor(self) -> str:
        return self.module.split(".")[0]

    def load(self) -> type:
        """Import and return the platform class."""
        return getattr(importlib.import_module(self.module), self.class_name)


# --- discovery --------------------------------------------------------------


def _is_platform(value: Any) -> bool:
    """Whether ``value`` is a concrete, buildable platform class."""
    if not inspect.isclass(value) or not value.__name__.endswith("Platform"):
        return False
    # `_GlasgowRevCPlatform` is a shared base, not a board you can pick
    if value.__name__.startswith("_") or inspect.isabstract(value):
        return False

    try:
        from amaranth.build.plat import Platform
    except ImportError:  # pragma: no cover - amaranth is a hard dependency
        return False

    if not issubclass(value, Platform):
        return False

    # A board declares its own pins as a plain list. A vendor base class --
    # `GowinPlatform`, `SiliconBluePlatform` -- leaves `resources` an abstract
    # property and is not something you can build for. Testing for `device`
    # instead would quietly drop every Gowin board, which names its chip
    # `part` rather than `device`.
    return isinstance(getattr(value, "resources", None), (list, tuple))


def _modules(package: str) -> Iterator[str]:
    try:
        root = importlib.import_module(package)
    except ImportError:
        log.debug("platform package %s is not installed", package)
        return

    for info in pkgutil.iter_modules(root.__path__):
        if info.name.startswith("_") or info.name in SKIP_MODULES:
            continue
        yield f"{package}.{info.name}"


@lru_cache(maxsize=1)
def list_platforms() -> tuple[PlatformSpec, ...]:
    """Every platform class installed on this machine.

    Cached: importing eighty board modules is not something to do on every
    menu open, and the set cannot change while the editor is running.
    """
    found: dict[str, PlatformSpec] = {}

    for package in PLATFORM_PACKAGES:
        for module_name in _modules(package):
            try:
                module = importlib.import_module(module_name)
            except Exception as error:  # a board module that will not import
                log.debug("skipping %s: %s", module_name, error)
                continue

            for name, value in vars(module).items():
                if not _is_platform(value) or value.__module__ != module_name:
                    continue

                spec = PlatformSpec(
                    id=f"{module_name}:{name}",
                    label=_label(name),
                    module=module_name,
                    class_name=name,
                )
                found.setdefault(spec.id, spec)

    return tuple(sorted(found.values(), key=lambda spec: (spec.vendor, spec.label)))


def _label(class_name: str) -> str:
    """``GlasgowRevC123Platform`` -> ``Glasgow Rev C123``."""
    import re

    stripped = (
        class_name[: -len("Platform")]
        if class_name.endswith("Platform")
        else class_name
    )
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", stripped)
    return spaced or class_name


def find(platform_id: str) -> PlatformSpec | None:
    for spec in list_platforms():
        if spec.id == platform_id:
            return spec
    return None


def load(platform_id: str) -> type:
    """The platform class for ``platform_id``."""
    spec = find(platform_id)
    if spec is None:
        raise KeyError(f"no platform {platform_id!r} installed")
    return spec.load()


# --- the ios a platform offers ----------------------------------------------


def _direction_of(port) -> str:
    """``"i"``, ``"o"`` or ``"io"`` for an amaranth port object."""
    direction = getattr(port, "direction", None)
    name = getattr(direction, "name", str(direction)).lower()
    return {"input": "i", "output": "o", "bidir": "io"}.get(name, "io")


@lru_cache(maxsize=16)
def list_ios(platform_id: str) -> tuple[IOSpec, ...]:
    """The IOs a design built for ``platform_id`` can attach to.

    Resources are probed by requesting them, because a declared resource is
    not necessarily available: Glasgow's constructor claims the pins behind
    ``led`` for its own use, and offering a block that cannot be built would
    be worse than not offering it.
    """
    if find(platform_id) is None:
        # an expected, recoverable state: the design names a board whose
        # support package is not installed here. The resource blocks say so
        # on the canvas, so this does not warrant a warning in the log.
        log.debug("board package for %s is not installed", platform_id)
        return ()

    try:
        platform = load(platform_id)()
    except Exception as error:
        # installed but unusable, which is worth complaining about
        log.warning("could not inspect board %s: %s", platform_id, error)
        return ()

    ios: list[IOSpec] = []

    for name, number in sorted(getattr(platform, "resources", {})):
        try:
            port = platform.request(name, number, dir="-")
        except Exception:
            continue  # already claimed, or not a simple port
        ios.append(
            IOSpec(
                id=f"{name} {number}",
                kind=IOKind.REQUEST,
                name=name,
                number=number,
                direction=_direction_of(port),
            )
        )

    for name, port in sorted(getattr(platform, NAMED_PORTS_ATTRIBUTE, {}).items()):
        ios.append(IOSpec(id=name, kind=IOKind.NAMED, direction=_direction_of(port)))

    return tuple(ios)


#: separates an io from an explicit direction in a resource block's text,
#: as in ``LED0:o``. Needed because a bidirectional pin could be driven or
#: read, and only the user knows which they meant.
DIRECTION_SEPARATOR = ":"

DIRECTIONS = ("i", "o")


def parse_io(text: str) -> tuple[str, str | None]:
    """Split ``"LED0:o"`` into its io id and the direction asked for."""
    io_id, separator, direction = text.strip().rpartition(DIRECTION_SEPARATOR)
    if separator and direction.strip() in DIRECTIONS:
        return io_id.strip(), direction.strip()
    return text.strip(), None


def effective_direction(spec: "IOSpec | None", requested: str | None) -> str:
    """Which way a resource block's signal flows.

    A bidirectional pin is driven unless the design says otherwise: that is
    what an LED or a port pin is usually for, and guessing the other way
    would leave a block that cannot drive anything.
    """
    if requested in DIRECTIONS:
        return requested
    if spec is None:
        return "o"
    return "o" if spec.direction == "io" else spec.direction


def normalise_io(io_id: str) -> str:
    """``"LED0"`` and ``"led 0"`` both become ``"led0"``.

    The two spellings are the same physical pin seen through two revisions of
    the same support package: Glasgow used to offer its LEDs as requestable
    resources (``led 0``) and now claims them and hands them out as named
    ports (``LED0``). A design should not stop working because the board's
    package was updated.
    """
    return "".join(c for c in io_id.lower() if c.isalnum())


def find_io(platform_id: str, io_id: str) -> IOSpec | None:
    """The io ``io_id`` names, exactly if possible and by spelling if not."""
    available = list_ios(platform_id)

    for spec in available:
        if spec.id == io_id:
            return spec

    wanted = normalise_io(io_id)
    for spec in available:
        if normalise_io(spec.id) == wanted:
            log.debug("resolved io %r to %r on %s", io_id, spec.id, platform_id)
            return spec

    return None
