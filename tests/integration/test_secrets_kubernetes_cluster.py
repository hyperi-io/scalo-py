#  Project:   scalo
#  File:      tests/integration/test_secrets_kubernetes_cluster.py
#  Purpose:   Kubernetes secrets provider against a real API server
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The Kubernetes secrets provider against a real API server: an existing one, or the run's k3s in Docker.

tests/common/kube_cluster.py resolves the server. Each test gets its own namespace and a service account
whose Role grants ``get`` and ``update`` on named Secrets only, as a deployment would. The parity tests send
the same requests to the server and to the fake the unit tests use, so the fake cannot drift from it. One
read runs in core, and the rest run in full.
"""

import os
import ssl
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from common.fake_kube_api import running_fake_kube_api
from common.fake_secrets import opaque_secret
from common.kube_cluster import ClusterUnavailable, KubeCluster, Namespace, existing_cluster, shared_k3s

from scalo.deployment.test_support.pytest_plugin import suite_for, unavailable
from scalo.secrets import KubernetesConfig, KubernetesProvider, ProviderError, SecretAlreadyExistsError
from scalo.secrets.providers import kubernetes as kubernetes_module

pytestmark = pytest.mark.integration

SECRET = "ingest-bearer-tokens"
OTHER = "not-in-the-role"
ABSENT = "never-created"


@pytest.fixture(scope="session")
def cluster(tmp_path_factory: pytest.TempPathFactory, pytestconfig: pytest.Config) -> KubeCluster:
    try:
        found = existing_cluster()
    except ClusterUnavailable as e:
        pytest.fail(str(e))
    if found is not None:
        return found
    try:
        return shared_k3s(suite_for(pytestconfig), tmp_path_factory.mktemp("k3s"))
    except ClusterUnavailable as e:
        unavailable(f"Kubernetes API server unavailable: {e}")
        raise


@pytest.fixture
def namespace(cluster: KubeCluster) -> Iterator[Namespace]:
    with cluster.admin() as admin:
        ns = Namespace(admin)
        try:
            yield ns
        finally:
            ns.delete()


@pytest.fixture
def token_file(namespace: Namespace, tmp_path: Path) -> Path:
    path = tmp_path / "token"
    namespace.grant([SECRET, ABSENT], path)
    return path


@pytest.fixture
def make_provider(
    cluster: KubeCluster, namespace: Namespace, token_file: Path
) -> Iterator[Callable[..., KubernetesProvider]]:
    made: list[KubernetesProvider] = []

    def make(**overrides: Any) -> KubernetesProvider:
        settings: dict[str, Any] = {
            "secret_name": SECRET,
            "namespace": namespace.name,
            "api_server": cluster.api,
            "token_path": str(token_file),
            "ca_cert": str(cluster.ca_file),
        }
        settings.update(overrides)
        provider = KubernetesProvider(KubernetesConfig(**settings))
        made.append(provider)
        return provider

    yield make
    for provider in made:
        if provider._sync_client is not None:
            provider._sync_client.close()


def _watch_puts(provider: KubernetesProvider, before_put: Callable[[], None]) -> list[int]:
    """Run ``before_put`` ahead of each PUT the provider sends, and collect the PUT answers' status codes."""
    statuses: list[int] = []

    def on_request(request: httpx.Request) -> None:
        if request.method == "PUT":
            before_put()

    def on_response(response: httpx.Response) -> None:
        if response.request.method == "PUT":
            statuses.append(response.status_code)

    provider._get_sync_client().event_hooks = {"request": [on_request], "response": [on_response]}
    return statuses


