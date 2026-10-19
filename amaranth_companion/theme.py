"""Application-wide colour theme.

Every colour the editor paints comes from here instead of from Qt's palette
roles: the stock roles (``Light``, ``Mid``, ``Midlight``, ...) are defined
relative to a *widget* background and are not usable as canvas, node or wire
colours -- on most styles they collapse into three nearly identical greys, and
on a dark platform theme several of them invert, which is what made the node
graph unreadable.

The theme is chosen once at start-up (:func:`install`) and can be switched at
run time (:meth:`ThemeManager.mode`); anything that paints theme colours
should read them through :func:`current_theme` *at paint time* and repaint on
:attr:`ThemeManager.changed`, so a switch needs no restart.
"""

from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from subprocess import DEVNULL, SubprocessError, run
from typing import Mapping

from PyQt5.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPalette, QPen
from PyQt5.QtWidgets import QApplication

log = getLogger(__name__)

SETTINGS_ORGANISATION = "amaranth-companion"
SETTINGS_APPLICATION = "amaranth-companion"
SETTINGS_KEY_THEME = "appearance/theme"


class ThemeMode(Enum):
    """What the user asked for, as opposed to what gets painted."""

    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"

    @property
    def title(self) -> str:
        return {
            ThemeMode.AUTO: "Follow &System",
            ThemeMode.LIGHT: "&Light",
            ThemeMode.DARK: "&Dark",
        }[self]


@dataclass
class Theme:
    """A full set of colours, plus the pens and brushes painted with them."""

    name: str
    dark: bool

    # widget chrome, mapped onto Qt's palette roles
    window: QColor
    window_text: QColor
    base: QColor
    alternate_base: QColor
    text: QColor
    button: QColor
    button_text: QColor
    bright_text: QColor
    highlight: QColor
    highlighted_text: QColor
    link: QColor
    tooltip_base: QColor
    tooltip_text: QColor
    disabled_text: QColor

    # canvas
    canvas: QColor
    grid_minor: QColor
    grid_major: QColor

    # nodes
    node_background: QColor
    node_title: QColor
    node_title_text: QColor
    node_outline: QColor
    node_outline_selected: QColor

    # edges
    edge: QColor
    edge_selected: QColor

    # sockets, keyed by ``SocketKind.value`` (a plain string, so that the
    # element package can keep importing this module and not the other way)
    socket_outline: QColor
    #: the port name written beside a socket; dimmer than the node title, so
    #: the labels read as annotation rather than competing with it
    socket_label: QColor = field(default_factory=lambda: QColor("#8a8a98"))
    socket_colors: Mapping[str, QColor] = field(default_factory=dict)
    socket_default: QColor = field(default_factory=lambda: QColor("#f08a24"))

    # python syntax highlighting inside code blocks
    syntax_keyword: QColor = field(default_factory=lambda: QColor("#c792ea"))
    syntax_builtin: QColor = field(default_factory=lambda: QColor("#82aaff"))
    syntax_string: QColor = field(default_factory=lambda: QColor("#c3e88d"))
    syntax_comment: QColor = field(default_factory=lambda: QColor("#6a6a7a"))
    syntax_number: QColor = field(default_factory=lambda: QColor("#f78c6c"))
    syntax_definition: QColor = field(default_factory=lambda: QColor("#ffcb6b"))
    syntax_decorator: QColor = field(default_factory=lambda: QColor("#89ddff"))
    #: background wash on the line a block's error came from
    syntax_error_line: QColor = field(default_factory=lambda: QColor("#4a1f2a"))

    GRID_MAJOR_WIDTH = 2.0
    NODE_OUTLINE_WIDTH = 1.5
    EDGE_WIDTH = 2.5
    SOCKET_OUTLINE_WIDTH = 1.0

    def __post_init__(self) -> None:
        self.pen_grid_minor = QPen(self.grid_minor)
        self.pen_grid_major = QPen(self.grid_major)
        self.pen_grid_major.setWidthF(self.GRID_MAJOR_WIDTH)

        self.pen_node_outline = QPen(self.node_outline)
        self.pen_node_outline.setWidthF(self.NODE_OUTLINE_WIDTH)
        self.pen_node_outline_selected = QPen(self.node_outline_selected)
        self.pen_node_outline_selected.setWidthF(self.NODE_OUTLINE_WIDTH)

        self.pen_edge = QPen(self.edge)
        self.pen_edge_selected = QPen(self.edge_selected)
        for pen in (self.pen_edge, self.pen_edge_selected):
            pen.setWidthF(self.EDGE_WIDTH)
            pen.setCapStyle(Qt.RoundCap)

        self.pen_socket_outline = QPen(self.socket_outline)
        self.pen_socket_outline.setWidthF(self.SOCKET_OUTLINE_WIDTH)

        self.brush_canvas = QBrush(self.canvas)
        self.brush_node_background = QBrush(self.node_background)
        self.brush_node_title = QBrush(self.node_title)

    def socket_color(self, socket_kind: str) -> QColor:
        return self.socket_colors.get(socket_kind, self.socket_default)

    def palette(self) -> QPalette:
        """The widget palette for this theme (menus, dialogs, node content)."""
        palette = QPalette()
        for role, color in (
            (QPalette.Window, self.window),
            (QPalette.WindowText, self.window_text),
            (QPalette.Base, self.base),
            (QPalette.AlternateBase, self.alternate_base),
            (QPalette.Text, self.text),
            (QPalette.Button, self.button),
            (QPalette.ButtonText, self.button_text),
            (QPalette.BrightText, self.bright_text),
            (QPalette.Highlight, self.highlight),
            (QPalette.HighlightedText, self.highlighted_text),
            (QPalette.Link, self.link),
            (QPalette.LinkVisited, self.link),
            (QPalette.ToolTipBase, self.tooltip_base),
            (QPalette.ToolTipText, self.tooltip_text),
            (QPalette.PlaceholderText, self.disabled_text),
        ):
            palette.setColor(role, color)

        # without this, disabled menu entries and the placeholder submenus are
        # drawn in full-contrast text and read as enabled
        for role in (
            QPalette.WindowText,
            QPalette.Text,
            QPalette.ButtonText,
            QPalette.HighlightedText,
        ):
            palette.setColor(QPalette.Disabled, role, self.disabled_text)

        return palette


