# Scrubbing

What the logger redacts and how. `setup()` builds one scrubber and every sink shares it: the message, each field and the traceback pass through it before anything is written, at each level `ScrubConfig.log_levels` leaves on. See [logging.md](logging.md) for the sinks and formats around it.

`LogLevelsConfig.trace` is false by default, so a TRACE record's message and traceback reach the sinks unscrubbed, and a field with a credential name is the one thing still masked. To scrub TRACE, call `setup(scrub_config=ScrubConfig(log_levels=LogLevelsConfig(trace=True)))`. `ScrubConfig(enabled=False)` turns the scrubber off, and `ScrubConfig(observe_only=True)` counts matches without redacting them.

`setup()` reads the same settings from `logging.scrub.*` when no scrubber or `scrub_config` argument is given (see [Excluding one L1 rule](#excluding-one-l1-rule)). `ServiceApp` reads that section from the config it loaded, a `--config` file and the app's env prefix included, and passes it as `scrub_config`.

## Scrub architecture

Three layers fire in order on every message at a scrubbed level. They are built from the `scalo.logger.scrub` package, configured with `ScrubConfig` and composed by `build_scrubber()`:

| Layer | Source | Detects |
|-------|--------|---------|
| L1 secrets | `src/scalo/logger/scrub/secrets.py` + `gitleaks.toml` rules | AWS keys, GitHub tokens, JWTs, private keys, third-party API keys |
| L2 fields | `src/scalo/logger/scrub/field_names.py` (regex on key names) | `password=...`, `"token":"..."`, `CARGO_REGISTRY_TOKEN=...`, `token = "..."`, bearer tokens, DB URLs, refused header values |
| L3 PII | `src/scalo/logger/scrub/pii/` validators (Luhn, mod-97, libphonenumber, structural regex) | Credit cards, IBANs, emails (literal and percent-encoded), phones, AU ABN, ACN, TFN and Medicare |

There is no NLP or NER layer. The L1 rule set is `src/scalo/data/gitleaks.toml`, a byte-for-byte copy of hyperi-ai's gitleaks TOML, parsed by `src/scalo/logger/scrub/gitleaks_toml.py`. L1 replaces a rule's secret and nothing more, so the key name and quoting around it survive and a JSON line still parses: the rule's `secretGroup` when it has one, else its first non-empty capture group when only a terminator follows it in the match, else the whole match.

`build_scrubber()` compiles no rule. A rule's regex compiles on the first scrub with text that hits one of its keywords (a rule with no keywords, on the first scrub), so a regex that does not compile warns, and joins `skipped_rules` and the `log_scrub_skipped_rules_total` gauge, at that first scrub, not at build. `GitleaksTomlScrubber.compile_all()` (in `gitleaks_toml.py`) compiles them all at once.

`setup()` picks the scrubber through `src/scalo/logger/scrub_resolver.py`: an explicit `scrubber=`, then `scrub_config=`, then the legacy `mask_sensitive` / `masking_level` arguments, then `logging.scrub`, then the defaults. The resolver reads `logging.scrub.*` and the legacy `logging.mask_sensitive_data` from a config dict. `setup()` hands it `get_logging_config()`, which carries `logging.scrub` when set and not `logging.mask_sensitive_data`, so that legacy key does nothing through `setup()`.

```python
from scalo.logger import setup
from scalo.logger.scrub import ScrubConfig, build_scrubber

scrubber = build_scrubber(ScrubConfig(
    hash_redaction=True,    # [EMAIL_a3f5b2] lets you correlate without leaking
))
setup(scrubber=scrubber)
```

## Excluding one L1 rule

L1 runs every gitleaks rule over log prose, where a broad rule can match ordinary text. `generic-api-key` is the one known to: it turns `Renamed config keys in .hyperi-ci.yaml: publish.container -> ...` into `Renamed config keys in .hyperi-ci.yaml: [GENERIC_API_KEY_REDACTED] -> ...`. Drop the offending rule by id and keep the rest of the set running:

```yaml
logging:
  scrub:
    secrets:
      exclude_rules: [generic-api-key]   # a comma-separated string also works, for env vars
```

A `ServiceApp` reads that section from its loaded config. A direct `setup()` call reads it from the process-wide settings, or takes the same rule as an argument:

```python
from scalo.logger import setup
from scalo.logger.scrub import ScrubConfig, SecretsConfig

setup(scrub_config=ScrubConfig(secrets=SecretsConfig(exclude_rules=frozenset({"generic-api-key"}))))
```

The specific rules still catch the credential formats, so a GitHub token is still `[GITHUB_PAT_REDACTED]` with `generic-api-key` excluded. L2 still masks by key name, so `CARGO_REGISTRY_TOKEN=...` and `token = "..."` stay masked. Do not reach for `patterns: minimal` to silence a false positive: it keeps the rules in `_MINIMAL_RULES` (`src/scalo/logger/scrub/secrets.py`) and no others, and drops cloudflare, npm and pypi detection with it.

An id the rule set does not hold raises a `RuntimeWarning` at startup and excludes nothing. `exclude_rules` applies to `patterns: gitleaks` and `patterns: minimal`, and the `detect-secrets` path warns and ignores it.

## Layer 2 field-name regex

A key is masked when a field in `SENSITIVE_FIELDS` sits anywhere in it, case-insensitively, the substring rule scalo-rs applies. The key is read word by word as well, so separators and camelCase do not hide a field: `CARGO_REGISTRY_TOKEN=...`, `x-api-key: ...`, `secretAccessKey=...` and `PGPASSWORD=...` all mask. The rule over-masks, and that is accepted: `token_count=5`, `max_tokens=4096`, `tokenizer`, `mapping` (on `pin`) and `author` (on `auth`) are masked as well.

One matcher decides every case, `scalo.logger.filters.is_credential_name`. Record fields, dicts, message text and Kafka config reprs all call it. A bare `key` or `value` is checked with the name of the mapping or list holding it, so `tls={"key": ...}` and `accepted_headers=[{"values": [...]}]` mask but `partitioner={"key": ...}` does not.

| Format | Input | Output |
|-------|-------|--------|
| env, form data | `JFROG_TOKEN=abc` | `JFROG_TOKEN=***REDACTED***` |
| TOML, INI | `token = "abc def"` | `token = ***REDACTED***` |
| JSON | `{"CARGO_REGISTRY_TOKEN": "abc"}` | `{"CARGO_REGISTRY_TOKEN": "***REDACTED***"}` |
| Python repr | `{'password': 'abc'}` | `{'password': ***REDACTED***}` |
| YAML, HTTP header | `x-auth-token: abc` | `x-auth-token: ***REDACTED***` |
| header value httpx refused, any auth scheme, bytes or str form | `Illegal header value b'SSWS abc\nX: 1'` | `Illegal header value b'***REDACTED***'` |

## Values L2 masks whole

The password in `scheme://user:password@host` is masked up to the last `@` a host follows, so one holding `@`, `/`, `?` or `#` is masked whole. Nothing tells such a password from an `@` later in the path or query, so `https://u:p@host/x?to=ops@example.com` is masked through to `example.com`. `scalo.logger.filters.mask_url_userinfo(text, mask, keep_user=True)` applies the same rule to any string, and `keep_user=False` masks the whole `user:password`. `scalo.logger.filters.url_passwords(text)` returns every non-empty password that call masks, in order, read by the same scanner, so code that checks or rejects a URL password needs no pattern of its. The scan holds no memory per character of a password.

A quoted value after `=`, or a single-quoted one after `:`, is masked whole with its quotes. A double-quoted JSON value keeps its quotes so the line stays valid JSON. A quoted value runs to the first quote no backslash escapes, so `password="a\"b"` and `{"password": "a\"b"}` are masked whole. One with no such quote is masked to its next quote. One with no closing quote at all is masked to the end of its line, or, for a double-quoted value after `:`, which may cross lines, to the end of the text short of a line break that ends it. Whitespace around `=` never crosses a line, and `==` and `=>` are not read as assignments.

A `Name(...)` value, as a Rust `Debug` dump or a Python repr writes one, is masked whole up to its closing parenthesis, so `db_password: Some("a b")` and `token=Token(value='a b')` leave nothing of the value behind. The name is letters, digits and `_`. Parentheses nest, and a quoted string inside may hold `)` and span lines. It closes at its first quote no backslash escapes or, with none left in the text, at its next quote. A value that does not close within 4096 UTF-8 bytes is masked to the end of the text, short of a line break that ends it.

These rules are checked against scalo-rs's credential-masking corpus, copied as `tests/fixtures/patterns/credential_masking_parity.json`, so scalo-py and scalo-rs mask the same text the same way.

`SensitiveDataFilter` in `scalo.logger.filters` holds the L2 field set. Add custom fields with `SensitiveDataFilter.add_sensitive_fields({"employee_id", "ssn"})`.

## Layer 3 email addresses

L3 redacts an email address written literally or percent-encoded, the way a URL or an HTTP or IdP error writes it: `@` as `%40` or `%2540`, and `+` in the local part as `%2B` or `%252B`, hex in either case. The address alone is replaced, so an escape before it survives:

| Input | Output |
|-------|--------|
| `userKey=sentinel.user%40example.com` | `userKey=[EMAIL_REDACTED]` |
| `filter=login%20eq%20%22sentinel.user%40example.com%22` | `filter=login%20eq%20%22[EMAIL_REDACTED]%22` |
| `next=%253Fuser%253Dsentinel.user%2540example.com` | `next=%253Fuser%253D[EMAIL_REDACTED]` |
| `discount=50%40off` | unchanged, no dot in the domain |
| `pkg@1.2.3`, `lodash%404.17.21` | unchanged, no letter in the last domain label |
| `user@10.0.0.1` | unchanged, an IPv4 host is not an email domain |

Both forms need a local part, a separator and a dotted domain with a letter in its last label. Package version pins and npm or pip specs therefore pass through, and so does `user@10.0.0.1`.

L3 cannot detect an opaque provider user id such as Okta's `00u1sentinel2abc3`. Mask it by field name: `SensitiveDataFilter.add_sensitive_fields({"okta_user_id"})` masks a bound `okta_user_id` field and `okta_user_id=...` in message text.

## Authorization headers

L2 masks the scheme and credentials after a key holding `authorization`, such as `Proxy-Authorization` or `HTTP_AUTHORIZATION`, so `Authorization: SSWS abc` becomes `Authorization: ***REDACTED***`. The credentials are comma-separated items, so a `Digest username="u", response="r"` list goes whole. An item runs to white space, `,`, `}` or `"`, takes a quoted string after `=` whole, and never crosses a line, so `Authorization: Basic abc status=401` keeps `status=401`. After `=` an item ends at `&` as well, which separates form fields there, so `Authorization: SharedAccessSignature sr=x&sig=y` masks whole, but `authorization=Basic abc&page=2` keeps `&page=2`. Prose with no `:` or `=` after the word is left alone, but `authorization_url=https://idp/authorize next=1` loses `next=1` as well.

After any other credential key, an unquoted value starting with an authentication scheme is read the same way, so `x-api-key: Token abc` and `header_value=Basic abc` mask whole. The schemes are the IANA registry's (`Basic`, `Bearer`, `Concealed`, `Digest`, `DPoP`, `GNAP`, `HOBA`, `Mutual`, `Negotiate`, `OAuth`, `PrivateToken`, `SCRAM-SHA-1`, `SCRAM-SHA-256`, `vapid`) and `ApiKey`, `AWS4-HMAC-SHA256`, `NTLM`, `SharedAccessSignature`, `SharedKey`, `SharedKeyLite`, `Splunk`, `SSWS` and `Token`, in any case. A value starting with any other word keeps the word after it, so `password: abc later` keeps `later`, but `auth=basic user=bob` loses `user=bob`.

## Double-colon keys and signed URLs

A key and its value may be joined by `::`, and L2 reads the value after both colons, so `password::abc` becomes `password::***REDACTED***`. A path with a first segment that names a credential loses the rest: `aws_sdk_secretsmanager::client` becomes `aws_sdk_secretsmanager::***REDACTED***`.

scalo-rs leaves a Hiera-style key such as `profile::db::password: x` in clear, an accepted divergence, because in its text logs a `module::path: value` line reads exactly like a log target and it cannot tell the two apart.

L2 masks the value of `sig`, `X-Amz-Signature`, `X-Amz-Security-Token` and `X-Goog-Signature`, written in any case right after `?` or `&` and followed by `=`, up to the next `&`, white space, quote or the end of the text. So an Azure SAS URL keeps everything but its `sig=`, and S3 and GCS presigned URLs lose their signatures. A longer name holding `sig`, such as `signal=`, `design=` or `?signature_type=`, is left alone.
