from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QBrush, QPainterPath, QPalette, QPen
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsProxyWidget, QGraphicsTextItem

from .graphics_item import GraphicsItem

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


class NodeGraphicsItem(GraphicsItem, QGraphicsItem):
    WIDTH = 200
    HEIGHT = 300
    EDGE_SIZE = 10
    TITLE_HEIGHT = 24

    def __init__(self, node: "Node", title: str = "Node", parent=None):
        super().__init__(element=node, parent=parent)

        self._node = node

        palette = QPalette()
        self._pen_default = QPen(palette.color(QPalette.Dark))
        self._pen_selected = QPen(palette.color(QPalette.Highlight))
        self._brush_title = QBrush(palette.color(QPalette.Midlight))
        self._brush_background = QBrush(palette.color(QPalette.Light))

        self._title_item = QGraphicsTextItem(self)
        self.title = title

        self._proxy_widget = NodeProxyWidget(self)
        self.content_widget = self._node.content_widget

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

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
    def content_widget(self):
        return self._content

    @content_widget.setter
    def content_widget(self, value) -> None:
        self._content = value
        self._content.setGeometry(
            self.EDGE_SIZE,
            self.TITLE_HEIGHT + self.EDGE_SIZE,
            self.WIDTH - 2 * self.EDGE_SIZE,
            self.HEIGHT - 2 * self.EDGE_SIZE - self.TITLE_HEIGHT,
        )
        self._proxy_widget.setWidget(self._content)

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
        grid_size = self.module_scene.GRID_SIZE

        if not rect.contains(value):
            value.setX(min(max(rect.left(), value.x()), rect.right() - grid_size))
            value.setY(min(max(rect.top(), value.y()), rect.bottom() - grid_size))

        value.setX(round(value.x() / grid_size) * grid_size)
        value.setY(round(value.y() / grid_size) * grid_size)

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
        painter.setPen(Qt.NoPen)

        painter.setBrush(self._brush_title)
        painter.drawPath(self._band(0, self.TITLE_HEIGHT, square_edge="bottom"))

        painter.setBrush(self._brush_background)
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
        painter.setPen(self._pen_selected if self.isSelected() else self._pen_default)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(outline.simplified())
