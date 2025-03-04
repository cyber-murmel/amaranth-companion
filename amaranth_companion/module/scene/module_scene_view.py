from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QPainter, QMouseEvent, QTransform
from PyQt5.QtWidgets import QGraphicsView, QGraphicsTextItem

from .module_scene_history import ModuleSceneHistory

from amaranth_companion.module.element import Edge
from amaranth_companion.module.element.graphics_item import (
    EdgeGraphicsItem,
    NodeGraphicsItem,
    SocketGraphicsItem,
)


class ModuleSceneView(QGraphicsView):
    class DragMode:
        NONE = 0
        EDGE = 1
        NODE = 2

    ZOOM_STEP = 1
    ZOOM_MIN, ZOOM_MAX = -10, 5
    ZOOM_FACTOR = 1.25

    def __init__(self, module, parent=None):
        super().__init__(parent)

        if module:
            self._module = module
            self._history = ModuleSceneHistory(self._module)
            self._history.check_in()

        self._node_edit = False
        self._zoom = 0
        self._drag_mode = ModuleSceneView.DragMode.NONE
        self._lmb_press_scene_pos = None
        self._edge_drag_threshold = 10
        self._drag_start_socket = None
        self._drag_edge_item = None
        self._drag_node_item = None
        self._drag_old_pos = None

        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.HighQualityAntialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # self.setScene(self.scene)
        # self.centerOn(0, 0)

    @property
    def module(self):
        return self._module

    @module.setter
    def module(self, value):
        self._module = value
        self.setScene(self._module.scene)
        self.centerOn(0, 0)
        self._history = ModuleSceneHistory(self._module)
        self._history.check_in()

    @property
    def node_edit(self):
        return self._node_edit

    @node_edit.setter
    def node_edit(self, val):
        # save state when done editing
        if self._node_edit and not val:
            self._history.check_in()
        self._node_edit = val

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

    def left_button_press(self, event):
        item = self.get_item_at_click(event)
        self._lmb_press_scene_pos = self.mapToScene(event.pos())

        if self._drag_mode == self.DragMode.NONE:
            if type(item) is SocketGraphicsItem:
                self.edge_drag_start(item)
                return

            if type(item) is NodeGraphicsItem:
                self.node_drag_start(item)
            if type(item) is QGraphicsTextItem:
                self.node_drag_start(item.parentItem())

        if self._drag_mode == self.DragMode.EDGE:
            self.edge_drag_end(item)

        if item:
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            self.setDragMode(QGraphicsView.RubberBandDrag)

        super().mousePressEvent(event)

    def left_button_release(self, event):
        if self._drag_mode == ModuleSceneView.DragMode.EDGE:
            # calculate drag distance
            lmb_release_scene_pos = self.mapToScene(event.pos())
            diff_press_release = self._lmb_press_scene_pos - lmb_release_scene_pos
            drag_distance = (
                diff_press_release.x() ** 2 + diff_press_release.y() ** 2
            ) ** 0.5

            if drag_distance > self._edge_drag_threshold:
                item = self.get_item_at_click(event)
                self.edge_drag_end(item)

        if self._drag_mode == ModuleSceneView.DragMode.NODE:
            item = self.get_item_at_click(event)
            self.node_drag_end(item)
        super().mouseReleaseEvent(event)

    def right_button_press(self, event):
        super().mousePressEvent(event)

    def right_button_release(self, event):
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

    def get_item_at_click(self, event):
        """return the object on which we've clicked/release mouse button"""
        pos = event.pos()
        obj = self.itemAt(pos)
        return obj

    def node_drag_start(self, node_item: NodeGraphicsItem):
        self._drag_mode = ModuleSceneView.DragMode.NODE
        self._drag_node_item = node_item
        self._drag_old_pos = node_item.node.pos

    def node_drag_end(self, item: NodeGraphicsItem):
        self._drag_mode = ModuleSceneView.DragMode.NONE
        self._history.check_in()

    def edge_drag_start(self, socket_item):
        self._drag_mode = ModuleSceneView.DragMode.EDGE
        self._drag_start_socket = socket_item.socket
        start_point = socket_item.socket.scene_pos
        self._drag_edge_item = EdgeGraphicsItem(None)
        self._drag_edge_item.start_point = start_point
        self._drag_edge_item.end_point = start_point
        self.scene().addItem(self._drag_edge_item)

    def edge_drag_end(self, item):
        self._drag_mode = ModuleSceneView.DragMode.NONE

        self.scene().removeItem(self._drag_edge_item)

        del self._drag_edge_item

        if type(item) is SocketGraphicsItem:
            new_edge = Edge(self._drag_start_socket, item.socket)
            if self.module.addEdge(new_edge):
                for edge in item.socket.edges:
                    if not (edge is new_edge):
                        self.module.removeEdge(edge)
            self._history.check_in()

    def mouseMoveEvent(self, event):
        if self._drag_mode == self.DragMode.EDGE:
            pos = self.mapToScene(event.pos())
            self._drag_edge_item.end_point = pos
            self._drag_edge_item.update_path()

        if self.module:
            selected_nodes = [
                node
                for node in self.module._nodes.values()
                if node.graphics_item.isSelected()
            ]

            selected_edges = {
                edge
                for node in selected_nodes
                for socket in list(node._input_sockets.values())
                + list(node._output_sockets.values())
                for edge in socket._edges
            }

            for edge in selected_edges:
                edge.update_path()

        super().mouseMoveEvent(event)

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
        zoom = self._zoom + self.ZOOM_STEP * steps

        # clamp zoom
        while zoom < self.ZOOM_MIN:
            zoom += self.ZOOM_STEP

        while zoom > self.ZOOM_MAX:
            zoom -= self.ZOOM_STEP

        self._zoom = zoom

        transform = QTransform()
        transform.scale(self.ZOOM_FACTOR**self._zoom, self.ZOOM_FACTOR**self._zoom)
        self.setTransform(transform)

    def keyPressEvent(self, event):
        if (not self.node_edit) and (event.key() == Qt.Key_Delete):
            self.delete_selected()
        else:
            super().keyPressEvent(event)

    def delete_selected(self):
        selected_items = self.scene().selectedItems()

        selected_edge_items = [
            item for item in selected_items if isinstance(item, EdgeGraphicsItem)
        ]
        selected_node_items = [
            item for item in selected_items if isinstance(item, NodeGraphicsItem)
        ]

        for edge_item in selected_edge_items:
            self.module.removeEdge(edge_item.edge)
        for node_item in selected_node_items:
            self.module.removeNode(node_item.node)

        self._history.check_in()

    def undo(self):
        self._history.undo()

    def redo(self):
        self._history.redo()
