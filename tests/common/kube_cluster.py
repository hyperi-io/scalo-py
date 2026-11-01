#  Project:   scalo
#  File:      tests/common/kube_cluster.py
#  Purpose:   A real Kubernetes API server for integration tests: an existing one, or k3s in Docker
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A real Kubernetes API server for the secrets provider's integration tests.

Resolution, as tests/TESTING.md documents: ``SCALO_TEST_K8S_API``, ``SCALO_TEST_K8S_TOKEN_FILE`` and
``SCALO_TEST_K8S_CA_FILE`` name an existing API server and a token that may create and delete namespaces and
the ServiceAccounts, Roles, RoleBindings and Secrets in them. Unset, the run's one k3s starts in Docker, API
server only, through the shared-service owner. Neither available, the tests skip locally and fail in CI.

Each test works in a namespace of its own, deleted afterwards, so an existing cluster keeps nothing.
"""

import base64
import os
import ssl
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from scalo.deployment.test_support.shared_service import (
    ExecReady,
    ServiceSpec,
    SharedServiceError,
    Suite,
    acquire,
)

K3S_IMAGE = "rancher/k3s:v1.37.1-k3s1@sha256:ca7f37d993d82ef0dcdcfecb2e0e2618ea541dbaffc620c8cedebe01a82acd0d"
K3S_PORT = 6443

# Only the API server and its controllers run: no kubelet, so no privileges and no pods.
_K3S_ARGS = (
    "server",
    "--disable-agent",
    "--tls-san=127.0.0.1",
    "--disable=traefik,servicelb,metrics-server,local-storage,coredns",
    "--disable-helm-controller",
    "--disable-network-policy",
    "--disable-cloud-controller",
)
_READY_DEADLINE_SECS = 120.0
_ADMIN = "scalo-test-admin"


class ClusterUnavailable(Exception):
    """No API server could be found or started. The message says why."""


def k3s_spec() -> ServiceSpec:
    """The run's k3s, ready once its API server answers ``/readyz``."""
    return ServiceSpec(
        service="k3s",
        image=K3S_IMAGE,
        startup_timeout=_READY_DEADLINE_SECS,
        ready=ExecReady(("kubectl", "get", "--raw", "/readyz"), "ok"),
        ports=(K3S_PORT,),
        args=_K3S_ARGS,
    )


@dataclass
class KubeCluster:
    """An API server and an admin bearer token for it."""

    api: str
    ca_file: Path
    admin_token_file: Path
    container: str | None = None

    def admin(self) -> httpx.Client:
        """An HTTP client acting as the cluster admin."""
        token = self.admin_token_file.read_text(encoding="utf-8").strip()
        return httpx.Client(
            base_url=self.api,
            verify=ssl.create_default_context(cafile=str(self.ca_file)),
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )


def existing_cluster() -> KubeCluster | None:
    """The API server the environment names, or None when it names none.

    Raises:
        ClusterUnavailable: Some but not all of the variables are set, or the API server does not answer.
    """
    names = ("SCALO_TEST_K8S_API", "SCALO_TEST_K8S_TOKEN_FILE", "SCALO_TEST_K8S_CA_FILE")
    values = [os.environ.get(name) for name in names]
    if not any(values):
        return None
    if not all(values):
        raise ClusterUnavailable(f"set all of {', '.join(names)} to use an existing API server")
    api, token_file, ca_file = (value or "" for value in values)
    cluster = KubeCluster(api=api.rstrip("/"), ca_file=Path(ca_file), admin_token_file=Path(token_file))
    try:
        with cluster.admin() as admin:
            admin.get("/version").raise_for_status()
    except (httpx.HTTPError, OSError) as e:
        raise ClusterUnavailable(f"SCALO_TEST_K8S_API {api} did not answer: {e}") from e
    return cluster


