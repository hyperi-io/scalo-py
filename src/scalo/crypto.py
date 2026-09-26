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

**Secure by default, with two consistent escape valves (config cascade).** Both
are read where every context is minted, so ONE env setting flips behaviour for
every scalo-minted client; an explicit ``verify=`` / ``allow_weak=`` argument
overrides the env per client (a consumer threads its own prefixed setting, e.g.
``DFE_TLS_VERIFY``, straight through). Both log one loud warning per process.

- ``SCALO_TLS_VERIFY=false`` drops the peer-CERTIFICATE check (self-signed
  dev/test infra) but KEEPS the cipher/version floor.
- ``SCALO_TLS_ALLOW_WEAK=true`` drops the ALGORITHM floor for a legacy peer that
  cannot do TLS 1.2+/AES-256 (min -> TLS 1.0, permissive ciphers at a lowered
  security level). The "that is all the old box offers, accept it until you
  remediate" valve - so it is never a hard blocker. HIGHSEC refuses it.

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
import os
import ssl
import warnings
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# AES-256-GCM AEAD suites (TLS 1.2 layer; the TLS 1.3 suite set is fixed by
# OpenSSL). No AES-128, no CBC.
_AES256_CIPHERS = "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"
# Hybrid post-quantum group, as OpenSSL 3.5 names it. Add SecP384r1MLKEM1024
# (the CNSA-pure hybrid) to the prefer list when it deploys.
_PQC_GROUP = "X25519MLKEM768"
_CLASSICAL_GROUPS = ["P-384", "x25519"]

# Two config-cascade escape valves, both secure-by-default and read at the point
# every context is minted (so ONE env setting flips behaviour for EVERY
# scalo-minted client - scalo.http, scalo.secrets, and any consumer that threads
# its own prefixed setting through the `verify=` / `allow_weak=` arguments):
#
#   SCALO_TLS_VERIFY=false     - drop the peer-CERTIFICATE check (self-signed
#                                dev/test infra). Keeps the cipher/version floor.
#   SCALO_TLS_ALLOW_WEAK=true  - drop the ALGORITHM floor (a legacy server that
#                                cannot do TLS 1.2+/AES-256). Accept what the peer
#                                offers - "that is all you have, we accept it
#                                until you remediate" - so an old dev box is NOT a
#                                hard blocker.
#
# Both log one loud warning per process. HIGHSEC refuses the weak-floor valve.
_TLS_VERIFY_ENV = "SCALO_TLS_VERIFY"
_TLS_ALLOW_WEAK_ENV = "SCALO_TLS_ALLOW_WEAK"

# Warnings fire once per process, keyed to avoid log spam. Tests clear the set.
_warned_once: set[str] = set()


def _warn_once(key: str, msg: str, *args: object) -> None:
    """Log a warning at most once per process, keyed to avoid spam."""
    if key in _warned_once:
        return
    _warned_once.add(key)
    logger.warning(msg, *args)


def _falsey(env: str) -> bool:
    """True if the env var is set to a falsey token (unset -> False)."""
    return os.environ.get(env, "").strip().lower() in {"false", "0", "no", "off"}


def _truthy(env: str) -> bool:
    """True if the env var is set to a truthy token (unset -> False)."""
    return os.environ.get(env, "").strip().lower() in {"true", "1", "yes", "on"}


def tls_verify_default() -> bool:
    """Effective default for cert verification from the env escape valve.

    True (verify) unless ``SCALO_TLS_VERIFY`` is falsey. The config-cascade seam
    a consumer's ENV layer sets for a whole dev/test environment; an explicit
    ``verify=`` argument still overrides it per client.
    """
    return not _falsey(_TLS_VERIFY_ENV)


def tls_allow_weak() -> bool:
    """Effective default for the legacy weak-floor escape valve.

    False (enforce the floor) unless ``SCALO_TLS_ALLOW_WEAK`` is truthy. When on,
    :func:`ssl_context` accepts legacy TLS versions/ciphers from an old peer that
    cannot meet the floor, and warns loudly. HIGHSEC ignores it.
    """
    return _truthy(_TLS_ALLOW_WEAK_ENV)


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

    min_version: str  # "1.0" (allow_weak) | "1.2" | "1.3"
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
    if not profile.warn_on_downgrade or openssl_supports_pqc():
        return
    _warn_once(
        "pqc",
        "post-quantum TLS unavailable: OpenSSL %s < 3.5 has no ML-KEM; connections use classical key exchange",
        ssl.OPENSSL_VERSION,
    )


def _warn_verify_off_once(source: str) -> None:
    _warn_once(
        "verify_off",
        "TLS certificate verification is DISABLED (%s) - the cipher/version floor "
        "still applies, but the peer certificate is NOT checked. Dev/test only, "
        "NEVER production.",
        source,
    )


def _warn_weak_floor_once() -> None:
    _warn_once(
        "weak_floor",
        "TLS crypto floor RELAXED (%s) - accepting legacy TLS versions/ciphers a "
        "modern peer would reject. INSECURE: that is all the peer offers, so we "
        "accept it until you remediate, but the peer (not scalo) is the problem.",
        _TLS_ALLOW_WEAK_ENV,
    )


