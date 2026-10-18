from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, QEvent, QPointF
from PyQt5.QtGui import QMouseEvent, QPainter, QTransform
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsTextItem, QGraphicsView

from ..element import Edge, Socket
from ..element.graphics_item import (
    EdgeGraphicsItem,
    NodeGraphicsItem,
    SocketGraphicsItem,
)

if TYPE_CHECKING:
    from .. import Module, ModuleHistory


class DragMode(Enum):
    NONE = 0
    EDGE = 1
    NODE = 2


@dataclass
class DragState:
    mode: DragMode = DragMode.NONE
    #: socket the in-progress edge was dragged out of
    start_socket: Socket | None = None
    #: detached preview curve following the cursor
    edge_item: EdgeGraphicsItem | None = None
    #: where the left button went down, to measure the drag distance
    press_scene_pos: QPointF | None = None

    def reset(self) -> None:
        self.mode = DragMode.NONE
        self.start_socket = None
        self.edge_item = None


class ModuleSceneView(QGraphicsView):
    ZOOM_STEP = 1
    ZOOM_MIN, ZOOM_MAX = -10, 5
    ZOOM_FACTOR = 1.25
    EDGE_DRAG_THRESHOLD = 10

    def __init__(self, module: "Module | None" = None, parent=None):
        super().__init__(parent)

        self._module: "Module | None" = None
        self._node_edit = False
        self._zoom = 0
        self._drag = DragState()

        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.HighQualityAntialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        if module is not None:
            self.module = module

    # --- module ------------------------------------------------------------

    @property
    def module(self) -> "Module | None":
        return self._module

    @module.setter
    def module(self, value: "Module") -> None:
        self._module = value
        self.setScene(value.scene)
        self.centerOn(0, 0)

    @property
    def history(self) -> "ModuleHistory | None":
        return self._module.history if self._module else None

    @property
    def node_edit(self) -> bool:
        return self._node_edit

    @node_edit.setter
    def node_edit(self, value: bool) -> None:
        # editing node content is one undo step, recorded when it ends
        if self._node_edit and not value and self.history:
            self.history.check_in()
        self._node_edit = value

    # --- mouse dispatch ----------------------------------------------------
    # Each handler is responsible for calling the base implementation exactly
    # once; the branches are mutually exclusive so it cannot happen twice.

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._middle_button_press(event)
        elif event.button() == Qt.LeftButton:
            self._left_button_press(event)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._middle_button_release(event)
        elif event.button() == Qt.LeftButton:
            self._left_button_release(event)
        else:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag.mode is DragMode.EDGE and self._drag.edge_item:
            self._drag.edge_item.end_point = self.mapToScene(event.pos())
        super().mouseMoveEvent(event)

    def _left_button_press(self, event):
        item = self.item_at(event)
        self._drag.press_scene_pos = self.mapToScene(event.pos())

        if self._drag.mode is DragMode.NONE:
            if isinstance(item, SocketGraphicsItem):
                # swallow the event: starting an edge must not also select the
                # socket or begin a rubber-band drag
                self._edge_drag_start(item)
                return

            if isinstance(item, (NodeGraphicsItem, QGraphicsTextItem)):
                self._drag.mode = DragMode.NODE

        elif self._drag.mode is DragMode.EDGE:
            self._edge_drag_end(item)

        self.setDragMode(QGraphicsView.NoDrag if item else QGraphicsView.RubberBandDrag)
        super().mousePressEvent(event)

    def _left_button_release(self, event):
        if self._drag.mode is DragMode.EDGE:
            if self._drag_distance(event) > self.EDGE_DRAG_THRESHOLD:
                self._edge_drag_end(self.item_at(event))
        elif self._drag.mode is DragMode.NODE:
            self._node_drag_end()

        super().mouseReleaseEvent(event)

    def _middle_button_press(self, event):
        # QGraphicsView only pans with the left button, so translate the middle
        # button into a synthetic left-button drag
        super().mouseReleaseEvent(
            self._as_left_button(event, QEvent.MouseButtonRelease)
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mousePressEvent(self._as_left_button(event, event.type()))

    def _middle_button_release(self, event):
        super().mouseReleaseEvent(
            self._as_left_button(event, event.type(), pressed=False)
        )
        self.setDragMode(QGraphicsView.NoDrag)

    @staticmethod
    def _as_left_button(event, event_type, pressed: bool = True) -> QMouseEvent:
        buttons = (
            event.buttons() | Qt.LeftButton
            if pressed
            else event.buttons() & ~Qt.LeftButton
        )
        return QMouseEvent(
            event_type,
            event.localPos(),
            event.screenPos(),
            Qt.LeftButton,
            buttons,
            event.modifiers(),
        )

    def item_at(self, event) -> QGraphicsItem | None:
        """The item under the mouse for a press/release event."""
        return self.itemAt(event.pos())

    def _drag_distance(self, event) -> float:
        if self._drag.press_scene_pos is None:
            return 0.0
        delta = self._drag.press_scene_pos - self.mapToScene(event.pos())
        return (delta.x() ** 2 + delta.y() ** 2) ** 0.5

    # --- dragging ----------------------------------------------------------

    def _node_drag_end(self) -> None:
        self._drag.reset()
        if self.history:
            self.history.check_in()

    def _edge_drag_start(self, socket_item: SocketGraphicsItem) -> None:
        start_point = socket_item.socket.scene_pos

        self._drag.mode = DragMode.EDGE
        self._drag.start_socket = socket_item.socket
        self._drag.edge_item = EdgeGraphicsItem(None)
        self._drag.edge_item.set_points(start_point, start_point)

        self.scene().addItem(self._drag.edge_item)

    def _edge_drag_end(self, item) -> None:
        start_socket = self._drag.start_socket

        if self._drag.edge_item is not None:
            self.scene().removeItem(self._drag.edge_item)
        self._drag.reset()

        if not isinstance(item, SocketGraphicsItem) or self._module is None:
            return

        target = item.socket
        new_edge = Edge(start_socket, target)
        if self._module.add_edge(new_edge):
            # an input takes a single edge: drop whatever was there before.
            # list() because remove_edge mutates the socket's edge list.
            for edge in list(target.edges):
                if edge is not new_edge:
                    self._module.remove_edge(edge)

        self.history.check_in()

    # --- view --------------------------------------------------------------

    def enterEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        super().leaveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.zoom_in_out(1 if delta > 0 else -1 if delta < 0 else 0)

    def zoom_in_out(self, steps: int) -> None:
        self._zoom = min(
            max(self._zoom + self.ZOOM_STEP * steps, self.ZOOM_MIN), self.ZOOM_MAX
        )

        scale = self.ZOOM_FACTOR**self._zoom
        transform = QTransform()
        transform.scale(scale, scale)
        self.setTransform(transform)

    def keyPressEvent(self, event):
        if (not self.node_edit) and (event.key() == Qt.Key_Delete):
            self.delete_selected()
        else:
            super().keyPressEvent(event)

    def delete_selected(self) -> None:
        if self._module is None:
            return

        selected = self.scene().selectedItems()

        # edges first: removing a node also removes its remaining edges, so
        # doing it the other way round would delete some edges twice
        for item in selected:
            if isinstance(item, EdgeGraphicsItem) and item.edge is not None:
                self._module.remove_edge(item.edge)
        for item in selected:
            if isinstance(item, NodeGraphicsItem):
                self._module.remove_node(item.node)

        self.history.check_in()

    def undo(self) -> None:
        if self.history:
            self.history.undo()

    def redo(self) -> None:
        if self.history:
            self.history.redo()
