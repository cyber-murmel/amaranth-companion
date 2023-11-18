from PyQt5.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PyQt5.QtGui import QPainterPath, QPen, QPalette
from PyQt5.QtCore import QPointF, Qt

# from math import abs


class EdgeGraphicsItem(QGraphicsPathItem):
    def __init__(self, start_point: QPointF, end_point: QPointF, parent=None):
        super().__init__(parent)

        self.radius = 6
        self.outline_width = 1

        # select colors
        palette = QPalette()
        self._pen = QPen(palette.color(QPalette.Light))
        self._pen_selected = QPen(palette.color(QPalette.Highlight))
        self._pen.setWidthF(2)
        self._pen_selected.setWidthF(2)

        self.setFlag(QGraphicsItem.ItemIsSelectable)

        # push to background
        self.setZValue(-1)

        self.start_point = start_point
        self.end_point = end_point

        self.posSource = [0, 0]
        self.posDestination = [200, 100]

    @property
    def start_point(self):
        return self._start_socket

    @start_point.setter
    def start_point(self, val):
        self._start_point = val

    @property
    def end_point(self):
        return self._end_socket

    @end_point.setter
    def end_point(self, val):
        self._end_point = val

    def paint(self, painter, QStyleOptionGraphicsItem, widget=None, **kwargs):
        self.update_path()

        painter.setPen(self._pen if not self.isSelected() else self._pen_selected)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

    def update_path(self):
        s = self.posSource
        d = self.posDestination
        # dist = (d[0] - s[0]) * 0.5
        dist = abs(self._start_point.x() - self._end_point.x())
        # if s[0] > d[0]:
        #     dist *= -1

        path = QPainterPath(self._start_point)
        path.cubicTo(
            self._start_point.x() + dist,
            self._start_point.y(),
            self._end_point.x() - dist,
            self._end_point.y(),
            self._end_point.x(),
            self._end_point.y(),
        )
        self.setPath(path)
