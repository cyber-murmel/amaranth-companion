from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainterPath, QBrush, QPen, QPalette
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsTextItem, QGraphicsProxyWidget

from .graphics_item import GraphicsItem


class NodeProxyWidget(QGraphicsProxyWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self._item = parent

    @property
    def scene_view(self):
        return self._item.node.module.scene_view

    # tell the scene if node content is being edited
    def focusInEvent(self, a0):
        self.scene_view.node_edit = True
        super().focusInEvent(a0)

    def focusOutEvent(self, a0):
        self.scene_view.node_edit = False
        super().focusOutEvent(a0)


class NodeGraphicsItem(GraphicsItem, QGraphicsItem):
    def __init__(self, node, title: str = "Node", parent=None):
        super().__init__(element=node, parent=parent)

        self._node = node

        self.width = 200
        self.height = 300
        self.edge_size = 10
        self.title_height = 24
        self._padding = 4.0

        # select colors
        palette = QPalette()
        self._pen_default = QPen(palette.color(QPalette.Dark))
        self._pen_selected = QPen(palette.color(QPalette.Highlight))
        self._brush_title = QBrush(palette.color(QPalette.Midlight))
        self._brush_background = QBrush(palette.color(QPalette.Light))

        # init title
        self._title_item = QGraphicsTextItem(self)
        self.title = title

        # init content
        self._proxy_widget = NodeProxyWidget(self)
        self.content_widget = self._node.content_widget

        # enable movement
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

    @property
    def node(self):
        return self._node

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value
        self._title_item.setPlainText(self._title)

    @property
    def content_widget(self):
        return self._content

    @content_widget.setter
    def content_widget(self, value):
        self._content = value
        self._content.setGeometry(
            self.edge_size,
            self.title_height + self.edge_size,
            self.width - 2 * self.edge_size,
            self.height - 2 * self.edge_size - self.title_height,
        )
        self._proxy_widget.setWidget(self._content)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            rect = self.scene.sceneRect()
            grid_size = self.scene.GRID_SIZE

            # limit movement to scene
            if not rect.contains(value):
                value.setX(min(max(rect.left(), value.x()), rect.right() - grid_size))
                value.setY(min(max(rect.top(), value.y()), rect.bottom() - grid_size))

            # place on grid
            value.setX(round(value.x() / grid_size) * grid_size)
            value.setY(round(value.y() / grid_size) * grid_size)

        return value

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height).normalized()

    def paint(self, painter, QStyleOptionGraphicsItem, widget=None, **kwargs):
        # title
        path_title = QPainterPath()
        path_title.setFillRule(Qt.WindingFill)
        path_title.addRoundedRect(
            0, 0, self.width, self.title_height, self.edge_size, self.edge_size
        )
        path_title.addRect(
            0, self.title_height - self.edge_size, self.edge_size, self.edge_size
        )
        path_title.addRect(
            self.width - self.edge_size,
            self.title_height - self.edge_size,
            self.edge_size,
            self.edge_size,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._brush_title)
        painter.drawPath(path_title.simplified())

        # content
        path_content = QPainterPath()
        path_content.setFillRule(Qt.WindingFill)
        path_content.addRoundedRect(
            0,
            self.title_height,
            self.width,
            self.height - self.title_height,
            self.edge_size,
            self.edge_size,
        )
        path_content.addRect(0, self.title_height, self.edge_size, self.edge_size)
        path_content.addRect(
            self.width - self.edge_size,
            self.title_height,
            self.edge_size,
            self.edge_size,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._brush_background)
        painter.drawPath(path_content.simplified())

        # outline
        path_outline = QPainterPath()
        path_outline.addRoundedRect(
            0, 0, self.width, self.height, self.edge_size, self.edge_size
        )
        painter.setPen(
            self._pen_default if not self.isSelected() else self._pen_selected
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path_outline.simplified())
