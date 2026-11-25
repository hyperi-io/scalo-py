#  Project:   scalo
#  File:      tests/common/fake_secrets.py
#  Purpose:   Runtime-constructed fake secret fixtures for scrubber tests
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Build fake but regex-matching secret strings at runtime.

GitHub Push Protection, gitleaks, AWS secret scanning, and other
source-scanning tools detect credentials by pattern-matching the
*source bytes* of files. They cannot see strings produced by
runtime concatenation -- they only see the source expression.

Every helper here returns a string that:

- Matches the corresponding gitleaks / detect-secrets regex (so the
  L1 scrubber's pattern still fires when the fixture flows through
  it),
- Is constructed by concatenating parts that, individually, never
  form the full pattern as a contiguous byte sequence in source.
  No literal `sk_live_<32 chars>`, no literal `AKIA<16 chars>`,
  no literal `ghp_<36 chars>` appears anywhere on disk.

The trick: scanners read files; they don't evaluate Python. So
``"sk" + "_live_"`` in source looks like ``"sk" + "_live_"`` (no
match), but produces ``"sk_live_"`` at runtime (which the scrubber's
regex catches normally).

All helpers are deterministic -- same call yields the same string so
test assertions stay stable. Bodies are seeded pseudo-random, because the
L1 scrubber applies each gitleaks rule's entropy threshold and an all-X body
(``AKIAXXXXXXXXXXXXXXXX``) is a gitleaks false positive, not a secret.
"""

import random
import string

_ALNUM = string.ascii_letters + string.digits
# The AWS access-key rule takes its 16 body characters from base32.
_BASE32 = string.ascii_uppercase + "234567"


def _body(length: int, alphabet: str = _ALNUM) -> str:
    """Return ``length`` seeded pseudo-random characters of ``alphabet``, the same on every call."""
    rng = random.Random(f"scalo-fake-secret:{length}:{alphabet}")
    return "".join(rng.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# AWS -- long-lived + session
# ---------------------------------------------------------------------------


def aws_access_key() -> str:
    """AWS access key id (`AKIA` + 16 uppercase alphanumeric)."""
    # Source never contains the literal "AKIA".
    prefix = "A" + "K" + "I" + "A"
    return prefix + _body(16, _BASE32)


def aws_session_token() -> str:
    """AWS session token id (`ASIA` + 16 uppercase alphanumeric)."""
    prefix = "A" + "S" + "I" + "A"
    return prefix + _body(16, _BASE32)


# ---------------------------------------------------------------------------
# GitHub -- classic PAT, fine-grained PAT, OAuth, server, user
# ---------------------------------------------------------------------------


def github_classic_pat() -> str:
    """Classic GitHub PAT (`ghp_` + 36 alphanumeric)."""
    prefix = "gh" + "p" + "_"
    return prefix + _body(36)


def github_fine_grained_pat() -> str:
    """Fine-grained GitHub PAT (`github_pat_` + 82+ alphanumeric/underscores)."""
    prefix = "github" + "_pat_"
    return prefix + _body(82)


def github_oauth() -> str:
    """GitHub OAuth token (`gho_` + 36 alphanumeric)."""
    prefix = "gh" + "o" + "_"
    return prefix + _body(36)


def github_server_token() -> str:
    """GitHub server-to-server token (`ghs_` + 36 alphanumeric)."""
    prefix = "gh" + "s" + "_"
    return prefix + _body(36)


def github_user_token() -> str:
    """GitHub user-to-server token (`ghu_` + 36 alphanumeric)."""
    prefix = "gh" + "u" + "_"
    return prefix + _body(36)


def github_refresh_token() -> str:
    """GitHub refresh token (`ghr_` + 36 alphanumeric)."""
    prefix = "gh" + "r" + "_"
    return prefix + _body(36)


# ---------------------------------------------------------------------------
# GitLab
# ---------------------------------------------------------------------------


def gitlab_pat() -> str:
    """GitLab personal access token (`glpat-` + 20 alphanumeric)."""
    prefix = "gl" + "pat" + "-"
    return prefix + _body(20)


# ---------------------------------------------------------------------------
# Stripe -- the family that triggers GitHub Push Protection most often
# ---------------------------------------------------------------------------


def stripe_live_key() -> str:
    """Stripe live secret key (`sk_live_` + 24+ alphanumeric)."""
    # No literal "sk_live_" anywhere in source.
    prefix = "sk" + "_" + "live" + "_"
    return prefix + _body(30)


def stripe_test_key() -> str:
    """Stripe test secret key (`sk_test_` + 24+ alphanumeric)."""
    prefix = "sk" + "_" + "test" + "_"
    return prefix + _body(30)


def stripe_live_restricted_key() -> str:
    """Stripe live restricted key (`rk_live_` + 24+ alphanumeric)."""
    prefix = "rk" + "_" + "live" + "_"
    return prefix + _body(30)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def openai_key() -> str:
    """OpenAI API key (`sk-` + 20+ alphanumeric/underscore/hyphen)."""
    prefix = "sk" + "-"
    return prefix + _body(40, _ALNUM + "_-")


def openai_proj_key() -> str:
    """OpenAI project key (`sk-proj-` + 20+ alphanumeric/underscore/hyphen)."""
    prefix = "sk" + "-" + "proj" + "-"
    return prefix + _body(40, _ALNUM + "_-")


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


def slack_bot_token() -> str:
    """Slack bot token (`xoxb-` + 10-48 alphanumeric/hyphen)."""
    prefix = "xo" + "xb" + "-"
    return prefix + _body(11, string.digits) + "-" + _body(12, string.digits) + "-" + _body(24)


def slack_user_token() -> str:
    """Slack user token (`xoxp-` + 10-48 alphanumeric/hyphen)."""
    prefix = "xo" + "xp" + "-"
    return prefix + _body(11, string.digits) + "-" + _body(12, string.digits) + "-" + _body(24)


# ---------------------------------------------------------------------------
# JWT -- three base64url segments
# ---------------------------------------------------------------------------


def jwt() -> str:
    """A regex-matching JWT (header.payload.signature, base64url).

    Body uses base64url-alphabet characters in varied positions so the
    detect-secrets entropy check fires. Built from parts so the source
    bytes don't form a contiguous JWT-shaped literal.
    """
    # Header / payload mix base64url alphabet to clear entropy thresholds
    # without containing a plausibly-real claim set.
    header = "ey" + "J" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    payload = "ey" + "J" + "zdWIiOiJ0ZXN0LXVzZXItMSIsImlhdCI6MTcwMDAwMDAwMH0"
    signature = "Q" + "WJjRGVmR2hpSmtsTW5vUHFyU3R1Vnd4WXowMTIzNDU2Nzg5"
    return header + "." + payload + "." + signature


# ---------------------------------------------------------------------------
# Private key -- PEM block
# ---------------------------------------------------------------------------


def private_key_block(body_chars: int = 256) -> str:
    """A PEM-shaped private key block.

    The gitleaks ``private-key`` regex requires at least 64 chars
    between BEGIN and END markers. ``body_chars`` controls the body
    length so callers can test long-block edge cases.
    """
    begin = "-----" + "BEGIN" + " RSA PRIVATE KEY-----"
    body = "X" * body_chars
    end = "-----" + "END" + " RSA PRIVATE KEY-----"
    return f"{begin}\n{body}\n{end}"


# ---------------------------------------------------------------------------
# Generic opaque secret -- for key-name / repr redaction tests that don't
# need a provider pattern, just a sentinel that must not leak.
# ---------------------------------------------------------------------------


def opaque_secret(label: str = "value") -> str:
    """A unique, non-provider-shaped sentinel built at runtime.

    No literal secret on disk; ``label`` keeps assertion failures readable.
    """
    return "FAKE" + "-" + label + "-" + "X" * 12


# ---------------------------------------------------------------------------
# Misc third-party -- extend on demand
# ---------------------------------------------------------------------------


def twilio_api_key() -> str:
    """Twilio API key (`SK` + 32 hex)."""
    prefix = "S" + "K"
    return prefix + _body(32, string.hexdigits[:16])


def sendgrid_api_key() -> str:
    """SendGrid API key (`SG.` + 22 + `.` + 43, all alphanumeric/_-)."""
    prefix = "S" + "G" + "."
    seg1 = _body(22, _ALNUM + "_-")
    seg2 = _body(43, _ALNUM + "_-")
    return f"{prefix}{seg1}.{seg2}"
