#  Project:   scalo
#  File:      tests/unit/cli_openapi/conftest.py
#  Purpose:   A real scalo.api service, served in-process, for the generated CLI to drive
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Fixtures: a FastAPI service built to the scalo.api conventions, and a CLI generated from its spec.

The service runs in-process behind Starlette's TestClient, so every command goes
through the real routes, validation, problem+json handlers and pagination. The
CLI sees only the spec, as it does in production.
"""

import json
import logging
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import pytest
from fastapi import APIRouter, FastAPI, Header, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typer.testing import CliRunner

from scalo.api import (
    CliHints,
    DryRun,
    Hierarchy,
    ListParams,
    Page,
    PreconditionHeaders,
    ProblemError,
    etag_of,
    install,
    paginate,
    scalo_extra,
)
from scalo.cli.openapi import Response as CliResponse
from scalo.cli.openapi import SpecCli, Store

BASE_URL = "http://svc.test"
HIERARCHY = Hierarchy(base_path="/api/v1")


class Source(BaseModel):
    """A source, as the test service stores it."""

    name: str
    kind: str = Field("syslog", description="The shipper kind")
    port: int | None = None
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class SourcePatch(BaseModel):
    """The fields a merge patch changes. A field left out keeps its stored value."""

    kind: str | None = None
    port: int | None = None
    tags: list[str] | None = None
    labels: dict[str, str] | None = None


class Rule(BaseModel):
    """A source's routing rule."""

    name: str
    match: str


class Deployed(BaseModel):
    """What a deploy did."""

    source: str
    dry_run: bool


class Seen(BaseModel):
    """The credentials a request arrived with."""

    authorization: str | None = None
    api_key: str | None = None


def build_service() -> FastAPI:
    """The test service: sources, their rules, an action, a hidden route and the error answers."""
    store: dict[str, Source] = {f"src-{i:02d}": Source(name=f"src-{i:02d}", port=5000 + i) for i in range(7)}
    rules = {name: [Rule(name=f"{name}-r{j}", match=f"host == 'h{j}'") for j in range(3)] for name in store}
    router = APIRouter(prefix="/sources")

    @router.get("", openapi_extra=scalo_extra(public=True))
    def list_sources(query: ListParams) -> Page[Source]:
        """List sources."""
        found = [source for _, source in sorted(store.items())]
        if query.filter:
            found = [source for source in found if source.kind == query.filter]
        return paginate(found, query)

    @router.get("/{source}", openapi_extra=scalo_extra(public=True))
    def get_source(source: str) -> Source:
        """Get one source."""
        if source not in store:
            raise ProblemError(404, f"no source {source!r}", code="source_not_found")
        return store[source]

    @router.put("/{source}", openapi_extra=scalo_extra(public=True))
    def apply_source(
        source: str, body: Source, pre: PreconditionHeaders, dry_run: DryRun, response: Response
    ) -> Source:
        """Create or replace a source."""
        current = store.get(source)
        pre.check(etag_of(current) if current is not None else None)
        if not dry_run:
            store[source] = body
        response.headers["ETag"] = etag_of(body)
        return body

    @router.patch("/{source}", openapi_extra=scalo_extra(public=True))
    def update_source(
        source: str, body: SourcePatch, pre: PreconditionHeaders, dry_run: DryRun, response: Response
    ) -> Source:
        """Change some of a source's fields."""
        current = store.get(source)
        if current is None:
            raise ProblemError(404, f"no source {source!r}", code="source_not_found")
        pre.check(etag_of(current))
        changed = current.model_copy(update=body.model_dump(exclude_unset=True))
        if not dry_run:
            store[source] = changed
        response.headers["ETag"] = etag_of(changed)
        return changed

    @router.delete("/{source}", status_code=204, openapi_extra=scalo_extra(public=True))
    def delete_source(source: str, pre: PreconditionHeaders, dry_run: DryRun) -> None:
        """Delete a source."""
        current = store.get(source)
        if current is None:
            raise ProblemError(404, f"no source {source!r}", code="source_not_found")
        pre.check(etag_of(current))
        if not dry_run:
            del store[source]

    @router.get("/{source}/rules", openapi_extra=scalo_extra(public=True))
    def list_rules(source: str, query: ListParams) -> Page[Rule]:
        """List a source's rules."""
        return paginate(rules.get(source, []), query)

    @router.post(
        "/{source}/deploy",
        openapi_extra=scalo_extra(public=True, cli=CliHints(aliases=("ship",), positional=("source",))),
    )
    def deploy_source(source: str, dry_run: DryRun) -> Deployed:
        """Deploy a source."""
        return Deployed(source=source, dry_run=dry_run)

    @router.get("/{source}/secret", openapi_extra=scalo_extra(verb="secret", public=True, cli=CliHints(hidden=True)))
    def secret(source: str) -> dict[str, str]:
        """Not for the CLI."""
        return {"source": source}

    whoami = APIRouter(prefix="/session")

    @whoami.get("", openapi_extra=scalo_extra(verb="whoami", public=True))
    def who(
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None, alias="X-API-Key"),
    ) -> Seen:
        """Report the credentials the request carried."""
        return Seen(authorization=authorization, api_key=x_api_key)

    app = FastAPI(title="Test service", description="A test service.", generate_unique_id_function=HIERARCHY.unique_id)
    app.include_router(router, prefix="/api/v1")
    app.include_router(whoami, prefix="/api/v1")
    install(app, HIERARCHY)
    return app


