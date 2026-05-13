#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/gitleaks_toml.py
#  Purpose:   TOML-driven L1 secret-artefact scrubber (replaces detect-secrets)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""TOML-driven Layer 1 secret-artefact scrubber.

Loads gitleaks-format rules from the bundled
``hyperi_pylib/data/gitleaks.toml`` (vendored byte-identical from
``hyperi-ai/standards/patterns/gitleaks.toml``, which is in turn
synced from upstream ``gitleaks/gitleaks`` per spec §3.2) and applies
them as a Scrubber Protocol implementation.

**Regex engine**: this module uses the PyPI ``regex`` package, not
stdlib ``re``. Upstream gitleaks uses Go's RE2 syntax which permits
constructs Python's stdlib ``re`` rejects (mid-expression ``(?i)``
flags, ``\\z`` end-anchor). The ``regex`` package accepts both
syntaxes plus a superset. Pylib is not on the hot path
(per ``standards/languages/PYTHON.md``) so the modest ``regex`` vs
``re`` overhead is fine. Rustlib will compile the same rules through
the ``regex`` Rust crate which also accepts the superset.

Unused upstream sections (``[allowlist]``, ``[[rules.tags]]``,
``[[rules.allowlists]]``, ``title``, ``minVersion``) are tolerated
silently — the loader reads only the fields it understands.

The legacy :mod:`hyperi_pylib.logger.secrets_leak` path
(detect-secrets-backed) remains available for callers that want
entropy heuristics; ``SecretsScrubber`` picks between them via the
``patterns`` setting.
"""

from __future__ import annotations

import tomllib
import warnings
from importlib import resources
from pathlib import Path
from typing import Any

import regex

from .labeler import LabelFn, _static_label
from .metrics import ScrubMetrics


def _derive_label(rule_id: str) -> str:
    """Convert a gitleaks rule id (``"aws-access-key"``) to a redaction label
    slug (``"AWS_ACCESS_KEY"``)."""
    return regex.sub(r"[^A-Za-z0-9]+", "_", rule_id).strip("_").upper()


def load_gitleaks_rules(
    path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load and parse the gitleaks TOML.

    Args:
        path: optional custom TOML path. ``None`` (default) reads the
            package-bundled ``hyperi_pylib/data/gitleaks.toml``.

    Returns:
        A tuple ``(rules, meta)`` where ``rules`` is a list of rule
        dicts (with keys ``id``, ``regex``, optional ``label``,
        optional ``keywords``) and ``meta`` is the metadata derived
        from the TOML's top-level ``title``/``minVersion`` fields (or
        an explicit ``[meta]`` table, when present).

    Tolerant: a missing or malformed file emits a one-time warning and
    returns ``([], {})`` rather than raising. Unknown rule fields and
    top-level sections (``[allowlist]``, ``[[allowlists]]``, etc.)
    are ignored — the loader extracts what it needs and leaves the
    rest alone.
    """
    if path is not None:
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            warnings.warn(
                f"gitleaks TOML at {path} not loadable: {e}. "
                f"L1 will have no rules.",
                RuntimeWarning,
                stacklevel=2,
            )
            return [], {}
    else:
        try:
            resource = resources.files("hyperi_pylib") / "data" / "gitleaks.toml"
            with resource.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError, ModuleNotFoundError) as e:
            warnings.warn(
                f"bundled gitleaks.toml not loadable: {e}. "
                f"L1 will have no rules.",
                RuntimeWarning,
                stacklevel=2,
            )
            return [], {}

    rules = data.get("rules", []) or []
    if not isinstance(rules, list):
        warnings.warn(
            "gitleaks.toml [[rules]] must be an array of tables; got "
            f"{type(rules).__name__}. L1 will have no rules.",
            RuntimeWarning,
            stacklevel=2,
        )
        return [], {}

    # Meta resolution: prefer explicit [meta] (HyperI-added when we
    # extend upstream); fall back to upstream's [title]/[minVersion].
    meta: dict[str, Any] = {}
    explicit_meta = data.get("meta", {})
    if isinstance(explicit_meta, dict) and explicit_meta:
        meta = dict(explicit_meta)
    else:
        title = data.get("title")
        min_version = data.get("minVersion")
        if title:
            meta["title"] = str(title)
        if min_version:
            meta["version"] = str(min_version)
        if not meta:
            meta["version"] = "unversioned"

    return rules, meta


class _CompiledRule:
    """A compiled gitleaks rule ready to scan log text."""

    __slots__ = ("id", "label", "pattern", "keywords")

    def __init__(self, id_: str, label: str, pattern: regex.Pattern[str],
                 keywords: tuple[str, ...]) -> None:
        self.id = id_
        self.label = label
        self.pattern = pattern
        self.keywords = keywords

    def __repr__(self) -> str:
        return f"_CompiledRule(id={self.id!r}, label={self.label!r})"


