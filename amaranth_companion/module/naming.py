"""Keeping two blocks on one module from going by the same name.

Dropping a second AND gate used to leave two blocks both called "AND", which
is ambiguous on the canvas and in the hierarchy tree. The second arrival
numbers the family instead: the one already there becomes "AND0", the new one
"AND1", and the next "AND2".

Numbering only starts when there is a collision, so a module with one AND gate
is left reading "AND" rather than "AND0".
"""

from logging import getLogger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .element import Node
    from .module import Module

log = getLogger(__name__)


def index_in_family(title: str, base: str) -> int | None:
    """``("AND3", "AND")`` -> 3; the unnumbered ``"AND"`` -> ``None``.

    Returns ``None`` for a title outside the family too, so callers should
    check membership with :func:`in_family` first.
    """
    suffix = title[len(base) :]
    return int(suffix) if suffix.isdigit() else None


def in_family(title: str, base: str) -> bool:
    """Whether ``title`` is ``base`` or ``base`` with a counter on the end.

    The base is taken whole, never stripped of its own digits: a block
    labelled "and2" is a family of its own, not a numbered "and".
    """
    return title == base or (title.startswith(base) and title[len(base) :].isdigit())


def family_name(node: "Node") -> str:
    """``node``'s title with an instance counter taken back off.

    Two AND gates are "AND0" and "AND1", but they are still one kind of
    block, and the generated class should be called "AND" once rather than
    after whichever instance was emitted first. A counter is only stripped
    when it is one that was added to the block's own label, so renaming a
    block to "Half Adder" still names its class after that.
    """
    label = node.definition.label if node.definition else ""
    if label and in_family(node.title, label):
        return label
    return node.title


def _lowest_free(used: set[int]) -> int:
    index = 0
    while index in used:
        index += 1
    return index


def disambiguate(module: "Module", node: "Node") -> list["Node"]:
    """Number ``node``'s family on ``module``; returns the nodes renamed.

    ``node`` itself is renamed in place and is not in the returned list, which
    holds the blocks that were already there and had to make room.
    """
    base = node.title
    if not base:
        return []

    siblings = [
        other
        for other in module.nodes.values()
        if other is not node
        and not other.kind.is_port  # a port's title *is* its name
        and in_family(other.title, base)
    ]
    if not siblings:
        return []

    used = {
        index
        for other in siblings
        if (index := index_in_family(other.title, base)) is not None
    }

    # whoever is still unnumbered gets a number, lowest first
    renamed = []
    for other in siblings:
        if index_in_family(other.title, base) is None:
            index = _lowest_free(used)
            used.add(index)
            other.title = f"{base}{index}"
            renamed.append(other)

    node.title = f"{base}{_lowest_free(used)}"
    log.debug("numbered %s as %s", base, node.title)
    return renamed
