class ModuleSceneHistory:
    def __init__(self, module):
        self._module = module
        self._past: [str] = []
        self._future: [str] = []

    def check_in(self):
        self._past.append(self._module.to_json())
        self._future = []

    @property
    def is_undoable(self):
        return len(self._past) > 1

    @property
    def is_redoable(self):
        return len(self._future) > 0

    def undo(self):
        if self.is_undoable:
            self._future.append(self._past[-1])
            self._past = self._past[:-1]
            self._module.from_json(self._past[-1])

    def redo(self):
        if self.is_redoable:
            self._past.append(self._future[-1])
            self._future = self._future[:-1]
            self._module.from_json(self._past[-1])
