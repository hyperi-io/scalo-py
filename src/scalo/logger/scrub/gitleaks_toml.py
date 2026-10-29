#  Project:   scalo
#  File:      src/scalo/logger/scrub/gitleaks_toml.py
#  Purpose:   TOML-driven L1 secret-artefact scrubber (replaces detect-secrets)
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

r"""TOML-driven Layer 1 secret-artefact scrubber.

Loads gitleaks-format rules from the bundled
``scalo/data/gitleaks.toml`` (vendored byte-identical from
``hyperi-ai/standards/patterns/gitleaks.toml``, which is in turn
synced from upstream ``gitleaks/gitleaks`` per spec Section 3.2) and applies
them as a Scrubber Protocol implementation.

**Regex engine**: this module uses the PyPI ``regex`` package, not
stdlib ``re``. Upstream gitleaks uses Go's RE2 syntax which permits
constructs Python's stdlib ``re`` rejects (mid-expression ``(?i)``
flags, ``\z`` end-anchor). The ``regex`` package accepts both
syntaxes plus a superset. Pylib is not on the hot path
(per ``standards/languages/PYTHON.md``) so the modest ``regex`` vs
``re`` overhead is fine. Rustlib will compile the same rules through
the ``regex`` Rust crate which also accepts the superset.

Unused upstream sections (``[allowlist]``, ``[[rules.tags]]``,
``[[rules.allowlists]]``, ``title``, ``minVersion``) are tolerated
silently -- the loader reads only the fields it understands.

The legacy :mod:`scalo.logger.secrets_leak` path
(detect-secrets-backed) remains available for callers that want
entropy heuristics; ``SecretsScrubber`` picks between them via the
``patterns`` setting.
"""

import re
import threading
import tomllib
import warnings
from collections.abc import Collection
from pathlib import Path
from typing import Any

import regex

from ._bundled import load_bundled_table
from .labeler import LabelFn, _static_label
from .metrics import ScrubMetrics

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def _derive_label(rule_id: str) -> str:
    """Convert a gitleaks rule id (``"aws-access-key"``) to a redaction label slug (``"AWS_ACCESS_KEY"``)."""
    return _NON_ALNUM.sub("_", rule_id).strip("_").upper()


