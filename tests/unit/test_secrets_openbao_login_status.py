#  Project:   scalo
#  File:      tests/unit/test_secrets_openbao_login_status.py
#  Purpose:   Only a 4xx other than 429 is a refused OpenBao login
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Only a 4xx other than 429 is a refused OpenBao login; a 429 or a redirect is the store not answering.

A real local HTTP server answers ``/v1/auth/<mount>/login`` with the status named in the mount, so
each case is a genuine HTTP response the provider has to classify.
"""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scalo.secrets.exceptions import AuthenticationError, ProviderError
from scalo.secrets.providers.openbao import HTTPX_AVAILABLE, OpenBaoProvider
from scalo.secrets.types import OpenBaoConfig

pytestmark = pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")

httpx = pytest.importorskip("httpx")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        status = int(self.path.split("/")[3].removeprefix("status-"))
        self.send_response(status)
        if 300 <= status < 400:
            self.send_header("Location", "/v1/elsewhere")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize(
    ("status", "refused"),
    [
        pytest.param(403, True, id="403-refused"),
        pytest.param(429, False, id="429-rate-limited"),
        pytest.param(307, False, id="307-redirect"),
    ],
)
@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
async def test_login_status_classification(server, status, refused, use_async):
    provider = OpenBaoProvider(
        OpenBaoConfig(
            address=server, auth_method="approle", role_id="role", secret_id="secret", mount=f"status-{status}"
        )
    )

    with pytest.raises(ProviderError) as caught:
        if use_async:
            await provider._authenticate_async()
        else:
            provider._authenticate_sync()

    assert isinstance(caught.value, AuthenticationError) is refused
    assert isinstance(caught.value.__cause__, httpx.HTTPStatusError)
    assert caught.value.__cause__.response.status_code == status
    await provider.close()