@dataclass
class AppTransport:
    """Sends the CLI's requests into an in-process app, keeping what each one carried."""

    app: FastAPI
    sent: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._client = TestClient(self.app, base_url=BASE_URL, raise_server_exceptions=True)

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        credentials: Mapping[str, str],
        content: bytes | None,
        timeout: float,
    ) -> CliResponse:
        self.sent.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "credentials": dict(credentials),
                "body": json.loads(content) if content else None,
            }
        )
        reply = self._client.request(method, url, headers={**headers, **credentials}, content=content)
        return CliResponse(
            reply.status_code, {k.lower(): v for k, v in reply.headers.items()}, reply.content, reply.reason_phrase
        )


type Answer = tuple[int, dict[str, str], bytes]


class _Handler(BaseHTTPRequestHandler):
    """Answers from the server's route table and records every request."""

    server: _Server

    def _serve(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        path = urlsplit(self.path).path
        headers = {name.lower(): value for name, value in self.headers.items()}
        self.server.seen.append({"method": self.command, "path": self.path, "headers": headers, "body": body})
        answers = self.server.routes.get((self.command, path)) or [(404, {}, b"")]
        status, headers, content = answers.pop(0) if len(answers) > 1 else answers[0]
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # http.server dispatches on these exact names.
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _serve  # noqa: N815

    def log_message(self, format: str, *args: Any) -> None:
        return None


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.routes: dict[tuple[str, str], list[Answer]] = {}
        self.seen: list[dict[str, Any]] = []

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def route(self, method: str, path: str, *answers: Answer) -> None:
        """Answer ``method path`` with each answer in turn, repeating the last."""
        self.routes[(method, path)] = list(answers)


@pytest.fixture
def http_server() -> Iterator[Any]:
    """Start real HTTP servers on loopback ports, each with its own route table."""
    started: list[_Server] = []

    def start() -> _Server:
        server = _Server()
        threading.Thread(target=server.serve_forever, name="cli-openapi-test-http", daemon=True).start()
        started.append(server)
        return server

    yield start
    for server in started:
        server.shutdown()
        server.server_close()


@pytest.fixture
def service() -> FastAPI:
    return build_service()


@pytest.fixture
def spec(service: FastAPI) -> dict[str, Any]:
    return service.openapi()


@pytest.fixture
def transport(service: FastAPI, caplog: pytest.LogCaptureFixture) -> AppTransport:
    # The TestClient logs each request at INFO. Under log_cli that line suspends pytest's
    # capture mid-command, which swaps sys.stdout under CliRunner and loses the output.
    caplog.set_level(logging.WARNING, logger="httpx2")
    return AppTransport(service)


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "config")


@pytest.fixture
def cli(spec: dict[str, Any], transport: AppTransport, store: Store, monkeypatch: pytest.MonkeyPatch) -> SpecCli:
    for name in ("SVC_API_URL", "SVC_API_KEY", "SVC_API_TOKEN", "SVC_PROFILE", "SVC_OUTPUT", "SVC_CONFIG_HOME"):
        monkeypatch.delenv(name, raising=False)
    return SpecCli(spec, name="svc", version="1.2.3", transport=transport, store=store)


@dataclass(frozen=True)
class Run:
    """One CLI run's outcome."""

    exit_code: int
    stdout: str
    stderr: str


@pytest.fixture
def run(cli: SpecCli) -> Any:
    """Run the CLI on an argument list, as ``svc <args>``."""
    runner = CliRunner()

    def invoke(*args: str) -> Run:
        result = runner.invoke(cli.app(list(args)), list(args), prog_name="svc")
        return Run(result.exit_code, result.stdout, result.stderr)

    return invoke
