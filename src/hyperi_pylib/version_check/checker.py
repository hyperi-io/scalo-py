# Project:   hyperi-pylib
# File:      version_check/checker.py
# Purpose:   Non-blocking startup version check implementation
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Version check implementation — daemon thread, fire-and-forget."""

from __future__ import annotations

import logging
import os
import platform
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hyperi.version_check")

# Default version check API endpoint
DEFAULT_API_URL = "https://releases.hyperi.io/api/v1/check"

# HTTP timeout (seconds) — short, we don't want to delay anything
DEFAULT_TIMEOUT = 5.0


@dataclass
class VersionCheckConfig:
    """Configuration for the startup version check."""

    product: str = ""
    current_version: str = ""
    deployment: str | None = None
    api_url: str = field(default_factory=lambda: os.getenv("VERSION_CHECK_URL", DEFAULT_API_URL))
    timeout: float = DEFAULT_TIMEOUT
    disabled: bool = field(
        default_factory=lambda: os.getenv("VERSION_CHECK_DISABLED", "").lower() in ("true", "1", "yes")
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
) -> None:
    """Spawn a daemon thread to check for a newer version.

    Returns immediately. The check runs in a self-terminating daemon
    thread that logs the result and exits. Never blocks, never raises.

    Args:
        product: Product identifier (e.g., "dfe-receiver").
        version: Current version string (e.g., "1.2.0").
        deployment: Optional deployment type (e.g., "k8s", "docker").
        config: Optional configuration override.
    """
    cfg = config or VersionCheckConfig()
    cfg.product = product
    cfg.current_version = version
    if deployment is not None:
        cfg.deployment = deployment

    if cfg.disabled:
        logger.debug("version check disabled")
        return

    if not cfg.product or not cfg.current_version:
        logger.debug("version check skipped: product or version not set")
        return

    thread = threading.Thread(
        target=_run_check,
        args=(cfg,),
        name="version-check",
        daemon=True,
    )
    thread.start()


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

    instance_id = _get_or_create_instance_id()

    payload = {
        "product": config.product,
        "current_version": config.current_version,
        "instance_id": instance_id,
        "os": platform.system(),
        "arch": platform.machine(),
    }
    if config.deployment:
        payload["deployment"] = config.deployment

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
            parts.append(f"— {resp.release_url}")
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
    from datetime import datetime, timezone

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


def _get_or_create_instance_id() -> str:
    """Get or create a persistent anonymous instance ID.

    Reads from ~/.config/hyperi/instance_id. If missing, generates a
    new UUIDv4 and persists it. Falls back to ephemeral UUID on any
    filesystem error.
    """
    config_dir = Path.home() / ".config" / "hyperi"
    id_path = config_dir / "instance_id"

    # Try to read existing
    try:
        content = id_path.read_text().strip()
        if content:
            return content
    except OSError:
        pass

    # Generate new
    instance_id = str(uuid.uuid4())

    # Try to persist (best-effort)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        id_path.write_text(instance_id)
    except OSError:
        pass

    return instance_id
