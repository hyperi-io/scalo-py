#  Project:   scalo
#  File:      tests/unit/cli_openapi/test_commands.py
#  Purpose:   Generated commands driving a real scalo.api service: output, query, input, errors
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Each generated command, run against the in-process service the conftest builds."""

import json
import sys

import pytest
import yaml

from scalo.cli.openapi import Credential
from scalo.cli.openapi import app as app_module
from scalo.cli.openapi.errors import ExitCode

URL = ("--endpoint-url", "http://svc.test")


class TestTree:
    """The command tree the service's spec gives."""

    def test_the_tree_is_the_resource_hierarchy(self, cli):
        assert cli.command_paths() == [
            ("session", "whoami"),
            ("sources", "apply"),
            ("sources", "delete"),
            ("sources", "deploy"),
            ("sources", "get"),
            ("sources", "list"),
            ("sources", "rules", "list"),
            ("sources", "update"),
        ]

    def test_a_hidden_operation_has_no_command(self, run):
        result = run(*URL, "sources", "secret", "--source", "src-01")

        assert result.exit_code == ExitCode.USAGE
        assert "No such command 'secret'" in result.stderr

    def test_root_help_lists_the_groups(self, run):
        result = run("--help")

        assert result.exit_code == 0
        assert "sources" in result.stdout
        assert "session" in result.stdout

    def test_version(self, run):
        result = run("--version")

        assert result.exit_code == 0
        assert result.stdout.strip() == "svc 1.2.3"


class TestOutput:
    """``--output`` and ``--query`` over a real answer."""

    def test_get_prints_json_off_a_terminal(self, run):
        result = run(*URL, "sources", "get", "--source", "src-03")

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"name": "src-03", "kind": "syslog", "port": 5003, "tags": [], "labels": {}}

    def test_yaml(self, run):
        result = run(*URL, "--output", "yaml", "sources", "get", "--source", "src-03")

        assert yaml.safe_load(result.stdout)["port"] == 5003

    def test_global_options_work_after_the_command(self, run):
        result = run("sources", "get", "--source", "src-03", "-o", "yaml", *URL)

        assert result.exit_code == 0, result.stderr
        assert yaml.safe_load(result.stdout)["name"] == "src-03"

    def test_table_has_a_row_per_item(self, run):
        result = run(*URL, "-o", "table", "sources", "list")

        assert result.exit_code == 0, result.stderr
        assert result.stdout.count("src-0") == 7
        assert "name" in result.stdout
        assert "port" in result.stdout

    def test_query_applies_before_formatting(self, run):
        result = run(*URL, "--query", "items[].port", "sources", "list")

        assert json.loads(result.stdout) == [5000, 5001, 5002, 5003, 5004, 5005, 5006]

    def test_a_bad_query_is_a_usage_error(self, run):
        result = run(*URL, "--query", "items[", "sources", "list")

        assert result.exit_code == ExitCode.USAGE
        assert "invalid --query" in result.stderr


