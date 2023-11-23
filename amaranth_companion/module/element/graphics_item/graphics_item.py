from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import ModuleElement


class GraphicsItem:
    def __init__(self, element: "ModuleElement", parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        print(element)
        self._element = element

    @property
    def scene(self):
        return self._element.module.scene
