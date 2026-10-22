#  Project:   scalo
#  File:      tests/unit/cli_openapi/test_parts.py
#  Purpose:   The pieces under the commands: pagination, output, errors, profiles and the input document
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit behaviour that the end-to-end commands do not reach on their own."""

import json
import os
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from scalo.cli.openapi import Credential, Response, Store, TransportError, UrllibTransport
from scalo.cli.openapi.client import Client
from scalo.cli.openapi.config import resolve
from scalo.cli.openapi.errors import (
    ApiError,
    CliConfigError,
    CliUsageError,
    ExitCode,
    exit_code_for_status,
    report_for,
    report_for_response,
)
from scalo.cli.openapi.layout import layout_for, option_name
from scalo.cli.openapi.output import apply_query, default_format, render
from scalo.cli.openapi.paginate import collect, decode_starting, encode_resume, single_page
from scalo.cli.openapi.skeleton import load_input
from scalo.cli.openapi.spec import Field, Operation


def _pages(total: int, size: int) -> Callable[[str | None], dict]:
    """A paged list held in memory: token ``p<n>`` is the page starting at item ``n``."""
    items = list(range(total))

    def fetch(token: str | None) -> dict:
        start = int(token[1:]) if token else 0
        end = start + size
        return {"items": items[start:end], "next_page_token": f"p{end}" if end < total else None, "total_size": total}

    return fetch


class TestCollect:
    """Following tokens, cutting at --max-items and resuming."""

    def test_every_page(self):
        assert collect(_pages(5, 2), max_items=None, starting_token=None, warn=print) == {
            "items": [0, 1, 2, 3, 4],
            "total_size": 5,
        }

    def test_a_cut_at_a_page_boundary_resumes_at_the_next_page(self):
        first = collect(_pages(6, 2), max_items=2, starting_token=None, warn=print)

        assert first["items"] == [0, 1]
        assert decode_starting(first["next_page_token"]).page_token == "p2"

    def test_a_cut_on_the_last_item_has_nothing_to_resume(self):
        assert "next_page_token" not in collect(_pages(4, 2), max_items=4, starting_token=None, warn=print)

    def test_a_raw_api_token_starts_a_list(self):
        assert collect(_pages(5, 2), max_items=None, starting_token="p3", warn=print)["items"] == [3, 4]

    def test_a_repeated_token_stops_with_a_warning(self):
        notes = []

        def stuck(token):
            return {"items": [token], "next_page_token": "same"}

        result = collect(stuck, max_items=None, starting_token=None, warn=notes.append)

        assert result["items"] == [None, "same"]
        assert "returned page token 'same' again" in notes[0]

    def test_an_empty_page_stops_a_server_that_keeps_handing_out_tokens(self):
        notes = []
        calls = []

        def endless(token):
            calls.append(token)
            if len(calls) > 50:
                raise AssertionError("pagination kept going past an empty page")
            return {"items": [] if token else [0], "next_page_token": f"t{len(calls)}"}

        result = collect(endless, max_items=None, starting_token=None, warn=notes.append)

        assert result["items"] == [0]
        assert decode_starting(result["next_page_token"]).page_token == "t2"
        assert "empty page" in notes[0]
        assert len(calls) == 2

    def test_the_page_cap_stops_a_list_and_says_where_to_resume(self):
        notes = []

        def one_each(token):
            n = int(token[1:]) if token else 0
            return {"items": [n], "next_page_token": f"p{n + 1}"}

        result = collect(one_each, max_items=None, starting_token=None, warn=notes.append, max_pages=3)

        assert result["items"] == [0, 1, 2]
        assert decode_starting(result["next_page_token"]).page_token == "p3"
        assert "3 pages" in notes[0]

    def test_an_answer_that_is_not_a_page_is_returned_as_is(self):
        assert collect(lambda _token: [1, 2], max_items=1, starting_token=None, warn=print) == [1, 2]

    def test_a_single_page_honours_a_mid_page_resume(self):
        assert single_page(_pages(5, 3), starting_token=encode_resume(None, 1))["items"] == [1, 2]

    @pytest.mark.parametrize("token", ["r1.!!!", "r1." + "eyJ0IjogMX0", "r1." + "eyJzIjogLTF9"])
    def test_a_damaged_resume_token_is_a_usage_error(self, token):
        with pytest.raises(CliUsageError, match="not a token this CLI printed"):
            decode_starting(token)


class TestOutput:
    """Formats and the JMESPath query."""

    def test_defaults_follow_the_verb_on_a_terminal(self):
        assert default_format("get", is_tty=True) == "yaml"
        assert default_format("list", is_tty=True) == "table"
        assert default_format("deploy", is_tty=True) == "json"
        assert default_format("get", is_tty=False) == "json"

    def test_table_falls_back_to_json_without_scalar_columns(self):
        assert json.loads(render([{"nested": {"a": 1}}], "table")) == [{"nested": {"a": 1}}]

    def test_table_cells(self):
        text = render([{"a": True, "b": None, "c": [1]}, {"a": False, "b": 2}], "table")

        assert "true" in text
        assert "false" in text

    def test_an_empty_table(self):
        assert render([], "table") == "\n"

    def test_a_table_ends_with_the_resume_token(self):
        text = render({"items": [{"a": 1}], "next_page_token": "r1.abc"}, "table")

        assert text.endswith("next_page_token: r1.abc\n")
        assert render({"items": [{"a": 1}], "next_page_token": None}, "table").count("next_page_token") == 0

    def test_text_and_yaml(self):
        assert render({"items": [{"a": 1, "b": "x"}]}, "text") == "ITEMS\t1\tx\n"
        assert yaml.safe_load(render({"a": [1]}, "yaml")) == {"a": [1]}

    def test_an_unknown_format(self):
        with pytest.raises(CliUsageError, match="unknown output format"):
            render({}, "xml")

    def test_query_over_plain_data(self):
        assert apply_query({"items": [{"n": 1}, {"n": 2}]}, "items[?n > `1`].n") == [2]
        assert apply_query({"a": 1}, None) == {"a": 1}


class TestErrors:
    """Status mapping and reading whatever error body the API sends."""

    @pytest.mark.parametrize(
        ("status", "code"),
        [(400, 2), (401, 4), (403, 4), (404, 3), (409, 5), (410, 3), (412, 5), (422, 2), (428, 2), (429, 1), (500, 1)],
    )
    def test_status_to_exit_code(self, status, code):
        assert exit_code_for_status(status) == code

    def test_an_http_exception_with_a_dict_detail(self):
        report = report_for_response(Response(409, {}, b'{"detail": {"code": "taken", "message": "name taken"}}'))

        assert (report.error_type, report.message, report.exit_code) == ("taken", "name taken", ExitCode.CONFLICT)

    def test_fastapi_default_validation_errors(self):
        body = {"detail": [{"loc": ["body", "port"], "msg": "not an int"}, {"loc": ["query"], "msg": "bad"}]}
        report = report_for_response(Response(422, {}, json.dumps(body).encode()))

        assert report.errors == (("port", "not an int"), ("", "bad"))

    def test_a_body_that_is_not_json(self):
        report = report_for_response(Response(502, {}, b"<html>bad gateway</html>", "Bad Gateway"))

        assert (report.message, report.retryable) == ("Bad Gateway", True)

    def test_a_json_string_body(self):
        assert report_for_response(Response(500, {}, b'"exploded"')).message == "exploded"

    def test_reports_for_each_known_error(self):
        reports = [report_for(ApiError(Response(404, {}, b""))), report_for(TransportError("down"))]
        reports.append(report_for(CliConfigError("no url")))

        assert [(r.exit_code, r.retryable, r.error_type) for r in reports if r is not None] == [
            (ExitCode.NOT_FOUND, False, "not_found"),
            (ExitCode.GENERAL, True, "connection"),
            (ExitCode.USAGE, False, "config"),
        ]
        assert report_for(ValueError("bug")) is None

    def test_the_text_form_lists_field_errors(self):
        report = report_for_response(
            Response(422, {}, b'{"title": "Unprocessable", "errors": [{"field": "", "detail": "empty"}]}')
        )

        assert report.text() == "Error (422 unprocessable_content): Unprocessable\n  (request): empty"


class TestStore:
    """Profiles, the active pointer and the credential file."""

    def test_round_trip(self, tmp_path):
        store = Store(tmp_path)
        store.create_profile("staging")
        store.set_value("url", "https://s.test", "staging")
        store.set_active_profile("staging")

        assert store.list_profiles() == ["staging"]
        assert store.active_profile() == "staging"
        assert store.profile_items() == {"url": "https://s.test"}

        store.delete_profile("staging")
        assert store.active_profile() == "default"
        assert store.list_profiles() == []

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_credentials_are_owner_only(self, tmp_path):
        store = Store(tmp_path)
        store.save_credential(Credential(account="ops", api_key="k"))

        assert stat.S_IMODE(store.credentials_file.stat().st_mode) == 0o600
        assert store.get_credential("ops") == Credential(account="ops", api_key="k")
        assert store.list_accounts() == ["ops"]

        store.delete_credential("ops")
        assert store.get_credential("ops") is None

    def test_a_credential_repr_hides_the_secret(self):
        assert "s3cret" not in repr(Credential(account="ops", token="s3cret"))

    def test_an_unreadable_credential_file_is_a_config_error(self, tmp_path):
        store = Store(tmp_path)
        store.home.mkdir(parents=True, exist_ok=True)
        store.credentials_file.write_text("{not json", encoding="utf-8")

        with pytest.raises(CliConfigError, match="credentials.json"):
            store.list_accounts()

    def test_a_torn_credential_file_is_never_overwritten(self, tmp_path):
        store = Store(tmp_path)
        store.save_credential(Credential(account="a", token="t-a"))
        store.save_credential(Credential(account="b", token="t-b"))
        torn = store.credentials_file.read_text(encoding="utf-8")[:-5]
        store.credentials_file.write_text(torn, encoding="utf-8")

        with pytest.raises(CliConfigError):
            store.save_credential(Credential(account="c", token="t-c"))
        assert store.credentials_file.read_text(encoding="utf-8") == torn

    def test_a_save_replaces_the_file_rather_than_rewriting_it(self, tmp_path):
        store = Store(tmp_path)
        store.save_credential(Credential(account="a", token="t-a"))
        before = tmp_path / "before.json"
        os.link(store.credentials_file, before)

        store.save_credential(Credential(account="b", token="t-b"))

        assert json.loads(before.read_text(encoding="utf-8")) == {"a": {"token": "t-a"}}
        assert store.list_accounts() == ["a", "b"]
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            ".credentials.lock",
            "before.json",
            "configurations",
            "credentials.json",
        ]

    def test_two_processes_saving_at_once_keep_every_account(self, tmp_path):
        saves = 200
        home, gate = tmp_path / "home", tmp_path / "gate"
        gate.mkdir()
        # Each writer says it is ready, then waits for the go file, so the two run their saves at the same time.
        script = (
            "import sys, time\n"
            "from pathlib import Path\n"
            "from scalo.cli.openapi import Credential, Store\n"
            "home, gate, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]\n"
            "store = Store(home)\n"
            "(gate / f'ready-{name}').touch()\n"
            "deadline = time.monotonic() + 60\n"
            "while not (gate / 'go').exists():\n"
            "    if time.monotonic() > deadline:\n"
            "        sys.exit('the go file never appeared')\n"
            "    time.sleep(0.001)\n"
            f"for index in range({saves}):\n"
            "    store.save_credential(Credential(account=f'{name}-{index}', token='t'))\n"
        )
        writers = [
            subprocess.Popen([sys.executable, "-c", script, str(home), str(gate), name], stderr=subprocess.PIPE)
            for name in ("first", "second")
        ]
        deadline = time.monotonic() + 60
        while not all((gate / f"ready-{name}").exists() for name in ("first", "second")):
            assert time.monotonic() < deadline, "a writer never started"
            time.sleep(0.01)
        (gate / "go").touch()
        failures = [writer.communicate(timeout=120)[1] for writer in writers if writer.wait(timeout=120) != 0]

        assert failures == []
        accounts = Store(home).list_accounts()
        assert len(accounts) == 2 * saves
        assert {"first-0", f"first-{saves - 1}", "second-0", f"second-{saves - 1}"} <= set(accounts)

    def test_a_broken_profile_is_a_config_error(self, tmp_path):
        store = Store(tmp_path)
        store.configurations_dir.mkdir(parents=True)
        (store.configurations_dir / "config_default").write_text("no section header\n", encoding="utf-8")

        with pytest.raises(CliConfigError, match="not a readable INI"):
            store.get_value("url")

    def test_resolution_order(self, tmp_path, monkeypatch):
        store = Store(tmp_path)
        store.set_value("url", "https://profile.test")
        store.set_value("account", "ops")
        store.save_credential(Credential(account="ops", token="stored"))
        for name in ("APP_API_URL", "APP_API_KEY", "APP_API_TOKEN", "APP_PROFILE"):
            monkeypatch.delenv(name, raising=False)

        stored = resolve(store, "APP")
        assert stored.url == "https://profile.test"
        assert stored.credential == Credential(account="ops", token="stored")

        monkeypatch.setenv("APP_API_URL", "https://env.test")
        monkeypatch.setenv("APP_API_TOKEN", "env-token")
        from_env = resolve(store, "APP")
        assert from_env.url == "https://env.test"
        assert from_env.credential == Credential(account="ops", token="env-token")
        assert resolve(store, "APP", url_override="https://flag.test").url == "https://flag.test"


class TestClient:
    """What reaches the wire."""

    def test_booleans_go_as_true_and_false_in_headers_and_the_query(self, http_server):
        server = http_server()
        server.route("GET", "/things", (200, {"Content-Type": "application/json"}, b"[]"))
        operation = Operation(
            operation_id="things.list",
            method="get",
            path="/things",
            hierarchy=("things",),
            verb="list",
            parameters=(Field("X-Strict", "header", "bool"), Field("all", "query", "bool")),
        )

        Client(server.url, None, UrllibTransport()).call(
            operation, {"header": {"X-Strict": True}, "query": {"all": False}}
        )

        assert server.seen[0]["headers"]["x-strict"] == "true"
        assert parse_qs(urlsplit(server.seen[0]["path"]).query) == {"all": ["false"]}


class TestInputDocument:
    """What --cli-input-* accepts."""

    def test_nothing_given(self):
        assert load_input(None, None) == {}
        assert load_input(None, "") == {}

    @pytest.mark.parametrize("document", ["[1, 2]", '{"path": [1]}'])
    def test_a_document_of_the_wrong_shape(self, document):
        with pytest.raises(CliUsageError):
            load_input(document, None)

    def test_json_is_not_read_as_yaml(self):
        with pytest.raises(CliUsageError, match="not valid JSON"):
            load_input("path: {}", None)

    def test_a_missing_file(self, tmp_path):
        with pytest.raises(CliUsageError, match="cannot read"):
            load_input(f"file://{tmp_path / 'missing.json'}", None)


class TestLayout:
    """Option names, collisions and the reserved flags."""

    @pytest.mark.parametrize(
        ("wire", "option"),
        [("If-Match", "if-match"), ("pageSize", "page-size"), ("$filter", "filter"), ("__", "value")],
    )
    def test_option_names(self, wire, option):
        assert option_name(wire) == option

    def test_a_clash_goes_to_the_later_field_with_its_location(self):
        operation = Operation(
            operation_id="things.list",
            method="get",
            path="/things",
            hierarchy=("things",),
            verb="list",
            parameters=(
                Field("query", "query", "str"),
                Field("name", "query", "str"),
                Field("output", "header", "str"),
            ),
            body=(Field("name", "body", "str"), Field("body", "body", "object")),
            body_schema={"type": "object"},
        )
        slots = [slot for slot in layout_for(operation).by_kind("field") if slot.field is not None]
        flags = {f"{slot.field.location}:{slot.field.name}": slot.flag for slot in slots if slot.field is not None}

        assert flags == {
            "query:query": "--query-query",
            "query:name": "--name",
            "header:output": "--header-output",
            "body:name": "--body-name",
            "body:body": "--body-body",
        }
