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

A match is redacted only when gitleaks would report it. Per match the scrubber
applies, in gitleaks' own terms: the rule's ``entropy`` (a Shannon entropy at or
below the threshold drops the match), the global ``[allowlist]`` and
``[[allowlists]]``, and the rule's ``[[rules.allowlists]]`` (``regexes`` against the
secret, the whole match or the line per ``regexTarget``, ``stopwords`` against the
secret, ``condition`` ``OR`` or ``AND``). An allowlist's ``paths`` and ``commits``
need a file or commit that log text lacks, so an ``AND`` allowlist that lists one
never applies and an ``OR`` allowlist ignores it, as gitleaks does for an empty
path. A rule's own ``path`` is not evaluated, so those rules still fire on text.
Secret decoding passes, ``gitleaks:allow`` comments and ``[[rules.required]]`` are
not applied. Sections the loader does not use (``[[rules.tags]]``, ``title``,
``minVersion``) are tolerated silently.

The legacy :mod:`scalo.logger.secrets_leak` path
(detect-secrets-backed) remains available for callers that want
entropy heuristics; ``SecretsScrubber`` picks between them via the
``patterns`` setting.
"""

import math
import re
import threading
import tomllib
import warnings
from collections import Counter
from collections.abc import Callable, Collection, Mapping
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
        optional ``keywords``, ``entropy`` and ``allowlists``) and ``meta`` is the
        metadata derived from the TOML's top-level ``title``/``minVersion`` fields
        (or an explicit ``[meta]`` table, when present).

    Tolerant: a missing or malformed file emits a one-time warning and
    returns ``([], {})`` rather than raising. The global ``[allowlist]`` is not part
    of the return value: :class:`GitleaksTomlScrubber` reads it from the same file.
    """
    rules, _, meta = _load_config(path)
    return rules, meta


