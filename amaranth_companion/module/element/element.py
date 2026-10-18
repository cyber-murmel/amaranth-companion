from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import Module


class ModuleElement(ABC):
    """Anything that belongs to a :class:`Module` and can locate it.

    ``GraphicsItem`` relies on this contract to reach the scene its element is
    drawn on, so every element that owns a graphics item implements it.
    """

    @property
    @abstractmethod
    def module(self) -> "Module":
        raise NotImplementedError()
