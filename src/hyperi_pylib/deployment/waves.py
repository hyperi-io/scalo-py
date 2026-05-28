# Project:   hyperi-pylib
# File:      deployment/waves.py
# Purpose:   Shared ArgoCD sync-wave constants (mirrors hyperi-rustlib)
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""ArgoCD sync-wave constants.

Convention for the order in which ArgoCD applies resources during a
sync. Lower waves run first. Used as the ``argocd.argoproj.io/sync-wave``
annotation on Application resources and as the default for
:class:`hyperi_pylib.deployment.ArgocdConfig.sync_wave`.

The numeric values are gaps wide enough that consumer projects can
slot custom waves (e.g. ``-15`` for "between operators and CRDs",
``-3`` for "before topics but after CRDs"). Stick to the canonical
bands where possible -- operators install order is genuinely
dependency-driven.

Mirrors ``hyperi_rustlib::deployment::waves`` for byte-level
cross-language parity. The numeric values match.
"""

from __future__ import annotations

WAVE_OPERATORS: int = -20
"""Operators that must install before everything else (Strimzi, ESO).
Their CRDs are prerequisites for later waves."""

WAVE_CRDS: int = -10
"""Custom Resource Definitions that other resources depend on.
Runs after operators (which often install their own CRDs)."""

WAVE_TOPICS: int = -5
"""Cross-application Kafka topology: KafkaTopic, KafkaUser, etc."""

WAVE_APPS: int = 0
"""DFE apps themselves. The default for Applications without an
explicit sync wave."""

WAVE_POST: int = 10
"""Post-deployment work: smoke tests, notification webhooks,
observability registrations."""

__all__ = [
    "WAVE_APPS",
    "WAVE_CRDS",
    "WAVE_OPERATORS",
    "WAVE_POST",
    "WAVE_TOPICS",
]
