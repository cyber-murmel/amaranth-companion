from typing import Protocol


class Snapshotable(Protocol):
    """Anything that can be captured whole and put back."""

    def to_dict(self) -> dict: ...

    def load(self, data) -> None: ...


class History:
    """Undo/redo stack of whole-document snapshots.

    Owned by the subject itself -- a :class:`~.module.Module`, or the
    :class:`~amaranth_companion.design.Design` that contains it -- rather than
    by a view, so the history survives being shown in a different view, or in
    none at all. A design's snapshot nests the whole hierarchy, so one stack
    covers edits made at any depth.
    """

    def __init__(self, subject: Snapshotable):
        self._subject = subject
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

        snapshot = self._subject.to_dict()
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
            self._subject.load(snapshot)
        finally:
            self._restoring = False


#: the name this class had when only modules were snapshotted
ModuleHistory = History
