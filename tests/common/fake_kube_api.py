#  Project:   scalo
#  File:      tests/common/fake_kube_api.py
#  Purpose:   A TLS fake of the Kubernetes API server's Secret endpoints
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A fake Kubernetes API server, serving GET and PUT on Secrets over real TLS.

It holds the API server behaviour the Kubernetes secrets provider depends on: bearer-token
authentication, RBAC on named Secrets, ``resourceVersion`` optimistic concurrency answering 409,
data-key validation answering 422, and a value that is not base64 answering 400, as k3s does
(tests/integration/test_secrets_kubernetes_cluster.py). A test can make a second writer change a
Secret between the provider's read and its replace, queue 429 and 5xx answers, or drop connections.
"""

import base64
import binascii
import datetime
import http.server
import json
import re
import ssl
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_SECRET_PATH = re.compile(r"^/api/v1/namespaces/(?P<ns>[^/]+)/secrets/(?P<name>[^/?]+)$")
_DATA_KEY = re.compile(r"^[-._a-zA-Z0-9]+$")


@dataclass
class FakeKubeApi:
    """State and knobs of a running fake API server."""

    url: str
    ca_file: str
    token: str
    secrets: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    readable: set[tuple[str, str]] = field(default_factory=set)
    writable: set[tuple[str, str]] = field(default_factory=set)
    requests: list[tuple[str, str]] = field(default_factory=list)
    tokens_seen: list[str] = field(default_factory=list)
    before_put: Callable[[dict[str, Any]], None] | None = None
    answer_next: list[tuple[str, int, dict[str, str]]] = field(default_factory=list)
    drop_next: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    _version: int = 100

    def add_secret(self, namespace: str, name: str, data: dict[str, bytes] | None = None) -> None:
        """Store a Secret the service account may get and update, as a least-privilege Role grants."""
        with self.lock:
            self._version += 1
            obj: dict[str, Any] = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "resourceVersion": str(self._version),
                    "creationTimestamp": "2026-10-01T00:00:00Z",
                    "annotations": {"owner": "chart"},
                },
                "type": "Opaque",
            }
            if data is not None:
                obj["data"] = {k: base64.b64encode(v).decode("ascii") for k, v in data.items()}
            self.secrets[(namespace, name)] = obj
            self.readable.add((namespace, name))
            self.writable.add((namespace, name))

    def data(self, namespace: str, name: str) -> dict[str, bytes]:
        """The decoded data of a stored Secret."""
        with self.lock:
            stored = self.secrets[(namespace, name)].get("data") or {}
            return {k: base64.b64decode(v) for k, v in stored.items()}

    def write_behind(self, namespace: str, name: str, key: str, value: bytes) -> None:
        """Change one key as another writer would, bumping the resourceVersion unless the value was already there."""
        encoded = base64.b64encode(value).decode("ascii")
        with self.lock:
            obj = self.secrets[(namespace, name)]
            data = obj.setdefault("data", {})
            if data.get(key) == encoded:
                return
            data[key] = encoded
            self._version += 1
            obj["metadata"]["resourceVersion"] = str(self._version)

    def puts(self) -> int:
        """How many PUTs the server received."""
        return sum(1 for method, _ in self.requests if method == "PUT")

    def gets(self) -> int:
        """How many GETs the server received."""
        return sum(1 for method, _ in self.requests if method == "GET")

    def handle(
        self, method: str, path: str, authorization: str | None, body: bytes
    ) -> tuple[int, dict[str, Any], dict[str, str]] | None:
        """Answer one request as the API server would. None means close the connection unanswered."""
        token = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
        with self.lock:
            self.requests.append((method, path))
            self.tokens_seen.append(token)
            if self.drop_next > 0:
                self.drop_next -= 1
                return None
            queued = next((entry for entry in self.answer_next if entry[0] == method), None)
            if queued is not None:
                self.answer_next.remove(queued)
        if queued is not None:
            _, code, headers = queued
            return code, _status(code, f"queued answer {code}"), headers
        if token != self.token:
            return 401, _status(401, "Unauthorized"), {}
        match = _SECRET_PATH.match(path)
        if match is None:
            return 404, _status(404, "the server could not find the requested resource"), {}
        target = (match["ns"], match["name"])
        if method == "GET":
            return (*self._get(target), {})
        if method == "PUT":
            return (*self._put(target, body), {})
        return 405, _status(405, "method not allowed"), {}

    def _get(self, target: tuple[str, str]) -> tuple[int, dict[str, Any]]:
        with self.lock:
            if target not in self.readable:
                return 403, _status(403, f'secrets "{target[1]}" is forbidden')
            obj = self.secrets.get(target)
            if obj is None:
                return 404, _status(404, f'secrets "{target[1]}" not found')
            return 200, json.loads(json.dumps(obj))

    def _put(self, target: tuple[str, str], body: bytes) -> tuple[int, dict[str, Any]]:
        incoming = json.loads(body)
        if self.before_put is not None:
            self.before_put(incoming)
        with self.lock:
            if target not in self.writable:
                return 403, _status(403, f'secrets "{target[1]}" is forbidden')
            # The API server decodes the body after authorising it and before reading the stored object.
            for value in (incoming.get("data") or {}).values():
                try:
                    base64.b64decode(value, validate=True)
                except binascii.Error, ValueError:
                    return 400, _status(
                        400, 'Secret in version "v1" cannot be handled as a Secret: illegal base64 data at input byte 0'
                    )
            current = self.secrets.get(target)
            if current is None:
                return 404, _status(404, f'secrets "{target[1]}" not found')
            if incoming.get("metadata", {}).get("resourceVersion") != current["metadata"]["resourceVersion"]:
                return 409, _status(
                    409, "the object has been modified; please apply your changes to the latest version"
                )
            for key in incoming.get("data") or {}:
                if not _DATA_KEY.match(key) or len(key) > 253:
                    return 422, _status(
                        422, f"data[{key}]: Invalid value: a valid config key must consist of alphanumeric characters"
                    )
            # A replace that changes nothing is stored as nothing, so the resourceVersion stays.
            if incoming == current:
                return 200, json.loads(json.dumps(current))
            self._version += 1
            incoming["metadata"]["resourceVersion"] = str(self._version)
            self.secrets[target] = incoming
            return 200, json.loads(json.dumps(incoming))


def _status(code: int, message: str) -> dict[str, Any]:
    return {"kind": "Status", "apiVersion": "v1", "status": "Failure", "message": message, "code": code}


def _self_signed(directory: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP384R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA384())
    )
    cert_file, key_file = directory / "apiserver.crt", directory / "apiserver.key"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_file, key_file


@contextmanager
def running_fake_kube_api(directory: Path, token: str) -> Iterator[FakeKubeApi]:
    """Serve a fake API server on localhost over TLS until the block exits."""
    cert_file, key_file = _self_signed(directory)
    state: FakeKubeApi | None = None

    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            assert state is not None
            answer = state.handle(self.command, self.path, self.headers.get("Authorization"), body)
            if answer is None:
                self.close_connection = True
                return
            code, payload, headers = answer
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            self._answer()

        def do_PUT(self) -> None:
            self._answer()

        def do_POST(self) -> None:
            self._answer()

        def do_DELETE(self) -> None:
            self._answer()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_file), str(key_file))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    state = FakeKubeApi(url=f"https://localhost:{server.server_address[1]}", ca_file=str(cert_file), token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