class TestPagination:
    """Lists follow page_token until the last page, after the AWS CLI's paginator."""

    def test_every_page_is_followed(self, run, transport):
        result = run(*URL, "sources", "list", "--page-size", "2")

        assert result.exit_code == 0, result.stderr
        body = json.loads(result.stdout)
        assert [item["name"] for item in body["items"]] == [f"src-{i:02d}" for i in range(7)]
        assert "next_page_token" not in body
        assert len(transport.sent) == 4

    def test_max_items_cuts_mid_page_and_the_token_resumes_there(self, run):
        first = json.loads(run(*URL, "sources", "list", "--page-size", "3", "--max-items", "4").stdout)
        assert [item["name"] for item in first["items"]] == ["src-00", "src-01", "src-02", "src-03"]

        rest = run(*URL, "sources", "list", "--page-size", "3", "--starting-token", first["next_page_token"])

        assert [item["name"] for item in json.loads(rest.stdout)["items"]] == ["src-04", "src-05", "src-06"]

    def test_no_paginate_prints_one_page_as_the_api_sent_it(self, run, transport):
        result = run(*URL, "--no-paginate", "sources", "list", "--page-size", "2")

        body = json.loads(result.stdout)
        assert len(body["items"]) == 2
        assert body["next_page_token"]
        assert len(transport.sent) == 1

    def test_a_cut_short_table_ends_with_its_resume_token(self, run):
        table = run(*URL, "-o", "table", "sources", "list", "--page-size", "3", "--max-items", "4")

        assert table.exit_code == 0, table.stderr
        last = table.stdout.strip().splitlines()[-1]
        assert last.startswith("next_page_token: ")
        rest = run(
            *URL, "sources", "list", "--page-size", "3", "--starting-token", last.removeprefix("next_page_token: ")
        )
        assert [item["name"] for item in json.loads(rest.stdout)["items"]] == ["src-04", "src-05", "src-06"]

    def test_max_items_with_no_paginate_is_refused(self, run):
        result = run(*URL, "sources", "list", "--no-paginate", "--max-items", "2")

        assert result.exit_code == ExitCode.USAGE
        assert "--no-paginate" in result.stderr

    def test_filter_reaches_every_page(self, run, transport):
        run(*URL, "sources", "list", "--page-size", "3", "--filter", "syslog")

        assert all("filter=syslog" in sent["url"] for sent in transport.sent)

    def test_a_child_list_takes_its_parent_as_an_option(self, run):
        result = run(*URL, "sources", "rules", "list", "--source", "src-02")

        assert [rule["name"] for rule in json.loads(result.stdout)["items"]] == ["src-02-r0", "src-02-r1", "src-02-r2"]


