from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import Module


class ModuleElement(ABC):
    @property
    @abstractmethod
    def module(self) -> "Module":
        raise NotImplementedError()
