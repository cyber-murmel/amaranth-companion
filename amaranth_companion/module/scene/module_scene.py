from math import floor

from PyQt5.QtCore import QLine
from PyQt5.QtWidgets import QGraphicsScene

from ..element.graphics_item.graphics_item import GraphicsItem
from ..grid import SIZE, STRIDE
from ...theme import current_theme, theme_manager


class ModuleScene(QGraphicsScene):
    GRID_SIZE = SIZE  # size of unit length
    GRID_STRIDE = STRIDE  # number of unit lengths per macro length
    WIDTH, HEIGHT = 80000, 60000

    def __init__(self, parent=None):
        super().__init__(parent)

        theme_manager().changed.connect(self._theme_changed)
        self._apply_theme()

        self.scene_width, self.scene_height = self.WIDTH, self.HEIGHT
        self.setSceneRect(
            -self.scene_width // 2,
            -self.scene_height // 2,
            self.scene_width,
            self.scene_height,
        )

    def _apply_theme(self) -> None:
        self.setBackgroundBrush(current_theme().brush_canvas)

    def _theme_changed(self) -> None:
        self._apply_theme()
        for item in self.items():
            if isinstance(item, GraphicsItem):
                item.apply_theme()
        # the grid pens and the item brushes are read while painting, but
        # nothing has asked for a repaint yet
        self.update()

    @property
    def macro_size(self) -> int:
        return self.GRID_SIZE * self.GRID_STRIDE

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        theme = current_theme()
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
            painter.setPen(theme.pen_grid_minor)
            painter.drawLines(lines_minor)
        if lines_major:
            painter.setPen(theme.pen_grid_major)
            painter.drawLines(lines_major)
