from PyQt5.QtWidgets import QGraphicsView
from PyQt5.QtGui import QPainter, QMouseEvent, QTransform
from PyQt5.QtCore import Qt, QEvent

from . import ModuleScene


class ModuleSceneView(QGraphicsView):
    def __init__(self, scene: ModuleScene = None, parent=None):
        super().__init__(parent)

        self.scene = scene  # calls setter, setter call setScene
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

    @property
    def scene(self):
        return self._scene

    @scene.setter
    def scene(self, val: ModuleScene):
        self._scene = val
        if self._scene:
            self.setScene(self._scene)

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

    def enterEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def leaveEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)

    def wheelEvent(self, event):
        self.zoomInOut(1 if (event.angleDelta().y() > 0) else -1)

    def zoomInOut(self, steps):
        zoom = self.zoom + self.zoom_step * steps

        # clamp zoom
        while zoom < self.zoom_min:
            zoom += self.zoom_step

        while zoom > self.zoom_max:
            zoom -= self.zoom_step

        self.zoom = zoom

        transform = QTransform()
        transform.scale(self.zoom_factor**self.zoom, self.zoom_factor**self.zoom)
        self.setTransform(transform)