def ssl_context(
    profile: CryptoProfile = CryptoProfile.PROD,
    *,
    cafile: str | None = None,
    capath: str | None = None,
    verify: bool | None = None,
    allow_weak: bool | None = None,
) -> ssl.SSLContext:
    """Mint an ``ssl.SSLContext`` with the posture baked in (the object form).

    Consumed AS-IS by httpx (``verify=ctx``), aiohttp (``ssl=ctx``), urllib3,
    asyncpg (``ssl=ctx``), aiokafka (``ssl_context=ctx``). Sets the version
    floor, the AES-256 cipher list and cert verification; the PQC group is the
    OpenSSL default (see the module docstring for why it cannot be set here).

    Two escape valves, each ``None`` -> consult the env seam (config cascade),
    else the explicit value wins:

    - ``verify``: ``False`` drops the peer-CERTIFICATE check (keeps the floor,
      ``CERT_NONE`` + loud warning) - self-signed dev/test infra. Env:
      ``SCALO_TLS_VERIFY``.
    - ``allow_weak``: ``True`` drops the ALGORITHM floor (min version -> TLS 1.0,
      permissive ciphers at a lowered security level) so a legacy peer that
      cannot meet the floor still connects, with a loud warning. Env:
      ``SCALO_TLS_ALLOW_WEAK``. HIGHSEC refuses it.
    """
    ctx = ssl.create_default_context(cafile=cafile, capath=capath)
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    if allow_weak is None:
        allow_weak = tls_allow_weak()
    if allow_weak and profile is CryptoProfile.HIGHSEC:
        _warn_once("weak_refused", "%s ignored: the HIGHSEC profile refuses to weaken its floor", _TLS_ALLOW_WEAK_ENV)
        allow_weak = False
    if allow_weak:
        # Legacy escape valve - accept what an old peer offers. Floor -> TLS 1.0,
        # widen ciphers with a lowered OpenSSL security level (admits SHA-1 /
        # small keys / CBC). INSECURE; loud warning; remediate the peer. Python
        # deprecates the TLSv1 enum member (rightly - it IS legacy); that is the
        # deliberate point here, and our own warning is the real signal, so
        # silence the redundant internal DeprecationWarning.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        # Reached only through the SCALO_TLS_ALLOW_WEAK / allow_weak=True opt-in, which HIGHSEC refuses.
        try:
            # nosemgrep: python.lang.security.audit.insecure-transport.ssl.no-set-ciphers.no-set-ciphers
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        except ssl.SSLError:  # pragma: no cover - depends on OpenSSL build
            # nosemgrep: python.lang.security.audit.insecure-transport.ssl.no-set-ciphers.no-set-ciphers
            ctx.set_ciphers("DEFAULT")
        _warn_weak_floor_once()
    else:
        ctx.minimum_version = profile.tls_floor
        # Narrows TLS 1.2 to the two ECDHE AES-256-GCM suites, a subset of the stdlib default list.
        # nosemgrep: python.lang.security.audit.insecure-transport.ssl.no-set-ciphers.no-set-ciphers
        ctx.set_ciphers(_AES256_CIPHERS)
    if verify is None:
        verify = tls_verify_default()
    if not verify:
        # Order matters: CERT_NONE while check_hostname is True raises ValueError.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _warn_verify_off_once(f"verify=False / {_TLS_VERIFY_ENV}")
    _warn_pqc_once(profile)
    return ctx


def tls_parts(
    profile: CryptoProfile = CryptoProfile.PROD,
    *,
    ca_paths: list[str] | None = None,
    verify: bool | None = None,
    allow_weak: bool | None = None,
) -> TlsParts:
    """Emit the primitives mint form for path/string-based consumers.

    ``verify`` and ``allow_weak`` mirror :func:`ssl_context` (each ``None`` ->
    the env seam, else explicit wins). ``TlsParts.verify`` is what a libpq
    ``sslmode`` / clickhouse-connect ``verify`` / librdkafka
    ``enable.ssl.certificate.verification`` should follow; when ``allow_weak`` is
    on, ``min_version`` drops to ``"1.0"`` and ``cipher_string`` widens for the
    same legacy-peer reason.
    """
    if profile.pqc is PqcMode.REQUIRE:
        curves = [_PQC_GROUP]
    elif profile.pqc is PqcMode.PREFER:
        curves = [_PQC_GROUP, *_CLASSICAL_GROUPS]
    else:
        curves = list(_CLASSICAL_GROUPS)
    if allow_weak is None:
        allow_weak = tls_allow_weak()
    if allow_weak and profile is CryptoProfile.HIGHSEC:
        allow_weak = False
    if verify is None:
        verify = tls_verify_default()
    if not verify:
        _warn_verify_off_once(f"verify=False / {_TLS_VERIFY_ENV}")
    if allow_weak:
        _warn_weak_floor_once()
        min_version, ciphers = "1.0", "DEFAULT:@SECLEVEL=0"
    else:
        min_version = "1.3" if profile.tls_floor is ssl.TLSVersion.TLSv1_3 else "1.2"
        ciphers = _AES256_CIPHERS
    return TlsParts(
        min_version=min_version,
        curves=curves,
        cipher_string=ciphers,
        ca_paths=list(ca_paths or []),
        verify=verify,
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
    "tls_allow_weak",
    "tls_parts",
    "tls_verify_default",
    "warn_if_downgraded",
]
