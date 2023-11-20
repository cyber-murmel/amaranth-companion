from PyQt5.QtWidgets import QGraphicsItem
from PyQt5.QtGui import QBrush, QPen, QPalette, QColor
from PyQt5.QtCore import QRectF


class SocketGraphicsItem(QGraphicsItem):
    def __init__(self, socket):
        super().__init__(socket.node.graphics_item)

        self._socket = socket

        self.radius = 6
        self.outline_width = 1

        # select colors
        palette = QPalette()
        self._pen = QPen(palette.color(QPalette.Dark))
        self._brush = QBrush(QColor("#FFFF7700"))

        self.setFlag(QGraphicsItem.ItemIsSelectable)

    def boundingRect(self):
        return QRectF(
            -self.radius - self.outline_width,
            -self.radius - self.outline_width,
            2 * (self.radius + self.outline_width),
            2 * (self.radius + self.outline_width),
        )

    def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
        # painting circle
        painter.setBrush(self._brush)
        painter.setPen(self._pen)
        painter.drawEllipse(
            -self.radius, -self.radius, 2 * self.radius, 2 * self.radius
        )

    @property
    def socket(self):
        return self._socket
