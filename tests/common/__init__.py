"""Shared test helpers.

Importable from any test module via ``from common.X import ...``
(``tests/`` is on ``pythonpath`` per pyproject.toml).

**Test-fixture hygiene convention** -- `fake_secrets` + `fake_pii`:

GitHub Push Protection, gitleaks, AWS secret scanning, and similar
source-byte scanners detect credentials by pattern-matching the bytes
of files in the repository. The two modules :mod:`fake_secrets` and
:mod:`fake_pii` build regex-matching but clearly-synthetic fixtures
at **runtime** by concatenating parts that never form the full
pattern as a contiguous byte sequence in source.

Use these factories instead of inline literals whenever a test needs
a string that:

- Matches a credential / PII regex (so the scrubber's pattern fires), OR
- Could conceivably be flagged by a future content scanner.

Concrete examples -- DO use factories for: AWS keys, GitHub tokens,
Stripe keys, JWTs, private-key blocks, credit-card numbers, IBANs,
phone numbers in international form, and AU national IDs (ABN /
ACN / TFN / Medicare).

OK to keep as inline literals: ``alice@example.com`` (RFC-2606
placeholder domain), ``hunter2`` (well-known fake password), and
similar deliberately-symbolic test strings that scanners do not
fingerprint as credentials.

See spec ``2026-05-13-log-scrub-spec.md`` for the underlying scrubber
contract.
"""
