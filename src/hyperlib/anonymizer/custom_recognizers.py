"""
Custom Presidio recognizers for security-critical patterns.

Adds detection for:
- Passwords (common patterns in configs/URLs)
- API Keys (various formats)
- Bearer tokens
- Secret keys
- AWS credentials

These patterns complement Presidio's built-in PII recognizers.
"""


from presidio_analyzer import Pattern, PatternRecognizer


class PasswordRecognizer(PatternRecognizer):
    """
    Detect passwords in common formats.

    Patterns:
    - password=value
    - "password": "value"
    - postgres://user:password@host
    """

    PATTERNS = [
        # Key-value formats
        Pattern(
            name="password_keyvalue",
            regex=r'\b(?:password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\'&\n]{4,})["\']?',
            score=0.6,
        ),
        # Database URLs (://user:password@host)
        Pattern(
            name="password_dburl",
            regex=r"://[^:/@]+:([^@\s]{4,})@",
            score=0.7,
        ),
        # JSON format
        Pattern(
            name="password_json",
            regex=r'["\'](?:password|passwd|pwd)["\']\s*:\s*["\']([^"\']{4,})["\']',
            score=0.6,
        ),
    ]

    CONTEXT = ["password", "passwd", "pwd", "credentials", "auth"]

    def __init__(self):
        super().__init__(
            supported_entity="PASSWORD", patterns=self.PATTERNS, context=self.CONTEXT, supported_language="en"
        )


class ApiKeyRecognizer(PatternRecognizer):
    """
    Detect API keys and tokens.

    Patterns based on detect-secrets and secrets-patterns-db (2025 patterns).

    Supported formats:
    - Generic API keys
    - AWS (AKIA...)
    - Stripe (sk_live_..., sk_test_...)
    - GitHub (ghp_..., github_pat_...)
    - OpenAI (sk-..., sk-proj-...)
    - Slack (xox[p|b|o|a]-...)
    - Bearer tokens
    - JWT tokens
    """

    PATTERNS = [
        # Generic API key patterns
        Pattern(
            name="api_key_generic",
            regex=r'\b(?:api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            score=0.7,
        ),
        # AWS Access Key ID (AKIA followed by 16 alphanumeric)
        Pattern(
            name="aws_access_key",
            regex=r"\b(AKIA[0-9A-Z]{16})\b",
            score=0.95,
        ),
        # AWS Secret Key (40 alphanumeric with context)
        Pattern(
            name="aws_secret_key",
            regex=r'\b(?:aws[_-]?secret|secret[_-]?access[_-]?key)\s*[=:]\s*["\']?([A-Za-z0-9/+=]{40})["\']?',
            score=0.9,
        ),
        # Stripe API keys (live and test)
        Pattern(
            name="stripe_key",
            regex=r"\b(sk_(?:live|test)_[0-9a-zA-Z]{24,})\b",
            score=0.95,
        ),
        # GitHub Personal Access Token (classic and fine-grained)
        Pattern(
            name="github_token_pat",
            regex=r"\b(github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59})\b",
            score=0.95,
        ),
        Pattern(
            name="github_token_ghp",
            regex=r"\b(ghp_[a-zA-Z0-9]{36,})\b",
            score=0.95,
        ),
        # Generic GitHub token pattern
        Pattern(
            name="github_generic",
            regex=r'[g|G][i|I][t|T][h|H][u|U][b|B].*[\'"][0-9a-zA-Z]{35,40}[\'"]',
            score=0.8,
        ),
        # OpenAI API keys (updated patterns for 2025)
        Pattern(
            name="openai_key_sk",
            regex=r"\b(sk-[a-zA-Z0-9]{48})\b",
            score=0.95,
        ),
        Pattern(
            name="openai_key_proj",
            regex=r"\b(sk-proj-[a-zA-Z0-9]{48,})\b",
            score=0.95,
        ),
        # Slack tokens (multiple formats)
        Pattern(
            name="slack_token",
            regex=r"\b(xox[p|b|o|a]-[0-9]{12}-[0-9]{12}-[0-9]{12}-[a-z0-9]{32})\b",
            score=0.95,
        ),
        # Bearer tokens
        Pattern(
            name="bearer_token",
            regex=r"\bbearer\s+([a-zA-Z0-9_\-\.]{20,})",
            score=0.7,
        ),
        # JWT tokens (header.payload.signature format)
        Pattern(
            name="jwt_token",
            regex=r"\b(eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]+)\b",
            score=0.85,
        ),
        # Generic secret/token patterns
        Pattern(
            name="secret_generic",
            regex=r'\b(?:secret|token)\s*[=:]\s*["\']?([a-zA-Z0-9_\-\.]{20,})["\']?',
            score=0.6,
        ),
        # SendGrid API key
        Pattern(
            name="sendgrid_key",
            regex=r"\b(SG\.[a-zA-Z0-9_\-\.]{22,}\.[a-zA-Z0-9_\-\.]{43,})\b",
            score=0.95,
        ),
        # Mailchimp API key
        Pattern(
            name="mailchimp_key",
            regex=r"\b([a-f0-9]{32}-us[0-9]{1,2})\b",
            score=0.9,
        ),
        # Twilio API key
        Pattern(
            name="twilio_key",
            regex=r"\b(SK[a-z0-9]{32})\b",
            score=0.9,
        ),
    ]

    CONTEXT = [
        "api",
        "key",
        "token",
        "secret",
        "auth",
        "bearer",
        "aws",
        "stripe",
        "github",
        "openai",
        "slack",
        "jwt",
        "sendgrid",
        "mailchimp",
        "twilio",
    ]

    def __init__(self):
        super().__init__(
            supported_entity="API_KEY", patterns=self.PATTERNS, context=self.CONTEXT, supported_language="en"
        )


class SecretKeyRecognizer(PatternRecognizer):
    """
    Detect secret keys in various formats.

    Patterns:
    - JWT secrets
    - Encryption keys
    - Private keys (BEGIN PRIVATE KEY)
    """

    PATTERNS = [
        # Generic secret patterns
        Pattern(
            name="secret_keyvalue",
            regex=r'\b(?:secret[_-]?key|jwt[_-]?secret)\s*[=:]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?',
            score=0.7,
        ),
        # Private key headers (BEGIN ... PRIVATE KEY)
        Pattern(
            name="private_key_header",
            regex=r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            score=0.95,
        ),
        # Base64-encoded secrets (long strings in quotes)
        Pattern(
            name="base64_secret",
            regex=r'["\']([A-Za-z0-9+/]{40,}={0,2})["\']',
            score=0.5,
        ),
    ]

    CONTEXT = ["secret", "key", "private", "jwt", "encryption", "cipher"]

    def __init__(self):
        super().__init__(
            supported_entity="SECRET_KEY", patterns=self.PATTERNS, context=self.CONTEXT, supported_language="en"
        )


def get_custom_recognizers() -> list[PatternRecognizer]:
    """
    Get list of all custom recognizers.

    Returns:
        List of custom recognizer instances
    """
    return [
        PasswordRecognizer(),
        ApiKeyRecognizer(),
        SecretKeyRecognizer(),
    ]
