from PyQt5.QtWidgets import QGraphicsItem, QGraphicsTextItem, QGraphicsProxyWidget
from PyQt5.QtGui import QPainterPath, QBrush, QPen, QPalette
from PyQt5.QtCore import Qt, QRectF
from .content_widget import NodeContentWidget


class NodeGraphicsItem(QGraphicsItem):
    def __init__(self, node, title: str = "Node", parent=None):
        super().__init__(parent)

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
        self._proxy_widget = QGraphicsProxyWidget(self)
        self.content_widget = self._node.content_widget

        # enable movement
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)

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
