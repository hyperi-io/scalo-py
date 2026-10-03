# Project:   scalo
# File:      src/scalo/kafka/contract.py
# Purpose:   Opt-in STRICT Kafka credential profile - blessed provider set +
#            never-weakened auth, layered on top of the vanilla provider facts.
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Opt-in STRICT Kafka credential profile.

This is a SEPARATE, OPT-IN module. The vanilla provider facts in
``scalo.kafka.providers`` (``derive``, ``validate``, ``KnownProvider``, ...)
work without ever importing this module - reach for ``contract`` only when
you want an opinionated STRICT policy on top:

- a blessed allow-list of providers (``DEFAULT_ALLOWED`` - the quarantined
  ``msk_iam`` is deliberately excluded), and
- a guard against a hand-set config that WEAKENS a provider's strongest auth
  (e.g. someone hand-setting PLAIN on a provider that supports SCRAM).

This encodes an opinionated credential contract, framed generically so any
consumer can opt in rather than reinvent it: any security-conscious operator
wants "strongest available, never downgraded, only these providers".
``scalo.kafka.providers`` carries no policy; this module is where policy
lives, by deliberate choice.
"""

from __future__ import annotations

from .providers import KafkaProviderError, derive

# The blessed provider set - the username+password / no-auth contract.
# msk_iam is deliberately EXCLUDED (quarantined): IAM is a different
# credential shape, not part of this strict user+password profile.
DEFAULT_ALLOWED: frozenset[str] = frozenset(
    {
        "strimzi",
        "redpanda",
        "msk",
        "redpanda-cloud",
        "confluent-cloud",
        "plaintext",
    }
)


def require(provider: str, *, allowed: frozenset[str] = DEFAULT_ALLOWED) -> tuple[str, str]:
    """Return ``(security_protocol, sasl_mechanism)`` for a BLESSED provider only.

    Refuses (raises ``KafkaProviderError``) any provider not in ``allowed`` -
    including the quarantined ``msk_iam`` under the default allow-list, and
    any provider unknown to ``derive()``.
    """
    if provider not in allowed:
        raise KafkaProviderError(f"kafka provider {provider!r} is not in the blessed set {sorted(allowed)}")
    return derive(provider)


def assert_not_weakened(provider: str, security_protocol: str, sasl_mechanism: str) -> None:
    """Refuse a hand-set config weaker than the provider's strongest auth.

    Re-derives ``provider``'s canonical ``(security_protocol, sasl_mechanism)``
    and raises ``KafkaProviderError`` if the passed-in pair differs - catches a
    hand-set downgrade (e.g. PLAIN on a provider that supports SCRAM, or
    plaintext substituted for SASL_SSL).
    """
    expected = derive(provider)
    got = (security_protocol, sasl_mechanism)
    if got != expected:
        raise KafkaProviderError(
            f"kafka provider {provider!r} strongest auth is {expected!r}; got {got!r} - never weaken a provider's auth"
        )
