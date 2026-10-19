"""The design's module tree, down the left side.

The breadcrumb shows the way *in* to where you are; this shows the whole
shape at once, so a block three levels down is one click away rather than
three double-clicks.
"""

from logging import getLogger

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem

log = getLogger(__name__)

#: where the path of node uuids is kept on each row
PATH_ROLE = Qt.UserRole


class HierarchyDock(QDockWidget):
    """A tree of every module in the design, with the current one selected."""

    #: a module was chosen; carries the path of node uuids to it
    module_chosen = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__("Hierarchy", parent)
        self.setObjectName("hierarchy")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemClicked.connect(self._chosen)
        self.setWidget(self.tree)

        #: suppresses the signal while the tree is being rebuilt, or selecting
        #: the current row would navigate to it again
        self._rebuilding = False

    def rebuild(self, design) -> None:
        """Show ``design``'s tree, selecting where the user currently is."""
        self._rebuilding = True
        try:
            self.tree.clear()
            if design is None:
                return

            here = [node.uuid for node in design.stack]
            items: dict[tuple, QTreeWidgetItem] = {}

            for path, node in design.paths():
                label = node.title if node is not None else design.name
                parent = items.get(tuple(path[:-1])) if path else None

                item = (
                    QTreeWidgetItem(parent, [label])
                    if parent is not None
                    else QTreeWidgetItem(self.tree, [label])
                )
                item.setData(0, PATH_ROLE, list(path))
                items[tuple(path)] = item

                if path == here:
                    self.tree.setCurrentItem(item)

            self.tree.expandAll()
        finally:
            self._rebuilding = False

    def _chosen(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._rebuilding or item is None:
            return

        path = item.data(0, PATH_ROLE)
        if path is not None:
            self.module_chosen.emit(list(path))
