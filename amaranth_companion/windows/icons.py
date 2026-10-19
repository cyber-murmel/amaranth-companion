"""Toolbar and menu icons, recoloured for the theme.

The shipped icons are black line art, which is invisible on a dark toolbar.
Qt's svg renderer has no document colour to resolve ``currentColor`` against,
so the colour is substituted in the svg text before it is rendered -- the same
trick the hierarchical block icons use.

Icons are rebuilt when the theme changes, which is why :func:`themed_icon`
takes a resource path rather than a cached ``QIcon``.
"""

from functools import lru_cache
from logging import getLogger

from PyQt5.QtCore import QByteArray, QFile, QIODevice, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from .. import qrc_resources  # noqa: F401 - registers the ":*.svg" paths
from ..theme import current_theme

log = getLogger(__name__)

#: the colour the shipped icons are drawn in, and so the one to replace
SOURCE_COLOR = "#000000"

#: rendered at several sizes so the icon stays sharp on a scaled display
ICON_SIZES = (16, 24, 32, 48)


@lru_cache(maxsize=64)
def _read(resource: str) -> str:
    """The svg text behind a ``:name.svg`` resource path."""
    handle = QFile(resource)
    if not handle.open(QIODevice.ReadOnly):
        log.warning("no icon resource %s", resource)
        return ""

    try:
        return bytes(handle.readAll()).decode("utf-8", "replace")
    finally:
        handle.close()


def _render(svg: str, size: int) -> QPixmap:
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
    finally:
        painter.end()

    return pixmap


def themed_icon(resource: str, color=None) -> QIcon:
    """The icon at ``resource``, drawn in the theme's foreground colour.

    Falls back to loading the resource unchanged if it cannot be read, so a
    missing icon costs a blank button rather than an exception.
    """
    svg = _read(resource)
    if not svg:
        return QIcon(resource)

    name = (color or current_theme().button_text).name()
    svg = svg.replace(SOURCE_COLOR, name)

    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(_render(svg, size))
    return icon
