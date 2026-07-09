"""Common crypto posture - the opinionated, reusable crypto stance.

Python twin of the scalo-rs ``crypto`` + ``tls`` modules. One
:class:`CryptoProfile` mints an :class:`ssl.SSLContext` (the object form that
httpx / aiohttp / urllib3 / asyncpg / aiokafka consume AS-IS) AND the
:class:`TlsParts` primitives (paths + strings for libpq / librdkafka / sqlx /
requests). A consumer SELECTS a profile and inherits the algorithm floor, the
commercial-grade fallback, and the warnings - it never hand-assembles a
cipher/curve/version policy.

**Base is commercial-floor best practice; high-security is opt-in.**

- ``PROD`` (default, drop-in): TLS 1.2 floor (1.3 preferred), hybrid ML-KEM
  where the runtime supports it, AES-256-GCM, verified certs. Deployable in
  ordinary commercial estates without locking out enterprise middleboxes or
  legacy clients.
- ``HIGHSEC``: national-security opt-in. TLS 1.3 only, post-quantum required.
- ``DEVTEST``: prod algorithms, warnings quietened.

**Honest Python limits (scalo-py and scalo-rs deliberately DIFFER).** The
version floor, the AES-256 cipher list and cert verification are fully
controlled here. The post-quantum key-exchange group is NOT: OpenSSL >= 3.5
ships ``X25519MLKEM768`` and offers it by default, but CPython's stdlib ``ssl``
exposes no API to set the group list (``set_groups`` is absent;
``set_ecdh_curve`` rejects the hybrid name). So the SSLContext form RELIES on
the OpenSSL 3.5 default for PQC and can neither force nor disable it; below 3.5
there is no PQC and no way to add it here. The primitives form still emits the
curve string, which a librdkafka/OpenSSL consumer (``ssl.curves.list``) CAN
apply - so for Kafka the primitives carry PQC even where the SSLContext cannot.
Python ``ssl`` also exposes the negotiated TLS version but NOT the kx group, so
the downgrade warning here covers version only.

The symmetric + hash choices (AES-256-GCM, SHA-384) meet CNSA 2.0; the
asymmetric choices (P-384) are the CNSA 1.0 classical suite; the hybrid ML-KEM
layer is the feasible step toward full CNSA 2.0. We do not label a P-384
baseline "CNSA 2.0".
"""

from __future__ import annotations

import enum
import logging
import ssl
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# AES-256-GCM AEAD suites (TLS 1.2 layer; the TLS 1.3 suite set is fixed by
# OpenSSL). No AES-128, no CBC.
_AES256_CIPHERS = "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"
# Hybrid post-quantum group, as OpenSSL 3.5 names it. Add SecP384r1MLKEM1024
# (the CNSA-pure hybrid) to the prefer list when it deploys.
_PQC_GROUP = "X25519MLKEM768"
_CLASSICAL_GROUPS = ["P-384", "x25519"]

# Warn only once per process about a missing PQC capability.
_pqc_warned = False


class PqcMode(enum.Enum):
    """Post-quantum key-exchange stance."""

    PREFER = "prefer"  # hybrid preferred, classical fallback (commercial default)
    REQUIRE = "require"  # hybrid only - refuse non-PQC peers (highsec)
    OFF = "off"  # classical only (explicit, logged downgrade)


class CryptoProfile(enum.Enum):
    """Operating crypto profile. ``PROD`` is the drop-in default."""

    PROD = "prod"
    HIGHSEC = "highsec"
    DEVTEST = "devtest"

    @property
    def tls_floor(self) -> ssl.TLSVersion:
        """Minimum TLS version this profile mandates."""
        if self is CryptoProfile.HIGHSEC:
            return ssl.TLSVersion.TLSv1_3
        return ssl.TLSVersion.TLSv1_2  # prod + devtest: commercial floor

    @property
    def pqc(self) -> PqcMode:
        """Post-quantum stance this profile mandates."""
        if self is CryptoProfile.HIGHSEC:
            return PqcMode.REQUIRE
        return PqcMode.PREFER

    @property
    def warn_on_downgrade(self) -> bool:
        """Whether a below-preferred negotiation should warn."""
        return self is not CryptoProfile.DEVTEST


@dataclass(frozen=True)
class TlsParts:
    """Primitive TLS-posture values for consumers that take paths/strings
    rather than an ``ssl.SSLContext`` - libpq (``sslmode``/``sslrootcert``),
    librdkafka (``ssl.ca.location``/``ssl.cipher.suites``/``ssl.curves.list``),
    ``requests``. Same posture as :func:`ssl_context`, as those fields."""

    min_version: str  # "1.2" | "1.3"
    curves: list[str]  # preference order
    cipher_string: str
    ca_paths: list[str] = field(default_factory=list)
    verify: bool = True


def openssl_supports_pqc() -> bool:
    """True if the runtime OpenSSL ships the hybrid ML-KEM groups (>= 3.5).

    CPython's ``ssl`` has no API to set the group, so we RELY on the OpenSSL
    default; this only reports whether PQC is available at all.
    """
    return ssl.OPENSSL_VERSION_INFO[:3] >= (3, 5, 0)


