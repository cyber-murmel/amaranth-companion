from typing import TYPE_CHECKING

from .serialization import module_to_dict

if TYPE_CHECKING:
    from .module import Module


class ModuleHistory:
    """Undo/redo stack of whole-module snapshots.

    Owned by the :class:`Module`, not by a view, so that the history survives
    the module being shown in a different view (or in none at all).
    """

    def __init__(self, module: "Module"):
        self._module = module
        self._past: list[dict] = []
        self._future: list[dict] = []
        self._restoring = False

    def reset(self) -> None:
        """Forget everything and make the current state the only snapshot."""
        self._past.clear()
        self._future.clear()
        self.check_in()

    def check_in(self) -> None:
        """Record the current state, unless it is the one already on top."""
        if self._restoring:
            return

        snapshot = module_to_dict(self._module)
        if self._past and self._past[-1] == snapshot:
            return

        self._past.append(snapshot)
        self._future.clear()

    @property
    def is_undoable(self) -> bool:
        return len(self._past) > 1

    @property
    def is_redoable(self) -> bool:
        return len(self._future) > 0

    def undo(self) -> None:
        if not self.is_undoable:
            return
        self._future.append(self._past.pop())
        self._restore(self._past[-1])

    def redo(self) -> None:
        if not self.is_redoable:
            return
        self._past.append(self._future.pop())
        self._restore(self._past[-1])

    def _restore(self, snapshot: dict) -> None:
        # rebuilding the module must not record a snapshot of itself
        self._restoring = True
        try:
            self._module.load(snapshot)
        finally:
            self._restoring = False
