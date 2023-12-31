from math import floor
from PyQt5.QtCore import QLine
from PyQt5.QtGui import QPalette, QPen
from PyQt5.QtWidgets import QGraphicsScene


class ModuleScene(QGraphicsScene):
    GRID_SIZE = 20  # size of unit length
    GRID_STRIDE = 5  # number of unit length in macro length

    def __init__(self, parent=None):
        super().__init__(parent)

        palette = QPalette()
        self._color_major = palette.color(QPalette.Dark)
        self._color_minor = palette.color(QPalette.Mid)

        self._pen_minor = QPen(self._color_minor)
        self._pen_major = QPen(self._color_major)
        self._pen_major.setWidth(2)

        self.scene_width, self.scene_height = 80000, 60000
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

        left_most = left - (left % self.GRID_SIZE)
        top_most = top - (top % self.GRID_SIZE)

        lines_major, lines_minor = [], []
        for x in range(left_most, right, self.GRID_SIZE):
            line = QLine(x, top, x, bottom)
            if 0 == (x % (self.GRID_SIZE * self.GRID_STRIDE)):
                lines_major.append(line)
            else:
                lines_minor.append(line)
        for y in range(top_most, bottom, self.GRID_SIZE):
            line = QLine(left, y, right, y)
            if 0 == (y % (self.GRID_SIZE * self.GRID_STRIDE)):
                lines_major.append(line)
            else:
                lines_minor.append(line)

        if lines_minor:
            painter.setPen(self._pen_minor)
            painter.drawLines(*lines_minor)
        if lines_major:
            painter.setPen(self._pen_major)
            painter.drawLines(*lines_major)
