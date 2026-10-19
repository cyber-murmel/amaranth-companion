"""The widget drawn inside a node, one variety per block kind.

A code block needs a source editor, a port block a single name field, a
hierarchical block a summary of what it contains. They all expose the same
``text`` property, which is what gets serialised, so the rest of the editor
does not care which one a node happens to be holding.
"""

from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt5.QtCore import QByteArray, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QFontDatabase, QTextCursor, QTextFormat
from PyQt5.QtSvg import QSvgRenderer, QSvgWidget
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....blocks.definition import BlockKind
from ....theme import current_theme, theme_manager
from .highlighter import PythonHighlighter

if TYPE_CHECKING:
    from ....blocks.definition import BlockDefinition

log = getLogger(__name__)


class NodeContentWidget(QWidget):
    """Base content widget: a label over a free-text editor."""

    #: the user changed something that may change the block's interface
    content_changed = pyqtSignal()

    def __init__(self, parent=None, text: str = "", **options):
        super().__init__(parent)

        # not `self.layout`: that would shadow QWidget.layout()
        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.setLayout(self._layout)

        self._options = options
        self._build(text)

    def _build(self, text: str) -> None:
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(text)
        self.editor.textChanged.connect(self.content_changed)
        self._layout.addWidget(self.editor)

    @property
    def text(self) -> str:
        return self.editor.toPlainText()

    @text.setter
    def text(self, value: str) -> None:
        if value != self.text:
            self.editor.setPlainText(value)


class CodeContentWidget(NodeContentWidget):
    """An Amaranth source editor, plus whatever introspection last said."""

    def _build(self, text: str) -> None:
        super()._build(text)

        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        self.editor.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)

        self.highlighter = PythonHighlighter(self.editor.document())

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.hide()  # takes no room until there is something to say
        self._layout.addWidget(self.status)

        self._error_line: int | None = None
        theme_manager().changed.connect(self._apply_theme)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.highlighter.rehighlight()
        self.status.setStyleSheet(
            f"color: {current_theme().node_outline_selected.name()};"
        )
        self._mark_error_line()

    def show_error(self, message: str, line: int | None = None) -> None:
        """Report why the ports could not be read, or clear the report.

        ``line`` is where in this block the failure came from, which is washed
        in the editor -- a message naming a line the user then has to count to
        is most of the way to no message at all.
        """
        self._error_line = line
        self.status.setText(message)
        self.status.setVisible(bool(message))
        self._mark_error_line()

    def _mark_error_line(self) -> None:
        if not self._error_line:
            self.editor.setExtraSelections([])
            return

        block = self.editor.document().findBlockByNumber(self._error_line - 1)
        if not block.isValid():
            self.editor.setExtraSelections([])
            return

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(current_theme().syntax_error_line)
        # without this the wash stops at the end of the text on that line
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = QTextCursor(block)
        selection.cursor.clearSelection()

        self.editor.setExtraSelections([selection])


class PortContentWidget(NodeContentWidget):
    """One field: the name of the port this block becomes on its parent.

    Just the name. Which way the port faces is the block's kind, chosen when
    it was placed, so renaming it cannot move it to the other side.
    """

    def _build(self, text: str) -> None:
        self.editor = QLineEdit(text)
        self.editor.setPlaceholderText("name")
        self.editor.textChanged.connect(self.content_changed)
        self._layout.addWidget(self.editor)
        self._layout.addStretch(1)

    @property
    def text(self) -> str:
        return self.editor.text()

    @text.setter
    def text(self, value: str) -> None:
        if value != self.text:
            self.editor.setText(value)


class VariableContentWidget(NodeContentWidget):
    """One assignment, ``name = expression``, exposed as a parameter output.

    A single line rather than two fields: it is how the value would be written
    in Python anyway, it serialises as one string, and it keeps the name and
    the expression from drifting apart.
    """

    def _build(self, text: str) -> None:
        self.editor = QLineEdit(text)
        self.editor.setPlaceholderText("width = 8")
        self.editor.textChanged.connect(self.content_changed)
        self._layout.addWidget(self.editor)
        self._layout.addStretch(1)

    @property
    def text(self) -> str:
        return self.editor.text()

    @text.setter
    def text(self, value: str) -> None:
        if value != self.text:
            self.editor.setText(value)


