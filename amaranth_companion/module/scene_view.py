from PyQt5.QtWidgets import QGraphicsView
from PyQt5.QtGui import QPainter, QMouseEvent, QTransform
from PyQt5.QtCore import Qt, QEvent

from . import ModuleScene
from ..socket import SocketGraphicsItem
from ..edge import Edge, EdgeGraphicsItem


class ModuleSceneView(QGraphicsView):
    class DragMode:
        NONE = 0
        EDGE = 1

    def __init__(self, module=None, parent=None):
        super().__init__(parent)

        self.module = module
        if module:
            self.scene = self.module.scene  # calls setter, setter calls setScene
        self.zoom_min, self.zoom_max = -10, 5
        self.zoom_factor = 1.25
        self.zoom_step = 1
        self.zoom = 0
        self.drag_mode = ModuleSceneView.DragMode.NONE
        self._lmb_press_scene_pos = None
        self._edge_drag_threshold = 10
        self._drag_start_socket = None
        self._drag_edge_item = None

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
    def module(self):
        return self._module

    @module.setter
    def module(self, val):
        self._module = val
        if self.module:
            self.scene = self.module.scene

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
            self.middle_button_press(event)
        if event.button() == Qt.LeftButton:
            self.left_button_press(event)
        if event.button() == Qt.RightButton:
            self.right_button_press(event)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.middle_button_release(event)
        if event.button() == Qt.LeftButton:
            self.left_button_release(event)
        if event.button() == Qt.RightButton:
            self.right_button_release(event)
        else:
            super().mouseReleaseEvent(event)

    def middle_button_press(self, event):
        # inject release
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

    def middle_button_release(self, event):
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

    def left_button_press(self, event):
        item = self.get_item_at_click(event)
        self._lmb_press_scene_pos = self.mapToScene(event.pos())

        if self.drag_mode == self.DragMode.NONE:
            if self.edge_drag_start(item):
                return

        if self.drag_mode == self.DragMode.EDGE:
            if self.edge_drag_end(item):
                return

        super().mousePressEvent(event)

    def right_button_press(self, event):
        super().mousePressEvent(event)

    def left_button_release(self, event):
        if self.drag_mode == ModuleSceneView.DragMode.EDGE:
            # calculate drag distance
            lmb_release_scene_pos = self.mapToScene(event.pos())
            diff_press_release = self._lmb_press_scene_pos - lmb_release_scene_pos
            drag_distance = (
                diff_press_release.x() ** 2 + diff_press_release.y() ** 2
            ) ** 0.5

            if drag_distance > self._edge_drag_threshold:
                item = self.get_item_at_click(event)
                if self.edge_drag_end(item):
                    return

        super().mouseReleaseEvent(event)

    def right_button_release(self, event):
        super().mouseReleaseEvent(event)

    def get_item_at_click(self, event):
        """return the object on which we've clicked/release mouse button"""
        pos = event.pos()
        obj = self.itemAt(pos)
        return obj

    def edge_drag_start(self, item):
        if type(item) is SocketGraphicsItem:
            self.drag_mode = ModuleSceneView.DragMode.EDGE
            self._drag_start_socket = item.socket
            start_point = item.socket.scene_pos
            self._drag_edge_item = EdgeGraphicsItem(None)
            self._drag_edge_item.start_point = start_point
            self._drag_edge_item.end_point = start_point
            self.scene.addItem(self._drag_edge_item)

            print("Start dragging edge")
            print("  assign Start Socket")
            return True

        return False

    def mouseMoveEvent(self, event):
        if self.drag_mode == self.DragMode.EDGE:
            pos = self.mapToScene(event.pos())
            self._drag_edge_item.end_point = pos
            self._drag_edge_item.update_path()

        super().mouseMoveEvent(event)

    def edge_drag_end(self, item):
        self.drag_mode = self.DragMode.NONE

        self.scene.removeItem(self._drag_edge_item)

        del self._drag_edge_item

        if type(item) is SocketGraphicsItem:
            print("  assign End Socket")

            for edge in item.socket._edges:
                self.module.removeEdge(edge)

            self.module.addEdge(Edge(self._drag_start_socket, item.socket))
            return True

        return False

    def enterEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def leaveEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)

    def wheelEvent(self, event):
        self.zoom_in_out(
            1
            if (event.angleDelta().y() > 0)
            else (-1 if (event.angleDelta().y() < 0) else 0)
        )

    def zoom_in_out(self, steps):
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