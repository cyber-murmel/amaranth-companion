"""Writing a module out as a reusable block.

The inverse of loading one, and deliberately the *same* pair of files the
shipped gates use: a ``*.block.yml`` describing the block, and an ordinary
module beside it holding what is inside. Nothing about a built-in block is
privileged -- the gates are what this function produces, and anything it
produces can be opened and edited like a design.

The block's interface comes from the port blocks in the module, so there is
nothing to declare: place an input port and the block gains an input.
"""

import re
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .definition import BlockKind, bare_port_name
from .library import SUFFIX

if TYPE_CHECKING:
    from ..module import Module

log = getLogger(__name__)

#: where a block made from a module goes when the design has not been saved
DEFAULT_CATEGORY = ("Blocks",)

_ILLEGAL = re.compile(r"[^a-z0-9]+")


class BlockWriteError(ValueError):
    """The module cannot be written out as a block."""


def block_id_for(label: str, category=()) -> str:
    """``"Half Adder"`` in ``["Math"]`` -> ``"math.half_adder"``.

    Namespaced by category so two blocks called "Counter" under different
    headings do not collide, the way ``logic.and2`` is namespaced today.
    """

    def slug(text: str) -> str:
        return _ILLEGAL.sub("_", text.strip().lower()).strip("_")

    name = slug(label)
    if not name:
        raise BlockWriteError("a block needs a name")

    prefix = ".".join(filter(None, (slug(part) for part in category)))
    return f"{prefix}.{name}" if prefix else name


def describe_ports(module: "Module") -> dict[str, list[str]]:
    """The port names a module exposes, by role. Used for the block's doc."""
    found: dict[str, list[str]] = {"in": [], "out": [], "param": []}

    for node in module.nodes.values():
        role = node.kind.port_role
        if role is None:
            continue
        name = bare_port_name(node.text.strip())
        if name:
            found[role.value].append(name)

    return found


def default_params(module: "Module") -> dict:
    """Parameter declarations for the module's parameter port blocks.

    Only the names are known here -- a parameter's default lives in the code
    block that consumes it, which is where it belongs. Writing the names out
    is what lets the Insert menu show them before anything is instantiated.
    """
    return {
        f"{name}_param": {"default": None, "dtype": "int"}
        for name in describe_ports(module)["param"]
    }


def write_block(
    module: "Module",
    *,
    label: str,
    directory,
    category=DEFAULT_CATEGORY,
    block_id: str | None = None,
    doc: str = "",
    icon: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Write ``module`` out as a block; returns the definition's path.

    Refuses to clobber an existing block unless asked: a block is something
    other designs already point at by id.
    """
    from ..module.serialization import dumps, module_to_dict

    if not list(module.nodes.values()):
        raise BlockWriteError("an empty module makes an empty block")

    identifier = block_id or block_id_for(label, category)
    root = Path(directory)
    definition_path = root / f"{identifier}{SUFFIX}"
    module_path = root / f"{identifier}.json"

    if definition_path.exists() and not overwrite:
        raise BlockWriteError(f"{identifier!r} already exists in {root}")

    root.mkdir(parents=True, exist_ok=True)
    module_path.write_text(dumps(module_to_dict(module)) + "\n")

    definition: dict = {
        "id": identifier,
        "label": label,
        "kind": BlockKind.HIERARCHICAL.value,
        "category": list(category),
        "implementation": module_path.name,
    }
    if doc:
        definition["doc"] = doc
    if icon:
        definition["icon"] = icon

    params = default_params(module)
    if params:
        definition["params"] = params

    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False, default_flow_style=False)
    )

    log.debug("wrote block %s to %s", identifier, definition_path)
    return definition_path
