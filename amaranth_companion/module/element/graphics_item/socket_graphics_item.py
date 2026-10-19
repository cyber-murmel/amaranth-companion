from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGraphicsItem

from ....theme import current_theme
from .graphics_item import GraphicsItem

if TYPE_CHECKING:
    from .. import Socket


class SocketGraphicsItem(GraphicsItem, QGraphicsItem):
    RADIUS = 6
    OUTLINE_WIDTH = 1

    #: room for the label between the socket and the node's content widget.
    #: The node reserves the same width as a gutter, so the two never overlap.
    LABEL_WIDTH = 44
    LABEL_PADDING = 5
    LABEL_POINT_SIZE = 9

    def __init__(self, socket: "Socket"):
        super().__init__(element=socket, parent=socket.node.graphics_item)

        self._socket = socket

        self.setFlag(QGraphicsItem.ItemIsSelectable)

    @property
    def socket(self) -> "Socket":
        return self._socket

    @property
    def label(self) -> str:
        """What to write beside the socket.

        The stripped name: which side the socket is on already says ``_in`` or
        ``_out``, and the square shape already says ``_param``, so spelling the
        suffix out again on every socket is noise.
        """
        return self._socket.label

    def _label_rect(self) -> QRectF:
        """Where the label goes: inboard of the socket, inside the node."""
        offset = self.RADIUS + self.LABEL_PADDING
        left = offset if self._socket.is_input else -offset - self.LABEL_WIDTH
        return QRectF(left, -self.RADIUS - 2, self.LABEL_WIDTH, 2 * self.RADIUS + 4)

    def boundingRect(self):
        extent = self.RADIUS + self.OUTLINE_WIDTH
        return QRectF(-extent, -extent, 2 * extent, 2 * extent).united(
            self._label_rect()
        )

    def paint(self, painter, style_option, widget=None, **kwargs):
        theme = current_theme()
        painter.setBrush(theme.socket_color(self._socket.kind.value))
        painter.setPen(theme.pen_socket_outline)

        extent = 2 * self.RADIUS
        if self._socket.is_param:
            # parameters carry an elaboration-time value rather than a wire, so
            # they are square: the shape says at a glance what may connect to
            # what, without having to read the colours
            painter.drawRect(-self.RADIUS, -self.RADIUS, extent, extent)
        else:
            painter.drawEllipse(-self.RADIUS, -self.RADIUS, extent, extent)

        self._paint_label(painter, theme)

    def _paint_label(self, painter, theme) -> None:
        text = self.label
        if not text:
            return

        font = QFont(painter.font())
        font.setPointSize(self.LABEL_POINT_SIZE)
        painter.setFont(font)
        painter.setPen(theme.socket_label)

        # inputs read left to right away from their socket, outputs read back
        # towards theirs, so both sit tight against the edge they belong to
        alignment = Qt.AlignLeft if self._socket.is_input else Qt.AlignRight
        painter.drawText(
            self._label_rect(),
            alignment | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(text, Qt.ElideRight, self.LABEL_WIDTH),
        )