class GitleaksTomlScrubber:
    """L1 — secret artefacts, TOML-driven.

    Args:
        rules: pre-loaded list of rule dicts from
            :func:`load_gitleaks_rules`. ``None`` triggers a fresh
            load of the bundled TOML.
        path: optional TOML path override (used when ``rules`` is None).
        labeler: redaction-label producer. Defaults to static
            ``[LABEL_REDACTED]``.
        metrics: :class:`ScrubMetrics` instance. Defaults to no-op.
        rule_ids: optional ``set[str]`` of rule IDs to enable. ``None``
            (default) enables every rule with a compilable regex.

    Per spec §3.2, rules whose regex doesn't compile in Python's ``re``
    module are skipped with a one-time warning and their ID recorded
    in :attr:`skipped_rules` (also emitted via the
    ``log_scrub_skipped_rules_total`` gauge for cross-language parity).
    """

    def __init__(
        self,
        rules: list[dict[str, Any]] | None = None,
        path: Path | None = None,
        labeler: LabelFn | None = None,
        metrics: ScrubMetrics | None = None,
        rule_ids: set[str] | None = None,
    ) -> None:
        if rules is None:
            rules, meta = load_gitleaks_rules(path)
            self.version: str = str(meta.get("version", "unversioned"))
        else:
            self.version = "explicit-rules"

        self._labeler: LabelFn = labeler if labeler is not None else _static_label
        self._metrics = metrics if metrics is not None else ScrubMetrics.noop()
        self.skipped_rules: list[str] = []
        self._compiled: list[_CompiledRule] = []

        for entry in rules:
            if not isinstance(entry, dict):
                continue
            rule_id = str(entry.get("id", "")).strip()
            regex_str = entry.get("regex")
            # Upstream gitleaks rules don't carry a `label` field — we derive
            # one from the id (kebab-case -> UPPER_SNAKE_CASE). Hand-authored
            # HyperI rules MAY supply an explicit label override.
            label = str(entry.get("label") or _derive_label(rule_id))
            if not rule_id or not isinstance(regex_str, str) or not regex_str:
                continue
            if rule_ids is not None and rule_id not in rule_ids:
                continue
            try:
                # `regex.MULTILINE | regex.V1` — V1 enables the modern
                # behaviour (better Unicode, fewer footguns). Accepts the
                # mid-expression `(?i)` and `\z` constructs upstream uses.
                pattern = regex.compile(regex_str, regex.MULTILINE | regex.V1)
            except regex.error as e:
                warnings.warn(
                    f"gitleaks rule {rule_id!r} regex did not compile: {e}. "
                    f"Skipping rule.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self.skipped_rules.append(rule_id)
                self._metrics.set_skipped("L1", rule_id, value=1)
                continue
            keywords = entry.get("keywords") or ()
            if not isinstance(keywords, (list, tuple)):
                keywords = ()
            self._compiled.append(
                _CompiledRule(rule_id, label, pattern, tuple(str(k) for k in keywords))
            )

    @property
    def rule_count(self) -> int:
        """Number of rules compiled successfully and active in this scrubber."""
        return len(self._compiled)

    def scrub(self, text: str) -> str:
        if not text or not self._compiled:
            return text

        # Scan every rule against the ORIGINAL text, collect matches,
        # then resolve overlaps and emit a single redacted output. This
        # mirrors gitleaks-the-tool: rules are independent and a generic
        # rule (e.g. ``generic-api-key``) shouldn't consume text that a
        # more specific rule (e.g. ``private-key``) needs to match.
        #
        # Tie-breaking when matches overlap: prefer the longer match
        # (more specific). Equal lengths → earlier rule wins (preserves
        # upstream TOML ordering as a deterministic tiebreaker).
        lowered = text.lower()
        candidates: list[tuple[int, int, _CompiledRule]] = []
        for idx, rule in enumerate(self._compiled):
            if rule.keywords and not any(k in lowered for k in rule.keywords):
                continue
            for m in rule.pattern.finditer(text):
                start, end = m.span()
                # Zero-length matches don't redact anything sensible
                if end <= start:
                    continue
                candidates.append((start, end, rule))

        if not candidates:
            return text

        # Resolve overlapping matches by greedy-longest-first: a
        # specific multi-line rule (e.g. ``private-key`` spanning ~250
        # chars) outranks a broad single-line rule (e.g. ``generic-api-key``
        # spanning ~15 chars) when they overlap. This matches gitleaks-
        # the-tool's intent: structural rules take precedence over
        # heuristic catch-alls.
        #
        # Algorithm: sort by (-span DESC, start ASC) so the longest
        # match comes first. Greedily take matches that don't overlap
        # anything already kept. Track kept spans in start-order so
        # final assembly is one left-to-right walk.
        candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))

        kept: list[tuple[int, int, _CompiledRule]] = []
        for start, end, rule in candidates:
            overlaps = any(
                start < ke and end > ks
                for ks, ke, _ in kept
            )
            if not overlaps:
                kept.append((start, end, rule))
        kept.sort(key=lambda k: k[0])

        # Build the redacted output in one walk.
        out: list[str] = []
        cursor = 0
        for start, end, rule in kept:
            if start > cursor:
                out.append(text[cursor:start])
            value = text[start:end]
            self._metrics.inc_match("L1", rule.label)
            self._metrics.inc_redaction("L1", rule.label)
            out.append(self._labeler(rule.label, value))
            cursor = end
        if cursor < len(text):
            out.append(text[cursor:])
        return "".join(out)

    def __repr__(self) -> str:
        return (
            f"GitleaksTomlScrubber(rules={self.rule_count}, "
            f"skipped={len(self.skipped_rules)}, version={self.version!r})"
        )
