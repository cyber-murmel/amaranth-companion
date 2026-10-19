"""The block palette, down the right side.

Everything the library offers, grouped the way the Insert menu groups it, but
visible at once and draggable onto the canvas.

It is also where a block goes to die: dragging a node out of the canvas and
onto the palette deletes it -- putting it back in the box. Dropping it
anywhere else does nothing, because a design should not lose a block to a
slip of the wrist.
"""

from logging import getLogger

from PyQt5.QtCore import QMimeData, Qt, pyqtSignal
from PyQt5.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem

from .. import mime
from ..blocks.library import library

log = getLogger(__name__)

#: where a row keeps the block id it stands for
BLOCK_ROLE = Qt.UserRole


class BlockTree(QTreeWidget):
    """The list itself: drags blocks out, accepts nodes dropped in."""

    #: a node was dropped here; carries its uuid
    node_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setSelectionMode(QTreeWidget.SingleSelection)

    # --- dragging a block out ----------------------------------------------

    def mimeData(self, items):
        data = QMimeData()
        for item in items:
            block_id = item.data(0, BLOCK_ROLE)
            if block_id:
                data.setData(mime.BLOCK, block_id.encode())
                data.setText(block_id)
                break
        return data

    def startDrag(self, actions):
        # a category row stands for nothing draggable
        item = self.currentItem()
        if item is None or not item.data(0, BLOCK_ROLE):
            return
        super().startDrag(Qt.CopyAction)

    # --- accepting a node dropped in ---------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(mime.NODE):
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(mime.NODE):
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(mime.NODE):
            event.ignore()
            return

        uuid = bytes(event.mimeData().data(mime.NODE)).decode()
        event.setDropAction(Qt.MoveAction)
        event.accept()
        self.node_dropped.emit(uuid)


class BlockPalette(QDockWidget):
    """Every block the library knows, grouped by category."""

    #: a block was dropped on the canvas, or double-clicked
    block_chosen = pyqtSignal(str)
    #: a node was dragged onto the palette and should go
    node_discarded = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Blocks", parent)
        self.setObjectName("blocks")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.tree = BlockTree()
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.node_dropped.connect(self.node_discarded)
        self.setWidget(self.tree)

        self.rebuild()

    def rebuild(self) -> None:
        """Re-read the library, so a block written just now shows up."""
        self.tree.clear()
        groups: dict[tuple, QTreeWidgetItem] = {}

        for category, definitions in library().by_category().items():
            parent = None
            for level, name in enumerate(category):
                key = tuple(category[: level + 1])
                if key not in groups:
                    groups[key] = (
                        QTreeWidgetItem(parent, [name])
                        if parent is not None
                        else QTreeWidgetItem(self.tree, [name])
                    )
                parent = groups[key]

            for definition in definitions:
                item = (
                    QTreeWidgetItem(parent, [definition.label])
                    if parent is not None
                    else QTreeWidgetItem(self.tree, [definition.label])
                )
                item.setData(0, BLOCK_ROLE, definition.id)
                item.setToolTip(0, definition.doc or definition.id)

        self.tree.expandAll()

    def _double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        block_id = item.data(0, BLOCK_ROLE)
        if block_id:
            self.block_chosen.emit(block_id)
