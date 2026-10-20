# Project:   scalo
# File:      rules/_errors.py
# Purpose:   What a rule set check finds, and the errors rules raise
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Findings carry the config location, the rule id when there is one, and a span.

The span is the byte range within a ``when`` condition, so an editor can point at the
row and the token.
"""

import json
from dataclasses import dataclass
from enum import StrEnum

from scalo.expression.diagnostic import Span

__all__ = ["RuleDiagnostic", "RulesError", "RulesLoadError", "Severity"]


class Severity(StrEnum):
    """Whether a finding stops the set compiling."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class RuleDiagnostic:
    """One finding of a rule set check.

    Attributes:
        severity: ``ERROR`` stops the set compiling, ``WARNING`` does not.
        location: Where in the config, e.g. ``rules[2].match.value`` or ``targets[0]``.
        rule: The id of the row it concerns, when it concerns one.
        message: What is wrong.
        span: The byte range within the ``when`` condition at ``location``.
    """

    severity: Severity
    location: str
    message: str
    rule: str | None = None
    span: Span | None = None

    @property
    def is_error(self) -> bool:
        """True for a finding that stops the set compiling."""
        return self.severity is Severity.ERROR

    def __str__(self) -> str:
        text = f"{self.severity}: {self.location}"
        if self.rule is not None:
            text += f" (rule {self.rule})"
        text += f": {self.message}"
        if self.span is not None:
            text += f" at {self.span}"
        return text


def quoted(text: str) -> str:
    """Quote ``text`` for a finding's message, in double quotes with escapes."""
    return json.dumps(text, ensure_ascii=False)


def error(location: str, message: str, rule: str | None = None, span: Span | None = None) -> RuleDiagnostic:
    """Build an error finding, naming ``rule`` only when it is a non-empty id."""
    return RuleDiagnostic(Severity.ERROR, location, message, rule or None, span)


def warning(location: str, message: str, rule: str | None = None) -> RuleDiagnostic:
    """Build a warning finding, naming ``rule`` only when it is a non-empty id."""
    return RuleDiagnostic(Severity.WARNING, location, message, rule or None)


class RulesError(Exception):
    """A rule set did not compile.

    Attributes:
        diagnostics: Every finding, warnings included.
    """

    def __init__(self, diagnostics: list[RuleDiagnostic], message: str | None = None) -> None:
        self.diagnostics = diagnostics
        if message is None:
            message = "the rule set is invalid: " + "; ".join(str(d) for d in diagnostics if d.is_error)
        super().__init__(message)


class RulesLoadError(RulesError):
    """The file holding a rule set could not be read or parsed. It carries no findings.

    Attributes:
        origin: The file, and the section within it.
        reason: Why.
    """

    def __init__(self, origin: str, reason: str) -> None:
        self.origin = origin
        self.reason = reason
        super().__init__([], f"cannot load the rule set from {origin}: {reason}")