def _warn_pqc_once(profile: CryptoProfile) -> None:
    global _pqc_warned
    if _pqc_warned or not profile.warn_on_downgrade:
        return
    if not openssl_supports_pqc():
        _pqc_warned = True
        logger.warning(
            "post-quantum TLS unavailable: OpenSSL %s < 3.5 has no ML-KEM; connections use classical key exchange",
            ssl.OPENSSL_VERSION,
        )


def ssl_context(
    profile: CryptoProfile = CryptoProfile.PROD,
    *,
    cafile: str | None = None,
    capath: str | None = None,
) -> ssl.SSLContext:
    """Mint an ``ssl.SSLContext`` with the posture baked in (the object form).

    Consumed AS-IS by httpx (``verify=ctx``), aiohttp (``ssl=ctx``), urllib3,
    asyncpg (``ssl=ctx``), aiokafka (``ssl_context=ctx``). Sets the version
    floor, the AES-256 cipher list and cert verification; the PQC group is the
    OpenSSL default (see the module docstring for why it cannot be set here).
    """
    ctx = ssl.create_default_context(cafile=cafile, capath=capath)
    ctx.minimum_version = profile.tls_floor
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_ciphers(_AES256_CIPHERS)
    _warn_pqc_once(profile)
    return ctx


def tls_parts(
    profile: CryptoProfile = CryptoProfile.PROD,
    *,
    ca_paths: list[str] | None = None,
) -> TlsParts:
    """Emit the primitives mint form for path/string-based consumers."""
    if profile.pqc is PqcMode.REQUIRE:
        curves = [_PQC_GROUP]
    elif profile.pqc is PqcMode.PREFER:
        curves = [_PQC_GROUP, *_CLASSICAL_GROUPS]
    else:
        curves = list(_CLASSICAL_GROUPS)
    return TlsParts(
        min_version="1.3" if profile.tls_floor is ssl.TLSVersion.TLSv1_3 else "1.2",
        curves=curves,
        cipher_string=_AES256_CIPHERS,
        ca_paths=list(ca_paths or []),
        verify=True,
    )


def warn_if_downgraded(profile: CryptoProfile, negotiated_version: ssl.TLSVersion | None, peer: str) -> None:
    """Warn if a completed handshake negotiated below the preferred TLS version.

    Python ``ssl`` exposes ``SSLSocket.version()`` but not the negotiated kx
    group, so (unlike scalo-rs) only the version downgrade is observable here.
    """
    if not profile.warn_on_downgrade:
        return
    if negotiated_version == ssl.TLSVersion.TLSv1_2:
        logger.warning("TLS negotiated 1.2 to %s, below the preferred 1.3 (commercial floor)", peer)


# --- Config-emitter mint form ------------------------------------------------
# The same posture, emitted as infra/IaC config for the layers that are not a
# code library at all - Envoy, Terraform, a cloud load balancer. scalo is the
# single source of the decision across code AND infra.


def emit_envoy_client_traffic_policy(profile: CryptoProfile = CryptoProfile.PROD) -> str:
    """Emit the Envoy Gateway ClientTrafficPolicy ``tls`` block for a profile."""
    p = tls_parts(profile)
    curves = "\n".join(f"      - {g}" for g in p.curves)
    ciphers = "\n".join(f"      - {c}" for c in p.cipher_string.split(":"))
    return f'tls:\n  minVersion: "{p.min_version}"\n  maxVersion: "1.3"\n  ecdhCurves:\n{curves}\n  ciphers:\n{ciphers}'


def emit_terraform_tfvars(profile: CryptoProfile = CryptoProfile.PROD) -> str:
    """Emit terraform.tfvars for a TLS module from a profile."""
    p = tls_parts(profile)
    curves = ", ".join(f'"{g}"' for g in p.curves)
    return f'tls_min_version = "{p.min_version}"\ntls_ecdh_curves = [{curves}]\ntls_ciphers     = "{p.cipher_string}"\n'


def emit_aws_lb_ssl_policy(profile: CryptoProfile = CryptoProfile.PROD) -> tuple[str, list[str]]:
    """Pick the closest AWS ALB/NLB named ``ssl_policy`` + the deltas it cannot
    express. Named bundles are not a-la-carte, so the deltas are RECORDED, not
    hidden (the managed-service caveat, machine-readable)."""
    p = tls_parts(profile)
    name = "ELBSecurityPolicy-TLS13-1-3-2021-06" if p.min_version == "1.3" else "ELBSecurityPolicy-TLS13-1-2-2021-06"
    deltas = [
        "also admits AES-128-GCM (posture prefers AES-256-GCM only)",
        "also admits P-256 ECDHE (posture prefers P-384 + hybrid ML-KEM)",
        "no hybrid ML-KEM at the AWS edge yet - classical only on this hop",
    ]
    return name, deltas


__all__ = [
    "CryptoProfile",
    "PqcMode",
    "TlsParts",
    "emit_aws_lb_ssl_policy",
    "emit_envoy_client_traffic_policy",
    "emit_terraform_tfvars",
    "openssl_supports_pqc",
    "ssl_context",
    "tls_parts",
    "warn_if_downgraded",
]
