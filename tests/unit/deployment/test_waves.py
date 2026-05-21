# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_waves.py
# Purpose:   Tests for ArgoCD sync-wave constants
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Tests for ArgoCD sync-wave constants."""

from __future__ import annotations

from hyperi_pylib.deployment.waves import (
    WAVE_APPS,
    WAVE_CRDS,
    WAVE_OPERATORS,
    WAVE_POST,
    WAVE_TOPICS,
)


def test_waves_are_in_canonical_order():
    assert WAVE_OPERATORS < WAVE_CRDS
    assert WAVE_CRDS < WAVE_TOPICS
    assert WAVE_TOPICS < WAVE_APPS
    assert WAVE_APPS < WAVE_POST


def test_wave_apps_is_zero():
    """WAVE_APPS=0 is the documented default for plain Application
    resources without a more specific wave."""
    assert WAVE_APPS == 0


def test_waves_have_gaps_for_custom_slots():
    """Each band leaves room for consumer-specific slots between the
    canonical waves (e.g. -15 between OPERATORS and CRDS)."""
    assert WAVE_CRDS - WAVE_OPERATORS >= 5
    assert WAVE_TOPICS - WAVE_CRDS >= 5
    assert WAVE_APPS - WAVE_TOPICS >= 5
    assert WAVE_POST - WAVE_APPS >= 5


def test_waves_match_rustlib_constants():
    """Cross-language parity: constants match hyperi_rustlib::deployment::waves."""
    assert WAVE_OPERATORS == -20
    assert WAVE_CRDS == -10
    assert WAVE_TOPICS == -5
    assert WAVE_APPS == 0
    assert WAVE_POST == 10
