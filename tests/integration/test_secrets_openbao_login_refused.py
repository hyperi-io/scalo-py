#  Project:   scalo
#  File:      tests/integration/test_secrets_openbao_login_refused.py
#  Purpose:   A refused AppRole login is an AuthenticationError chained to the HTTP refusal
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A refused AppRole login against a real OpenBao is an AuthenticationError chained to the refusal.

Uses the ``openbao_endpoint`` fixture from conftest.py. Each test enables AppRole on its own
mount with the root token, so the credentials it refuses or accepts are real ones.
"""

import uuid
from collections.abc import Iterator

import pytest

from scalo.secrets.exceptions import AuthenticationError
from scalo.secrets.providers.openbao import HTTPX_AVAILABLE, OpenBaoProvider
from scalo.secrets.types import OpenBaoConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed"),
]

httpx = pytest.importorskip("httpx")


@pytest.fixture
def approle(openbao_endpoint) -> Iterator[tuple[str, str, str, str]]:
    """Enable AppRole on a throwaway mount and yield (address, mount, role_id, secret_id)."""
    addr, token = openbao_endpoint
    mount = f"approle-{uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=addr, headers={"X-Vault-Token": token}, timeout=10) as root:
        root.post(f"/v1/sys/auth/{mount}", json={"type": "approle"}).raise_for_status()
        root.post(f"/v1/auth/{mount}/role/app", json={"token_ttl": "5m"}).raise_for_status()
        role_id = root.get(f"/v1/auth/{mount}/role/app/role-id").json()["data"]["role_id"]
        secret_id = root.post(f"/v1/auth/{mount}/role/app/secret-id").json()["data"]["secret_id"]
    yield addr, mount, role_id, secret_id
    with httpx.Client(base_url=addr, headers={"X-Vault-Token": token}, timeout=10) as root:
        root.delete(f"/v1/sys/auth/{mount}")


def _provider(addr: str, mount: str, role_id: str, secret_id: str) -> OpenBaoProvider:
    return OpenBaoProvider(
        OpenBaoConfig(address=addr, auth_method="approle", role_id=role_id, secret_id=secret_id, mount=mount)
    )


async def _login(provider: OpenBaoProvider, *, use_async: bool) -> None:
    if use_async:
        await provider._authenticate_async()
    else:
        provider._authenticate_sync()


@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
async def test_good_approle_credentials_log_in(approle, use_async):
    addr, mount, role_id, secret_id = approle
    provider = _provider(addr, mount, role_id, secret_id)

    await _login(provider, use_async=use_async)

    assert provider._token
    await provider.close()


@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
async def test_refused_secret_id_is_an_authentication_error_chained_to_the_refusal(approle, use_async):
    addr, mount, role_id, _ = approle
    provider = _provider(addr, mount, role_id, "not-the-secret-id")

    with pytest.raises(AuthenticationError) as caught:
        await _login(provider, use_async=use_async)

    cause = caught.value.__cause__
    assert isinstance(cause, httpx.HTTPStatusError)
    assert 400 <= cause.response.status_code < 500
    await provider.close()
