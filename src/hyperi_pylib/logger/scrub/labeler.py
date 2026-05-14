#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/labeler.py
#  Purpose:   Redaction-label formatting (static + deterministic-hash)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Redaction-label formatting per spec §4.

Two modes:

- **Static** (default): every match for a given LABEL collapses to the
  same string ``[LABEL_REDACTED]``. Identical PII produces identical
  output — no operator correlation possible.
- **Deterministic hash** (opt-in, ``scrub.hash_redaction: true``): each
  unique value gets a short keyed-hash suffix, e.g.
  ``[EMAIL_a3f5b2]``. Same value → same suffix within a process (or
  across processes when ``HYPERI_LOG_SCRUB_HASH_KEY`` is set), letting
  operators correlate events without exposing the value.

Hash algorithm: BLAKE2b keyed with ``secret_hash_key``,
``digest_size=4`` (8 hex chars), truncated to 6 hex chars per spec.
BLAKE2b is in the Python stdlib (``hashlib.blake2b``) and has a Rust
counterpart in the RustCrypto ``blake2`` crate — chosen over BLAKE3
to avoid a build-time Rust-wheel dep in pylib for what is functionally
a short-label hash.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Callable
from typing import TypeAlias

type LabelFn = Callable[[str, str], str]
"""Label-producing function. Takes ``(label, value)``, returns redaction string."""


def _static_label(label: str, value: str) -> str:
    """Default: collapse every match for ``label`` to ``[LABEL_REDACTED]``."""
    return f"[{label}_REDACTED]"


def make_hash_labeler(secret_hash_key: bytes | None = None) -> LabelFn:
    """Build a deterministic-hash labeler.

    Args:
        secret_hash_key: Bytes used to key the BLAKE2b hash. If ``None``,
            the environment variable ``HYPERI_LOG_SCRUB_HASH_KEY`` is
            consulted; if it is empty/unset, a per-process random key is
            generated. Within a process, the same value always produces
            the same suffix.

    Returns:
        A :data:`LabelFn` that produces ``[LABEL_xxxxxx]`` strings.

    The key is bound into the returned closure — callers may construct
    distinct labelers with distinct keys, but the typical case is one
    labeler per scrubber instance.
    """
    if secret_hash_key is None:
        env_key = os.environ.get("HYPERI_LOG_SCRUB_HASH_KEY", "")
        if env_key:
            secret_hash_key = env_key.encode("utf-8")
        else:
            secret_hash_key = secrets.token_bytes(32)

    # BLAKE2b accepts keys up to 64 bytes. Truncate operator-supplied
    # keys if necessary; longer keys add no entropy.
    if len(secret_hash_key) > 64:
        secret_hash_key = secret_hash_key[:64]

    def _hash_label(label: str, value: str) -> str:
        digest = hashlib.blake2b(
            value.encode("utf-8"),
            key=secret_hash_key,
            digest_size=4,
        ).hexdigest()[:6]
        return f"[{label}_{digest}]"

    return _hash_label


def resolve_labeler(
    hash_redaction: bool,
    secret_hash_key: bytes | None = None,
) -> LabelFn:
    """Pick the right labeler given a scrub config.

    Convenience for factory wiring — ``build_scrubber()`` calls this
    once and passes the result to every layer that produces labels.
    """
    if hash_redaction:
        return make_hash_labeler(secret_hash_key)
    return _static_label
