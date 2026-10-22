#  Project:   scalo
#  File:      tests/unit/test_secrets_kubernetes_provider.py
#  Purpose:   Kubernetes Secret provider against a TLS fake API server
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The Kubernetes secrets provider, exercised over real TLS against a fake API server (no mocks).

The fake answers as the API server does: 401 for a bad token, 403 outside the Role, 404 for a
missing Secret, 409 for a stale resourceVersion, 422 for a bad key and 400 for a value that is not
base64. tests/integration/test_secrets_kubernetes_cluster.py checks those answers against k3s.
"""

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from common.fake_kube_api import FakeKubeApi, running_fake_kube_api
from common.fake_secrets import opaque_secret

from scalo.secrets import (
    AuthenticationError,
    KubernetesConfig,
    KubernetesProvider,
    ProviderError,
    ProviderType,
    SecretAlreadyExistsError,
    SecretFilter,
    SecretNotFoundError,
    SecretPermissionError,
    SecretsManager,
)
from scalo.secrets.providers.kubernetes import check_data_key

NAMESPACE = "dfe"
SECRET = "ingest-bearer-tokens"


@pytest.fixture
def sa_token() -> str:
    return opaque_secret("sa-token")


@pytest.fixture
def kube_api(tmp_path: Path, sa_token: str) -> Iterator[FakeKubeApi]:
    with running_fake_kube_api(tmp_path, sa_token) as api:
        yield api


@pytest.fixture
def token_file(tmp_path: Path, sa_token: str) -> Path:
    path = tmp_path / "token"
    path.write_text(sa_token + "\n", encoding="utf-8")
    return path


def _config(api: FakeKubeApi, token_file: Path, **overrides: object) -> KubernetesConfig:
    settings: dict = {
        "secret_name": SECRET,
        "namespace": NAMESPACE,
        "api_server": api.url,
        "token_path": str(token_file),
        "ca_cert": api.ca_file,
    }
    settings.update(overrides)
    return KubernetesConfig(**settings)


@pytest.fixture
def provider(kube_api: FakeKubeApi, token_file: Path) -> Iterator[KubernetesProvider]:
    kube_api.add_secret(NAMESPACE, SECRET, {"http": b"cred-a:token-a\n"})
    p = KubernetesProvider(_config(kube_api, token_file))
    yield p
    if p._sync_client is not None:
        p._sync_client.close()


class TestRead:
    def test_reads_a_key_decoded(self, provider, kube_api):
        value = provider.get_sync("http")
        assert value.data == b"cred-a:token-a\n"
        assert value.source == "kubernetes"
        assert value.version == kube_api.secrets[(NAMESPACE, SECRET)]["metadata"]["resourceVersion"]

    def test_every_read_goes_to_the_api_server(self, provider, kube_api):
        provider.get_sync("http")
        kube_api.write_behind(NAMESPACE, SECRET, "http", b"rotated\n")
        assert provider.get_sync("http").data == b"rotated\n"

    def test_missing_key_is_not_found(self, provider):
        with pytest.raises(SecretNotFoundError, match="'grpc'"):
            provider.get_sync("grpc")

    def test_missing_secret_names_the_secret(self, kube_api, token_file):
        kube_api.readable.add((NAMESPACE, SECRET))
        p = KubernetesProvider(_config(kube_api, token_file))
        with pytest.raises(SecretNotFoundError, match=f"{NAMESPACE}/{SECRET}"):
            p.get_sync("http")

    def test_json_key_is_extracted(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"db": json.dumps({"password": "pw", "port": 5432}).encode()})
        p = KubernetesProvider(_config(kube_api, token_file))
        assert p.get_sync("db", key="password").data == b"pw"
        assert p.get_sync("db", key="port").data == b"5432"
        with pytest.raises(SecretNotFoundError):
            p.get_sync("db", key="absent")

    def test_secret_created_with_no_data_reads_as_no_keys(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET)
        p = KubernetesProvider(_config(kube_api, token_file))
        assert p.list_sync() == []
        with pytest.raises(SecretNotFoundError):
            p.get_sync("http")

    def test_metadata_carries_resource_version_and_creation_time(self, provider, kube_api):
        meta = provider.get_metadata_sync("http")
        assert meta.version == kube_api.secrets[(NAMESPACE, SECRET)]["metadata"]["resourceVersion"]
        assert meta.created_at is not None
        assert meta.created_at.year == 2026
        with pytest.raises(SecretNotFoundError):
            provider.get_metadata_sync("grpc")


class TestList:
    def test_lists_keys_sorted_and_filtered(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"otlp": b"x", "http": b"x", "grpc": b"x", "splunk_hec": b"x"})
        p = KubernetesProvider(_config(kube_api, token_file))
        assert p.list_sync() == ["grpc", "http", "otlp", "splunk_hec"]
        assert p.list_sync(SecretFilter(prefix="s")) == ["splunk_hec"]
        assert p.list_sync(SecretFilter(pattern="*c")) == ["grpc", "splunk_hec"]

    def test_missing_secret_lists_nothing(self, kube_api, token_file):
        kube_api.readable.add((NAMESPACE, SECRET))
        assert KubernetesProvider(_config(kube_api, token_file)).list_sync() == []


class TestWrite:
    def test_create_adds_a_key_and_keeps_the_rest(self, provider, kube_api):
        meta = provider.create_sync("grpc", b"cred-b:token-b\n")
        stored = kube_api.secrets[(NAMESPACE, SECRET)]
        assert kube_api.data(NAMESPACE, SECRET) == {"http": b"cred-a:token-a\n", "grpc": b"cred-b:token-b\n"}
        assert meta.version == stored["metadata"]["resourceVersion"]
        assert stored["metadata"]["annotations"] == {"owner": "chart"}

    def test_create_of_an_existing_key_refuses_without_writing(self, provider, kube_api):
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync("http", b"other")
        assert kube_api.puts() == 0
        assert kube_api.data(NAMESPACE, SECRET)["http"] == b"cred-a:token-a\n"

    def test_update_replaces_a_key(self, provider, kube_api):
        provider.update_sync("http", b"\n")
        assert kube_api.data(NAMESPACE, SECRET) == {"http": b"\n"}

    def test_update_of_a_missing_key_is_not_found(self, provider, kube_api):
        with pytest.raises(SecretNotFoundError):
            provider.update_sync("otlp", b"x")
        assert kube_api.puts() == 0

    def test_delete_removes_the_key_and_leaves_the_secret(self, provider, kube_api):
        provider.delete_sync("http")
        assert (NAMESPACE, SECRET) in kube_api.secrets
        assert kube_api.data(NAMESPACE, SECRET) == {}
        with pytest.raises(SecretNotFoundError):
            provider.delete_sync("http")

    def test_binary_value_round_trips(self, provider):
        provider.create_sync("blob", bytes(range(256)))
        assert provider.get_sync("blob").data == bytes(range(256))

    def test_write_to_a_missing_secret_never_creates_one(self, kube_api, token_file):
        kube_api.readable.add((NAMESPACE, SECRET))
        p = KubernetesProvider(_config(kube_api, token_file))
        with pytest.raises(ProviderError, match="does not exist"):
            p.create_sync("http", b"x")
        assert all(method == "GET" for method, _ in kube_api.requests)
        assert (NAMESPACE, SECRET) not in kube_api.secrets


class TestConcurrency:
    def test_a_concurrent_change_is_kept_and_the_write_retried(self, provider, kube_api):
        raced = []

        def other_writer(_incoming: dict) -> None:
            if not raced:
                raced.append(True)
                kube_api.write_behind(NAMESPACE, SECRET, "otlp", b"from-the-other-writer")

        kube_api.before_put = other_writer
        provider.create_sync("grpc", b"mine")
        assert kube_api.puts() == 2
        assert kube_api.data(NAMESPACE, SECRET) == {
            "http": b"cred-a:token-a\n",
            "otlp": b"from-the-other-writer",
            "grpc": b"mine",
        }

    def test_a_create_racing_a_create_of_the_same_key_reports_it_exists(self, provider, kube_api):
        def other_writer(_incoming: dict) -> None:
            if kube_api.puts() == 1:
                kube_api.write_behind(NAMESPACE, SECRET, "grpc", b"theirs")

        kube_api.before_put = other_writer
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync("grpc", b"mine")
        assert kube_api.data(NAMESPACE, SECRET)["grpc"] == b"theirs"

    def test_conflicts_on_every_attempt_give_up(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        writes = iter(range(100))
        kube_api.before_put = lambda _incoming: kube_api.write_behind(
            NAMESPACE, SECRET, "otlp", str(next(writes)).encode()
        )
        p = KubernetesProvider(_config(kube_api, token_file, conflict_retries=2))
        with pytest.raises(ProviderError, match="3 attempts"):
            p.update_sync("http", b"y")
        assert kube_api.puts() == 3
        assert kube_api.data(NAMESPACE, SECRET)["http"] == b"x"


class TestKeys:
    @pytest.mark.parametrize(
        "key", ["", "a b", "a/b", ".", "..", "..x", "k" * 254, "tab\tkey", "na" + chr(0xEF) + "ve"]
    )
    def test_invalid_key_is_refused_before_any_request(self, provider, kube_api, key):
        with pytest.raises(ValueError, match="not a valid Kubernetes Secret key"):
            provider.create_sync(key, b"x")
        with pytest.raises(ValueError, match="not a valid Kubernetes Secret key"):
            provider.get_sync(key)
        assert kube_api.requests == []

    @pytest.mark.parametrize("key", ["http", "splunk_hec", "prometheus_rw", "a.b-c_D9", ".hidden", "k" * 253])
    def test_valid_key_is_accepted(self, key):
        check_data_key(key)

    def test_the_api_server_refusal_of_a_value_is_reported(self, provider, kube_api):
        def corrupt(incoming: dict) -> None:
            incoming["data"]["grpc"] = "!!not-base64!!"

        kube_api.before_put = corrupt
        with pytest.raises(ProviderError, match="refused as invalid: .*illegal base64 data"):
            provider.create_sync("grpc", b"x")


class TestReadRetry:
    def test_a_5xx_read_is_retried(self, provider, kube_api):
        kube_api.answer_next = [("GET", 503, {})]
        assert provider.get_sync("http").data == b"cred-a:token-a\n"
        assert kube_api.gets() == 2

    def test_a_429_read_waits_out_retry_after(self, provider, kube_api):
        kube_api.answer_next = [("GET", 429, {"Retry-After": "1"})]
        started = time.monotonic()
        assert provider.get_sync("http").data == b"cred-a:token-a\n"
        assert time.monotonic() - started >= 1.0
        assert kube_api.gets() == 2

    def test_a_dropped_connection_is_retried(self, provider, kube_api):
        kube_api.drop_next = 1
        assert provider.get_sync("http").data == b"cred-a:token-a\n"
        assert kube_api.gets() == 2

    def test_retries_stop_after_three_attempts(self, provider, kube_api):
        kube_api.answer_next = [("GET", 503, {})] * 5
        with pytest.raises(ProviderError, match="HTTP 503"):
            provider.get_sync("http")
        assert kube_api.gets() == 3

    def test_the_read_inside_a_write_is_retried(self, provider, kube_api):
        kube_api.answer_next = [("GET", 502, {})]
        provider.create_sync("grpc", b"g")
        assert kube_api.gets() == 2
        assert kube_api.data(NAMESPACE, SECRET)["grpc"] == b"g"

    def test_a_refusal_is_not_retried(self, provider, kube_api):
        kube_api.readable.discard((NAMESPACE, SECRET))
        with pytest.raises(SecretPermissionError):
            provider.get_sync("http")
        assert kube_api.gets() == 1

    def test_a_write_is_never_repeated(self, provider, kube_api):
        kube_api.answer_next = [("PUT", 503, {})]
        with pytest.raises(ProviderError, match="HTTP 503"):
            provider.update_sync("http", b"y")
        assert kube_api.puts() == 1
        assert kube_api.data(NAMESPACE, SECRET)["http"] == b"cred-a:token-a\n"

    async def test_an_async_read_is_retried_and_bounded(self, provider, kube_api):
        kube_api.answer_next = [("GET", 500, {})]
        assert (await provider.get_async("http")).data == b"cred-a:token-a\n"
        kube_api.answer_next = [("GET", 503, {})] * 5
        with pytest.raises(ProviderError, match="HTTP 503"):
            await provider.get_async("http")
        assert kube_api.gets() == 5
        await provider.close()


class TestAuth:
    def test_a_refused_token_is_an_authentication_error(self, kube_api, tmp_path):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        wrong = tmp_path / "wrong-token"
        wrong.write_text(opaque_secret("not-the-token"), encoding="utf-8")
        with pytest.raises(AuthenticationError, match="401"):
            KubernetesProvider(_config(kube_api, wrong)).get_sync("http")

    def test_the_token_is_read_on_every_request(self, provider, kube_api, token_file, sa_token):
        provider.get_sync("http")
        rotated = opaque_secret("rotated-sa-token")
        token_file.write_text(rotated, encoding="utf-8")
        kube_api.token = rotated
        provider.get_sync("http")
        assert kube_api.tokens_seen == [sa_token, rotated]

    def test_a_missing_token_file_is_an_authentication_error(self, kube_api, tmp_path):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        with pytest.raises(AuthenticationError, match="not readable"):
            KubernetesProvider(_config(kube_api, tmp_path / "absent")).get_sync("http")
        assert kube_api.requests == []

    def test_a_secret_outside_the_role_is_a_permission_error(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, "other-secret", {"http": b"x"})
        kube_api.readable.discard((NAMESPACE, "other-secret"))
        p = KubernetesProvider(_config(kube_api, token_file, secret_name="other-secret"))
        with pytest.raises(SecretPermissionError, match="resourceNames"):
            p.get_sync("http")

    def test_a_read_only_role_refuses_the_write(self, provider, kube_api):
        kube_api.writable.discard((NAMESPACE, SECRET))
        with pytest.raises(SecretPermissionError, match="update"):
            provider.update_sync("http", b"x")

    def test_the_token_never_reaches_an_error(self, kube_api, tmp_path, sa_token):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        wrong_token = opaque_secret("leak-check")
        wrong = tmp_path / "wrong-token"
        wrong.write_text(wrong_token, encoding="utf-8")
        with pytest.raises(AuthenticationError) as excinfo:
            KubernetesProvider(_config(kube_api, wrong)).get_sync("http")
        assert wrong_token not in str(excinfo.value)
        assert sa_token not in str(excinfo.value)

    @pytest.mark.parametrize(
        "suffix",
        ["\x07bell-tail", "\nnext-line", "é-tail"],
        ids=["control-character", "embedded-newline", "non-ascii"],
    )
    def test_a_token_that_is_not_token68_names_its_path_and_never_its_text(self, kube_api, tmp_path, caplog, suffix):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        malformed = opaque_secret("malformed") + suffix
        path = tmp_path / "bad-token"
        path.write_text(malformed, encoding="utf-8")
        caplog.set_level(logging.INFO, logger="scalo.secrets.providers.kubernetes")
        provider = KubernetesProvider(_config(kube_api, path))

        with pytest.raises(AuthenticationError) as excinfo:
            provider.get_sync("http")
        healthy = provider.health_check_sync()

        chain = [excinfo.value, excinfo.value.__cause__, excinfo.value.__context__]
        rendered = " ".join(f"{error!s} {error!r}" for error in chain if error is not None)
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert str(path) in str(excinfo.value)
        assert healthy is False
        assert str(path) in logged
        assert opaque_secret("malformed") not in rendered
        assert opaque_secret("malformed") not in logged
        assert kube_api.requests == []

    def test_a_token_file_that_is_not_utf8_names_its_path_and_never_its_bytes(self, kube_api, tmp_path):
        path = tmp_path / "binary-token"
        path.write_bytes(opaque_secret("binary").encode() + b"\xff")

        with pytest.raises(AuthenticationError, match="not UTF-8") as excinfo:
            KubernetesProvider(_config(kube_api, path)).get_sync("http")

        assert str(path) in str(excinfo.value)
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__suppress_context__ is True
        assert kube_api.requests == []


class TestInCluster:
    def test_namespace_and_api_server_come_from_the_pod(self, kube_api, token_file, tmp_path, monkeypatch):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        namespace_file = tmp_path / "namespace"
        namespace_file.write_text(NAMESPACE, encoding="utf-8")
        port = kube_api.url.rsplit(":", 1)[1]
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "localhost")
        monkeypatch.setenv("KUBERNETES_SERVICE_PORT", port)
        p = KubernetesProvider(
            _config(kube_api, token_file, namespace=None, api_server=None, namespace_path=str(namespace_file))
        )
        assert p.get_sync("http").data == b"x"
        assert kube_api.requests == [("GET", f"/api/v1/namespaces/{NAMESPACE}/secrets/{SECRET}")]

    def test_ipv6_service_host_is_bracketed(self, monkeypatch):
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "fd00::1")
        monkeypatch.setenv("KUBERNETES_SERVICE_PORT", "443")
        p = KubernetesProvider(KubernetesConfig(secret_name=SECRET, namespace=NAMESPACE))
        assert p._base_url() == "https://[fd00::1]:443"

    def test_outside_a_pod_with_no_api_server_says_so(self, token_file, monkeypatch):
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_PORT", raising=False)
        p = KubernetesProvider(KubernetesConfig(secret_name=SECRET, namespace=NAMESPACE, token_path=str(token_file)))
        with pytest.raises(ProviderError, match="KUBERNETES_SERVICE_HOST"):
            p.get_sync("http")

    def test_unreadable_namespace_file_says_so(self, kube_api, token_file, tmp_path):
        p = KubernetesProvider(_config(kube_api, token_file, namespace=None, namespace_path=str(tmp_path / "absent")))
        with pytest.raises(ProviderError, match="no namespace"):
            p.get_sync("http")

    def test_malformed_namespace_file_is_refused(self, kube_api, token_file, tmp_path):
        namespace_file = tmp_path / "namespace"
        namespace_file.write_text("Not/A/Namespace", encoding="utf-8")
        p = KubernetesProvider(_config(kube_api, token_file, namespace=None, namespace_path=str(namespace_file)))
        with pytest.raises(ProviderError, match="DNS-1123 label"):
            p.get_sync("http")
        assert kube_api.requests == []

    def test_an_api_server_the_ca_does_not_vouch_for_is_refused(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"x"})
        p = KubernetesProvider(_config(kube_api, token_file, ca_cert=None))
        with pytest.raises(ProviderError, match="unreachable"):
            p.get_sync("http")

    def test_a_missing_ca_bundle_says_so(self, kube_api, token_file, tmp_path):
        p = KubernetesProvider(_config(kube_api, token_file, ca_cert=str(tmp_path / "absent.crt")))
        with pytest.raises(ProviderError, match="cannot load the API server CA"):
            p.get_sync("http")


class TestHealth:
    def test_healthy_when_the_secret_reads(self, provider):
        assert provider.health_check_sync() is True

    def test_unhealthy_when_the_secret_is_forbidden(self, provider, kube_api):
        kube_api.readable.discard((NAMESPACE, SECRET))
        assert provider.health_check_sync() is False

    async def test_async_health(self, provider, kube_api):
        assert await provider.health_check_async() is True
        kube_api.readable.discard((NAMESPACE, SECRET))
        assert await provider.health_check_async() is False
        await provider.close()

    def test_turning_unhealthy_is_logged_once_with_the_reason_and_so_is_recovery(self, provider, kube_api, caplog):
        caplog.set_level(logging.INFO, logger="scalo.secrets.providers.kubernetes")
        kube_api.readable.discard((NAMESPACE, SECRET))
        assert provider.health_check_sync() is False
        assert provider.health_check_sync() is False
        kube_api.readable.add((NAMESPACE, SECRET))
        assert provider.health_check_sync() is True
        logged = [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "scalo.secrets.providers.kubernetes"]
        assert [level for level, _ in logged] == [logging.WARNING, logging.INFO]
        assert f"{NAMESPACE}/{SECRET}" in logged[0][1]
        assert "resourceNames" in logged[0][1]

    async def test_a_missing_secret_is_logged_as_unhealthy(self, kube_api, token_file, caplog):
        caplog.set_level(logging.INFO, logger="scalo.secrets.providers.kubernetes")
        kube_api.readable.add((NAMESPACE, SECRET))
        p = KubernetesProvider(_config(kube_api, token_file))
        assert await p.health_check_async() is False
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("does not exist" in message for message in warnings)
        await p.close()


class TestAsync:
    async def test_crud(self, provider, kube_api):
        assert (await provider.get_async("http")).data == b"cred-a:token-a\n"
        await provider.create_async("grpc", b"g")
        await provider.update_async("http", b"h")
        await provider.delete_async("grpc")
        assert kube_api.data(NAMESPACE, SECRET) == {"http": b"h"}
        assert await provider.list_async() == ["http"]
        assert (await provider.get_metadata_async("http")).version is not None
        await provider.close()

    async def test_a_concurrent_change_is_kept_and_the_write_retried(self, provider, kube_api):
        raced = []

        def other_writer(_incoming: dict) -> None:
            if not raced:
                raced.append(True)
                kube_api.write_behind(NAMESPACE, SECRET, "otlp", b"theirs")

        kube_api.before_put = other_writer
        await provider.update_async("http", b"mine")
        assert kube_api.puts() == 2
        assert kube_api.data(NAMESPACE, SECRET) == {"http": b"mine", "otlp": b"theirs"}
        await provider.close()

    async def test_missing_secret(self, kube_api, token_file):
        kube_api.readable.add((NAMESPACE, SECRET))
        p = KubernetesProvider(_config(kube_api, token_file))
        with pytest.raises(SecretNotFoundError):
            await p.get_async("http")
        with pytest.raises(SecretNotFoundError):
            await p.get_metadata_async("http")
        with pytest.raises(ProviderError, match="does not exist"):
            await p.create_async("http", b"x")
        await p.close()


class TestConfig:
    @pytest.mark.parametrize("name", ["", "Upper", "under_score", "-lead", "trail-", "x" * 254])
    def test_malformed_secret_name_is_refused(self, name):
        with pytest.raises(ValueError, match="DNS-1123 subdomain"):
            KubernetesConfig(secret_name=name)

    def test_malformed_namespace_is_refused(self):
        with pytest.raises(ValueError, match="DNS-1123 label"):
            KubernetesConfig(secret_name=SECRET, namespace="a.b")

    def test_negative_conflict_retries_is_refused(self):
        with pytest.raises(ValueError, match="conflict_retries"):
            KubernetesConfig(secret_name=SECRET, conflict_retries=-1)

    @pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "HTTP://localhost"])
    def test_a_cleartext_api_server_is_refused(self, url):
        with pytest.raises(ValueError, match="allow_insecure_http"):
            KubernetesConfig(secret_name=SECRET, api_server=url)

    def test_a_cleartext_api_server_is_accepted_when_allowed(self):
        config = KubernetesConfig(secret_name=SECRET, api_server="http://127.0.0.1:8080", allow_insecure_http=True)
        assert config.api_server == "http://127.0.0.1:8080"

    @pytest.mark.parametrize("url", ["ftp://host", "127.0.0.1:6443", "localhost"])
    def test_an_api_server_that_is_not_an_https_url_is_refused(self, url):
        with pytest.raises(ValueError, match="https://"):
            KubernetesConfig(secret_name=SECRET, api_server=url, allow_insecure_http=True)

    def test_defaults_are_the_service_account_mount(self):
        config = KubernetesConfig(secret_name=SECRET)
        assert config.token_path == "/var/run/secrets/kubernetes.io/serviceaccount/token"
        assert config.ca_cert == "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        assert config.namespace_path == "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        assert config.namespace is None
        assert config.api_server is None


class TestManager:
    def _manager(self, api: FakeKubeApi, token_file: Path, **extra: object) -> SecretsManager:
        k8s = {
            "secret_name": SECRET,
            "namespace": NAMESPACE,
            "api_server": api.url,
            "token_path": str(token_file),
            "ca_cert": api.ca_file,
        }
        return SecretsManager.from_config({"kubernetes": k8s, "cache": {"enabled": False}, **extra})

    def test_from_config_reads_and_writes_through_the_provider(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"a"})
        sm = self._manager(kube_api, token_file)
        assert sm.get_sync("http", provider="kubernetes").data == b"a"
        sm.create_sync("grpc", b"g", provider="kubernetes")
        sm.update_sync("http", b"b", provider="kubernetes")
        assert kube_api.data(NAMESPACE, SECRET) == {"http": b"b", "grpc": b"g"}

    def test_a_named_source_reads_a_key(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"a"})
        sm = self._manager(kube_api, token_file, sources={"bearer": {"provider": "kubernetes", "path": "http"}})
        assert sm.get_string_sync("bearer") == "a"
        assert ProviderType("kubernetes") is ProviderType.KUBERNETES

    def test_from_config_without_a_secret_name_is_refused(self):
        with pytest.raises(ValueError, match="secret_name"):
            SecretsManager.from_config({"kubernetes": {"namespace": NAMESPACE}})

    def test_from_config_with_a_malformed_secret_name_is_refused(self):
        with pytest.raises(ValueError, match="DNS-1123"):
            SecretsManager.from_config({"kubernetes": {"secret_name": "Bad_Name"}})

    def test_from_config_carries_the_cleartext_opt_in(self):
        k8s = {"secret_name": SECRET, "api_server": "http://127.0.0.1:8080"}
        with pytest.raises(ValueError, match="allow_insecure_http"):
            SecretsManager.from_config({"kubernetes": k8s})
        SecretsManager.from_config({"kubernetes": {**k8s, "allow_insecure_http": True}})

    async def test_async_manager(self, kube_api, token_file):
        kube_api.add_secret(NAMESPACE, SECRET, {"http": b"a"})
        sm = self._manager(kube_api, token_file)
        assert (await sm.get("http", provider="kubernetes")).data == b"a"
        await sm.update("http", b"b", provider="kubernetes")
        assert kube_api.data(NAMESPACE, SECRET)["http"] == b"b"
        await sm.close()
