from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...scene import ModuleScene
    from .. import ModuleElement


class GraphicsItem:
    """Mixin tying a Qt graphics item to the module element it draws."""

    def __init__(self, element: "ModuleElement", parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self._element = element

    @property
    def module_scene(self) -> "ModuleScene":
        """The module's scene.

        Deliberately *not* named ``scene``: that would shadow Qt's
        ``QGraphicsItem.scene()`` method with a property.
        """
        return self._element.module.scene
