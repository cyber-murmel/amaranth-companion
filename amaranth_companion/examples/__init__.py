"""Designs shipped with the editor.

A new user has nowhere to start from: the Insert menu offers blocks, but not
what a finished design looks like. These are small, complete and meant to be
opened and taken apart -- the last of them is the blink example from the
amaranth-examples repository, rebuilt as blocks.

They are opened *detached* from the file they came from, so saving one asks
where to put it rather than writing back into the installed package.
"""

from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from ..design import Design

log = getLogger(__name__)

EXAMPLES_DIR = Path(__file__).parent
INDEX_FILE = EXAMPLES_DIR / "index.yml"


@dataclass(frozen=True)
class Example:
    """One shipped design."""

    name: str
    label: str
    doc: str = ""

    @property
    def path(self) -> Path:
        return EXAMPLES_DIR / f"{self.name}.json"

    @property
    def exists(self) -> bool:
        return self.path.is_file()


def list_examples() -> list[Example]:
    """Every shipped example, in the order the index lists them.

    An index entry whose file is missing is skipped rather than offered: a
    menu entry that cannot open anything is worse than no entry.
    """
    try:
        data = yaml.safe_load(INDEX_FILE.read_text()) or []
    except (OSError, yaml.YAMLError) as error:
        log.warning("could not read the example index: %s", error)
        return []

    examples = []
    for entry in data:
        if not isinstance(entry, dict) or "name" not in entry:
            log.warning("skipping malformed example entry: %r", entry)
            continue

        example = Example(
            name=entry["name"],
            label=entry.get("label", entry["name"]),
            doc=entry.get("doc", ""),
        )
        if not example.exists:
            log.warning("example %r has no file at %s", example.name, example.path)
            continue

        examples.append(example)

    return examples


def find(name: str) -> Example | None:
    for example in list_examples():
        if example.name == name:
            return example
    return None


def open_example(example: Example) -> "Design":
    """Load ``example`` as an untitled design.

    Detached from its path on purpose: an example is a starting point, and
    saving one must not overwrite what ships with the editor.
    """
    from ..design import Design

    design = Design.from_file(example.path)
    design.detach()
    return design
