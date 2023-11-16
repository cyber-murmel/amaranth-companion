from PyQt5.QtWidgets import QGraphicsScene, QGraphicsView
from PyQt5.QtGui import QPalette, QPen, QPainter, QMouseEvent, QTransform
from PyQt5.QtCore import QLine, Qt, QEvent
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
        self.zoom_min, self.zoom_max = -10, 1
        self.zoom_factor = 1.25
        self.zoom_step = 1
        self.zoom = 0

        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.HighQualityAntialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self.setScene(self.canvas_scene)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.middleButtonPress(event)
        if event.button() == Qt.LeftButton:
            self.leftButtonPress(event)
        if event.button() == Qt.RightButton:
            self.rightButtonPress(event)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.middleButtonRelease(event)
        if event.button() == Qt.LeftButton:
            self.leftButtonRelease(event)
        if event.button() == Qt.RightButton:
            self.rightButtonRelease(event)
        else:
            super().mouseReleaseEvent(event)

    def middleButtonPress(self, event):
        # inject relase
        fake_event = QMouseEvent(
            QEvent.MouseButtonRelease,
            event.localPos(),
            event.screenPos(),
            Qt.LeftButton,
            Qt.NoButton,
            event.modifiers(),
        )
        super().mouseReleaseEvent(fake_event)

        self.setDragMode(QGraphicsView.ScrollHandDrag)

        # inject press
        fake_event = QMouseEvent(
            event.type(),
            event.localPos(),
            event.screenPos(),
            Qt.LeftButton,
            event.buttons() | Qt.LeftButton,
            event.modifiers(),
        )
        super().mousePressEvent(fake_event)

    def middleButtonRelease(self, event):
        # inject release
        fake_event = QMouseEvent(
            event.type(),
            event.localPos(),
            event.screenPos(),
            Qt.LeftButton,
            event.buttons() & ~Qt.LeftButton,
            event.modifiers(),
        )
        super().mouseReleaseEvent(fake_event)

        self.setDragMode(QGraphicsView.NoDrag)

    def leftButtonPress(self, event):
        super().mousePressEvent(event)

    def rightButtonPress(self, event):
        super().mousePressEvent(event)

    def leftButtonRelease(self, event):
        super().mousePressEvent(event)

    def rightButtonRelease(self, event):
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        # add or substract zoom step according to scroll direction
        self.zoom += self.zoom_step if (event.angleDelta().y() > 0) else -self.zoom_step

        # clamp zoom
        while self.zoom < self.zoom_min:
            self.zoom += self.zoom_step

        while self.zoom > self.zoom_max:
            self.zoom -= self.zoom_step

        transform = QTransform()
        transform.scale(self.zoom_factor**self.zoom, self.zoom_factor**self.zoom)
        self.setTransform(transform)
