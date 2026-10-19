from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QFont, QPainterPath, QTextCursor
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsProxyWidget, QGraphicsTextItem

from ....theme import current_theme
from ....blocks.definition import BlockKind
from ...grid import SIZE, snap, squares
from .graphics_item import GraphicsItem
from .socket_graphics_item import SocketGraphicsItem

if TYPE_CHECKING:
    from .. import Node


class NodeProxyWidget(QGraphicsProxyWidget):
    def __init__(self, parent: "NodeGraphicsItem"):
        super().__init__(parent)
        self._item = parent

    @property
    def scene_views(self):
        return self._item.node.module.scene.views()

    # tell the scene views whether node content is being edited, so that they
    # can stop treating key presses as editor shortcuts
    def focusInEvent(self, event):
        for scene_view in self.scene_views:
            scene_view.node_edit = True
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        for scene_view in self.scene_views:
            scene_view.node_edit = False
        super().focusOutEvent(event)


class NodeTitleItem(QGraphicsTextItem):
    """The node's name, editable in place.

    Read-only until asked: a title that accepted clicks all the time would
    swallow the press that starts dragging the node around.
    """

    def __init__(self, parent: "NodeGraphicsItem"):
        super().__init__(parent)
        self._item = parent
        self._before = ""
        self._ending = False

    @property
    def editing(self) -> bool:
        return self.textInteractionFlags() != Qt.NoTextInteraction

    def begin_edit(self) -> None:
        if self.editing:
            return

        self._before = self.toPlainText()
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)

        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        self.setTextCursor(cursor)

        self._set_node_edit(True)

    def _end_edit(self, *, keep: bool) -> None:
        """Stop editing, keeping the new name or putting the old one back.

        Guarded against re-entry: dropping the interaction flags makes the
        item lose focus *synchronously*, and the resulting ``focusOutEvent``
        would otherwise come back in here and commit the very text that
        Escape is in the middle of discarding.
        """
        if not self.editing or self._ending:
            return

        self._ending = True
        try:
            self.setTextInteractionFlags(Qt.NoTextInteraction)
            self._set_node_edit(False)

            # deselect, or the highlight stays drawn after focus has gone
            cursor = self.textCursor()
            cursor.clearSelection()
            self.setTextCursor(cursor)

            if keep:
                self._item.commit_title(self.toPlainText())
            else:
                self.setPlainText(self._before)
        finally:
            self._ending = False

    def _set_node_edit(self, editing: bool) -> None:
        """Keep Delete from deleting the node while its name is being typed."""
        for scene_view in self._item.node.module.scene.views():
            scene_view.node_edit = editing

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._end_edit(keep=True)
            return
        if event.key() == Qt.Key_Escape:
            self._end_edit(keep=False)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self._end_edit(keep=True)
        super().focusOutEvent(event)


#: how big a node is drawn, by what it holds. A port block is a single name
#: field and a code block is an editor, so one size for both leaves either a
#: vast empty box or source that cannot be read.
#:
#: Written as grid squares rather than pixels: a node that starts off-grid can
#: never be nudged back onto it, because dragging only ever snaps the corner
#: the user is holding.
SIZE_BY_KIND: dict[BlockKind, tuple[int, int]] = {
    BlockKind.PORT_IN: (squares(13), squares(5)),
    BlockKind.PORT_OUT: (squares(13), squares(5)),
    BlockKind.PORT_PARAM: (squares(13), squares(5)),
    BlockKind.VARIABLE: (squares(14), squares(6)),
    BlockKind.RESOURCE: (squares(14), squares(7)),
    BlockKind.HIERARCHICAL: (squares(14), squares(7)),
    BlockKind.CODE: (squares(22), squares(15)),
    BlockKind.TESTBENCH: (squares(22), squares(15)),
    BlockKind.FORMAL: (squares(22), squares(15)),
}

DEFAULT_SIZE = (squares(14), squares(15))

#: nothing may be dragged smaller than this, or the title and the resize grip
#: would overlap and the node become impossible to grab
MIN_WIDTH = squares(9)
MIN_HEIGHT = squares(4)


