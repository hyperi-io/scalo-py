#  Project:   scalo
#  File:      src/scalo/api/__init__.py
#  Purpose:   API conventions for FastAPI services: one resource hierarchy for API, CLI and MCP
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""API conventions for FastAPI services, behind the ``api`` extra.

One resource hierarchy names every operation, so the spec, the CLI and MCP
tools generated from it agree. The module supplies the operation ids, the
``x-scalo`` OpenAPI extension, ETag and If-Match, ``dry_run``, problem+json
errors, list pagination, ``view``, and a conformance check::

    from fastapi import FastAPI
    from scalo.api import Hierarchy, install

    hierarchy = Hierarchy(base_path="/api/v1", singletons={"deployment"})
    app = FastAPI(generate_unique_id_function=hierarchy.unique_id)
    ...
    install(app, hierarchy)

Install with ``pip install 'scalo[api]'``. Base ``import scalo`` never imports
this module or FastAPI.
"""

try:
    import fastapi
except ImportError as exc:
    raise ImportError("scalo.api needs the 'api' extra: pip install 'scalo[api]'") from exc
del fastapi

from .conformance import ConformanceReport, Violation, assert_conformant, check_conformance
from .extension import ACTION_ATTRIBUTE, EXTENSION, CliHints, McpHints, permission, scalo_extra
from .hierarchy import DEFAULT_PLURALS, Hierarchy, OperationName
from .openapi import annotate_openapi, install
from .pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ListParams,
    ListQuery,
    Page,
    decode_page_token,
    encode_page_token,
    list_query,
    paginate,
)
from .params import DryRun, GetView, ListView, View
from .preconditions import (
    EntityTag,
    PreconditionHeaders,
    Preconditions,
    check_preconditions,
    etag_of,
    format_etag,
    parse_etags,
)
from .problems import (
    PROBLEM_MEDIA_TYPE,
    FieldError,
    Problem,
    ProblemError,
    declare_problem_responses,
    install_problem_handlers,
    problem_response,
)

__all__ = [
    "ACTION_ATTRIBUTE",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_PLURALS",
    "EXTENSION",
    "MAX_PAGE_SIZE",
    "PROBLEM_MEDIA_TYPE",
    "CliHints",
    "ConformanceReport",
    "DryRun",
    "EntityTag",
    "FieldError",
    "GetView",
    "Hierarchy",
    "ListParams",
    "ListQuery",
    "ListView",
    "McpHints",
    "OperationName",
    "Page",
    "PreconditionHeaders",
    "Preconditions",
    "Problem",
    "ProblemError",
    "View",
    "Violation",
    "annotate_openapi",
    "assert_conformant",
    "check_conformance",
    "check_preconditions",
    "declare_problem_responses",
    "decode_page_token",
    "encode_page_token",
    "etag_of",
    "format_etag",
    "install",
    "install_problem_handlers",
    "list_query",
    "paginate",
    "parse_etags",
    "permission",
    "problem_response",
    "scalo_extra",
]
