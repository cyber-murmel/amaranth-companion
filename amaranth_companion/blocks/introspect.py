"""Derive a code block's ports by running its Amaranth source.

Port widths routinely depend on parameters -- ``Signal(range(half_period))`` in
the blink example -- so there is no way to read a block's real interface off
the source text without executing it. This module does execute it, but never in
the editor's own process: :func:`introspect` spawns ``python -m`` on this file,
so a syntax error, an infinite loop or a segfault in block code costs a worker
rather than the user's unsaved work.

The worker speaks JSON over stdin/stdout::

    {"source": "...", "params": {"width_param": 8}}
    -> {"ok": true, "class_name": "And2", "ports": [...], "params": {...}}
    -> {"ok": false, "error": "...", "traceback": "..."}
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from logging import getLogger
from typing import Any, Mapping, Sequence

from ..errors import locate
from .definition import ParamSpec, PortSpec, PortRole, Shape, split_port_name

log = getLogger(__name__)

#: the name the executed source is given, so that classes defined by it can be
#: told apart from ones it imported (``from amaranth import *`` brings in
#: ``Module``, which is itself an ``Elaboratable``)
BLOCK_MODULE_NAME = "_amaranth_companion_block"

#: the filename the block's source is compiled under, which is what makes its
#: own frames findable in a traceback
BLOCK_FILENAME = "<block>"

#: a block that never returns must not wedge the editor
DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class Introspection:
    """What the worker found, or why it could not look."""

    ok: bool
    ports: Sequence[PortSpec] = ()
    params: Sequence[ParamSpec] = ()
    class_name: str = ""
    error: str = ""
    traceback: str = ""
    #: 1-based line in the block's source the failure came from
    line: int | None = None

    @property
    def signal_ports(self) -> list[PortSpec]:
        return [port for port in self.ports if not port.is_param]

    @property
    def param_ports(self) -> list[PortSpec]:
        return [port for port in self.ports if port.is_param]

    @classmethod
    def from_dict(cls, data: Mapping) -> "Introspection":
        if not data.get("ok"):
            return cls(
                ok=False,
                error=data.get("error", "introspection failed"),
                traceback=data.get("traceback", ""),
                line=data.get("line"),
            )
        return cls(
            ok=True,
            class_name=data.get("class_name", ""),
            ports=tuple(PortSpec.from_dict(port) for port in data.get("ports", ())),
            params=tuple(
                ParamSpec.from_dict(name, value)
                for name, value in (data.get("params") or {}).items()
            ),
        )

    @classmethod
    def failed(
        cls, error: str, traceback: str = "", line: int | None = None
    ) -> "Introspection":
        return cls(ok=False, error=error, traceback=traceback, line=line)

    @property
    def summary(self) -> str:
        """The error with its line, which is what a node shows."""
        if self.ok:
            return ""
        return f"line {self.line}: {self.error}" if self.line else self.error


# --- client ----------------------------------------------------------------


def introspect(
    source: str,
    params: Mapping[str, Any] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    executable: str | None = None,
) -> Introspection:
    """Run ``source`` in a worker and report the ports it declares.

    Never raises for bad block code: a failure comes back as an
    :class:`Introspection` with ``ok=False`` and a message to show on the node.
    """
    request = json.dumps({"source": source, "params": dict(params or {})})

    try:
        completed = subprocess.run(
            [executable or sys.executable, "-m", __name__],
            input=request,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Introspection.failed(f"block code did not finish within {timeout:g}s")
    except OSError as error:
        return Introspection.failed(
            f"could not start the introspection worker: {error}"
        )

    if not completed.stdout.strip():
        # the worker died before it could report anything -- a segfault in a
        # native extension, or the interpreter being killed
        detail = completed.stderr.strip().splitlines()
        return Introspection.failed(
            f"introspection worker exited with code {completed.returncode}",
            detail[-1] if detail else "",
        )

    try:
        return Introspection.from_dict(json.loads(completed.stdout))
    except (ValueError, KeyError) as error:
        return Introspection.failed(f"malformed worker response: {error}")


@lru_cache(maxsize=256)
def _cached(source: str, params: tuple[tuple[str, Any], ...]) -> Introspection:
    return introspect(source, dict(params))


def introspect_cached(
    source: str, params: Mapping[str, Any] | None = None
) -> Introspection:
    """:func:`introspect`, memoised on the source and parameter values.

    Instantiating a block definition introspects its code, and a design holds
    many copies of the same few gates; without this, opening a file would
    spawn one interpreter per node.
    """
    try:
        key = tuple(sorted((params or {}).items()))
    except TypeError:  # an unhashable parameter value: skip the cache
        return introspect(source, params)
    return _cached(source, key)


# --- worker ----------------------------------------------------------------


def _elaboratable_classes(namespace: Mapping) -> list[type]:
    """The ``Elaboratable`` subclasses *defined by* the source, in order.

    Filtering on ``__module__`` is what keeps imported elaboratables out:
    ``from amaranth import *`` binds ``Module``, which would otherwise look
    like the block's own class.
    """
    import inspect

    from amaranth import Elaboratable

    return [
        value
        for value in namespace.values()
        if inspect.isclass(value)
        and issubclass(value, Elaboratable)
        and getattr(value, "__module__", None) == BLOCK_MODULE_NAME
    ]


def _declared_params(cls: type) -> dict[str, ParamSpec]:
    """``*_param`` keyword arguments of ``__init__``, with their defaults."""
    import inspect

    specs: dict[str, ParamSpec] = {}
    try:
        signature = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return specs

    for name, parameter in signature.parameters.items():
        if not name.endswith(PortRole.PARAM.suffix):
            continue
        default = (
            None if parameter.default is inspect.Parameter.empty else parameter.default
        )
        specs[name] = ParamSpec(
            name=name,
            default=default,
            dtype=type(default).__name__ if default is not None else "int",
        )
    return specs


def _signal_ports(instance: Any) -> list[PortSpec]:
    """Attributes that are ``Signal``s with a port suffix, with real shapes."""
    from amaranth.hdl import Signal

    ports: list[PortSpec] = []
    for name, value in vars(instance).items():
        if not isinstance(value, Signal) or split_port_name(name) is None:
            continue
        shape = value.shape()
        spec = PortSpec.from_name(
            name, shape=Shape(width=shape.width, signed=shape.signed)
        )
        if spec is not None and not spec.is_param:
            ports.append(spec)
    return ports


def analyse(source: str, params: Mapping[str, Any] | None = None) -> dict:
    """Execute ``source`` and describe the block it defines.

    Runs in the worker process. Returns the response dict rather than printing
    it, so that it can be unit-tested without spawning anything.
    """
    namespace: dict[str, Any] = {"__name__": BLOCK_MODULE_NAME}

    try:
        exec(compile(source, BLOCK_FILENAME, "exec"), namespace)
    except Exception as error:  # any failure in user code, including SyntaxError
        return _failure(error)

    classes = _elaboratable_classes(namespace)
    if not classes:
        return {"ok": False, "error": "no Elaboratable subclass defined in this block"}

    # the last definition wins, which is the convention a file builds up to:
    # helpers first, the block's own class last
    cls = classes[-1]
    declared = _declared_params(cls)

    # unknown parameters would be a TypeError; the editor may still be holding
    # values for a parameter the source has since dropped
    arguments = {
        name: value for name, value in (params or {}).items() if name in declared
    }
    for name, spec in declared.items():
        arguments.setdefault(name, spec.default)

    try:
        instance = cls(**{k: v for k, v in arguments.items() if v is not None})
    except Exception as error:
        return _failure(error, f"could not instantiate {cls.__name__}: ")

    ports = [
        PortSpec(name=name, role=PortRole.PARAM, default=declared[name].default)
        for name in declared
    ]
    ports += _signal_ports(instance)

    return {
        "ok": True,
        "class_name": cls.__name__,
        "ports": [port.to_dict() for port in ports],
        "params": {name: spec.to_dict() for name, spec in declared.items()},
    }


def _failure(error: BaseException, prefix: str = "") -> dict:
    located = locate(error, BLOCK_FILENAME, prefix)
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

    json.dump(analyse(request.get("source", ""), request.get("params")), sys.stdout)
    return 0


if "__main__" == __name__:
    sys.exit(main())