class TestInput:
    """Field options, ``--body``, ``--cli-input-*`` and ``--generate-cli-skeleton``."""

    def test_field_options_build_the_body(self, run, transport):
        result = run(
            *URL, "sources", "apply", "--source", "new", "--name", "new", "--port", "7", "--tags", "a", "--tags", "b",
            "--labels", '{"team": "x"}', "--if-none-match", "*",
        )  # fmt: skip

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {
            "name": "new",
            "kind": "syslog",
            "port": 7,
            "tags": ["a", "b"],
            "labels": {"team": "x"},
        }
        assert transport.sent[-1]["headers"]["If-None-Match"] == "*"

    def test_body_from_a_file_with_a_field_option_over_it(self, run, tmp_path):
        source = tmp_path / "source.yaml"
        source.write_text("name: filed\nkind: beats\nport: 9\n", encoding="utf-8")

        result = run(
            *URL,
            "sources",
            "apply",
            "--source",
            "filed",
            "--body",
            f"file://{source}",
            "--port",
            "10",
            "--if-none-match",
            "*",
        )

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout)["kind"] == "beats"
        assert json.loads(result.stdout)["port"] == 10

    def test_cli_input_yaml_supplies_every_section(self, run, transport):
        document = "path: {source: doc}\nquery: {dry_run: true}\nheader: {If-None-Match: '*'}\nbody: {name: doc}\n"

        result = run(*URL, "sources", "apply", "--cli-input-yaml", document)

        assert result.exit_code == 0, result.stderr
        assert "dry_run=true" in transport.sent[-1]["url"]
        assert run(*URL, "sources", "get", "--source", "doc").exit_code == ExitCode.NOT_FOUND

    def test_a_yaml_date_in_the_body_is_sent_as_iso_8601(self, run, transport):
        document = (
            "path: {source: dated}\nheader: {If-None-Match: '*'}\n"
            "body: {name: dated, labels: {since: 2026-10-22, at: 2026-10-22T10:30:00Z}}\n"
        )

        result = run(*URL, "sources", "apply", "--cli-input-yaml", document)

        assert result.exit_code == 0, result.stderr
        labels = transport.sent[-1]["body"]["labels"]
        assert labels["since"] == "2026-10-22"
        assert labels["at"].startswith("2026-10-22T10:30:00")

    def test_a_yaml_value_json_cannot_carry_is_a_usage_error(self, run, transport):
        document = (
            "path: {source: blob}\nheader: {If-None-Match: '*'}\nbody: {name: blob, labels: {raw: !!binary aGk=}}\n"
        )

        result = run(*URL, "sources", "apply", "--cli-input-yaml", document)

        assert result.exit_code == ExitCode.USAGE
        assert "cannot carry" in result.stderr
        assert transport.sent == []

    def test_a_flag_wins_over_the_input_document(self, run, transport):
        run(*URL, "sources", "get", "--cli-input-json", '{"path": {"source": "src-01"}}', "--source", "src-02")

        assert transport.sent[-1]["url"].endswith("/sources/src-02")

    def test_an_empty_placeholder_is_not_sent(self, run, transport):
        document = json.dumps({"path": {"source": "src-01"}, "header": {"If-Match": ""}, "query": {"filter": None}})

        result = run(*URL, "sources", "get", "--cli-input-json", document)

        assert result.exit_code == 0, result.stderr
        assert "If-Match" not in transport.sent[-1]["headers"]
        assert "?" not in transport.sent[-1]["url"]

    def test_an_unknown_section_is_refused(self, run):
        result = run(*URL, "sources", "get", "--cli-input-json", '{"source": "src-01"}')

        assert result.exit_code == ExitCode.USAGE
        assert "unknown section" in result.stderr

    def test_both_input_documents_are_refused(self, run):
        result = run(*URL, "sources", "get", "--cli-input-json", "{}", "--cli-input-yaml", "{}")

        assert result.exit_code == ExitCode.USAGE

    def test_skeleton_has_a_section_per_input(self, run, transport):
        result = run("sources", "apply", "--generate-cli-skeleton")

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {
            "path": {"source": None},
            "query": {"dry_run": None},
            "header": {"If-Match": None, "If-None-Match": None},
            "body": {"name": None, "kind": None, "port": None, "tags": [None], "labels": None},
        }
        assert transport.sent == []

    def test_a_filled_skeleton_sends_only_what_was_filled(self, run, transport, tmp_path):
        document = yaml.safe_load(run("-o", "yaml", "sources", "apply", "--generate-cli-skeleton").stdout)
        document["path"]["source"] = "src-01"
        document["header"]["If-Match"] = "*"
        document["body"]["name"] = "src-01"
        path = tmp_path / "apply.yaml"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")

        result = run(*URL, "sources", "apply", "--cli-input-yaml", f"file://{path}")

        assert result.exit_code == 0, result.stderr
        assert transport.sent[-1]["body"] == {"name": "src-01"}
        assert transport.sent[-1]["url"] == "http://svc.test/api/v1/sources/src-01"

    def test_a_filled_skeleton_keeps_every_field_it_left_alone(self, run, tmp_path):
        document = yaml.safe_load(run("-o", "yaml", "sources", "update", "--generate-cli-skeleton").stdout)
        document["path"]["source"] = "src-01"
        document["header"]["If-Match"] = "*"
        document["body"]["port"] = 6001
        document["body"]["tags"] = ["edge"]
        path = tmp_path / "update.yaml"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")

        result = run(*URL, "sources", "update", "--cli-input-yaml", f"file://{path}")

        assert result.exit_code == 0, result.stderr
        stored = json.loads(run(*URL, "sources", "get", "--source", "src-01").stdout)
        assert stored == {"name": "src-01", "kind": "syslog", "port": 6001, "tags": ["edge"], "labels": {}}

    def test_an_explicit_empty_value_in_the_document_is_sent(self, run, transport):
        document = {"path": {"source": "src-02"}, "header": {"If-Match": "*"}, "body": {"tags": [], "labels": {}}}

        result = run(*URL, "sources", "update", "--cli-input-json", json.dumps(document))

        assert result.exit_code == 0, result.stderr
        assert transport.sent[-1]["body"] == {"tags": [], "labels": {}}

    def test_skeleton_as_yaml_round_trips_through_cli_input_yaml(self, run, tmp_path):
        document = yaml.safe_load(run("-o", "yaml", "sources", "deploy", "--generate-cli-skeleton").stdout)
        document["path"]["source"] = "src-04"
        path = tmp_path / "deploy.yaml"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")

        result = run(*URL, "sources", "deploy", "--cli-input-yaml", f"file://{path}")

        assert json.loads(result.stdout) == {"source": "src-04", "dry_run": False}

    def test_a_missing_required_parameter_names_its_option(self, run, transport):
        result = run(*URL, "sources", "get")

        assert result.exit_code == ExitCode.USAGE
        assert "--source" in result.stderr
        assert transport.sent == []

    def test_positional_and_alias_from_the_cli_hints(self, run):
        result = run(*URL, "sources", "ship", "src-05", "-n")

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"source": "src-05", "dry_run": True}

    def test_invalid_json_in_an_object_option(self, run):
        result = run(
            *URL, "sources", "apply", "--source", "x", "--name", "x", "--labels", "{nope", "--if-none-match", "*"
        )

        assert result.exit_code == ExitCode.USAGE
        assert "--labels" in result.stderr


