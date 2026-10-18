from typing import TYPE_CHECKING

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QBrush, QColor, QPalette, QPen
from PyQt5.QtWidgets import QGraphicsItem

from .graphics_item import GraphicsItem

if TYPE_CHECKING:
    from .. import Socket


class SocketGraphicsItem(GraphicsItem, QGraphicsItem):
    RADIUS = 6
    OUTLINE_WIDTH = 1
    COLOR = "#FFFF7700"

    def __init__(self, socket: "Socket"):
        super().__init__(element=socket, parent=socket.node.graphics_item)

        self._socket = socket

        self._pen = QPen(QPalette().color(QPalette.Dark))
        self._brush = QBrush(QColor(self.COLOR))

        self.setFlag(QGraphicsItem.ItemIsSelectable)

    @property
    def socket(self) -> "Socket":
        return self._socket

    def boundingRect(self):
        extent = self.RADIUS + self.OUTLINE_WIDTH
        return QRectF(-extent, -extent, 2 * extent, 2 * extent)

    def paint(self, painter, style_option, widget=None, **kwargs):
        painter.setBrush(self._brush)
        painter.setPen(self._pen)
        painter.drawEllipse(
            -self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS
        )