def shared_k3s(suite: Suite, workdir: Path) -> KubeCluster:
    """The run's k3s, with its CA and a cluster-admin token written under ``workdir``.

    Every process of the run joins the one container and mints a token of its own.

    Raises:
        ClusterUnavailable: The container did not start or the admin account could not be made.
    """
    try:
        container = acquire(suite, k3s_spec())
        ca_file = workdir / "ca.crt"
        ca_file.write_text(container.read_file("/var/lib/rancher/k3s/server/tls/server-ca.crt"), encoding="utf-8")
        # Every worker runs these, so one another worker made already counts, and anything else fails.
        account = f"kubectl -n kube-system create serviceaccount {_ADMIN} 2>/dev/null || kubectl -n kube-system get serviceaccount {_ADMIN}"
        container.exec("sh", "-c", account)
        grant = (
            f"kubectl create clusterrolebinding {_ADMIN} --clusterrole=cluster-admin "
            f"--serviceaccount=kube-system:{_ADMIN} 2>/dev/null || kubectl get clusterrolebinding {_ADMIN}"
        )
        container.exec("sh", "-c", grant)
        token = container.exec("kubectl", "create", "token", _ADMIN, "-n", "kube-system", "--duration=2h")
    except SharedServiceError as e:
        raise ClusterUnavailable(str(e)) from e
    token_file = workdir / "admin-token"
    token_file.touch(mode=0o600)
    token_file.write_text(token.strip(), encoding="utf-8")
    return KubeCluster(
        api=f"https://{container.addr(K3S_PORT)}",
        ca_file=ca_file,
        admin_token_file=token_file,
        container=container.name,
    )


def _encoded(data: dict[str, bytes]) -> dict[str, str]:
    return {key: base64.b64encode(value).decode("ascii") for key, value in data.items()}


class Namespace:
    """One test's namespace on the cluster, with the admin operations a test needs inside it."""

    def __init__(self, admin: httpx.Client) -> None:
        """Create a namespace with a unique name."""
        self.admin = admin
        self.name = f"scalo-test-{uuid.uuid4().hex[:10]}"
        self._post("/api/v1/namespaces", {"metadata": {"name": self.name}})

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.admin.post(path, json=body)
        response.raise_for_status()
        return response.json()

    def delete(self) -> None:
        """Delete the namespace and everything in it. Deletion finishes in the background."""
        self.admin.delete(f"/api/v1/namespaces/{self.name}")

    def grant(self, secret_names: list[str], token_file: Path) -> None:
        """Make a service account that may get and update the named Secrets only, and write its token to ``token_file``."""
        ns = f"/api/v1/namespaces/{self.name}"
        rbac = f"/apis/rbac.authorization.k8s.io/v1/namespaces/{self.name}"
        account = "scalo-provider"
        self._post(f"{ns}/serviceaccounts", {"metadata": {"name": account}})
        self._post(
            f"{rbac}/roles",
            {
                "metadata": {"name": account},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["secrets"],
                        "resourceNames": secret_names,
                        "verbs": ["get", "update"],
                    }
                ],
            },
        )
        self._post(
            f"{rbac}/rolebindings",
            {
                "metadata": {"name": account},
                "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": account},
                "subjects": [{"kind": "ServiceAccount", "name": account, "namespace": self.name}],
            },
        )
        issued = self._post(f"{ns}/serviceaccounts/{account}/token", {"spec": {"expirationSeconds": 3600}})
        token_file.touch(mode=0o600)
        token_file.write_text(issued["status"]["token"], encoding="utf-8")

    def create_secret(self, name: str, data: dict[str, bytes]) -> dict[str, Any]:
        """Create a Secret holding ``data``."""
        body = {"metadata": {"name": name}, "type": "Opaque", "data": _encoded(data)}
        return self._post(f"/api/v1/namespaces/{self.name}/secrets", body)

    def read_secret(self, name: str) -> dict[str, Any]:
        """The stored Secret object."""
        response = self.admin.get(f"/api/v1/namespaces/{self.name}/secrets/{name}")
        response.raise_for_status()
        return response.json()

    def data(self, name: str) -> dict[str, bytes]:
        """The decoded data of a stored Secret."""
        return {key: base64.b64decode(value) for key, value in (self.read_secret(name).get("data") or {}).items()}

    def write_behind(self, name: str, key: str, value: bytes) -> None:
        """Change one key as another writer would, which moves the Secret's resourceVersion on."""
        secret = self.read_secret(name)
        secret.setdefault("data", {})[key] = base64.b64encode(value).decode("ascii")
        self.admin.put(f"/api/v1/namespaces/{self.name}/secrets/{name}", json=secret).raise_for_status()
