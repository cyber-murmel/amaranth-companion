"""The canvas grid.

Lives on its own, with no imports, because both ends of the drawing code need
it: the scene paints it, and the nodes snap their position *and their size* to
it. Reaching for ``ModuleScene.GRID_SIZE`` from a graphics item would be a
circular import, which is how the node sizes drifted off the grid in the first
place -- they were written as "content plus two socket gutters" rather than as
a number of grid squares.
"""

#: one grid square, in scene units
SIZE = 20

#: grid squares between the heavier lines
STRIDE = 5


def snap(value: float) -> int:
    """``value`` moved to the nearest grid line."""
    return round(value / SIZE) * SIZE


def squares(count: int) -> int:
    """``count`` grid squares, for writing sizes that cannot be off-grid."""
    return count * SIZE


def is_aligned(value: float) -> bool:
    return value % SIZE == 0
