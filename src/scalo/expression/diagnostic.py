# Project:   scalo
# File:      expression/diagnostic.py
# Purpose:   Located problems found in an expression's text
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""A problem in an expression, with the byte range it covers.

:func:`scalo.expression.diagnose` returns these where :func:`scalo.expression.validate`
returns bare strings, so an editor can underline the call or token at fault.
"""

from dataclasses import dataclass

__all__ = ["Diagnostic", "Span", "span_at"]


@dataclass(frozen=True, slots=True)
class Span:
    """A byte range in an expression's UTF-8 text, ``end`` exclusive.

    ``expr.encode()[span.start:span.end]`` is the text it covers.

    Attributes:
        start: First byte of the range.
        end: One past the last byte of the range.
    """

    start: int
    end: int

    def __str__(self) -> str:
        return f"{self.start}..{self.end}"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One problem found in an expression.

    Attributes:
        message: What is wrong, without the position.
        span: Where it is, when the scanner or parser knows.
    """

    message: str
    span: Span | None = None

    def __str__(self) -> str:
        if self.span is None:
            return self.message
        return f"{self.message} (at {self.span})"


def _lines(expr: str) -> list[str]:
    """Split on newlines only, each line keeping its newline."""
    parts = expr.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def span_at(expr: str, line: int, column: int) -> Span | None:
    """Return the byte span of the character at a parser position.

    Args:
        expr: The expression text.
        line: Line number, from 1.
        column: Column, from 1, counted in characters.

    Returns:
        The span of that character, an empty span at the end of the line for a column
        past it, or ``None`` for a line the text does not have.
    """
    if line < 1 or column < 1:
        return None
    line_start = 0
    for number, text in enumerate(_lines(expr), start=1):
        width = len(text.encode("utf-8"))
        if number == line:
            if column > len(text):
                return Span(line_start + width, line_start + width)
            start = line_start + len(text[: column - 1].encode("utf-8"))
            return Span(start, start + len(text[column - 1].encode("utf-8")))
        line_start += width
    return None
