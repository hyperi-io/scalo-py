"""At-rest AES-256-GCM encryption for the secrets disk cache.

Python twin of the scalo-rs ``secrets::crypto`` module. Both sides share
the wire format so a cache written by one language is readable by the
other when the ``encryption_key`` matches:

- JSON envelope ``{"v":1,"nonce":<b64url-nopad 12B>,"ct":<b64url-nopad>}``
- HKDF-SHA256 key derivation with a fixed library-domain salt + info, so
  any-length key material (a passphrase or a pre-existing 32-byte key
  encoded as text) normalises to a 32-byte AES-256 key.
- Domain-separated AAD bound to the cache-key name, so an envelope for
  one secret cannot be renamed into another's slot and still decrypt.
- Random 96-bit nonce per entry (AES-GCM standard).

AES-256-GCM replaces the previous Fernet (AES-128-CBC + HMAC) at-rest
cipher to meet the CNSA 2.0 AES-256 symmetric target -- the Rust twin was
already AES-256-GCM, so this is parity, not a new design.
"""

import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .exceptions import CacheError

# HKDF salt -- fixed per-library so two services with the same
# encryption_key derive the same key ("same key = same cache"). Not
# secret. Byte-identical to scalo-rs HKDF_SALT for cross-language parity.
_HKDF_SALT = b"scalo::secrets::cache::v1::hkdf-salt-32bytes!"
_HKDF_INFO = b"scalo secrets disk cache AES-256-GCM key"

_ENVELOPE_VERSION = 1
_NONCE_LEN = 12  # 96 bits -- standard for AES-GCM

# AAD prefix. Domain-separates the cache AAD namespace so a future reuse
# of seal/open for a different purpose cannot share AAD values with the
# cache by accident. Byte-identical to scalo-rs AAD_DOMAIN.
_AAD_DOMAIN = b"scalo:secrets-cache:v1:"


def aad_for(cache_key: str) -> bytes:
    """Compose AAD for a cache slot: domain prefix + cache-key bytes."""
    return _AAD_DOMAIN + cache_key.encode("utf-8")


def _derive_key(user_key: bytes) -> bytes:
    """Derive a 32-byte AES-256-GCM key from user-supplied key material.

    HKDF-SHA256 with the fixed library-domain salt + info. Mirrors the
    Rust ``derive_key`` (IKM = the raw key bytes), so identical key
    material yields an identical derived key in both languages.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(user_key)


def _b64e(raw: bytes) -> str:
    """Base64-url encode without padding (matches Rust URL_SAFE_NO_PAD)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    """Base64-url decode, tolerating the stripped padding."""
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded)


def looks_like_envelope(raw: bytes) -> bool:
    """Cheap check that ``raw`` is a v1 AES-256-GCM envelope.

    Starts with ``{`` and contains the version key. Avoids a full JSON
    parse on legacy Fernet tokens or plaintext-JSON cache entries.
    """
    return raw[:1] == b"{" and b'"v":' in raw


def seal(user_key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Seal ``plaintext`` under ``user_key`` into a JSON envelope.

    ``aad`` (the cache-key name via :func:`aad_for`) is authenticated,
    not encrypted; a mismatch on :func:`open_envelope` fails auth.

    Raises:
        CacheError: on encryption failure.
    """
    try:
        key = _derive_key(user_key)
        nonce = os.urandom(_NONCE_LEN)
        ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    except Exception as exc:
        raise CacheError(f"encrypt failed: {exc}") from exc

    envelope = {
        "v": _ENVELOPE_VERSION,
        "nonce": _b64e(nonce),
        "ct": _b64e(ct),
    }
    # Compact separators match the Rust serde_json wire form.
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def open_envelope(user_key: bytes, envelope_bytes: bytes, aad: bytes) -> bytes:
    """Open an envelope produced by :func:`seal`. Same ``aad`` required.

    Raises:
        CacheError: on malformed envelope, wrong version, bad base64, or
            auth failure (wrong key / AAD / tampered ciphertext). The
            wrong-key and wrong-AAD paths return the same error -- no
            oracle.
    """
    try:
        envelope = json.loads(envelope_bytes)
    except (ValueError, TypeError) as exc:
        raise CacheError(f"envelope parse: {exc}") from exc

    if not isinstance(envelope, dict) or "v" not in envelope:
        raise CacheError("envelope parse: not a v1 envelope")

    version = envelope.get("v")
    if version != _ENVELOPE_VERSION:
        raise CacheError(f"unsupported envelope version {version} (expected {_ENVELOPE_VERSION})")

    try:
        nonce = _b64d(envelope["nonce"])
        ct = _b64d(envelope["ct"])
    except (KeyError, ValueError, TypeError) as exc:
        raise CacheError(f"envelope base64: {exc}") from exc

    if len(nonce) != _NONCE_LEN:
        raise CacheError(f"nonce length {len(nonce)} (expected {_NONCE_LEN})")

    try:
        key = _derive_key(user_key)
        return AESGCM(key).decrypt(nonce, ct, aad)
    except Exception as exc:
        raise CacheError("decrypt failed: wrong key, wrong AAD, or tampered data") from exc


__all__ = ["aad_for", "looks_like_envelope", "open_envelope", "seal"]
