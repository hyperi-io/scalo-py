#  Project:   scalo
#  File:      src/scalo/cli/openapi/__init__.py
#  Purpose:   A complete CLI generated from an OpenAPI spec, behind the cli extra
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A command-line interface generated from an OpenAPI spec alone, behind the ``cli`` extra.

The spec is the only input, a file or a server's ``/openapi.json``: no FastAPI app
and no route table. The command tree is the spec's resource hierarchy, read from
the ``x-scalo`` extension :mod:`scalo.api` writes::

    from scalo.cli.openapi import SpecCli, load_spec

    cli = SpecCli(load_spec("openapi.json"), name="svc")
    cli.main()        # svc sources rules list --source syslog --output table

Every command takes ``--output``, ``--query`` (JMESPath), ``--cli-input-json`` and
``--cli-input-yaml``, ``--generate-cli-skeleton``, and on a paged list
``--max-items``, ``--starting-token`` and ``--no-paginate``. Install with
``pip install 'scalo[cli]'``. Base ``import scalo`` never imports this package,
FastAPI, uvicorn or mcp.
"""

try:
    import jmespath
except ImportError as exc:
    raise ImportError("scalo.cli.openapi needs the 'cli' extra: pip install 'scalo[cli]'") from exc
del jmespath

from .app import Invocation, SpecCli, invocation
from .config import Credential, Store
from .spec import SpecError, load_spec
from .transport import Response, ScaloHttpTransport, Transport, TransportError, UrllibTransport

__all__ = [
    "Credential",
    "Invocation",
    "Response",
    "ScaloHttpTransport",
    "SpecCli",
    "SpecError",
    "Store",
    "Transport",
    "TransportError",
    "UrllibTransport",
    "invocation",
    "load_spec",
]