class NodeGraphicsItem(GraphicsItem, QGraphicsItem):
    #: class-level defaults; each instance overrides them for its block kind
    WIDTH, HEIGHT = DEFAULT_SIZE
    EDGE_SIZE = 10
    TITLE_HEIGHT = 26
    TITLE_PADDING = 6

    #: blank margin down each side of the content widget, where the sockets
    #: write their labels. Reserved unconditionally rather than only when a
    #: side has sockets, so the content does not jump about as ports change.
    SOCKET_GUTTER = (
        SocketGraphicsItem.RADIUS
        + SocketGraphicsItem.LABEL_PADDING
        + (SocketGraphicsItem.LABEL_WIDTH)
    )

    #: the grab area in the bottom-right corner that resizes the node
    RESIZE_GRIP = 16

    def __init__(self, node: "Node", title: str = "Node", parent=None):
        super().__init__(element=node, parent=parent)

        self._node = node
        self.WIDTH, self.HEIGHT = SIZE_BY_KIND.get(node.kind, DEFAULT_SIZE)
        self._resizing_from: QPointF | None = None

        self._title_item = NodeTitleItem(self)
        font = QFont(self._title_item.font())
        font.setBold(True)
        self._title_item.setFont(font)
        self._title_item.setPos(self.TITLE_PADDING, 0)
        self._title_item.setTextWidth(self.WIDTH - 2 * self.TITLE_PADDING)
        self.title = title

        # the title is a child item, so it does not inherit the widget
        # palette the way the proxied content widget does
        self.apply_theme()

        self._proxy_widget = NodeProxyWidget(self)
        self.content_widget = self._node.content_widget

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

    def apply_theme(self) -> None:
        self._title_item.setDefaultTextColor(current_theme().node_title_text)

    @property
    def node(self) -> "Node":
        return self._node

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value
        self._title_item.setPlainText(value)

    @property
    def title_item(self) -> NodeTitleItem:
        return self._title_item

    def begin_rename(self) -> None:
        """Start editing the title in place."""
        self._title_item.begin_edit()

    def commit_title(self, value: str) -> None:
        """Take the edited title, unless it is empty.

        An empty name would leave a block with nothing to identify it, so the
        old one is put back rather than accepted.
        """
        cleaned = " ".join(value.split())
        if not cleaned or cleaned == self._title:
            self._title_item.setPlainText(self._title)
            return

        self._node.title = cleaned
        self._node.module.history.check_in()

        scene = self.scene()
        if scene is not None:
            scene.node_renamed.emit(self._node)

    @property
    def content_widget(self):
        return self._content

    @content_widget.setter
    def content_widget(self, value) -> None:
        self._content = value
        self._layout_content()
        self._proxy_widget.setWidget(self._content)

    def _layout_content(self) -> None:
        self._content.setGeometry(
            self.SOCKET_GUTTER,
            self.TITLE_HEIGHT + self.EDGE_SIZE,
            self.WIDTH - 2 * self.SOCKET_GUTTER,
            self.HEIGHT - 2 * self.EDGE_SIZE - self.TITLE_HEIGHT,
        )

    # --- resizing ----------------------------------------------------------

    @property
    def size(self) -> tuple[int, int]:
        return self.WIDTH, self.HEIGHT

    def resize(self, width: float, height: float) -> None:
        """Set the node's size, re-laying out everything that depends on it.

        Snapped, so a node stays on the grid however it got its size -- from
        a drag, from a file, or from the defaults above.
        """
        width = max(snap(width), MIN_WIDTH)
        height = max(snap(height), MIN_HEIGHT)
        if (width, height) == (self.WIDTH, self.HEIGHT):
            return

        self.prepareGeometryChange()
        self.WIDTH, self.HEIGHT = width, height

        self._title_item.setTextWidth(self.WIDTH - 2 * self.TITLE_PADDING)
        self._layout_content()
        # the outputs live on the right edge, so they move with the width
        self._node.reposition_sockets()
        self.update()

    def _grip_rect(self) -> QRectF:
        """Where the bottom-right corner can be grabbed to resize."""
        return QRectF(
            self.WIDTH - self.RESIZE_GRIP,
            self.HEIGHT - self.RESIZE_GRIP,
            self.RESIZE_GRIP,
            self.RESIZE_GRIP,
        )

    def hoverMoveEvent(self, event):
        over_grip = self._grip_rect().contains(event.pos())
        self.setCursor(Qt.SizeFDiagCursor if over_grip else Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._grip_rect().contains(event.pos()):
            # swallowed: letting this reach the base implementation would
            # start dragging the node instead of resizing it
            self._resizing_from = event.pos()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing_from is None:
            super().mouseMoveEvent(event)
            return

        self.resize(event.pos().x(), event.pos().y())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._resizing_from is None:
            super().mouseReleaseEvent(event)
            return

        self._resizing_from = None
        self._node.module.history.check_in()
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return self._constrain_position(value)

        if change == QGraphicsItem.ItemPositionHasChanged:
            # keep the attached edges glued to the sockets that just moved
            for edge in self._node.edges:
                edge.update_path()

        return super().itemChange(change, value)

    def _constrain_position(self, value):
        """Clamp a proposed position to the scene and snap it to the grid."""
        rect = self.module_scene.sceneRect()

        if not rect.contains(value):
            value.setX(min(max(rect.left(), value.x()), rect.right() - SIZE))
            value.setY(min(max(rect.top(), value.y()), rect.bottom() - SIZE))

        value.setX(snap(value.x()))
        value.setY(snap(value.y()))

        return value

    def boundingRect(self):
        return QRectF(0, 0, self.WIDTH, self.HEIGHT).normalized()

    def _band(self, top: float, height: float, square_edge: str) -> QPainterPath:
        """A rounded rect with one of its two horizontal edges squared off.

        The title and content bands meet at a seam; squaring the corners that
        touch the seam makes the two rounded rects read as one node body.
        ``square_edge`` is the edge to square: ``"top"`` or ``"bottom"``.
        """
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        path.addRoundedRect(0, top, self.WIDTH, height, self.EDGE_SIZE, self.EDGE_SIZE)

        seam = top if square_edge == "top" else top + height - self.EDGE_SIZE
        path.addRect(0, seam, self.EDGE_SIZE, self.EDGE_SIZE)
        path.addRect(self.WIDTH - self.EDGE_SIZE, seam, self.EDGE_SIZE, self.EDGE_SIZE)
        return path.simplified()

    def paint(self, painter, style_option, widget=None, **kwargs):
        theme = current_theme()
        painter.setPen(Qt.NoPen)

        painter.setBrush(theme.brush_node_title)
        painter.drawPath(self._band(0, self.TITLE_HEIGHT, square_edge="bottom"))

        painter.setBrush(theme.brush_node_background)
        painter.drawPath(
            self._band(
                self.TITLE_HEIGHT,
                self.HEIGHT - self.TITLE_HEIGHT,
                square_edge="top",
            )
        )

        outline = QPainterPath()
        outline.addRoundedRect(
            0, 0, self.WIDTH, self.HEIGHT, self.EDGE_SIZE, self.EDGE_SIZE
        )
        painter.setPen(
            theme.pen_node_outline_selected
            if self.isSelected()
            else theme.pen_node_outline
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(outline.simplified())

        self._paint_grip(painter, theme)

    def _paint_grip(self, painter, theme) -> None:
        """Three diagonal ticks in the corner, so the grip can be found."""
        painter.setPen(theme.pen_node_outline)

        corner = self.RESIZE_GRIP - self.EDGE_SIZE // 2
        for offset in range(4, corner + 1, 4):
            painter.drawLine(
                int(self.WIDTH - offset),
                int(self.HEIGHT - self.EDGE_SIZE // 2),
                int(self.WIDTH - self.EDGE_SIZE // 2),
                int(self.HEIGHT - offset),
            )