class TestReadAndWrite:
    def test_get_reads_a_key_at_the_secret_resource_version(self, namespace, make_provider):
        namespace.create_secret(SECRET, {"http": b"cred-a:token-a\n"})
        value = make_provider().get_sync("http")
        stored = namespace.read_secret(SECRET)
        assert value.data == b"cred-a:token-a\n"
        assert value.version == stored["metadata"]["resourceVersion"]

    @pytest.mark.full
    async def test_async_get_list_and_metadata(self, namespace, make_provider):
        namespace.create_secret(SECRET, {"http": b"a", "grpc": b"b"})
        provider = make_provider()
        assert (await provider.get_async("grpc")).data == b"b"
        assert await provider.list_async() == ["grpc", "http"]
        assert (await provider.get_metadata_async("http")).created_at is not None
        await provider.close()

    @pytest.mark.full
    def test_create_adds_a_key_only_when_it_is_absent(self, namespace, make_provider):
        namespace.create_secret(SECRET, {"http": b"a"})
        provider = make_provider()
        provider.create_sync("grpc", b"b")
        assert namespace.data(SECRET) == {"http": b"a", "grpc": b"b"}
        version = namespace.read_secret(SECRET)["metadata"]["resourceVersion"]
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync("grpc", b"other")
        assert namespace.read_secret(SECRET)["metadata"]["resourceVersion"] == version
        assert namespace.data(SECRET)["grpc"] == b"b"

    @pytest.mark.full
    def test_update_replaces_at_the_resource_version_it_read(self, namespace, make_provider):
        created = namespace.create_secret(SECRET, {"http": b"a"})
        meta = make_provider().update_sync("http", b"rotated")
        stored = namespace.read_secret(SECRET)
        assert namespace.data(SECRET) == {"http": b"rotated"}
        assert meta.version == stored["metadata"]["resourceVersion"]
        assert meta.version != created["metadata"]["resourceVersion"]

    @pytest.mark.full
    def test_a_write_to_a_missing_secret_never_creates_it(self, namespace, make_provider, cluster):
        with pytest.raises(ProviderError, match="does not exist"):
            make_provider(secret_name=ABSENT).create_sync("http", b"x")
        with cluster.admin() as admin:
            assert admin.get(f"/api/v1/namespaces/{namespace.name}/secrets/{ABSENT}").status_code == 404


@pytest.mark.full
class TestConflicts:
    def test_a_write_racing_another_writer_is_retried_and_keeps_both(self, namespace, make_provider):
        namespace.create_secret(SECRET, {"http": b"a"})
        provider = make_provider()
        raced: list[bool] = []

        def other_writer() -> None:
            if not raced:
                raced.append(True)
                namespace.write_behind(SECRET, "otlp", b"theirs")

        statuses = _watch_puts(provider, other_writer)
        provider.create_sync("grpc", b"mine")
        assert statuses == [409, 200]
        assert namespace.data(SECRET) == {"http": b"a", "otlp": b"theirs", "grpc": b"mine"}

    def test_conflicts_on_every_attempt_give_up(self, namespace, make_provider):
        namespace.create_secret(SECRET, {"http": b"a"})
        provider = make_provider(conflict_retries=1)
        writes = iter(range(100))
        # Each write changes the value: a replace that changes nothing leaves the resourceVersion where it was.
        statuses = _watch_puts(provider, lambda: namespace.write_behind(SECRET, "otlp", str(next(writes)).encode()))
        with pytest.raises(ProviderError, match="2 attempts"):
            provider.update_sync("http", b"mine")
        assert statuses == [409, 409]
        assert namespace.data(SECRET)["http"] == b"a"


@pytest.mark.full
class TestRefusals:
    def test_a_value_that_is_not_base64_is_refused_as_invalid(self, namespace, make_provider, monkeypatch):
        namespace.create_secret(SECRET, {"http": b"a"})
        monkeypatch.setattr(kubernetes_module, "_encode", lambda _value: "!!not-base64!!")
        with pytest.raises(ProviderError, match="refused as invalid: .*illegal base64 data"):
            make_provider().create_sync("grpc", b"x")
        assert namespace.data(SECRET) == {"http": b"a"}


def _put_mutated(change: Callable[[dict[str, Any]], None]) -> Callable[[httpx.Client, str], int]:
    def send(client: httpx.Client, ns: str) -> int:
        secret = client.get(f"/api/v1/namespaces/{ns}/secrets/{SECRET}").json()
        change(secret)
        return client.put(f"/api/v1/namespaces/{ns}/secrets/{SECRET}", json=secret).status_code

    return send


def _bad_value(secret: dict[str, Any]) -> None:
    secret["data"]["grpc"] = "!!not-base64!!"


def _bad_key(secret: dict[str, Any]) -> None:
    secret["data"]["bad key"] = "eA=="


