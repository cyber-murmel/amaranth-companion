from PyQt5.QtWidgets import QGraphicsScene, QGraphicsView
from PyQt5.QtGui import QPalette, QPen, QPainter
from PyQt5.QtCore import QLine, Qt
from math import floor


class CanvasScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._grid_size = 20
        self._grid_stride = 5

        palette = QPalette()
        color_base = palette.color(palette.AlternateBase)
        self._color_major = color_base.darker()
        self._color_minor = self._color_major.lighter()

        self._pen_minor = QPen(self._color_minor)
        self._pen_major = QPen(self._color_major)
        self._pen_major.setWidth(2)

        self.scene_width, self.scene_height = 800000, 600000
        self.setSceneRect(
            -self.scene_width // 2,
            -self.scene_height // 2,
            self.scene_width,
            self.scene_height,
        )

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        left = floor(rect.left())
        top = floor(rect.top())
        right = floor(rect.right())
        bottom = floor(rect.bottom())

        left_most = left - (left % self._grid_size)
        top_most = top - (top % self._grid_size)

        lines_major, lines_minor = [], []
        for x in range(left_most, right, self._grid_size):
            line = QLine(x, top, x, bottom)
            if 0 == (x % (self._grid_size * self._grid_stride)):
                lines_major.append(line)
            else:
                lines_minor.append(line)
        for y in range(top_most, bottom, self._grid_size):
            line = QLine(left, y, right, y)
            if 0 == (y % (self._grid_size * self._grid_stride)):
                lines_major.append(line)
            else:
                lines_minor.append(line)

        if lines_major:
            painter.setPen(self._pen_major)
            painter.drawLines(*lines_major)
        if lines_minor:
            painter.setPen(self._pen_minor)
            painter.drawLines(*lines_minor)


class CanvasView(QGraphicsView):
    def __init__(self, parent, canvas_scene):
        super().__init__(parent)

        self.canvas_scene = canvas_scene

        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.HighQualityAntialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.setScene(self.canvas_scene)