def _load_config(
    path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return ``(rules, global_allowlists, meta)`` from the gitleaks TOML, as ``([], [], {})`` when it does not load."""
    if path is not None:
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            warnings.warn(
                f"gitleaks TOML at {path} not loadable: {e}. L1 will have no rules.",
                RuntimeWarning,
                stacklevel=3,
            )
            return [], [], {}
    else:
        try:
            data = load_bundled_table("gitleaks")
        except (OSError, tomllib.TOMLDecodeError, ModuleNotFoundError) as e:
            warnings.warn(
                f"bundled gitleaks.toml not loadable: {e}. L1 will have no rules.",
                RuntimeWarning,
                stacklevel=3,
            )
            return [], [], {}

    rules = data.get("rules", []) or []
    if not isinstance(rules, list):
        warnings.warn(
            f"gitleaks.toml [[rules]] must be an array of tables; got {type(rules).__name__}. L1 will have no rules.",
            RuntimeWarning,
            stacklevel=3,
        )
        return [], [], {}

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

    # Gitleaks reads the global list from `[[allowlists]]` and, deprecated, `[allowlist]`.
    allowlists: list[dict[str, Any]] = []
    legacy = data.get("allowlist")
    if isinstance(legacy, dict):
        allowlists.append(legacy)
    modern = data.get("allowlists")
    if isinstance(modern, list):
        allowlists.extend(a for a in modern if isinstance(a, dict))

    return rules, allowlists, meta


def _shannon_entropy(data: str) -> float:
    """Return gitleaks' Shannon entropy of ``data``: per code point, with frequencies over the UTF-8 byte length."""
    if not data:
        return 0.0
    inverse_length = 1.0 / len(data.encode("utf-8", "replace"))
    entropy = 0.0
    for count in Counter(data).values():
        frequency = count * inverse_length
        entropy -= frequency * math.log2(frequency)
    return entropy


_ALLOWLIST_COMPILE_LOCK = threading.Lock()


class _Allowlist:
    """One gitleaks allowlist, reduced to the checks that can apply to log text.

    ``paths`` and ``commits`` need a file or commit that text lacks. Under ``OR`` they
    never allow anything, so they are dropped. Under ``AND`` every listed check has to
    hold, so an allowlist that lists one can never allow and is not built at all.
    """

    __slots__ = (
        "_broken",
        "_pattern",
        "and_condition",
        "regex_sources",
        "regex_target",
        "stopword_lengths",
        "stopwords",
    )

    def __init__(
        self,
        regex_sources: tuple[str, ...],
        stopwords: tuple[str, ...],
        regex_target: str,
        *,
        and_condition: bool,
    ) -> None:
        self.regex_sources = regex_sources
        self.stopwords = frozenset(stopwords)
        # Probing the secret's substrings of each stopword length beats scanning for every word.
        self.stopword_lengths = tuple(sorted({len(word) for word in stopwords}))
        self.regex_target = regex_target
        self.and_condition = and_condition
        self._broken = False
        # regex ships no type stubs, so ty cannot see that its Pattern is generic.
        self._pattern: regex.Pattern[str] | None = None  # ty: ignore[invalid-type-form]

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any], origin: str) -> _Allowlist | None:
        """Build an allowlist from its TOML table, or return None when it can never allow anything.

        A table gitleaks would refuse (an unknown ``condition`` or ``regexTarget``, no check at all)
        is skipped with a warning, so the matches it would have excused stay redacted.
        """
        condition = str(spec.get("condition", "")).upper()
        if condition not in ("", "OR", "||", "AND", "&&"):
            warnings.warn(
                f"gitleaks allowlist for {origin} has unknown condition {spec.get('condition')!r}. Ignoring it.",
                RuntimeWarning,
                stacklevel=3,
            )
            return None
        target = str(spec.get("regexTarget", ""))
        if target not in ("", "secret", "match", "line"):
            warnings.warn(
                f"gitleaks allowlist for {origin} has unknown regexTarget {target!r}. Ignoring it.",
                RuntimeWarning,
                stacklevel=3,
            )
            return None
        regexes = tuple(str(r) for r in spec.get("regexes") or ())
        stopwords = tuple(dict.fromkeys(w for w in (str(w).lower() for w in spec.get("stopwords") or ()) if w))
        has_file_checks = bool(spec.get("paths") or spec.get("commits"))
        if not (regexes or stopwords or has_file_checks):
            warnings.warn(
                f"gitleaks allowlist for {origin} has no commits, paths, regexes or stopwords. Ignoring it.",
                RuntimeWarning,
                stacklevel=3,
            )
            return None
        and_condition = condition in ("AND", "&&")
        if (and_condition and has_file_checks) or not (regexes or stopwords):
            return None
        return cls(regexes, stopwords, "" if target == "secret" else target, and_condition=and_condition)

    def _compiled(self) -> regex.Pattern[str] | None:  # ty: ignore[invalid-type-form]
        """Return the allowlist's regexes as one alternation, as gitleaks joins them, compiled on first use."""
        if self._pattern is not None or self._broken:
            return self._pattern
        with _ALLOWLIST_COMPILE_LOCK:
            if self._pattern is None and not self._broken:
                joined = "(?:" + "|".join(self.regex_sources) + ")"
                try:
                    self._pattern = regex.compile(joined, regex.V1)
                except regex.error as e:
                    warnings.warn(
                        f"gitleaks allowlist regexes did not compile: {e}. The allowlist excuses nothing.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    self._broken = True
        return self._pattern

    def _has_stopword(self, lowered: str) -> bool:
        """Return True when ``lowered`` contains any stopword."""
        size = len(lowered)
        for length in self.stopword_lengths:
            if length > size:
                break
            if any(lowered[i : i + length] in self.stopwords for i in range(size - length + 1)):
                return True
        return False

    def allows(self, secret: str, match: str, line: Callable[[], str]) -> bool:
        """Return True when this allowlist excuses a match whose secret, whole match and line are given."""
        regex_hit: bool | None = None
        if self.regex_sources:
            if self.regex_target == "line":
                target = line()
            elif self.regex_target == "match":
                target = match
            else:
                target = secret
            pattern = self._compiled()
            if pattern is None:
                return False
            regex_hit = bool(target) and pattern.search(target) is not None
        stopword_hit: bool | None = None
        if self.stopwords:
            stopword_hit = self._has_stopword(secret.lower())
        if self.and_condition:
            return all(hit for hit in (regex_hit, stopword_hit) if hit is not None)
        return bool(regex_hit) or bool(stopword_hit)


def _line_around(text: str, start: int, end: int) -> str:
    """Return the line holding the match ``text[start:end]``, cut as gitleaks cuts ``Finding.Line``.

    The line runs to the first newline at or after ``end`` and, past the first line,
    starts at the newline that precedes it.
    """
    line_start = max(text.rfind("\n", 0, start), 0)
    newline = text.find("\n", end)
    if newline < 0:
        carriage_return = text.find("\r", end)
        newline = len(text) if carriage_return < 0 else carriage_return
    return text[line_start:newline]


class _CompiledRule:
    """A gitleaks rule whose regex compiles on first use.

    Compiling all 221 upstream regexes costs several hundred milliseconds, and a
    process that scrubs one line needs a handful of them, so
    :meth:`GitleaksTomlScrubber.scrub` compiles a rule only once its keywords hit.
    """

    __slots__ = ("allowlists", "entropy", "id", "keywords", "label", "pattern", "regex_str", "secret_group", "skipped")

    def __init__(
        self,
        id_: str,
        label: str,
        regex_str: str,
        keywords: tuple[str, ...],
        secret_group: int = 0,
        entropy: float = 0.0,
        allowlists: tuple[_Allowlist, ...] = (),
    ) -> None:
        self.id = id_
        self.label = label
        self.regex_str = regex_str
        self.keywords = keywords
        self.secret_group = secret_group
        self.entropy = entropy
        self.allowlists = allowlists
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
        allowlists: global allowlist tables, applied to every rule. ``None``
            takes the ones in the TOML read for ``rules=None`` and applies
            none to an explicit ``rules`` list. A table with ``targetRules``
            joins those rules' own allowlists instead.

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
        allowlists: Collection[Mapping[str, Any]] | None = None,
    ) -> None:
        excluded = frozenset(exclude_rule_ids or ())
        seen_ids: set[str] = set()
        if rules is None:
            rules, loaded_allowlists, meta = _load_config(path)
            if allowlists is None:
                allowlists = loaded_allowlists
            self.version: str = str(meta.get("version", "unversioned"))
        else:
            self.version = "explicit-rules"

        global_allowlists: list[_Allowlist] = []
        targeted: dict[str, list[_Allowlist]] = {}
        for spec in allowlists or ():
            built = _Allowlist.from_spec(spec, "the global list")
            if built is None:
                continue
            target_rules = spec.get("targetRules")
            if target_rules:
                for target_id in target_rules:
                    targeted.setdefault(str(target_id), []).append(built)
            else:
                global_allowlists.append(built)
        self._global_allowlists: tuple[_Allowlist, ...] = tuple(global_allowlists)

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
            entropy = entry.get("entropy", 0.0)
            if isinstance(entropy, bool) or not isinstance(entropy, (int, float)):
                entropy = 0.0
            rule_allowlists = self._rule_allowlists(entry, rule_id) + tuple(targeted.get(rule_id, ()))
            self._rules.append(
                _CompiledRule(
                    rule_id,
                    label,
                    regex_str,
                    tuple(str(k).lower() for k in keywords),
                    secret_group,
                    float(entropy),
                    rule_allowlists,
                )
            )

        unknown = sorted(excluded - seen_ids)
        if unknown:
            warnings.warn(
                f"exclude_rule_ids names rule(s) the gitleaks rule set does not carry: {', '.join(unknown)}. "
                "Nothing was excluded for them -- check the rule ids.",
                RuntimeWarning,
                stacklevel=2,
            )

    @staticmethod
    def _rule_allowlists(entry: Mapping[str, Any], rule_id: str) -> tuple[_Allowlist, ...]:
        """Return the allowlists a rule table carries, from ``allowlists`` and the older single ``allowlist``."""
        specs: list[Mapping[str, Any]] = []
        legacy = entry.get("allowlist")
        if isinstance(legacy, Mapping):
            specs.append(legacy)
        modern = entry.get("allowlists")
        if isinstance(modern, list):
            specs.extend(a for a in modern if isinstance(a, Mapping))
        built = (_Allowlist.from_spec(spec, f"rule {rule_id!r}") for spec in specs)
        return tuple(a for a in built if a is not None)

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

    def _reported(
        self,
        rule: _CompiledRule,
        pattern: regex.Pattern[str],  # ty: ignore[invalid-type-form]
        text: str,
        start: int,
        end: int,
    ) -> bool:
        """Return True when gitleaks would report the match ``text[start:end]`` of ``rule``.

        The secret is taken as gitleaks takes it: the match with its newlines trimmed, narrowed
        to ``secretGroup`` or the first non-empty group of the regex run again over that text.
        Entropy and the allowlists judge that secret, so they can differ from the span that
        :meth:`_CompiledRule.secret_span` redacts.
        """
        whole = text[start:end].strip("\n")
        if not whole:
            return False
        secret = whole
        if pattern.groups:
            found = pattern.search(whole)
            if found is not None:
                if rule.secret_group:
                    if rule.secret_group > pattern.groups:
                        return False
                    secret = found.group(rule.secret_group) or ""
                else:
                    secret = next((g for g in found.groups() if g), whole)

        if rule.entropy and _shannon_entropy(secret) <= rule.entropy:
            return False

        line: str | None = None

        def line_of_match() -> str:
            nonlocal line
            if line is None:
                line = _line_around(text, start, end)
            return line

        return not any(
            allowlist.allows(secret, whole, line_of_match) for allowlist in (*self._global_allowlists, *rule.allowlists)
        )

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
                if not self._reported(rule, pattern, text, start, end):
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
