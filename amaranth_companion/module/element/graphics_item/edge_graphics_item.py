from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPainterPath, QPalette, QPen
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsPathItem

from .graphics_item import GraphicsItem

if TYPE_CHECKING:
    from .. import Edge


class EdgeGraphicsItem(GraphicsItem, QGraphicsPathItem):
    WIDTH = 2.0

    def __init__(self, edge: "Edge | None", parent=None):
        """``edge`` may be ``None``: the scene view uses a detached item as the
        preview curve while an edge is being dragged out of a socket."""
        super().__init__(element=edge, parent=parent)

        self._edge = edge

        palette = QPalette()
        self._pen = QPen(palette.color(QPalette.Light))
        self._pen_selected = QPen(palette.color(QPalette.Highlight))
        self._pen.setWidthF(self.WIDTH)
        self._pen_selected.setWidthF(self.WIDTH)

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(-1)  # draw behind the nodes

        self._start_point: QPointF | None = None
        self._end_point: QPointF | None = None

    @property
    def edge(self) -> "Edge | None":
        return self._edge

    @property
    def start_point(self) -> QPointF | None:
        return self._start_point

    @start_point.setter
    def start_point(self, value: QPointF) -> None:
        self.set_points(value, self._end_point)

    @property
    def end_point(self) -> QPointF | None:
        return self._end_point

    @end_point.setter
    def end_point(self, value: QPointF) -> None:
        self.set_points(self._start_point, value)

    def set_points(self, start: QPointF | None, end: QPointF | None) -> None:
        """Move both endpoints and rebuild the path once."""
        self._start_point = start
        self._end_point = end
        self._rebuild_path()

    def _rebuild_path(self) -> None:
        if self._start_point is None or self._end_point is None:
            return

        start, end = self._start_point, self._end_point
        # horizontal control-point offset, so the curve leaves and enters
        # its sockets horizontally
        offset = abs(start.x() - end.x())

        path = QPainterPath(start)
        path.cubicTo(
            start.x() + offset,
            start.y(),
            end.x() - offset,
            end.y(),
            end.x(),
            end.y(),
        )
        self.setPath(path)

    def paint(self, painter, style_option, widget=None, **kwargs):
        # the drag preview has no edge yet, so it always draws highlighted
        detached = self._edge is None or self._edge.end_socket is None
        painter.setPen(
            self._pen_selected if (detached or self.isSelected()) else self._pen
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
