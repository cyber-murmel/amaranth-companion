"""Working out what value each parameter port carries.

A parameter edge is not a wire: nothing travels along it at run time. It says
that the value a block elaborates with comes from somewhere else in the graph
-- a variable block, or a parameter port of the block above -- and it has to be
resolved *before* the design is elaborated, because that value decides how wide
the signals are.

Resolution is a small dependency graph of its own: a variable may be written in
terms of other variables (``half_period = period // 2``), so the values are
worked out in rounds until they stop changing, and a cycle is reported rather
than looped on.
"""

import ast
from logging import getLogger
from typing import Any, Mapping, TYPE_CHECKING

from ..blocks.definition import BlockKind

if TYPE_CHECKING:
    from .element import Node
    from .module import Module

log = getLogger(__name__)

#: what a variable expression may call. Deliberately tiny: these are values a
#: user typed into their own document, at the same trust level as the Amaranth
#: in their code blocks, but there is no reason for a bit width to need more
#: than arithmetic -- and this way a typo cannot reach the filesystem.
SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "bool": bool,
    "divmod": divmod,
    "float": float,
    "int": int,
    "len": len,
    "max": max,
    "min": min,
    "pow": pow,
    "round": round,
    "sum": sum,
}

#: how many times the variables are re-evaluated before giving up. A chain of
#: n variables settles in n rounds; anything longer is a cycle.
MAX_ROUNDS = 16


class ParameterError(ValueError):
    """A parameter value could not be worked out."""


def evaluate(expression: str, context: Mapping[str, Any] | None = None) -> Any:
    """Evaluate a variable's expression against the variables around it.

    Literals take a fast path through :func:`ast.literal_eval`; anything else
    is compiled in ``eval`` mode with no builtins but :data:`SAFE_BUILTINS`, so
    a name that is not another variable raises rather than resolving to
    something unexpected.
    """
    text = expression.strip()
    if not text:
        raise ParameterError("no value given")

    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        pass  # not a literal, so it needs evaluating

    try:
        return eval(  # noqa: S307 - restricted namespace, see SAFE_BUILTINS
            compile(text, "<variable>", "eval"),
            {"__builtins__": SAFE_BUILTINS},
            dict(context or {}),
        )
    except Exception as error:
        raise ParameterError(f"{type(error).__name__}: {error}") from error


# --- variable blocks --------------------------------------------------------


def split_assignment(text: str) -> tuple[str, str]:
    """Split a variable block's ``"width = 8"`` into its name and expression.

    A bare expression with no ``=`` is allowed and takes the block's own name,
    so a user can drop a value down and name it later.
    """
    name, separator, expression = text.partition("=")
    if not separator:
        return "", name.strip()
    return name.strip(), expression.strip()


def variable_name(node: "Node") -> str:
    """The name a variable block declares, falling back to its title."""
    name, _expression = split_assignment(node.text)
    return name or node.title.strip()


def variable_port_name(node: "Node") -> str:
    """The parameter port a variable block exposes."""
    name = variable_name(node) or "value"
    return name if name.endswith("_param") else f"{name}_param"


def module_variables(module: "Module") -> dict[str, Any]:
    """Every variable declared in ``module``, resolved against each other.

    Re-evaluated in rounds so that order on the canvas does not matter: a
    variable may refer to one defined to its right, or below it.
    """
    blocks = {
        variable_name(node): node
        for node in module.nodes.values()
        if node.kind is BlockKind.VARIABLE and variable_name(node)
    }

    values: dict[str, Any] = {}
    unresolved = dict(blocks)

    for _round in range(MAX_ROUNDS):
        if not unresolved:
            break

        progressed = False
        for name, node in list(unresolved.items()):
            _name, expression = split_assignment(node.text)
            try:
                values[name] = evaluate(expression, values)
            except ParameterError:
                continue  # may depend on something not resolved yet
            unresolved.pop(name)
            progressed = True

        if not progressed:
            break

    for name in unresolved:
        log.debug("variable %r could not be resolved", name)

    return values


# --- parameter ports --------------------------------------------------------


def source_socket(socket) -> Any:
    """The socket feeding ``socket``, if exactly one edge arrives at it."""
    edges = socket.edges
    if len(edges) != 1:
        return None
    return edges[0].start_socket


def resolve_params(node: "Node") -> tuple[dict[str, Any], str]:
    """The parameter values ``node`` should elaborate with, and any error.

    A connected parameter port takes its value from whatever feeds it; an
    unconnected one falls back to the default its source declared. The error is
    a message for the node, not an exception: a design mid-edit is allowed to
    have a parameter that does not resolve yet.
    """
    values = dict(node.effective_params)
    problems: list[str] = []
    variables = module_variables(node.module)

    for name, socket in node.input_sockets.items():
        if not socket.is_param:
            continue

        feeding = source_socket(socket)
        if feeding is None:
            if values.get(name) is None and socket.default is not None:
                values[name] = socket.default
            continue

        try:
            values[name] = _value_of(feeding, variables)
        except ParameterError as error:
            problems.append(f"{socket.label}: {error}")

    return values, "; ".join(problems)


def _value_of(socket, variables: Mapping[str, Any]) -> Any:
    """The value a parameter *output* socket hands out."""
    node = socket.node

    if node.kind is BlockKind.VARIABLE:
        _name, expression = split_assignment(node.text)
        return evaluate(expression, variables)

    if node.kind.is_port:
        # a parameter port of the block above: its value is whatever that
        # block was given, so the lookup crosses one level of the hierarchy
        value = node.module.inherited_param(socket.name)
        if value is None:
            raise ParameterError("not set on the enclosing block")
        return value

    value = node.effective_params.get(socket.name, socket.default)
    if value is None:
        raise ParameterError("no value")
    return value
