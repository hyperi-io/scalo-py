#  Project:   scalo
#  File:      src/scalo/mcp/__init__.py
#  Purpose:   MCP tools generated from a scalo.api app's OpenAPI spec, served on the same app
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""MCP tools generated from a scalo.api app's OpenAPI spec, behind the ``mcp`` extra.

Each operation that opts in through ``x-scalo`` becomes one tool, and every tool
call runs in-process through the app with the caller's own bearer token, so RBAC,
If-Match, validation and audit apply unchanged::

    from scalo.api import Hierarchy, McpHints, install, scalo_extra
    from scalo.mcp import mount

    @router.get("/{source}", openapi_extra=scalo_extra(mcp=McpHints()))
    def get_source(source: str) -> Source: ...

    install(app, hierarchy)
    mount(app, issuer="https://idp.example.com/realms/acme")

The server speaks the stateless MCP revision of 2026-07-28, so any replica answers
any request. Install with ``pip install 'scalo[mcp]'``. Base ``import scalo``
never imports this module, the MCP SDK or FastAPI.
"""

try:
    import fastapi
    import mcp
except ImportError as exc:
    raise ImportError("scalo.mcp needs the 'mcp' extra: pip install 'scalo[mcp]'") from exc
del fastapi, mcp

from .server import DEFAULT_CALL_TIMEOUT, DEFAULT_TOOLS_TTL_MS, PROTOCOL_VERSION, McpServer, mount
from .tools import CREATE_ETAG, Argument, McpSpecError, ToolSpec, tools_from_spec

__all__ = [
    "CREATE_ETAG",
    "DEFAULT_CALL_TIMEOUT",
    "DEFAULT_TOOLS_TTL_MS",
    "PROTOCOL_VERSION",
    "Argument",
    "McpServer",
    "McpSpecError",
    "ToolSpec",
    "mount",
    "tools_from_spec",
]
