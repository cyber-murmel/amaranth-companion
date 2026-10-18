from math import floor

from PyQt5.QtCore import QLine
from PyQt5.QtGui import QPalette, QPen
from PyQt5.QtWidgets import QGraphicsScene


class ModuleScene(QGraphicsScene):
    GRID_SIZE = 20  # size of unit length
    GRID_STRIDE = 5  # number of unit lengths per macro length
    WIDTH, HEIGHT = 80000, 60000

    def __init__(self, parent=None):
        super().__init__(parent)

        palette = QPalette()
        self._pen_minor = QPen(palette.color(QPalette.Mid))
        self._pen_major = QPen(palette.color(QPalette.Dark))
        self._pen_major.setWidth(2)

        self.scene_width, self.scene_height = self.WIDTH, self.HEIGHT
        self.setSceneRect(
            -self.scene_width // 2,
            -self.scene_height // 2,
            self.scene_width,
            self.scene_height,
        )

    @property
    def macro_size(self) -> int:
        return self.GRID_SIZE * self.GRID_STRIDE

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        left = floor(rect.left())
        top = floor(rect.top())
        right = floor(rect.right())
        bottom = floor(rect.bottom())

        lines_major, lines_minor = [], []
        for x in range(left - (left % self.GRID_SIZE), right, self.GRID_SIZE):
            line = QLine(x, top, x, bottom)
            bucket = lines_major if 0 == (x % self.macro_size) else lines_minor
            bucket.append(line)
        for y in range(top - (top % self.GRID_SIZE), bottom, self.GRID_SIZE):
            line = QLine(left, y, right, y)
            bucket = lines_major if 0 == (y % self.macro_size) else lines_minor
            bucket.append(line)

        if lines_minor:
            painter.setPen(self._pen_minor)
            painter.drawLines(lines_minor)
        if lines_major:
            painter.setPen(self._pen_major)
            painter.drawLines(lines_major)