def load_gitleaks_rules(
    path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load and parse the gitleaks TOML.

    Args:
        path: optional custom TOML path. ``None`` (default) reads the
            package-bundled ``scalo/data/gitleaks.toml``.

    Returns:
        A tuple ``(rules, meta)`` where ``rules`` is a list of rule
        dicts (with keys ``id``, ``regex``, optional ``label``,
        optional ``keywords``) and ``meta`` is the metadata derived
        from the TOML's top-level ``title``/``minVersion`` fields (or
        an explicit ``[meta]`` table, when present).

    Tolerant: a missing or malformed file emits a one-time warning and
    returns ``([], {})`` rather than raising. Unknown rule fields and
    top-level sections (``[allowlist]``, ``[[allowlists]]``, etc.)
    are ignored -- the loader extracts what it needs and leaves the
    rest alone.
    """
    if path is not None:
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            warnings.warn(
                f"gitleaks TOML at {path} not loadable: {e}. L1 will have no rules.",
                RuntimeWarning,
                stacklevel=2,
            )
            return [], {}
    else:
        try:
            data = load_bundled_table("gitleaks")
        except (OSError, tomllib.TOMLDecodeError, ModuleNotFoundError) as e:
            warnings.warn(
                f"bundled gitleaks.toml not loadable: {e}. L1 will have no rules.",
                RuntimeWarning,
                stacklevel=2,
            )
            return [], {}

    rules = data.get("rules", []) or []
    if not isinstance(rules, list):
        warnings.warn(
            f"gitleaks.toml [[rules]] must be an array of tables; got {type(rules).__name__}. L1 will have no rules.",
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
    """A gitleaks rule whose regex compiles on first use.

    Compiling all 221 upstream regexes costs several hundred milliseconds, and a
    process that scrubs one line needs a handful of them, so
    :meth:`GitleaksTomlScrubber.scrub` compiles a rule only once its keywords hit.
    """

    __slots__ = ("id", "keywords", "label", "pattern", "regex_str", "secret_group", "skipped")

    def __init__(
        self,
        id_: str,
        label: str,
        regex_str: str,
        keywords: tuple[str, ...],
        secret_group: int = 0,
    ) -> None:
        self.id = id_
        self.label = label
        self.regex_str = regex_str
        self.keywords = keywords
        self.secret_group = secret_group
        # regex ships no type stubs, so ty cannot see that its Pattern is generic.
        self.pattern: regex.Pattern[str] | None = None  # ty: ignore[invalid-type-form]
        self.skipped = False

    def secret_span(
        self,
        pattern: regex.Pattern[str],  # ty: ignore[invalid-type-form]
        m: regex.Match[str],  # ty: ignore[invalid-type-form]
    ) -> tuple[int, int]:
        """Return the span of ``m`` that holds the secret, so the key name and quotes around it survive.

        An explicit ``secretGroup`` wins, as in gitleaks. Without one, gitleaks takes
        the first non-empty group, but some upstream rules capture a fragment
        (``microsoft-teams-webhook``, ``jwt-base64``), so that group is used only when
        nothing alphanumeric follows it in the match. Otherwise the whole match goes.
        """
        whole = m.span()
        if self.secret_group:
            if self.secret_group <= pattern.groups:
                start, end = m.span(self.secret_group)
                if end > start:
                    return start, end
            return whole
        for idx in range(1, pattern.groups + 1):
            start, end = m.span(idx)
            if end > start:
                tail = m.string[end : whole[1]]
                return (start, end) if not any(c.isalnum() for c in tail) else whole
        return whole

    def __repr__(self) -> str:
        return f"_CompiledRule(id={self.id!r}, label={self.label!r})"


class GitleaksTomlScrubber:
    """L1 -- secret artefacts, TOML-driven.

    Args:
        rules: pre-loaded list of rule dicts from
            :func:`load_gitleaks_rules`. ``None`` triggers a fresh
            load of the bundled TOML.
        path: optional TOML path override (used when ``rules`` is None).
        labeler: redaction-label producer. Defaults to static
            ``[LABEL_REDACTED]``.
        metrics: :class:`ScrubMetrics` instance. Defaults to no-op.
        rule_ids: optional collection of rule IDs to enable. ``None``
            (default) enables every rule with a compilable regex.
        exclude_rule_ids: optional rule IDs to leave out of whatever
            ``rule_ids`` selects. An ID the rule set does not carry is
            reported with a one-time warning, since a typo would otherwise
            leave the rule running unnoticed.

    Each rule's regex compiles on the first :meth:`scrub` whose text hits one of
    the rule's keywords, or on the first :meth:`scrub` at all for a rule with no
    keywords. Per spec Section 3.2, a rule whose regex doesn't compile in the
    ``regex`` package is skipped with a one-time warning at that point and its ID
    recorded in :attr:`skipped_rules` (also emitted via the
    ``log_scrub_skipped_rules_total`` gauge for cross-language parity). Both are
    empty after construction. :meth:`compile_all` compiles every rule at once.
    """

    def __init__(
        self,
        rules: list[dict[str, Any]] | None = None,
        path: Path | None = None,
        labeler: LabelFn | None = None,
        metrics: ScrubMetrics | None = None,
        rule_ids: Collection[str] | None = None,
        exclude_rule_ids: Collection[str] | None = None,
    ) -> None:
        excluded = frozenset(exclude_rule_ids or ())
        seen_ids: set[str] = set()
        if rules is None:
            rules, meta = load_gitleaks_rules(path)
            self.version: str = str(meta.get("version", "unversioned"))
        else:
            self.version = "explicit-rules"

        self._labeler: LabelFn = labeler if labeler is not None else _static_label
        self._metrics = metrics if metrics is not None else ScrubMetrics.noop()
        self.skipped_rules: list[str] = []
        self._rules: list[_CompiledRule] = []
        self._compile_lock = threading.Lock()

        for entry in rules:
            if not isinstance(entry, dict):
                continue
            rule_id = str(entry.get("id", "")).strip()
            regex_str = entry.get("regex")
            # Upstream gitleaks rules don't carry a `label` field -- we derive
            # one from the id (kebab-case -> UPPER_SNAKE_CASE). Hand-authored
            # HyperI rules MAY supply an explicit label override.
            label = str(entry.get("label") or _derive_label(rule_id))
            if rule_id:
                seen_ids.add(rule_id)
            if not rule_id or not isinstance(regex_str, str) or not regex_str:
                continue
            if rule_ids is not None and rule_id not in rule_ids:
                continue
            if rule_id in excluded:
                continue
            keywords = entry.get("keywords") or ()
            if not isinstance(keywords, (list, tuple)):
                keywords = ()
            secret_group = entry.get("secretGroup", 0)
            if not isinstance(secret_group, int) or secret_group < 0:
                secret_group = 0
            self._rules.append(_CompiledRule(rule_id, label, regex_str, tuple(str(k) for k in keywords), secret_group))

        unknown = sorted(excluded - seen_ids)
        if unknown:
            warnings.warn(
                f"exclude_rule_ids names rule(s) the gitleaks rule set does not carry: {', '.join(unknown)}. "
                "Nothing was excluded for them -- check the rule ids.",
                RuntimeWarning,
                stacklevel=2,
            )

    @property
    def rule_count(self) -> int:
        """Number of rules selected and not found uncompilable.

        A regex is only found uncompilable when it first compiles, so a rule
        counts until then. Call :meth:`compile_all` first for the final figure.
        """
        return sum(1 for rule in self._rules if not rule.skipped)

    def compile_all(self) -> None:
        """Compile every selected rule now, so :attr:`skipped_rules` is complete."""
        for rule in self._rules:
            self._pattern(rule)

    def _pattern(self, rule: _CompiledRule) -> regex.Pattern[str] | None:  # ty: ignore[invalid-type-form]
        """Return the rule's compiled regex, compiling it on first use, or None when it does not compile."""
        pattern = rule.pattern
        if pattern is not None or rule.skipped:
            return pattern
        with self._compile_lock:
            if rule.pattern is not None or rule.skipped:
                return rule.pattern
            try:
                # `regex.MULTILINE | regex.V1` -- V1 enables the modern
                # behaviour (better Unicode, fewer footguns). Accepts the
                # mid-expression `(?i)` and `\z` constructs upstream uses.
                rule.pattern = regex.compile(rule.regex_str, regex.MULTILINE | regex.V1)
            except regex.error as e:
                warnings.warn(
                    f"gitleaks rule {rule.id!r} regex did not compile: {e}. Skipping rule.",
                    RuntimeWarning,
                    stacklevel=3,
                )
                rule.skipped = True
                self.skipped_rules.append(rule.id)
                self._metrics.set_skipped("L1", rule.id, value=1)
            return rule.pattern

    def scrub(self, text: str) -> str:
        """Return ``text`` with the secret in each gitleaks rule match replaced by the labeler's output for it."""
        if not text or not self._rules:
            return text

        # Scan every rule against the ORIGINAL text, collect matches,
        # then resolve overlaps and emit a single redacted output. This
        # mirrors gitleaks-the-tool: rules are independent and a generic
        # rule (e.g. ``generic-api-key``) shouldn't consume text that a
        # more specific rule (e.g. ``private-key``) needs to match.
        #
        # Tie-breaking when matches overlap: prefer the longer match
        # (more specific). Equal lengths -> earlier rule wins (preserves
        # upstream TOML ordering as a deterministic tiebreaker).
        lowered = text.lower()
        # (match start, match end, secret start, secret end, rule)
        candidates: list[tuple[int, int, int, int, _CompiledRule]] = []
        for rule in self._rules:
            if rule.keywords and not any(k in lowered for k in rule.keywords):
                continue
            pattern = self._pattern(rule)
            if pattern is None:
                continue
            for m in pattern.finditer(text):
                start, end = m.span()
                # Zero-length matches don't redact anything sensible
                if end <= start:
                    continue
                secret_start, secret_end = rule.secret_span(pattern, m)
                candidates.append((start, end, secret_start, secret_end, rule))

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
        # final assembly is one left-to-right walk. Overlap is judged on the
        # whole match, and only the secret span inside it is replaced.
        candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))

        kept: list[tuple[int, int, int, int, _CompiledRule]] = []
        for candidate in candidates:
            start, end = candidate[0], candidate[1]
            overlaps = any(start < k[1] and end > k[0] for k in kept)
            if not overlaps:
                kept.append(candidate)
        kept.sort(key=lambda k: k[0])

        # Build the redacted output in one walk.
        out: list[str] = []
        cursor = 0
        for _, _, secret_start, secret_end, rule in kept:
            if secret_start > cursor:
                out.append(text[cursor:secret_start])
            value = text[secret_start:secret_end]
            self._metrics.inc_match("L1", rule.label)
            self._metrics.inc_redaction("L1", rule.label)
            out.append(self._labeler(rule.label, value))
            cursor = secret_end
        if cursor < len(text):
            out.append(text[cursor:])
        return "".join(out)

    def __repr__(self) -> str:
        return (
            f"GitleaksTomlScrubber(rules={self.rule_count}, "
            f"skipped={len(self.skipped_rules)}, version={self.version!r})"
        )
