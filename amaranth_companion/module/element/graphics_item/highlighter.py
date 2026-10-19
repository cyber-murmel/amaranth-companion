"""Python syntax highlighting for the source inside a code block.

Deliberately a rule-based highlighter rather than a real parse: a block is
edited a character at a time and spends most of its life syntactically
invalid, so anything that needs the source to parse would spend most of its
life showing nothing.

Colours come from the theme at highlight time, and the editor re-highlights on
a theme change.
"""

import builtins
import keyword
import re

from PyQt5.QtCore import QRegularExpression
from PyQt5.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from ....theme import current_theme

#: names Amaranth brings in with ``from amaranth import *`` and that a block
#: is likely to use; highlighted like builtins so the HDL reads as vocabulary
AMARANTH_NAMES = (
    "Array",
    "Cat",
    "ClockDomain",
    "ClockSignal",
    "Const",
    "Elaboratable",
    "Instance",
    "Memory",
    "Module",
    "Mux",
    "Repl",
    "ResetSignal",
    "Signal",
    "Value",
    "signed",
    "unsigned",
    "Assert",
    "Assume",
    "Cover",
)


def _word_pattern(words) -> str:
    return r"\b(?:" + "|".join(re.escape(word) for word in sorted(words)) + r")\b"


class PythonHighlighter(QSyntaxHighlighter):
    """Highlights Python, with Amaranth's vocabulary treated as builtins."""

    #: block states, for strings that run past the end of a line
    NONE = 0
    IN_SINGLE = 1
    IN_DOUBLE = 2

    def __init__(self, document):
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, str, bool]] = []
        self._build_rules()

    def _build_rules(self) -> None:
        """Patterns, paired with the theme attribute that colours them.

        Order matters: the last rule to match a span wins, so comments and
        strings are applied after the word rules they might contain.
        """
        rules: list[tuple[str, str, bool]] = [
            (
                _word_pattern(keyword.kwlist + keyword.softkwlist),
                "syntax_keyword",
                True,
            ),
            (_word_pattern(dir(builtins)), "syntax_builtin", False),
            (_word_pattern(AMARANTH_NAMES), "syntax_builtin", False),
            (r"\b\d+\.?\d*(?:[eE][+-]?\d+)?\b", "syntax_number", False),
            (r"\b0[xXbBoO][0-9a-fA-F_]+\b", "syntax_number", False),
            # the name being defined, not the keyword, which is already done
            (r"(?<=\bclass\s)\s*\w+", "syntax_definition", True),
            (r"(?<=\bdef\s)\s*\w+", "syntax_definition", True),
            (r"^\s*@\w+(?:\.\w+)*", "syntax_decorator", False),
            # single-line strings; the triple-quoted case is handled by state
            (r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'", "syntax_string", False),
            (r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"', "syntax_string", False),
            (r"#[^\n]*", "syntax_comment", False),
        ]

        self._rules = [
            (QRegularExpression(pattern), attribute, bold)
            for pattern, attribute, bold in rules
        ]

        self._triple_single = QRegularExpression(r"'''")
        self._triple_double = QRegularExpression(r'"""')

    @staticmethod
    def _format(color: QColor, bold: bool = False) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(color)
        if bold:
            text_format.setFontWeight(QFont.Bold)
        return text_format

    def highlightBlock(self, text: str) -> None:
        theme = current_theme()

        for expression, attribute, bold in self._rules:
            text_format = self._format(getattr(theme, attribute), bold)
            match = expression.globalMatch(text)
            while match.hasNext():
                found = match.next()
                self.setFormat(
                    found.capturedStart(), found.capturedLength(), text_format
                )

        self._highlight_triple_quoted(text, theme)

    def _highlight_triple_quoted(self, text: str, theme) -> None:
        """Docstrings and other strings that span lines.

        Rule-based highlighting sees one line at a time, so a string that does
        not close on its line leaves a note for the next one; that is what the
        block state is. The scan then carries on past a closing delimiter,
        because the rest of the line is ordinary code again -- and may open a
        second string of its own.
        """
        text_format = self._format(theme.syntax_string)
        start = self._resume(text, text_format)
        if start is None:
            return

        self.setCurrentBlockState(self.NONE)

        while start <= len(text):
            opening, state = self._next_opening(text, start)
            if opening is None:
                return

            delimiter = self._delimiter(state)
            closing = delimiter.match(text, opening.capturedEnd())

            if not closing.hasMatch():
                self.setFormat(
                    opening.capturedStart(),
                    len(text) - opening.capturedStart(),
                    text_format,
                )
                self.setCurrentBlockState(state)
                return

            self.setFormat(
                opening.capturedStart(),
                closing.capturedEnd() - opening.capturedStart(),
                text_format,
            )
            start = closing.capturedEnd()

    def _resume(self, text: str, text_format) -> int | None:
        """Finish a string carried over from the previous line.

        Returns where to carry on scanning, or ``None`` if the string runs to
        the end of this line too and there is nothing else to do.
        """
        state = self.previousBlockState()
        if state not in (self.IN_SINGLE, self.IN_DOUBLE):
            return 0

        closing = self._delimiter(state).match(text)
        if not closing.hasMatch():
            self.setFormat(0, len(text), text_format)
            self.setCurrentBlockState(state)
            return None

        self.setFormat(0, closing.capturedEnd(), text_format)
        return closing.capturedEnd()

    def _delimiter(self, state: int) -> QRegularExpression:
        return self._triple_single if state == self.IN_SINGLE else self._triple_double

    def _next_opening(self, text: str, start: int):
        """The earliest triple quote at or after ``start``, and its state."""
        found = [
            (match, state)
            for state in (self.IN_SINGLE, self.IN_DOUBLE)
            if (match := self._delimiter(state).match(text, start)).hasMatch()
        ]
        if not found:
            return None, self.NONE

        return min(found, key=lambda pair: pair[0].capturedStart())