class TestWrites:
    """Deletes ask first, dry runs do not, and preconditions travel as headers."""

    def test_a_delete_off_a_terminal_needs_yes(self, run, transport):
        result = run(*URL, "sources", "delete", "--source", "src-01", "--if-match", "*")

        assert result.exit_code == ExitCode.USAGE
        assert json.loads(result.stderr)["suggestion"] == "pass --yes"
        assert transport.sent == []

    def test_no_input_refuses_a_delete_even_on_a_terminal(self, run, transport, monkeypatch):
        monkeypatch.setattr(app_module, "_is_tty", lambda _stream: True)

        result = run(*URL, "--no-input", "-o", "json", "sources", "delete", "--source", "src-01", "--if-match", "*")

        assert result.exit_code == ExitCode.USAGE
        assert json.loads(result.stderr)["suggestion"] == "pass --yes"
        assert transport.sent == []

    def test_yes_deletes(self, run):
        result = run(*URL, "--yes", "sources", "delete", "--source", "src-01", "--if-match", "*")

        assert result.exit_code == 0, result.stderr
        assert result.stdout == ""
        assert run(*URL, "sources", "get", "--source", "src-01").exit_code == ExitCode.NOT_FOUND

    def test_a_dry_run_delete_needs_no_confirmation(self, run):
        result = run(*URL, "sources", "delete", "--source", "src-01", "--if-match", "*", "--dry-run")

        assert result.exit_code == 0, result.stderr
        assert run(*URL, "sources", "get", "--source", "src-01").exit_code == 0

    def test_an_etag_mismatch_is_a_conflict(self, run):
        result = run(*URL, "sources", "apply", "--source", "src-01", "--name", "src-01", "--if-match", '"stale"')

        assert result.exit_code == ExitCode.CONFLICT
        assert "etag_mismatch" in result.stderr


class TestErrors:
    """Exit codes and reports come from the problem+json answer."""

    def test_not_found_reports_the_problem(self, run):
        result = run(*URL, "sources", "get", "--source", "nope")

        assert result.exit_code == ExitCode.NOT_FOUND
        report = json.loads(result.stderr)
        assert report == {
            "error_type": "source_not_found",
            "message": "no source 'nope'",
            "input": {"source": "nope"},
            "suggestion": "run 'svc sources list' to see what exists",
            "retryable": False,
            "status": 404,
        }

    def test_a_text_report_on_request(self, run):
        result = run(*URL, "-o", "yaml", "sources", "get", "--source", "nope")

        assert result.stderr.strip() == (
            "Error (404 source_not_found): no source 'nope'\n  suggestion: run 'svc sources list' to see what exists"
        )

    def test_the_report_is_json_when_the_output_is_json_whatever_stderr_is(self, run, monkeypatch):
        # stderr on a terminal, stdout into a pipe: the output format is json, so the report is too.
        monkeypatch.setattr(app_module, "_is_tty", lambda stream: stream is sys.stderr)

        result = run(*URL, "sources", "get", "--source", "nope")

        assert json.loads(result.stderr)["error_type"] == "source_not_found"

    def test_the_report_is_text_when_the_output_is_not_json(self, run, monkeypatch):
        # stdout on a terminal makes a get print yaml, so the report is a line for a person.
        monkeypatch.setattr(app_module, "_is_tty", lambda stream: stream is sys.stdout)

        result = run(*URL, "sources", "get", "--source", "nope")

        assert result.stderr.startswith("Error (404 source_not_found): no source 'nope'")

    def test_a_missing_parameter_is_echoed_with_what_to_pass(self, run):
        report = json.loads(run(*URL, "sources", "get").stderr)

        assert report["input"] == {"missing": ["--source"]}
        assert report["suggestion"] == "pass --source"

    def test_no_endpoint_suggests_where_to_set_one(self, run):
        report = json.loads(run("sources", "list").stderr)

        assert report["suggestion"] == "pass --endpoint-url, or set SVC_API_URL"

    def test_a_precondition_failure_says_how_to_retry(self, run):
        report = json.loads(
            run(
                *URL, "-o", "json", "sources", "apply", "--source", "src-01", "--name", "x", "--if-match", '"old"'
            ).stderr
        )

        assert report["suggestion"] == "get the resource again and pass its current ETag as --if-match"

    def test_validation_errors_name_the_field(self, run):
        result = run(*URL, "sources", "apply", "--source", "x", "--port", "1", "--if-none-match", "*", "-o", "yaml")

        assert result.exit_code == ExitCode.USAGE
        assert "422 validation_error" in result.stderr
        assert "name: Field required" in result.stderr

    def test_a_precondition_the_server_requires(self, run):
        result = run(*URL, "sources", "apply", "--source", "src-01", "--name", "src-01")

        assert result.exit_code == ExitCode.USAGE
        assert "precondition_required" in result.stderr

    def test_no_endpoint_is_a_usage_error(self, run, transport):
        result = run("sources", "list")

        assert result.exit_code == ExitCode.USAGE
        assert "SVC_API_URL" in result.stderr
        assert transport.sent == []

    def test_debug_raises_instead(self, run):
        result = run(*URL, "--debug", "sources", "get", "--source", "nope")

        assert result.exit_code == 1
        assert result.stdout == ""