def _stale(secret: dict[str, Any]) -> None:
    secret["metadata"]["resourceVersion"] = "1"


_CASES: dict[str, Callable[[httpx.Client, str], int]] = {
    "value-not-base64": _put_mutated(_bad_value),
    "invalid-key": _put_mutated(_bad_key),
    "stale-resource-version": _put_mutated(_stale),
    "outside-the-role": lambda client, ns: client.get(f"/api/v1/namespaces/{ns}/secrets/{OTHER}").status_code,
    "missing-secret": lambda client, ns: client.get(f"/api/v1/namespaces/{ns}/secrets/{ABSENT}").status_code,
    "replace-of-a-missing-secret": lambda client, ns: (
        client.put(
            f"/api/v1/namespaces/{ns}/secrets/{ABSENT}",
            json={"apiVersion": "v1", "kind": "Secret", "metadata": {"name": ABSENT, "resourceVersion": "1"}},
        ).status_code
    ),
}

_EXPECTED = {
    "value-not-base64": 400,
    "invalid-key": 422,
    "stale-resource-version": 409,
    "outside-the-role": 403,
    "missing-secret": 404,
    "replace-of-a-missing-secret": 404,
}


@pytest.mark.full
class TestTheFakeAnswersAsTheApiServerDoes:
    @pytest.mark.parametrize("case", sorted(_CASES))
    def test_status(self, case, cluster, namespace, token_file, tmp_path):
        namespace.create_secret(SECRET, {"http": b"a"})
        namespace.create_secret(OTHER, {"http": b"a"})
        verify = ssl.create_default_context(cafile=str(cluster.ca_file))
        headers = {"Authorization": f"Bearer {token_file.read_text(encoding='utf-8').strip()}"}
        with httpx.Client(base_url=cluster.api, verify=verify, headers=headers, timeout=30) as client:
            real = _CASES[case](client, namespace.name)

        fake_token = opaque_secret("fake-sa-token")
        with running_fake_kube_api(tmp_path, fake_token) as fake:
            fake.add_secret("dfe", SECRET, {"http": b"a"})
            fake.add_secret("dfe", OTHER, {"http": b"a"})
            fake.readable.discard(("dfe", OTHER))
            fake.writable.discard(("dfe", OTHER))
            fake.readable.add(("dfe", ABSENT))
            fake.writable.add(("dfe", ABSENT))
            fake_verify = ssl.create_default_context(cafile=fake.ca_file)
            fake_headers = {"Authorization": f"Bearer {fake_token}"}
            with httpx.Client(base_url=fake.url, verify=fake_verify, headers=fake_headers, timeout=30) as client:
                imitated = _CASES[case](client, "dfe")

        assert real == _EXPECTED[case]
        assert imitated == real

    def test_a_replace_that_changes_nothing_keeps_the_resource_version(self, cluster, namespace, token_file, tmp_path):
        namespace.create_secret(SECRET, {"http": b"a"})
        verify = ssl.create_default_context(cafile=str(cluster.ca_file))
        headers = {"Authorization": f"Bearer {token_file.read_text(encoding='utf-8').strip()}"}
        with httpx.Client(base_url=cluster.api, verify=verify, headers=headers, timeout=30) as client:
            real = _replace_unchanged(client, namespace.name)

        fake_token = opaque_secret("fake-sa-token")
        with running_fake_kube_api(tmp_path, fake_token) as fake:
            fake.add_secret("dfe", SECRET, {"http": b"a"})
            fake_verify = ssl.create_default_context(cafile=fake.ca_file)
            with httpx.Client(
                base_url=fake.url, verify=fake_verify, headers={"Authorization": f"Bearer {fake_token}"}, timeout=30
            ) as client:
                imitated = _replace_unchanged(client, "dfe")

        assert real == (200, True)
        assert imitated == real


def _replace_unchanged(client: httpx.Client, ns: str) -> tuple[int, bool]:
    """Replace a Secret with what was read. Returns the status and whether the resourceVersion stayed put."""
    path = f"/api/v1/namespaces/{ns}/secrets/{SECRET}"
    secret = client.get(path).json()
    response = client.put(path, json=secret)
    return response.status_code, response.json()["metadata"]["resourceVersion"] == secret["metadata"]["resourceVersion"]
