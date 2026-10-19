"""Syntax highlighting, and pointing at the line an error came from."""

import pytest

from PyQt5.QtWidgets import QPlainTextEdit

from amaranth_companion.blocks.introspect import introspect
from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.errors import error_line, locate
from amaranth_companion.module.element.graphics_item import CodeContentWidget
from amaranth_companion.module.element.graphics_item.highlighter import (
    PythonHighlighter,
)
from amaranth_companion.module.instantiate import instantiate, refresh_node_ports
from amaranth_companion.theme import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeMode,
    theme_manager,
)

SAMPLE = '''from amaranth import *


class Gate(Elaboratable):
    """A docstring
    spanning two lines."""

    def __init__(self, width_param=8):
        self.a_in = Signal(width_param)  # trailing comment
        self.mask = 0xFF

    def elaborate(self, platform):
        return Module()
'''


@pytest.fixture
def design(qapp):
    return Design()


@pytest.fixture
def dark(qapp):
    """Pin the theme, so colour assertions do not depend on the ambient one."""
    manager = theme_manager()
    previous = manager.mode
    manager.apply(ThemeMode.DARK, persist=False)
    yield DARK_THEME
    manager.apply(previous, persist=False)


@pytest.fixture
def highlighted(dark):
    """An editor with the highlighter attached, holding :data:`SAMPLE`."""
    editor = QPlainTextEdit()
    highlighter = PythonHighlighter(editor.document())
    editor.setPlainText(SAMPLE)
    highlighter.rehighlight()
    return editor, highlighter


def colours(editor, line: int) -> set[str]:
    block = editor.document().findBlockByNumber(line)
    return {run.format.foreground().color().name() for run in block.layout().formats()}


# --- locating an error ------------------------------------------------------


def test_a_syntax_error_reports_its_own_line():
    try:
        compile("x = 1\ny = (\n", "<block>", "exec")
    except SyntaxError as error:
        assert error_line(error, "<block>") == 2


def test_a_syntax_error_in_another_file_is_not_ours():
    """Importing a broken module is not a mistake in *this* block."""
    try:
        compile("y = (\n", "<somewhere-else>", "exec")
    except SyntaxError as error:
        assert error_line(error, "<block>") is None


def test_a_runtime_error_reports_the_deepest_frame_in_the_block():
    """A failure inside a helper points at the helper, not at the call."""
    namespace: dict = {}
    source = "def helper():\n    raise ValueError('boom')\n\n\nhelper()\n"

    try:
        exec(compile(source, "<block>", "exec"), namespace)
    except ValueError as error:
        assert error_line(error, "<block>") == 2


def test_an_error_from_outside_the_block_has_no_line():
    try:
        int("not a number")
    except ValueError as error:
        assert error_line(error, "<block>") is None


def test_locate_strips_the_repeated_position_from_a_syntax_error():
    try:
        compile("y = (\n", "<block>", "exec")
    except SyntaxError as error:
        located = locate(error, "<block>")

    assert located.line == 1
    assert located.summary.startswith("line 1: SyntaxError:")
    assert "<block>" not in located.message


# --- introspection carries the line ----------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ("from amaranth import *\n\n\nclass Broken(:\n", 4),
        ("x = 1\n\nraise ValueError('boom')\n", 3),
    ],
)
def test_introspection_reports_where_it_failed(source, expected):
    result = introspect(source)

    assert not result.ok
    assert result.line == expected
    assert result.summary.startswith(f"line {expected}: ")


def test_a_node_keeps_the_error_line(design):
    node = instantiate(
        design.current_module,
        library().require("builtin.code"),
        text="from amaranth import *\n\n\nclass Broken(:\n",
    )

    assert node.error_line == 4


def test_fixing_a_block_clears_the_line(design):
    node = instantiate(
        design.current_module,
        library().require("builtin.code"),
        text="class Broken(:\n",
    )
    assert node.error_line

    node.content_widget.text = library().require("builtin.code").source
    refresh_node_ports(node)

    assert node.error == ""
    assert node.error_line is None


# --- marking the line in the editor ----------------------------------------


def test_the_error_line_is_washed_in_the_editor(qapp):
    widget = CodeContentWidget(text=SAMPLE)

    widget.show_error("something went wrong", 9)
    selections = widget.editor.extraSelections()

    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == 8  # zero-based


def test_clearing_the_error_clears_the_wash(qapp):
    widget = CodeContentWidget(text=SAMPLE)
    widget.show_error("something went wrong", 9)

    widget.show_error("")

    assert widget.editor.extraSelections() == []
    assert not widget.status.isVisible()


def test_an_error_without_a_line_still_shows_its_message(qapp):
    widget = CodeContentWidget(text=SAMPLE)

    widget.show_error("no Elaboratable subclass defined in this block")

    assert widget.editor.extraSelections() == []
    assert widget.status.text()


def test_a_line_past_the_end_is_ignored(qapp):
    """A stale error must not crash the editor after the source shrinks."""
    widget = CodeContentWidget(text="x = 1\n")

    widget.show_error("stale", 99)

    assert widget.editor.extraSelections() == []


# --- highlighting -----------------------------------------------------------


def test_keywords_are_coloured(highlighted, dark):
    editor, _ = highlighted

    assert dark.syntax_keyword.name() in colours(editor, 0) | colours(editor, 3)


def test_a_defined_name_is_coloured(highlighted, dark):
    editor, _ = highlighted

    assert dark.syntax_definition.name() in colours(editor, 3)


def test_amaranth_names_read_as_vocabulary(highlighted, dark):
    editor, _ = highlighted

    assert dark.syntax_builtin.name() in colours(editor, 3)


def test_a_docstring_spanning_lines_is_a_string(highlighted, dark):
    editor, _ = highlighted

    assert colours(editor, 4) == {dark.syntax_string.name()}
    assert colours(editor, 5) == {dark.syntax_string.name()}


def test_the_string_state_does_not_leak_past_the_docstring(highlighted, dark):
    """The line after a closed docstring is ordinary code again."""
    editor, _ = highlighted

    assert dark.syntax_keyword.name() in colours(editor, 7)
    assert colours(editor, 7) != {dark.syntax_string.name()}


def test_comments_and_numbers_are_coloured(highlighted, dark):
    editor, _ = highlighted

    assert dark.syntax_comment.name() in colours(editor, 8)
    assert dark.syntax_number.name() in colours(editor, 9)


def test_an_unterminated_string_carries_to_the_next_line(dark):
    editor = QPlainTextEdit()
    highlighter = PythonHighlighter(editor.document())
    editor.setPlainText('x = """open\nstill open\n')
    highlighter.rehighlight()

    assert dark.syntax_string.name() in colours(editor, 1)


def test_highlighting_follows_the_theme(qapp):
    editor = QPlainTextEdit()
    highlighter = PythonHighlighter(editor.document())
    editor.setPlainText(SAMPLE)
    mode = theme_manager().mode

    try:
        theme_manager().apply(ThemeMode.LIGHT, persist=False)
        highlighter.rehighlight()
        assert LIGHT_THEME.syntax_keyword.name() in colours(editor, 0)

        theme_manager().apply(ThemeMode.DARK, persist=False)
        highlighter.rehighlight()
        assert DARK_THEME.syntax_keyword.name() in colours(editor, 0)
    finally:
        theme_manager().apply(mode, persist=False)


def test_a_code_block_gets_a_highlighter(design):
    node = instantiate(design.current_module, library().require("builtin.code"))

    assert isinstance(node.content_widget, CodeContentWidget)
    assert node.content_widget.highlighter is not None