LIGHT_THEME = Theme(
    name="light",
    dark=False,
    window=QColor("#f1f1f5"),
    window_text=QColor("#1b1b1f"),
    base=QColor("#ffffff"),
    alternate_base=QColor("#e9e9ef"),
    text=QColor("#1b1b1f"),
    button=QColor("#e6e6ec"),
    button_text=QColor("#1b1b1f"),
    bright_text=QColor("#ffffff"),
    highlight=QColor("#c2185b"),
    highlighted_text=QColor("#ffffff"),
    link=QColor("#9c1248"),
    tooltip_base=QColor("#2a2a30"),
    tooltip_text=QColor("#f4f4f8"),
    disabled_text=QColor("#9a9aa6"),
    canvas=QColor("#e7e7ed"),
    grid_minor=QColor("#dadae2"),
    grid_major=QColor("#c2c2ce"),
    node_background=QColor("#fbfbfd"),
    node_title=QColor("#dcdce6"),
    node_title_text=QColor("#1b1b1f"),
    node_outline=QColor("#a9a9b8"),
    node_outline_selected=QColor("#c2185b"),
    edge=QColor("#6a6a7a"),
    edge_selected=QColor("#c2185b"),
    syntax_keyword=QColor("#7c3aed"),
    syntax_builtin=QColor("#1d4ed8"),
    syntax_string=QColor("#15803d"),
    syntax_comment=QColor("#8a8a98"),
    syntax_number=QColor("#c2410c"),
    syntax_definition=QColor("#a16207"),
    syntax_decorator=QColor("#0e7490"),
    syntax_error_line=QColor("#fbdfe5"),
    socket_outline=QColor("#3a3a44"),
    socket_label=QColor("#55555f"),
    socket_colors={"signal": QColor("#e07a1c"), "param": QColor("#3d8bd4")},
)

DARK_THEME = Theme(
    name="dark",
    dark=True,
    window=QColor("#26262b"),
    window_text=QColor("#e4e4ea"),
    base=QColor("#1e1e22"),
    alternate_base=QColor("#2b2b31"),
    text=QColor("#e4e4ea"),
    button=QColor("#32323a"),
    button_text=QColor("#e4e4ea"),
    bright_text=QColor("#ffffff"),
    highlight=QColor("#ff5d8f"),
    highlighted_text=QColor("#1b1b1f"),
    link=QColor("#ff8fb1"),
    tooltip_base=QColor("#3a3a44"),
    tooltip_text=QColor("#f0f0f4"),
    disabled_text=QColor("#6e6e7a"),
    canvas=QColor("#1a1a1e"),
    grid_minor=QColor("#24242a"),
    grid_major=QColor("#33333c"),
    node_background=QColor("#2c2c33"),
    node_title=QColor("#3b3b46"),
    node_title_text=QColor("#f0f0f4"),
    node_outline=QColor("#15151a"),
    node_outline_selected=QColor("#ff5d8f"),
    edge=QColor("#a8a8b6"),
    edge_selected=QColor("#ff5d8f"),
    syntax_keyword=QColor("#c792ea"),
    syntax_builtin=QColor("#82aaff"),
    syntax_string=QColor("#c3e88d"),
    syntax_comment=QColor("#71717f"),
    syntax_number=QColor("#f78c6c"),
    syntax_definition=QColor("#ffcb6b"),
    syntax_decorator=QColor("#89ddff"),
    syntax_error_line=QColor("#4a1f2a"),
    socket_outline=QColor("#15151a"),
    socket_label=QColor("#b6b6c4"),
    socket_colors={"signal": QColor("#ff9d3d"), "param": QColor("#5aa9f0")},
)

