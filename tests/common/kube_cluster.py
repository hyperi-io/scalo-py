#  Project:   scalo
#  File:      tests/common/kube_cluster.py
#  Purpose:   A real Kubernetes API server for integration tests: an existing one, or k3s in Docker
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A real Kubernetes API server for the secrets provider's integration tests.

Resolution, as tests/README.md documents: ``SCALO_TEST_K8S_API``, ``SCALO_TEST_K8S_TOKEN_FILE`` and
``SCALO_TEST_K8S_CA_FILE`` name an existing API server and a token that may create and delete namespaces and
the ServiceAccounts, Roles, RoleBindings and Secrets in them. Unset, k3s starts in Docker, API server only.
Neither available, the tests skip locally and fail when ``CI`` is set.

Each test works in a namespace of its own, deleted afterwards, so an existing cluster keeps nothing.
"""

import base64
import os
import re
import shutil
import ssl
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

K3S_IMAGE = "rancher/k3s:v1.37.1-k3s1@sha256:ca7f37d993d82ef0dcdcfecb2e0e2618ea541dbaffc620c8cedebe01a82acd0d"
REPO = "scalo-py"
SERVICE = "k3s"
SUITE_LABEL = f"{REPO}-integration"

# Only the API server and its controllers run: no kubelet, so no privileges and no pods.
_K3S_ARGS = [
    "server",
    "--disable-agent",
    "--tls-san=127.0.0.1",
    "--disable=traefik,servicelb,metrics-server,local-storage,coredns",
    "--disable-helm-controller",
    "--disable-network-policy",
    "--disable-cloud-controller",
]
_READY_DEADLINE_SECS = 120.0
_ADMIN = "scalo-test-admin"


class ClusterUnavailable(Exception):
    """No API server could be found or started. The message says why."""


def container_name(test: str, worker: str | None = None) -> str:
    """``<repo>-test-integration-<test>[-<xdist worker>]-k3s``, lowercased with other characters as ``-``."""
    parts = [REPO, "test", "integration", test, *([worker] if worker else []), SERVICE]
    return re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")


def _docker(*args: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def reap_stale(name: str) -> None:
    """Remove a stopped container left holding ``name``. A running one belongs to a concurrent run and stays."""
    if _docker("ps", "-q", "--filter", f"name=^{name}$").stdout.strip():
        return
    _docker("rm", "-f", "-v", name)


def remove(name: str) -> None:
    """Remove the container and its anonymous volumes."""
    _docker("rm", "-f", "-v", name)


def inspect(name: str, template: str) -> str:
    """``docker inspect`` of the container through a Go template, empty when there is no such container."""
    return _docker("inspect", name, "--format", template).stdout.strip()


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


def _exec(name: str, *command: str) -> str:
    result = _docker("exec", name, *command)
    if result.returncode != 0:
        raise ClusterUnavailable(f"docker exec {' '.join(command[:3])} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def start_k3s(name: str, workdir: Path) -> KubeCluster:
    """Start k3s in Docker as ``name`` and make an admin token for it. The caller removes the container.

    Raises:
        ClusterUnavailable: Docker is missing, the start failed, or the API server was not ready in time.
            A container that started is removed before this is raised.
    """
    if shutil.which("docker") is None or _docker("info", timeout=20).returncode != 0:
        raise ClusterUnavailable("Docker is not available")
    reap_stale(name)
    labels = {
        "io.hyperi.test.suite": SUITE_LABEL,
        "io.hyperi.test.repo": REPO,
        "io.hyperi.test.service": SERVICE,
        "io.hyperi.test.owner-pid": str(os.getpid()),
    }
    label_args = [arg for key, value in labels.items() for arg in ("--label", f"{key}={value}")]
    started = _docker(
        "run", "-d", "--name", name, *label_args, "-p", "127.0.0.1::6443", K3S_IMAGE, *_K3S_ARGS, timeout=300
    )
    if started.returncode != 0:
        raise ClusterUnavailable(f"docker run {name} failed: {started.stderr.strip()[:300]}")
    try:
        return _prepare(name, workdir)
    except BaseException:
        remove(name)
        raise


def _prepare(name: str, workdir: Path) -> KubeCluster:
    """Wait for the API server in ``name``, then fetch its CA and mint a cluster-admin token."""
    deadline = time.monotonic() + _READY_DEADLINE_SECS
    while _docker("exec", name, "kubectl", "get", "--raw", "/readyz").stdout.strip() != "ok":
        if time.monotonic() > deadline:
            raise ClusterUnavailable(f"k3s in {name} was not ready within {_READY_DEADLINE_SECS:.0f} s")
        time.sleep(0.5)
    published = _docker("port", name, "6443/tcp").stdout.strip()
    if not published:
        raise ClusterUnavailable(f"{name} published no port for the API server")
    port = published.splitlines()[0].rsplit(":", 1)[-1]
    ca_file = workdir / "ca.crt"
    ca_file.write_text(_exec(name, "cat", "/var/lib/rancher/k3s/server/tls/server-ca.crt"), encoding="utf-8")
    _exec(name, "kubectl", "create", "serviceaccount", _ADMIN, "-n", "kube-system")
    _exec(
        name,
        "kubectl",
        "create",
        "clusterrolebinding",
        _ADMIN,
        "--clusterrole=cluster-admin",
        f"--serviceaccount=kube-system:{_ADMIN}",
    )
    token_file = workdir / "admin-token"
    token_file.touch(mode=0o600)
    token = _exec(name, "kubectl", "create", "token", _ADMIN, "-n", "kube-system", "--duration=2h")
    token_file.write_text(token.strip(), encoding="utf-8")
    return KubeCluster(api=f"https://127.0.0.1:{port}", ca_file=ca_file, admin_token_file=token_file, container=name)


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
