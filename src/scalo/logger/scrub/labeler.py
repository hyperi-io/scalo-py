#  Project:   scalo
#  File:      src/scalo/logger/scrub/labeler.py
#  Purpose:   Redaction-label formatting (static + deterministic-hash)
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Redaction-label formatting per spec Section 4.

Two modes:

- **Static** (default): every match for a given LABEL collapses to the
  same string ``[LABEL_REDACTED]``. Identical PII produces identical
  output -- no operator correlation possible.
- **Deterministic hash** (opt-in, ``scrub.hash_redaction: true``): each
  unique value gets a short keyed-hash suffix, e.g.
  ``[EMAIL_a3f5b2c4d6e8f001]``. Same value -> same suffix within a process (or
  across processes when ``LOG_SCRUB_HASH_KEY`` is set), letting
  operators correlate events without exposing the value.

Hash algorithm: HMAC-SHA256 keyed with ``secret_hash_key``, truncated to
8 bytes (16 hex chars). grippo's Rust scrubber uses the same construction, so
a Python and a Rust service given the same key label the same value the same way.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable

from ..._env_compat import control_var

type LabelFn = Callable[[str, str], str]
"""Label-producing function. Takes ``(label, value)``, returns redaction string."""


def _static_label(label: str, value: str) -> str:
    """Default: collapse every match for ``label`` to ``[LABEL_REDACTED]``."""
    return f"[{label}_REDACTED]"


def make_hash_labeler(secret_hash_key: bytes | None = None) -> LabelFn:
    """Build a deterministic-hash labeler.

    Args:
        secret_hash_key: Bytes used to key the HMAC-SHA256 hash. If ``None``,
            the environment variable ``LOG_SCRUB_HASH_KEY`` is
            consulted; if it is empty/unset, a per-process random key is
            generated. Within a process, the same value always produces
            the same suffix.

    Returns:
        A :data:`LabelFn` that produces ``[LABEL_<16 hex>]`` strings.

    The key is bound into the returned closure -- callers may construct
    distinct labelers with distinct keys, but the typical case is one
    labeler per scrubber instance.
    """
    if secret_hash_key is None:
        env_key = control_var("LOG_SCRUB_HASH_KEY") or ""
        if env_key:
            secret_hash_key = env_key.encode("utf-8")
        else:
            secret_hash_key = secrets.token_bytes(32)

    def _hash_label(label: str, value: str) -> str:
        # Keyed, so a label can't be matched offline without the key.
        digest = hmac.new(secret_hash_key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        return f"[{label}_{digest}]"

    return _hash_label


def resolve_labeler(
    hash_redaction: bool,
    secret_hash_key: bytes | None = None,
) -> LabelFn:
    """Pick the right labeler given a scrub config.

    Convenience for factory wiring -- ``build_scrubber()`` calls this
    once and passes the result to every layer that produces labels.
    """
    if hash_redaction:
        return make_hash_labeler(secret_hash_key)
    return _static_label