THEMES: Mapping[str, Theme] = {
    LIGHT_THEME.name: LIGHT_THEME,
    DARK_THEME.name: DARK_THEME,
}


# --- system preference ------------------------------------------------------

#: the palette Qt derived from the platform theme, captured before we replace
#: it; afterwards ``QApplication.palette()`` only reports our own colours
_system_palette: QPalette | None = None


def _gnome_color_scheme() -> ThemeMode | None:
    """The freedesktop ``color-scheme`` preference, if one is expressed.

    This is the portal setting all of GNOME, Cinnamon and recent KDE write,
    and the only cross-desktop signal available from Qt 5, which has no
    colour-scheme API of its own.
    """
    try:
        result = run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            stdin=DEVNULL,
            timeout=2,
        )
    except (OSError, SubprocessError) as error:  # no gsettings, or a timeout
        log.debug("could not read the desktop colour scheme: %s", error)
        return None

    if result.returncode != 0:
        return None

    value = result.stdout.strip().strip("'")
    if "dark" in value:
        return ThemeMode.DARK
    if "light" in value:
        return ThemeMode.LIGHT
    return None  # "default": no preference, fall back to the palette


def _palette_mode(palette: QPalette | None) -> ThemeMode | None:
    """Dark or light, judged by how bright the platform window colour is."""
    if palette is None:
        return None
    return ThemeMode.DARK if palette.color(QPalette.Window).value() < 128 else None


def detect_system_mode() -> ThemeMode:
    """The desktop's preference, defaulting to light when it does not say."""
    for candidate in (_gnome_color_scheme(), _palette_mode(_system_palette)):
        if candidate is not None:
            return candidate
    return ThemeMode.LIGHT


def resolve(mode: ThemeMode) -> Theme:
    """The theme to paint for ``mode``, resolving :attr:`ThemeMode.AUTO`."""
    if mode is ThemeMode.AUTO:
        mode = detect_system_mode()
    return DARK_THEME if mode is ThemeMode.DARK else LIGHT_THEME


# --- manager ----------------------------------------------------------------


class ThemeManager(QObject):
    """Holds the active theme and announces changes."""

    #: emitted after the application palette has been swapped
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._mode = ThemeMode.AUTO
        self._theme = LIGHT_THEME

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @mode.setter
    def mode(self, value: ThemeMode) -> None:
        self.apply(value)

    def apply(self, mode: ThemeMode, *, persist: bool = True) -> Theme:
        self._mode = mode
        self._theme = resolve(mode)

        app = QApplication.instance()
        if app is not None:
            global _system_palette
            if _system_palette is None:
                _system_palette = QPalette(app.palette())
            # Fusion honours the palette on every platform; the native styles
            # hard-code parts of their chrome and would only half-follow
            app.setStyle("Fusion")
            app.setPalette(self._theme.palette())

        if persist:
            self.save()

        log.debug("theme mode %s -> %s", mode.value, self._theme.name)
        self.changed.emit()
        return self._theme

    def reapply(self) -> Theme:
        """Re-resolve the current mode, picking up a changed system setting."""
        return self.apply(self._mode, persist=False)

    # --- persistence -------------------------------------------------------

    @staticmethod
    def settings() -> QSettings:
        return QSettings(SETTINGS_ORGANISATION, SETTINGS_APPLICATION)

    def save(self) -> None:
        self.settings().setValue(SETTINGS_KEY_THEME, self._mode.value)

    @classmethod
    def stored_mode(cls) -> ThemeMode | None:
        value = cls.settings().value(SETTINGS_KEY_THEME)
        if not value:
            return None
        try:
            return ThemeMode(str(value))
        except ValueError:
            log.warning("ignoring unknown stored theme %r", value)
            return None


_manager: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    """The process-wide theme manager, created on first use."""
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def current_theme() -> Theme:
    """The colours to paint right now."""
    return theme_manager().theme


def install(mode: ThemeMode | None = None) -> Theme:
    """Apply ``mode``, the stored preference, or :attr:`ThemeMode.AUTO`.

    An explicitly passed ``mode`` is treated as a one-off override and is not
    written back to the settings, so ``--theme dark`` does not silently change
    what the next plain start-up looks like.
    """
    manager = theme_manager()
    if mode is not None:
        return manager.apply(mode, persist=False)
    return manager.apply(ThemeManager.stored_mode() or ThemeMode.AUTO, persist=False)
