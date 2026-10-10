#  Project:   scalo
#  File:      tests/unit/test_secrets_openbao_login_unreachable.py
#  Purpose:   An unreachable OpenBao fails login as ProviderError, never AuthenticationError
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""An unreachable OpenBao fails login as ProviderError, never AuthenticationError."""

import socket
from pathlib import Path

import pytest

from scalo.secrets.exceptions import AuthenticationError, ProviderError
from scalo.secrets.providers.openbao import HTTPX_AVAILABLE, OpenBaoProvider
from scalo.secrets.types import OpenBaoConfig

pytestmark = pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")

httpx = pytest.importorskip("httpx")


def _closed_port() -> int:
    """Return a local port with nothing listening on it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _config(tmp_path: Path, auth_method: str) -> OpenBaoConfig:
    token_path = tmp_path / "sa-token"
    token_path.write_text("service-account-jwt", encoding="utf-8")
    return OpenBaoConfig(
        address=f"http://127.0.0.1:{_closed_port()}",
        auth_method=auth_method,
        role_id="role",
        secret_id="secret",
        role="app",
        token_path=str(token_path),
        timeout_secs=2,
    )


@pytest.mark.parametrize("auth_method", ["approle", "kubernetes"])
@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
async def test_unreachable_store_is_a_provider_error_chained_to_the_transport_error(tmp_path, auth_method, use_async):
    provider = OpenBaoProvider(_config(tmp_path, auth_method))

    with pytest.raises(ProviderError) as caught:
        if use_async:
            await provider._authenticate_async()
        else:
            provider._authenticate_sync()

    assert not isinstance(caught.value, AuthenticationError)
    assert isinstance(caught.value.__cause__, httpx.TransportError)
    await provider.close()