class TestCredentials:
    """The endpoint and credential come from flags, the environment, then the profile."""

    def test_an_api_key_from_the_environment(self, run, monkeypatch):
        monkeypatch.setenv("SVC_API_KEY", "k-123")

        result = run(*URL, "session", "whoami")

        assert json.loads(result.stdout) == {"authorization": None, "api_key": "k-123"}

    def test_a_stored_token_from_the_active_profile(self, run, store):
        store.set_value("url", "http://svc.test")
        store.set_value("account", "ops")
        store.save_credential(Credential(account="ops", token="t-456"))

        result = run("session", "whoami")

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"authorization": "Bearer t-456", "api_key": None}

    def test_credentials_travel_as_credentials(self, run, transport, monkeypatch):
        monkeypatch.setenv("SVC_API_TOKEN", "t-789")

        run(*URL, "session", "whoami")

        assert transport.sent[-1]["credentials"] == {"Authorization": "Bearer t-789"}
        assert "Authorization" not in transport.sent[-1]["headers"]

    def test_a_credential_sent_elsewhere_is_warned_about(self, run, store, monkeypatch):
        store.set_value("url", "http://profile.test")
        monkeypatch.setenv("SVC_API_TOKEN", "t-789")

        result = run(*URL, "session", "whoami")

        assert result.exit_code == 0, result.stderr
        assert "warning: sending env credentials to svc.test" in result.stderr

    def test_verbose_traces_each_request_on_stderr_without_its_credential(self, run, monkeypatch):
        monkeypatch.setenv("SVC_API_TOKEN", "t-secret")

        result = run(*URL, "-v", "sources", "get", "--source", "src-01")

        assert result.exit_code == 0, result.stderr
        assert "> GET http://svc.test/api/v1/sources/src-01" in result.stderr
        assert "< 200 OK" in result.stderr
        assert "t-secret" not in result.stderr
        assert json.loads(result.stdout)["name"] == "src-01"

    def test_quiet_prints_bare_values_and_no_warnings(self, run, store, monkeypatch):
        store.set_value("url", "http://profile.test")
        monkeypatch.setenv("SVC_API_TOKEN", "t-789")

        result = run(*URL, "-q", "--query", "items[].name", "sources", "list", "--max-items", "3")

        assert result.exit_code == 0, result.stderr
        assert result.stdout == "src-00\nsrc-01\nsrc-02\n"
        assert result.stderr == ""

    def test_verbose_and_quiet_together_are_refused(self, run):
        result = run(*URL, "-v", "-q", "sources", "list")

        assert result.exit_code == ExitCode.USAGE

    @pytest.mark.parametrize("flag", ["--profile", "SVC_PROFILE"])
    def test_a_named_profile(self, run, store, monkeypatch, flag):
        store.set_value("url", "http://svc.test", "staging")
        args = ["session", "whoami"]
        if flag == "--profile":
            args = ["--profile", "staging", *args]
        else:
            monkeypatch.setenv(flag, "staging")

        assert run(*args).exit_code == 0