class ResourceContentWidget(NodeContentWidget):
    """Which io on the board this block binds to.

    Editable as well as a list: the boards are discovered from whatever is
    installed, so a design may legitimately name an io the current machine
    cannot enumerate, and that must still be openable and savable.
    """

    def _build(self, text: str) -> None:
        self.editor = QComboBox()
        self.editor.setEditable(True)
        self.editor.setInsertPolicy(QComboBox.NoInsert)
        self.editor.setCurrentText(text)
        self.editor.currentTextChanged.connect(self.content_changed)
        self._layout.addWidget(self.editor)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.hide()  # takes no room until there is something to say
        self._layout.addWidget(self.status)
        self._layout.addStretch(1)

        theme_manager().changed.connect(self._apply_theme)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.status.setStyleSheet(
            f"color: {current_theme().node_outline_selected.name()};"
        )

    def show_error(self, message: str, line: int | None = None) -> None:
        """Say why this block cannot bind, without hiding what it binds to."""
        self.status.setText(message)
        self.status.setVisible(bool(message))

    def set_choices(self, choices) -> None:
        """Offer ``choices`` without disturbing what is already selected."""
        current = self.text
        blocked = self.editor.blockSignals(True)
        try:
            self.editor.clear()
            self.editor.addItems(list(choices))
            self.editor.setCurrentText(current)
        finally:
            self.editor.blockSignals(blocked)

    @property
    def text(self) -> str:
        return self.editor.currentText()

    @text.setter
    def text(self, value: str) -> None:
        if value != self.text:
            self.editor.setCurrentText(value)


class HierarchicalContentWidget(NodeContentWidget):
    """A block whose contents are a level down, not in this view.

    Shows the definition's icon when it has one. A gate is recognised by its
    shape long before its label is read, which is the whole reason a block
    definition may carry an icon at all.
    """

    ICON_HEIGHT = 56

    #: icons are authored with ``stroke="currentColor"``; Qt's svg renderer
    #: has no document colour to resolve that against and falls back to black,
    #: so the keyword is substituted for the theme's colour before loading
    ICON_COLOR_KEYWORD = "currentColor"

    def _build(self, text: str) -> None:
        icon_path = self._options.get("icon")
        self._icon_source = self._read_icon(icon_path)

        if self._icon_source:
            self.icon = QSvgWidget()
            # QSvgWidget scales to fill whatever it is given, so a 64x40 gate
            # symbol in a wide node comes out stretched. Fixing both sides to
            # the symbol's own proportions is what keeps an AND looking like
            # an AND.
            self.icon.setFixedSize(*self._icon_size(icon_path))
            self._layout.addStretch(1)
            self._layout.addLayout(self._centered(self.icon))
            self._layout.addStretch(1)
            theme_manager().changed.connect(self._apply_theme)
            self._apply_theme()
        else:
            self.icon = None

        self.summary = QLabel(text or "Double-click to open")
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignCenter)
        if icon_path:
            # with a symbol carrying the meaning, the hint is just a hint
            self.summary.setText(text or "")
        self._layout.addWidget(self.summary)

        if not icon_path:
            self._layout.addStretch(1)

    def _icon_size(self, path: str) -> tuple[int, int]:
        """The symbol at :attr:`ICON_HEIGHT`, keeping its own proportions."""
        natural = QSvgRenderer(path).defaultSize()
        if natural.isEmpty() or natural.height() <= 0:
            return self.ICON_HEIGHT, self.ICON_HEIGHT

        aspect = natural.width() / natural.height()
        return round(self.ICON_HEIGHT * aspect), self.ICON_HEIGHT

    @staticmethod
    def _centered(widget: QWidget) -> QHBoxLayout:
        """``widget`` at its natural width, centred in the space available."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(widget)
        row.addStretch(1)
        return row

    @staticmethod
    def _read_icon(path: str | None) -> str:
        if not path:
            return ""
        try:
            return Path(path).read_text()
        except OSError as error:
            log.warning("could not read block icon %s: %s", path, error)
            return ""

    def _themed_icon(self) -> str:
        """The symbol's svg, recoloured for the theme now in use."""
        return self._icon_source.replace(
            self.ICON_COLOR_KEYWORD, current_theme().node_title_text.name()
        )

    def _apply_theme(self) -> None:
        if self.icon is None:
            return
        self.icon.load(QByteArray(self._themed_icon().encode()))

    @property
    def text(self) -> str:
        return ""

    @text.setter
    def text(self, value: str) -> None:
        if value:
            self.summary.setText(value)


#: which widget each block kind is edited with
WIDGETS: dict[BlockKind, type[NodeContentWidget]] = {
    BlockKind.CODE: CodeContentWidget,
    BlockKind.PORT_IN: PortContentWidget,
    BlockKind.PORT_OUT: PortContentWidget,
    BlockKind.PORT_PARAM: PortContentWidget,
    BlockKind.VARIABLE: VariableContentWidget,
    BlockKind.HIERARCHICAL: HierarchicalContentWidget,
    BlockKind.TESTBENCH: CodeContentWidget,
    BlockKind.FORMAL: CodeContentWidget,
    BlockKind.RESOURCE: ResourceContentWidget,
}


def content_widget_for(
    definition: "BlockDefinition | None", text: str = ""
) -> NodeContentWidget:
    """The content widget a node holding ``definition`` should get."""
    kind = definition.kind if definition else BlockKind.CODE

    options: dict = {}
    if kind is BlockKind.HIERARCHICAL and definition is not None:
        options["icon"] = definition.icon_path

    return WIDGETS.get(kind, NodeContentWidget)(text=text, **options)
