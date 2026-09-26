# Project:   scalo
# File:      version_check/checker.py
# Purpose:   Non-blocking startup version check implementation
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Version check implementation -- daemon thread, fire-and-forget."""

from __future__ import annotations

import hashlib
import logging
import platform
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path

logger = logging.getLogger("scalo.version_check")

# HTTP timeout (seconds) -- short, we don't want to delay anything
DEFAULT_TIMEOUT = 5.0


def _setting(key: str, default):
    """Read ``version_check.<key>`` from the config cascade (None-safe)."""
    try:
        from scalo.config import settings

        return settings.get(f"version_check.{key}", default)
    except Exception:
        return default


@dataclass
class VersionCheckConfig:
    """Configuration for the startup version check.

    The check is OPT-OUT: wiring it into an app is the opt-in, so
    ``enabled`` defaults true and the check stays inert until an
    ``api_url`` is supplied (by the app via :meth:`from_cascade_or`, or by
    config). An explicit ``version_check.enabled: false`` in any config
    layer always wins.
    """

    product: str = ""
    current_version: str = ""
    deployment: str | None = None
    api_url: str | None = field(default_factory=lambda: _setting("api_url", None))
    timeout: float = field(default_factory=lambda: float(_setting("timeout", DEFAULT_TIMEOUT)))
    enabled: bool = field(default_factory=lambda: bool(_setting("enabled", True)))
    # Include the platform-derived instance id so the same install reports as
    # the same install across restarts; version_check.send_instance_id: false
    # yields a payload with no identifier at all.
    send_instance_id: bool = field(default_factory=lambda: bool(_setting("send_instance_id", True)))
    # Explicit id, sent verbatim when set -- overrides the derived one.
    instance_id: str = field(default_factory=lambda: str(_setting("instance_id", "") or ""))

    @classmethod
    def from_cascade_or(
        cls,
        *,
        enabled: bool = True,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        send_instance_id: bool = True,
        instance_id: str = "",
    ) -> VersionCheckConfig:
        """Build from the cascade, falling back to the caller's defaults.

        Every ``version_check`` key the cascade sets wins -- an explicit
        ``enabled: false`` included -- and a key it leaves unset falls to
        the given default instead of this class's own. The seam an app
        uses to supply its endpoint default while any config layer (file
        or env) can still turn the check off. Mirrors scalo-rs
        ``VersionCheckConfig::from_cascade_or``.
        """
        return cls(
            api_url=_setting("api_url", api_url),
            timeout=float(_setting("timeout", timeout)),
            enabled=bool(_setting("enabled", enabled)),
            send_instance_id=bool(_setting("send_instance_id", send_instance_id)),
            instance_id=str(_setting("instance_id", instance_id) or ""),
        )


@dataclass
class VersionCheckResponse:
    """Response from the version check API."""

    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    published_at: str | None = None
    message: str | None = None


def check_on_startup(
    product: str,
    version: str,
    *,
    deployment: str | None = None,
    config: VersionCheckConfig | None = None,
) -> threading.Thread | None:
    """Spawn a daemon thread to check for a newer version.

    Returns immediately. The check runs in a self-terminating daemon
    thread that logs the result and exits. Never blocks, never raises.

    Args:
        product: Product identifier (e.g., "my-service").
        version: Current version string (e.g., "1.2.0").
        deployment: Optional deployment type (e.g., "k8s", "docker").
        config: Optional configuration override.

    Returns:
        The spawned :class:`threading.Thread` if a check was kicked
        off, or ``None`` when the check was skipped (disabled, missing
        product, missing version). Production callers can discard the
        return value; tests use it to ``.join()`` deterministically
        instead of racing on ``time.sleep``.
    """
    cfg = config or VersionCheckConfig()
    cfg.product = product
    cfg.current_version = version
    if deployment is not None:
        cfg.deployment = deployment

    if not cfg.enabled:
        logger.debug("version check disabled (version_check.enabled is false)")
        return None

    if not cfg.api_url:
        logger.debug("version check skipped: no version_check.api_url configured")
        return None

    if not cfg.product or not cfg.current_version:
        logger.debug("version check skipped: product or version not set")
        return None

    thread = threading.Thread(
        target=_run_check,
        args=(cfg,),
        name="version-check",
        daemon=True,
    )
    thread.start()
    return thread


def _run_check(config: VersionCheckConfig) -> None:
    """Execute the version check (runs in daemon thread)."""
    try:
        resp = _do_http_check(config)
        _log_response(config, resp)
    except Exception as exc:
        logger.warning("version check failed (non-fatal): %s", exc)


def _do_http_check(config: VersionCheckConfig) -> VersionCheckResponse:
    """Perform the HTTP POST to the version check API."""
    try:
        import httpx
    except ImportError:
        logger.debug("httpx not installed, version check skipped")
        return VersionCheckResponse()

    # deployment is never sent: operators embed sensitive names in free-form
    # deployment strings. The instance id is platform-derived and one-way
    # (see resolve_instance_id), and version_check.send_instance_id: false
    # strips it entirely.
    payload = {
        "product": config.product,
        "current_version": config.current_version,
        "os": platform.system(),
        "arch": platform.machine(),
    }
    if config.send_instance_id:
        payload["instance_id"] = resolve_instance_id(config)

    resp = httpx.post(
        config.api_url,
        json=payload,
        timeout=config.timeout,
    )
    resp.raise_for_status()

    data = resp.json()
    return VersionCheckResponse(
        latest_version=data.get("latest_version"),
        update_available=data.get("update_available", False),
        release_url=data.get("release_url"),
        published_at=data.get("published_at"),
        message=data.get("message"),
    )


def _log_response(config: VersionCheckConfig, resp: VersionCheckResponse) -> None:
    """Log the version check result."""
    if resp.update_available and resp.latest_version:
        age = _format_age(resp.published_at) if resp.published_at else ""
        parts = [
            f"new version available: {config.product}",
            f"(current: {config.current_version}, latest: {resp.latest_version})",
        ]
        if age:
            parts.append(f"[{age}]")
        if resp.release_url:
            parts.append(f"-- {resp.release_url}")
        logger.info(" ".join(parts))
    else:
        logger.debug(
            "%s %s is the latest version",
            config.product,
            config.current_version,
        )

    if resp.message:
        logger.info("[%s] %s", config.product, resp.message)


def _format_age(published_at: str) -> str:
    """Format an ISO 8601 timestamp into a human-readable age string."""
    from datetime import datetime

    try:
        # Try ISO 8601 with timezone
        if published_at.endswith("Z"):
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(published_at)

        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        now = datetime.now(UTC)
        delta = now - dt
        days = delta.days

        if days < 0:
            return "just released"
        if days == 0:
            return "released today"
        if days == 1:
            return "released 1 day ago"
        if days < 30:
            return f"released {days} days ago"

        months = days // 30
        if months == 1:
            return "released 1 month ago"
        if months < 12:
            return f"released {months} months ago"

        years = months // 12
        remaining = months % 12
        if remaining == 0:
            return f"released {years}y ago"
        return f"released {years}y {remaining}m ago"
    except (ValueError, TypeError):
        return ""


# UUIDv5 namespace for platform-derived instance ids:
# uuid5(NAMESPACE_DNS, "scalo.hyperi.io"). Shared with scalo-rs so both
# chassis derive the SAME id from the same platform material.
INSTANCE_ID_NS = uuid.UUID("10ada713-52f0-5b77-aab7-7792712f92a0")

_K8S_SA = Path("/var/run/secrets/kubernetes.io/serviceaccount")


def resolve_instance_id(config: VersionCheckConfig) -> str:
    """Stable per-install instance id, derived from what the app runs on.

    Resolution order, first hit wins:

    1. ``version_check.instance_id`` from the config, verbatim.
    2. Kubernetes: UUIDv5 over the serviceaccount cluster CA cert plus the
       pod namespace -- readable in-pod with no API permissions, unique per
       cluster, stable across every pod restart and reschedule.
    3. ``/etc/machine-id`` (UUIDv5, app-scoped per machine-id(5) -- the raw
       id never leaves the host). Skipped inside a container, where a
       machine-id baked into the image would make every install report as
       the same one.
    4. A UUID persisted at ``~/.config/scalo/instance_id`` (dev machines).
    5. An ephemeral UUID for this run alone.
    """
    if config.instance_id:
        return config.instance_id
    return _k8s_instance_id() or _machine_instance_id() or _persisted_instance_id() or str(uuid.uuid4())


def _k8s_instance_id() -> str | None:
    try:
        ca = (_K8S_SA / "ca.crt").read_bytes()
        ns = (_K8S_SA / "namespace").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    material = b"k8s:" + ca + b":" + ns.encode("utf-8")
    return str(_uuid5_bytes(material))


def _uuid5_bytes(material: bytes) -> uuid.UUID:
    """``uuid.uuid5`` over raw bytes -- byte-identical to scalo-rs, which
    hashes the material without a text round-trip."""
    # UUIDv5 is SHA-1 by definition (RFC 9562) -- an id derivation, not a signature, and it must match scalo-rs.
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    digest = hashlib.sha1(INSTANCE_ID_NS.bytes + material).digest()  # noqa: S324
    return uuid.UUID(bytes=digest[:16], version=5)


def _machine_instance_id() -> str | None:
    if _in_container():
        return None
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            machine_id = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if len(machine_id) >= 32 and set(machine_id) != {"0"}:
            return str(uuid.uuid5(INSTANCE_ID_NS, f"machine:{machine_id}"))
    return None


def _in_container() -> bool:
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8")
    except OSError:
        return False
    return any(marker in cgroup for marker in ("docker", "containerd", "kubepods"))


def _persisted_instance_id() -> str | None:
    directory = Path.home() / ".config" / "scalo"
    path = directory / "instance_id"
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    new_id = str(uuid.uuid4())
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(new_id, encoding="utf-8", newline="\n")
    except OSError:
        return None
    return new_id
