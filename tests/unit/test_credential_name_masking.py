#  Project:   scalo
#  File:      tests/unit/test_credential_name_masking.py
#  Purpose:   Every masking path hides a credential named in any spelling
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Log records, dicts, scrubbed text, URLs and Kafka configs all hide a credential by its name.

Every value is built at runtime, so no secret-shaped literal sits in source.
"""

import json
import random
import sys
import time

import pytest
from common.fake_secrets import opaque_secret
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.kafka.config import mask_credentials
from scalo.logger.filters import MASK_VALUE, SensitiveDataFilter, mask_url_userinfo
from scalo.logger.logger import setup
from scalo.logger.scrub import FieldNameScrubber, build_scrubber

SECRET = opaque_secret("credname")

# Credential names that each spelling rule has to reach: exact, case, kebab, camel, run-together, prefixed.
CREDENTIAL_KEYS = [
    "db_password",
    "PASSWORD",
    "api_token",
    "x-api-key",
    "secretAccessKey",
    "client_secret",
    "sasl_password",
    "KAFKA_SASL_PASSWORD",
    "rootPassword",
    "PGPASSWORD",
    "password_hash",
    "bearer_tokens",
    "refreshToken",
    "privateKey",
    "signingKey",
    "JWT_KEY",
    "maxmind_license_key",
    "KAFKA_SASL_JAAS_CONFIG",
    "X-Auth-Token",
    "passphrase",
    "ssl.key.password",
    "header_values",
]

SHOWN_KEYS = ["username", "host", "port", "topic", "KAFKA_PARTITION_KEY", "routing_key", "bootstrap.servers"]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    with preserved_stdlib_logging():
        yield
        logger.remove()


def _json_logger(monkeypatch) -> StreamDouble:
    stream = StreamDouble(False)
    monkeypatch.setattr(sys, "stderr", stream)
    setup(otel_tracing=False, log_format="json")
    return stream


def _fields(stream: StreamDouble) -> dict:
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1, lines
    return json.loads(lines[0])["fields"]


# ---------------------------------------------------------------------------
# log records
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CREDENTIAL_KEYS)
def test_a_log_field_named_as_a_credential_is_masked(monkeypatch, key):
    stream = _json_logger(monkeypatch)

    logger.warning("connect", **{key: SECRET})

    assert SECRET not in stream.getvalue()
    assert _fields(stream)[key] == MASK_VALUE


@pytest.mark.parametrize("key", SHOWN_KEYS)
def test_a_log_field_named_as_a_setting_is_shown(monkeypatch, key):
    stream = _json_logger(monkeypatch)

    logger.warning("connect", **{key: "plain-setting"})

    assert _fields(stream)[key] == "plain-setting"


def test_a_credential_nested_in_a_log_field_is_masked(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("connect", kafka={"brokers": "b1:9092", "sasl": {"saslPassword": SECRET}})

    kafka = _fields(stream)["kafka"]
    assert SECRET not in stream.getvalue()
    assert kafka["brokers"] == "b1:9092"
    assert kafka["sasl"]["saslPassword"] == MASK_VALUE


def test_a_credential_in_a_list_of_dicts_in_a_log_field_is_masked(monkeypatch):
    stream = _json_logger(monkeypatch)
    other = opaque_secret("second")

    logger.warning("sources", connections=[{"id": "a", "authToken": SECRET}, {"id": "b", "authToken": other}])

    connections = _fields(stream)["connections"]
    assert SECRET not in stream.getvalue()
    assert other not in stream.getvalue()
    assert connections == [{"id": "a", "authToken": MASK_VALUE}, {"id": "b", "authToken": MASK_VALUE}]


def test_a_bare_key_under_tls_in_a_log_field_is_masked(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("listener", tls={"enabled": True, "key": SECRET}, partitioner={"key": "order_id"})

    fields = _fields(stream)
    assert SECRET not in stream.getvalue()
    assert fields["tls"] == {"enabled": True, "key": MASK_VALUE}
    assert fields["partitioner"] == {"key": "order_id"}


def test_header_values_in_a_list_of_entries_are_masked(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("auth", accepted_headers=[{"name": "x-tenant", "values": [SECRET]}])

    assert SECRET not in stream.getvalue()
    assert _fields(stream)["accepted_headers"][0]["name"] == "x-tenant"


def test_a_two_item_pair_named_as_a_credential_masks_its_value(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("upstream", headers=[("X-Api-Key", SECRET), ("accept", "application/json")])

    headers = _fields(stream)["headers"]
    assert SECRET not in stream.getvalue()
    assert headers == [["X-Api-Key", MASK_VALUE], ["accept", "application/json"]]


@pytest.mark.parametrize(
    "header",
    [
        pytest.param(("Authorization", SECRET), id="tuple-field"),
        pytest.param({"upstream": ("Authorization", SECRET)}, id="tuple-under-a-key"),
        pytest.param([("Authorization", SECRET)], id="tuple-in-a-list"),
        pytest.param([["Authorization", SECRET]], id="list-in-a-list"),
    ],
)
def test_a_name_value_pair_headed_by_a_credential_masks_its_value(monkeypatch, header):
    stream = _json_logger(monkeypatch)

    logger.warning("upstream", header=header)

    assert SECRET not in stream.getvalue()


def test_a_list_of_field_names_is_shown(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.info("auth.account.updated", details={"fields": ["email", "name"]}, columns=["password", "username"])

    fields = _fields(stream)
    assert fields["details"] == {"fields": ["email", "name"]}
    assert fields["columns"] == ["password", "username"]


def test_a_two_item_tuple_of_names_is_read_as_a_pair(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.info("missing", columns=("email", "name"))

    assert _fields(stream)["columns"] == ["email", MASK_VALUE]


def test_a_url_password_holding_an_at_sign_is_masked_in_a_message(monkeypatch):
    stream = _json_logger(monkeypatch)
    password = "p" + "@" + SECRET

    # A dotless host, so L3's email rule cannot be what hides the tail of the password.
    logger.warning(f"connecting to postgres://svc:{password}@db:5432/app")

    assert SECRET not in stream.getvalue()


@pytest.mark.parametrize("separator", ["/", "?", "#"])
def test_a_url_password_holding_an_at_sign_and_a_separator_is_masked_in_a_message(monkeypatch, separator):
    stream = _json_logger(monkeypatch)
    password = "ab" + "@" + SECRET + separator + "ef"

    logger.warning(f"connecting to postgres://svc:{password}@db/app")

    assert SECRET not in stream.getvalue()
    assert "postgres://svc:" + MASK_VALUE + "@db/app" in stream.getvalue()


# ---------------------------------------------------------------------------
# dicts through the legacy SensitiveDataFilter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CREDENTIAL_KEYS)
def test_a_dict_key_named_as_a_credential_is_masked(key):
    masked = SensitiveDataFilter()._mask_sensitive_dict({key: SECRET, "host": "db"})

    assert masked == {key: MASK_VALUE, "host": "db"}


def test_nested_dicts_and_lists_of_dicts_are_masked():
    data = {
        "kafka": {"brokers": "b1:9092", "sasl": {"saslPassword": SECRET}},
        "connections": [{"id": "a", "authToken": SECRET}],
        "tls": {"enabled": True, "key": SECRET},
        "partitioner": {"key": "order_id"},
    }

    masked = SensitiveDataFilter()._mask_sensitive_dict(data)

    assert masked == {
        "kafka": {"brokers": "b1:9092", "sasl": {"saslPassword": MASK_VALUE}},
        "connections": [{"id": "a", "authToken": MASK_VALUE}],
        "tls": {"enabled": True, "key": MASK_VALUE},
        "partitioner": {"key": "order_id"},
    }


def test_a_non_string_dict_key_does_not_break_masking():
    masked = SensitiveDataFilter()._mask_sensitive_dict({1: "one", "apiKey": SECRET})

    assert masked == {1: "one", "apiKey": MASK_VALUE}


# ---------------------------------------------------------------------------
# text through L2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(f"secretAccessKey={SECRET}", f"secretAccessKey={MASK_VALUE}", id="camel-env"),
        pytest.param(f"x-api-key: {SECRET}", f"x-api-key: {MASK_VALUE}", id="kebab-header"),
        pytest.param(f"api_token_value={SECRET}", f"api_token_value={MASK_VALUE}", id="term-mid-key"),
        pytest.param(f'{{"clientSecret": "{SECRET}"}}', f'{{"clientSecret": "{MASK_VALUE}"}}', id="camel-json"),
        pytest.param(f"PGPASSWORD={SECRET}", f"PGPASSWORD={MASK_VALUE}", id="run-together"),
        pytest.param(f"db_password={SECRET}", f"db_password={MASK_VALUE}", id="snake-env"),
        pytest.param(f"ssl.key.pem: {SECRET}", f"ssl.key.pem: {MASK_VALUE}", id="dotted-librdkafka"),
    ],
)
def test_a_credential_key_in_text_is_masked(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("config:password:hunter2", f"config:password:{MASK_VALUE}", id="colon-chain"),
        pytest.param("ctx: a=1 token=abc", f"ctx: a=1 token={MASK_VALUE}", id="pair-after-a-pair"),
        pytest.param("password: token: abc", f"password: {MASK_VALUE} abc", id="value-is-masked-once"),
    ],
)
def test_a_credential_key_inside_another_pair_is_still_judged(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("pin: 1234 5678", f"pin: {MASK_VALUE}", id="colon-digit-groups"),
        pytest.param("password=1234 5678&next=1", f"password={MASK_VALUE}&next=1", id="equals-digit-groups"),
        pytest.param("phone: +61 412 345 678 on file", f"phone: {MASK_VALUE} on file", id="stops-at-a-word"),
    ],
)
def test_an_unquoted_value_runs_across_digit_groups(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "digits"),
    [
        pytest.param("TFN: 123 456 782", "456 782", id="tfn"),
        pytest.param("phone: +61 412 345 678", "345 678", id="phone"),
        pytest.param("credit_card: 4111 1111 1111 1111", "1111 1111", id="card"),
    ],
)
def test_the_default_chain_never_leaves_part_of_a_number_under_a_named_key(line, digits):
    assert digits not in build_scrubber().scrub(line)


# ---------------------------------------------------------------------------
# quoted values through L2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(r'{"password": "a\"b"}', f'{{"password": "{MASK_VALUE}"}}', id="json-mid"),
        pytest.param(r'password="a\"b" next=1', f"password={MASK_VALUE} next=1", id="equals-mid"),
        pytest.param(
            r'{"password": "\"ab", "user": "bob"}', f'{{"password": "{MASK_VALUE}", "user": "bob"}}', id="json-start"
        ),
        pytest.param(
            r'{"password": "ab\"", "user": "bob"}', f'{{"password": "{MASK_VALUE}", "user": "bob"}}', id="json-end"
        ),
        pytest.param(
            r'{"password": "a\\", "user": "bob"}',
            f'{{"password": "{MASK_VALUE}", "user": "bob"}}',
            id="json-escaped-backslash-closes",
        ),
        pytest.param(
            r'{"password": "a\\\"b", "user": "bob"}',
            f'{{"password": "{MASK_VALUE}", "user": "bob"}}',
            id="json-escaped-backslash-then-quote",
        ),
        pytest.param(
            '{"password": "a\\\nb", "user": "bob"}',
            f'{{"password": "{MASK_VALUE}", "user": "bob"}}',
            id="json-escaped-line-break",
        ),
        pytest.param(r'password="\"ab" next=1', f"password={MASK_VALUE} next=1", id="equals-start"),
        pytest.param(r'password="ab\"" next=1', f"password={MASK_VALUE} next=1", id="equals-end"),
        pytest.param(r'password="a\\" next=1', f"password={MASK_VALUE} next=1", id="equals-escaped-backslash-closes"),
        pytest.param(r"password='a\'b' next=1", f"password={MASK_VALUE} next=1", id="equals-single-quoted"),
        pytest.param(
            r"{'password': 'a\'b', 'user': 'bob'}", f"{{'password': {MASK_VALUE}, 'user': 'bob'}}", id="python-repr"
        ),
        pytest.param('password="a\\\nb" next=1', f'password={MASK_VALUE}\nb" next=1', id="equals-never-crosses-a-line"),
    ],
)
def test_an_escaped_quote_does_not_end_a_quoted_value(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(r'{"password": "abc\"}', f'{{"password": "{MASK_VALUE}"}}', id="json"),
        pytest.param(r'password="a b\"', f"password={MASK_VALUE}", id="equals"),
    ],
)
def test_a_quoted_value_with_no_unescaped_close_is_masked_to_its_next_quote(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


def _quoted_end(text: str, start: int, *, multiline: bool) -> int | None:
    """Return the end of the quoted value opening at ``start``, past backslash escapes, or None when it never closes."""
    quote = text[start]
    at = start + 1
    while at < len(text):
        char = text[at]
        if char == "\\":
            if at + 1 == len(text) or (text[at + 1] == "\n" and not multiline):
                return None
            at += 2
            continue
        if char == "\n" and not multiline:
            return None
        if char == quote:
            return at + 1
        at += 1
    return None


def _plain_quoted_end(text: str, start: int, *, multiline: bool) -> int | None:
    """Return the end of the quoted value opening at ``start`` at its next quote, escaped or not."""
    close = text.find(text[start], start + 1)
    if close == -1 or (not multiline and "\n" in text[start:close]):
        return None
    return close + 1


def _reference_equals(value: str) -> str:
    """Mask ``password=<value>`` by reading the value one character at a time, as a check on the regex."""
    start = len(value) - len(value.lstrip(" \t"))
    end = None
    if value[start : start + 1] in ('"', "'"):
        end = _quoted_end(value, start, multiline=False) or _plain_quoted_end(value, start, multiline=False)
    if end is None:
        end = start
        while end < len(value) and not value[end].isspace() and value[end] != "&":
            end += 1
    return "password=" + value[:start] + MASK_VALUE + value[end:]


def _reference_colon(value: str) -> str:
    """Mask ``{"password": <value>`` by reading the value one character at a time, as a check on the regex."""
    head = '{"password": '
    start = len(value) - len(value.lstrip())
    first = value[start : start + 1]
    if first == '"':
        end = _quoted_end(value, start, multiline=True) or _plain_quoted_end(value, start, multiline=True)
        if end is None:
            return head + value
        return head + value[:start] + f'"{MASK_VALUE}"' + value[end:]
    end = None
    if first == "'":
        end = _quoted_end(value, start, multiline=False) or _plain_quoted_end(value, start, multiline=False)
    if end is None:
        end = start
        while end < len(value) and not value[end].isspace() and value[end] not in ',"}':
            end += 1
        if end == start or value[end : end + 1] == '"':
            return head + value
    return head + value[:start] + MASK_VALUE + value[end:]


def test_a_quoted_value_is_read_as_a_scanner_reads_it():
    rng = random.Random(17)
    alphabet = ["a", "b", " ", "\n", '"', '"', "'", "'", "\\", "\\"]
    scrubber = FieldNameScrubber()
    for _ in range(10_000):
        value = "".join(rng.choices(alphabet, k=rng.randint(0, 16)))
        assert scrubber.scrub("password=" + value) == _reference_equals(value), repr(value)
        assert scrubber.scrub('{"password": ' + value) == _reference_colon(value), repr(value)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param('password: "' + "\\" * 200_000, id="backslashes"),
        pytest.param('password: "' + '\\"' * 100_000, id="escaped-quotes"),
        pytest.param('password="' + '\\"' * 100_000, id="equals-escaped-quotes"),
        pytest.param("password: '" + "\\'" * 100_000, id="escaped-single-quotes"),
        pytest.param('{"password": "' + "\\\\" * 100_000 + '"}', id="escaped-backslashes"),
        pytest.param('password: "' + 'password: \\"' * 16_000, id="escaped-quote-heads"),
        pytest.param('password="\\" ' * 15_000, id="repeated-equals-heads"),
        pytest.param('"\\' * 100_000, id="no-key"),
    ],
)
def test_a_long_line_of_backslashes_and_quotes_is_masked_in_linear_time(text):
    started = time.perf_counter()
    FieldNameScrubber().scrub(text)
    elapsed = time.perf_counter() - started

    # A quadratic scan of 200,000 characters takes minutes, so the bound sits far above a linear one.
    assert elapsed < 2.0


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(
            "postgres://svc:{pw}@db.internal:5432/app",
            f"postgres://svc:{MASK_VALUE}@db.internal:5432/app",
            id="one-at-sign-in-password",
        ),
        pytest.param(
            "mysql://root:a@b@{pw}@db:3306/app",
            f"mysql://root:{MASK_VALUE}@db:3306/app",
            id="two-at-signs-in-password",
        ),
        pytest.param(
            "amqp://guest:pa/{secret}@broker/vhost",
            f"amqp://guest:{MASK_VALUE}@broker/vhost",
            id="slash-in-password",
        ),
        pytest.param("postgres://u:ab@cd/ef@host/db", f"postgres://u:{MASK_VALUE}@host/db", id="at-and-slash-literal"),
        pytest.param(
            "postgres://u:ab@{secret}/ef@host/db",
            f"postgres://u:{MASK_VALUE}@host/db",
            id="at-and-slash-in-password",
        ),
        pytest.param(
            "postgres://u:ab@{secret}?ef@host/db",
            f"postgres://u:{MASK_VALUE}@host/db",
            id="at-and-query-mark-in-password",
        ),
        pytest.param(
            "postgres://u:ab@{secret}#ef@host/db",
            f"postgres://u:{MASK_VALUE}@host/db",
            id="at-and-hash-in-password",
        ),
        pytest.param("postgres://u:{secret}?x@host/db", f"postgres://u:{MASK_VALUE}@host/db", id="query-in-password"),
        pytest.param("postgres://u:{secret}#x@host/db", f"postgres://u:{MASK_VALUE}@host/db", id="hash-in-password"),
        pytest.param("redis://:{pw}@cache:6379/0", f"redis://:{MASK_VALUE}@cache:6379/0", id="no-user"),
        pytest.param(
            "https://svc:{pw}@api.example.com/v1?notify=ops@example.com",
            f"https://svc:{MASK_VALUE}@example.com",
            id="at-sign-in-query-masks-to-the-last-at",
        ),
        pytest.param("https://host:8443/@scope/pkg", f"https://host:{MASK_VALUE}@scope/pkg", id="scoped-npm-path"),
        pytest.param("https://api.example.com:8443/health", "https://api.example.com:8443/health", id="no-userinfo"),
        pytest.param("ssh://git@host/repo.git", "ssh://git@host/repo.git", id="user-with-no-password"),
        pytest.param(
            '{{"a":"x://u:{secret}@h1","b":"y://v:{secret}@h2"}}',
            f'{{"a":"x://u:{MASK_VALUE}@h1","b":"y://v:{MASK_VALUE}@h2"}}',
            id="two-urls-in-one-json-line",
        ),
    ],
)
def test_url_userinfo_is_masked_up_to_the_host(line, expected):
    text = line.format(pw="p" + "@" + SECRET, secret=SECRET)

    assert FieldNameScrubber().scrub(text) == expected


# ---------------------------------------------------------------------------
# the public URL masker
# ---------------------------------------------------------------------------

# Characters that end a URL's host.
_HOST_ENDS = "/?#"


def _host_follows(text: str, at: int) -> bool:
    """Return whether a host follows the `@` at ``at``: no `@` in it, and it ends at a host end, whitespace or the end."""
    end = at + 1
    while end < len(text) and not text[end].isspace() and text[end] not in "@" + _HOST_ENDS:
        end += 1
    return end == len(text) or text[end].isspace() or text[end] in _HOST_ENDS


def _reference_mask(text: str, mask: str, *, keep_user: bool) -> str:
    """Mask URL userinfo by reading the grammar one step at a time, as a check on the regex.

    A URL starts at `://`. The user holds no whitespace, `:`, `/` or `@` and ends at a `:`. The password runs to the
    last `@` a host follows, and never past whitespace or the next `://`. The next URL is looked for from that `@`.
    """
    out = []
    copied = 0
    head = text.find("://")
    while head != -1:
        colon = head + 3
        while colon < len(text) and not text[colon].isspace() and text[colon] not in ":/@":
            colon += 1
        if colon < len(text) and text[colon] == ":":
            run_end = colon + 1
            while run_end < len(text) and not text[run_end].isspace() and not text.startswith("://", run_end):
                run_end += 1
            ats = [at for at in range(colon + 1, run_end) if text[at] == "@" and _host_follows(text, at)]
            if ats:
                at = ats[-1]
                if not keep_user:
                    out.append(text[copied:head] + "://" + mask)
                elif at > colon + 1:
                    out.append(text[copied : colon + 1] + mask)
                else:
                    out.append(text[copied:at])
                copied = at
                head = text.find("://", at)
                continue
        head = text.find("://", head + 1)
    out.append(text[copied:])
    return "".join(out)


def test_the_url_masker_masks_the_password_to_the_last_at_sign_a_host_follows():
    assert mask_url_userinfo("postgres://u:ab@cd/ef@host/db") == f"postgres://u:{MASK_VALUE}@host/db"
    assert mask_url_userinfo("kafka://svc:pw@b1:9092,b2:9092", "***") == "kafka://svc:***@b1:9092,b2:9092"


def test_the_url_masker_can_mask_the_whole_userinfo():
    line = "Push to http://deploy:s3c@r/t@forge.svc:3000/deploy.git successful."

    masked = mask_url_userinfo(line, "***", keep_user=False)

    assert masked == "Push to http://***@forge.svc:3000/deploy.git successful."


@pytest.mark.parametrize(
    ("keep_user", "expected"),
    [pytest.param(True, "http://user:@host/x", id="keep-user"), pytest.param(False, "http://***@host/x", id="whole")],
)
def test_an_empty_password_leaves_only_the_user_to_mask(keep_user, expected):
    assert mask_url_userinfo("http://user:@host/x", "***", keep_user=keep_user) == expected


def test_the_mask_is_inserted_as_written():
    assert mask_url_userinfo("x://u:p@h", r"\1\g<0>") == r"x://u:\1\g<0>@h"


def test_the_url_masker_reads_random_text_as_the_grammar_does():
    rng = random.Random(124)
    alphabet = ["a", "B", "1", ".", ",", ":", ":", "/", "/", "@", "@", "?", "#", " ", "\\", "://"]
    for _ in range(20_000):
        text = "".join(rng.choices(alphabet, k=rng.randint(0, 24)))
        assert mask_url_userinfo(text) == _reference_mask(text, MASK_VALUE, keep_user=True), repr(text)
        whole = mask_url_userinfo(text, "***", keep_user=False)
        assert whole == _reference_mask(text, "***", keep_user=False), repr(text)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("A" * 200_000 + " a://x", id="letter-run"),
        pytest.param("a://:" + "A" * 200_000, id="after-userinfo"),
        pytest.param("1a" * 100_000 + " b://x", id="mixed-run"),
        pytest.param("a://:" + "@" * 200_000, id="at-signs"),
        pytest.param("a://:" + "@a" * 100_000, id="short-hosts"),
        pytest.param("a://:" + "@" + "a" * 200_000 + "@", id="one-long-host"),
        pytest.param("://a:" * 50_000, id="repeated-heads"),
        pytest.param("://" + "a" * 200_000, id="user-with-no-colon"),
    ],
)
def test_a_long_line_is_read_in_linear_time(text):
    started = time.perf_counter()
    mask_url_userinfo(text)
    mask_url_userinfo(text, keep_user=False)
    elapsed = time.perf_counter() - started

    # A quadratic scan of 200,000 characters takes minutes, so the bound sits far above a linear one.
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# Kafka client configs
# ---------------------------------------------------------------------------


def test_kafka_config_masks_credentials_by_name():
    config = {
        "bootstrap.servers": "b1:9092",
        "client.id": "orders-api",
        "sasl.username": "svc-orders",
        "sasl.password": SECRET,
        "sasl.oauthbearer.client.secret": SECRET,
        "ssl.key.pem": SECRET,
    }

    masked = mask_credentials(config)

    assert masked == {
        "bootstrap.servers": "b1:9092",
        "client.id": "orders-api",
        "sasl.username": "***",
        "sasl.password": "***",
        "sasl.oauthbearer.client.secret": "***",
        "ssl.key.pem": "***",
    }
