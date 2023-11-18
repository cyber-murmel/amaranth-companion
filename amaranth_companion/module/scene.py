from PyQt5.QtWidgets import QGraphicsScene, QGraphicsItem, QPushButton, QTextEdit
from PyQt5.QtGui import QPalette, QPen, QBrush, QFont, QColor
from PyQt5.QtCore import QLine, Qt
from math import floor


class ModuleScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._grid_size = 20
        self._grid_stride = 5

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

        if lines_minor:
            painter.setPen(self._pen_minor)
            painter.drawLines(*lines_minor)
        if lines_major:
            painter.setPen(self._pen_major)
            painter.drawLines(*lines_major)

    def addDebugContent(self):
        greenBrush = QBrush(Qt.green)
        outlinePen = QPen(Qt.black)
        outlinePen.setWidth(2)

        rect = self.addRect(100, 100, 80, 100, outlinePen, greenBrush)
        rect.setFlag(QGraphicsItem.ItemIsMovable)

        text = self.addText("This is my Awesome text!", QFont("Ubuntu"))
        text.setFlag(QGraphicsItem.ItemIsSelectable)
        text.setFlag(QGraphicsItem.ItemIsMovable)
        text.setDefaultTextColor(QColor.fromRgbF(1.0, 1.0, 1.0))

        widget1 = QPushButton("Hello World")
        proxy1 = self.addWidget(widget1)
        proxy1.setFlag(QGraphicsItem.ItemIsMovable)
        proxy1.setPos(200, 30)

        widget2 = QTextEdit()
        proxy2 = self.addWidget(widget2)
        proxy2.setFlag(QGraphicsItem.ItemIsSelectable)
        proxy2.setPos(200, 60)

        line = self.addLine(300, 300, 400, 500, outlinePen)
        line.setFlag(QGraphicsItem.ItemIsMovable)
        line.setFlag(QGraphicsItem.ItemIsSelectable)
