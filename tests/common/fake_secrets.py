#  Project:   hyperi-pylib
#  File:      tests/common/fake_secrets.py
#  Purpose:   Runtime-constructed fake secret fixtures for scrubber tests
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
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
test assertions stay stable. Bodies are low-entropy (all-X, repeated
``FAKE``) so even the runtime output isn't realistic enough to trip a
secondary content-based scanner.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# AWS -- long-lived + session
# ---------------------------------------------------------------------------


def aws_access_key() -> str:
    """AWS access key id (`AKIA` + 16 uppercase alphanumeric)."""
    # Source never contains the literal "AKIA".
    prefix = "A" + "K" + "I" + "A"
    return prefix + "X" * 16


def aws_session_token() -> str:
    """AWS session token id (`ASIA` + 16 uppercase alphanumeric)."""
    prefix = "A" + "S" + "I" + "A"
    return prefix + "X" * 16


# ---------------------------------------------------------------------------
# GitHub -- classic PAT, fine-grained PAT, OAuth, server, user
# ---------------------------------------------------------------------------


def github_classic_pat() -> str:
    """Classic GitHub PAT (`ghp_` + 36 alphanumeric)."""
    prefix = "gh" + "p" + "_"
    return prefix + "X" * 36


def github_fine_grained_pat() -> str:
    """Fine-grained GitHub PAT (`github_pat_` + 82+ alphanumeric/underscores)."""
    prefix = "github" + "_pat_"
    return prefix + "X" * 82


def github_oauth() -> str:
    """GitHub OAuth token (`gho_` + 36 alphanumeric)."""
    prefix = "gh" + "o" + "_"
    return prefix + "X" * 36


def github_server_token() -> str:
    """GitHub server-to-server token (`ghs_` + 36 alphanumeric)."""
    prefix = "gh" + "s" + "_"
    return prefix + "X" * 36


def github_user_token() -> str:
    """GitHub user-to-server token (`ghu_` + 36 alphanumeric)."""
    prefix = "gh" + "u" + "_"
    return prefix + "X" * 36


def github_refresh_token() -> str:
    """GitHub refresh token (`ghr_` + 36 alphanumeric)."""
    prefix = "gh" + "r" + "_"
    return prefix + "X" * 36


# ---------------------------------------------------------------------------
# GitLab
# ---------------------------------------------------------------------------


def gitlab_pat() -> str:
    """GitLab personal access token (`glpat-` + 20 alphanumeric)."""
    prefix = "gl" + "pat" + "-"
    return prefix + "X" * 20


# ---------------------------------------------------------------------------
# Stripe -- the family that triggers GitHub Push Protection most often
# ---------------------------------------------------------------------------


def stripe_live_key() -> str:
    """Stripe live secret key (`sk_live_` + 24+ alphanumeric)."""
    # No literal "sk_live_" anywhere in source.
    prefix = "sk" + "_" + "live" + "_"
    return prefix + "X" * 30


def stripe_test_key() -> str:
    """Stripe test secret key (`sk_test_` + 24+ alphanumeric)."""
    prefix = "sk" + "_" + "test" + "_"
    return prefix + "X" * 30


def stripe_live_restricted_key() -> str:
    """Stripe live restricted key (`rk_live_` + 24+ alphanumeric)."""
    prefix = "rk" + "_" + "live" + "_"
    return prefix + "X" * 30


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def openai_key() -> str:
    """OpenAI API key (`sk-` + 20+ alphanumeric/underscore/hyphen)."""
    prefix = "sk" + "-"
    return prefix + "X" * 40


def openai_proj_key() -> str:
    """OpenAI project key (`sk-proj-` + 20+ alphanumeric/underscore/hyphen)."""
    prefix = "sk" + "-" + "proj" + "-"
    return prefix + "X" * 40


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


def slack_bot_token() -> str:
    """Slack bot token (`xoxb-` + 10-48 alphanumeric/hyphen)."""
    prefix = "xo" + "xb" + "-"
    return prefix + "X" * 30


def slack_user_token() -> str:
    """Slack user token (`xoxp-` + 10-48 alphanumeric/hyphen)."""
    prefix = "xo" + "xp" + "-"
    return prefix + "X" * 30


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
# Misc third-party -- extend on demand
# ---------------------------------------------------------------------------


def twilio_api_key() -> str:
    """Twilio API key (`SK` + 32 hex)."""
    prefix = "S" + "K"
    return prefix + "0" * 32


def sendgrid_api_key() -> str:
    """SendGrid API key (`SG.` + 22 + `.` + 43, all alphanumeric/_-)."""
    prefix = "S" + "G" + "."
    seg1 = "X" * 22
    seg2 = "X" * 43
    return f"{prefix}{seg1}.{seg2}"
