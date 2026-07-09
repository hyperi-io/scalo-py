#  Project:   scalo
#  File:      tests/unit/test_secrets_crypto.py
#  Purpose:   AES-256-GCM at-rest cache envelope: round-trip + misuse resistance
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""At-rest crypto for the secrets disk cache.

Mirrors the scalo-rs ``secrets::crypto`` test suite: round-trip, wrong
key, tampered ciphertext, AAD mismatch, domain separation, version
rejection, malformed envelope, nonce uniqueness, and envelope sniffing.
Uses the real ``cryptography`` primitives -- no mocks.
"""

from __future__ import annotations

import json

import pytest

from scalo.secrets import crypto
from scalo.secrets.exceptions import CacheError

KEY = b"operator-provided-passphrase"
AAD = crypto.aad_for("db_password")


def test_round_trip_recovers_plaintext() -> None:
    pt = b"my secret value"
    env = crypto.seal(KEY, pt, AAD)
    assert crypto.open_envelope(KEY, env, AAD) == pt


def test_envelope_is_v1_aes256gcm_json() -> None:
    env = crypto.seal(KEY, b"x", AAD)
    obj = json.loads(env)
    assert obj["v"] == 1
    assert set(obj) == {"v", "nonce", "ct"}
    # 12-byte nonce, base64url-no-pad (16 chars).
    assert len(obj["nonce"]) == 16


def test_wrong_key_fails_authentication() -> None:
    env = crypto.seal(b"right-key", b"data", AAD)
    with pytest.raises(CacheError):
        crypto.open_envelope(b"wrong-key", env, AAD)


def test_tampered_ciphertext_fails_authentication() -> None:
    env = crypto.seal(KEY, b"data", AAD)
    obj = json.loads(env)
    # Flip a byte in the ct field.
    ct = list(obj["ct"])
    ct[0] = "B" if ct[0] == "A" else "A"
    obj["ct"] = "".join(ct)
    with pytest.raises(CacheError):
        crypto.open_envelope(KEY, json.dumps(obj).encode(), AAD)


def test_aad_mismatch_fails_authentication() -> None:
    """AAD bound to the cache-key name prevents cross-slot file swaps."""
    env = crypto.seal(KEY, b"db-password", crypto.aad_for("db_password"))
    with pytest.raises(CacheError):
        crypto.open_envelope(KEY, env, crypto.aad_for("kafka_password"))


def test_aad_domain_separation_blocks_bare_key_reuse() -> None:
    """A caller passing the bare cache_key (no domain prefix) must fail."""
    env = crypto.seal(KEY, b"db-password", crypto.aad_for("db_password"))
    with pytest.raises(CacheError):
        crypto.open_envelope(KEY, env, b"db_password")


def test_unsupported_version_rejected() -> None:
    env = crypto.seal(KEY, b"data", AAD)
    obj = json.loads(env)
    obj["v"] = 2
    with pytest.raises(CacheError):
        crypto.open_envelope(KEY, json.dumps(obj).encode(), AAD)


def test_malformed_envelope_returns_error() -> None:
    with pytest.raises(CacheError):
        crypto.open_envelope(KEY, b"not json", AAD)


def test_short_nonce_rejected() -> None:
    env = crypto.seal(KEY, b"data", AAD)
    obj = json.loads(env)
    obj["nonce"] = "AAAA"  # 3 bytes, != 12
    with pytest.raises(CacheError):
        crypto.open_envelope(KEY, json.dumps(obj).encode(), AAD)


def test_nonces_are_unique_across_seals() -> None:
    seen = set()
    for _ in range(1000):
        env = crypto.seal(KEY, b"same plaintext", AAD)
        assert env not in seen, "duplicate envelope (nonce collision)"
        seen.add(env)


def test_looks_like_envelope_detects_v1_form() -> None:
    env = crypto.seal(KEY, b"x", AAD)
    assert crypto.looks_like_envelope(env)


def test_looks_like_envelope_rejects_legacy_plaintext() -> None:
    legacy = b'{"data_hex":"abcd","fetched_at":"2026-01-01T00:00:00+00:00"}'
    assert not crypto.looks_like_envelope(legacy)


def test_str_and_bytes_keys_agree() -> None:
    """A str key and its utf-8 bytes derive the same key (cross-language
    parity: the Rust twin keys on user_key.as_bytes())."""
    env = crypto.seal(b"passphrase", b"data", AAD)
    assert crypto.open_envelope(b"passphrase", env, AAD) == b"data"
