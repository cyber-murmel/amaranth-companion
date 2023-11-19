from PyQt5.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PyQt5.QtGui import QPainterPath, QPen, QPalette
from PyQt5.QtCore import QPointF, Qt

# from .edge import Edge

# from math import abs


class EdgeGraphicsItem(QGraphicsPathItem):
    def __init__(self, edge, parent=None):
        super().__init__(parent)

        self._edge = edge

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

        self._start_point = None
        self._end_point = None

    @property
    def start_point(self):
        return self._start_point

    @start_point.setter
    def start_point(self, val):
        self._start_point = val

    @property
    def end_point(self):
        return self._end_point

    @end_point.setter
    def end_point(self, val):
        self._end_point = val

    def paint(self, painter, QStyleOptionGraphicsItem, widget=None, **kwargs):
        self.update_path()

        if not self._edge or not self._edge.end_socket:
            painter.setPen(self._pen_selected)
        else:
            painter.setPen(self._pen if not self.isSelected() else self._pen_selected)

        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

    def update_path(self):
        dist = abs(self.start_point.x() - self.end_point.x())

        path = QPainterPath(self.start_point)
        path.cubicTo(
            self.start_point.x() + dist,
            self.start_point.y(),
            self.end_point.x() - dist,
            self.end_point.y(),
            self.end_point.x(),
            self.end_point.y(),
        )
        self.setPath(path)
