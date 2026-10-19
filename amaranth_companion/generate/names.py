"""Turning the names on a canvas into names Python will accept.

A block title is whatever the user typed -- ``AND``, ``half period``, ``2nd
stage`` -- and it has to come out of the generator as a valid, unique, stable
identifier. Stable matters more than pretty: regenerating a design that has not
changed must produce the same file, or the diff is useless.
"""

import keyword
import re
from typing import Iterable

#: anything that cannot appear in a Python identifier
ILLEGAL = re.compile(r"\W+")

FALLBACK = "block"


def identifier(text: str, fallback: str = FALLBACK) -> str:
    """A lowercase identifier for ``text``.

    ``"2nd stage"`` becomes ``"n2nd_stage"``: a leading digit is prefixed
    rather than dropped, so two titles differing only in their first character
    cannot collide.
    """
    cleaned = ILLEGAL.sub("_", text.strip().lower()).strip("_")

    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        cleaned = f"n{cleaned}"
    if keyword.iskeyword(cleaned) or keyword.issoftkeyword(cleaned):
        cleaned = f"{cleaned}_"

    return cleaned


def class_name(text: str, fallback: str = "Block") -> str:
    """A CamelCase class name for ``text``.

    ``"logic.and2"`` becomes ``"LogicAnd2"``; ``"half adder"`` becomes
    ``"HalfAdder"``.
    """
    parts = [part for part in ILLEGAL.split(text.strip()) if part]
    if not parts:
        return fallback

    name = "".join(part[:1].upper() + part[1:] for part in parts)
    if name[0].isdigit():
        name = f"N{name}"
    return name


class NameAllocator:
    """Hands out names, never the same one twice.

    Collisions get a numeric suffix in the order they were asked for, so the
    second ``AND`` in a design is ``and_2`` however the dictionary happens to
    be ordered.
    """

    def __init__(self, reserved: Iterable[str] = ()) -> None:
        self._taken: set[str] = set(reserved)

    def __contains__(self, name: str) -> bool:
        return name in self._taken

    def take(self, preferred: str) -> str:
        if preferred not in self._taken:
            self._taken.add(preferred)
            return preferred

        for index in range(2, 1000):
            candidate = f"{preferred}_{index}"
            if candidate not in self._taken:
                self._taken.add(candidate)
                return candidate

        raise ValueError(f"could not find a free name for {preferred!r}")
