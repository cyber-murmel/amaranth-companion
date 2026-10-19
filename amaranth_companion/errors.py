"""Locating a failure inside a block's own source.

Block code is compiled with a made-up filename (``<block>``, ``<testbench>``),
so a traceback through it is full of frames the user has never seen -- the
editor's own, Amaranth's, the worker's. What matters is the *last* frame that
was in their block, because that is the line to point at.

Used from the worker processes, so it must not import Qt or anything that
drags the editor in.
"""

import traceback
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorLocation:
    """Where a failure happened, as far as the user is concerned."""

    message: str
    #: 1-based line within the block's own source, or ``None`` if the failure
    #: happened somewhere the user cannot see
    line: int | None = None
    traceback: str = ""

    @property
    def summary(self) -> str:
        return f"line {self.line}: {self.message}" if self.line else self.message


def error_line(error: BaseException, filename: str) -> int | None:
    """The line in ``filename`` that ``error`` came from.

    A ``SyntaxError`` carries its position directly; anything else has to be
    dug out of the traceback, taking the *deepest* frame still inside the
    user's own source so that a failure inside a helper they wrote points at
    the helper rather than at the call.
    """
    if isinstance(error, SyntaxError):
        # a syntax error in a different file is not this block's problem
        if error.filename in (filename, None):
            return error.lineno
        return None

    line = None
    for frame in traceback.extract_tb(error.__traceback__):
        if frame.filename == filename:
            line = frame.lineno

    return line


def locate(error: BaseException, filename: str, prefix: str = "") -> ErrorLocation:
    """Describe ``error`` and say where in ``filename`` it came from."""
    message = f"{type(error).__name__}: {error}"
    if isinstance(error, SyntaxError) and error.msg:
        # the default str() of a SyntaxError repeats the filename and line,
        # which the editor is about to show anyway
        message = f"SyntaxError: {error.msg}"

    return ErrorLocation(
        message=f"{prefix}{message}" if prefix else message,
        line=error_line(error, filename),
        traceback=traceback.format_exc(),
    )
