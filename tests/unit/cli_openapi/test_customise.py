#  Project:   scalo
#  File:      tests/unit/cli_openapi/test_customise.py
#  Purpose:   Hand-written commands over the generated tree, and building only the branch a run needs
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``SpecCli.command`` and ``SpecCli.add_typer`` layer hand-written commands over the generated ones."""

import json
from typing import Annotated, Any

import pytest
import typer
from typer.main import get_command

from scalo.cli.openapi import SpecCli, invocation
from scalo.cli.openapi.errors import CliUsageError, ExitCode

URL = ("--endpoint-url", "http://svc.test")


def _names(app: typer.Typer, *path: str) -> set[str]:
    """The command names Typer built at one group of an app."""
    node: Any = get_command(app)
    for name in path:
        node = node.commands[name]
    return set(node.commands)


class TestCommand:
    """A function registered at a path joins the tree beside the generated commands."""

    def test_a_command_inside_a_generated_group(self, cli, run):
        @cli.command("sources", "count")
        def count(ctx: typer.Context, kind: Annotated[str, typer.Option()] = "syslog") -> None:
            """Count sources of one kind."""
            current = invocation(ctx)
            page = current.client().send("GET", f"/api/v1/sources?filter={kind}&page_size=100").json()
            current.emit({"kind": kind, "count": len(page["items"])})

        result = run(*URL, "sources", "count")

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == {"kind": "syslog", "count": 7}
        assert ("sources", "count") in cli.command_paths()

    def test_a_command_creates_the_groups_it_needs(self, cli, run):
        @cli.command("auth", "login", help="Log in.")
        def login() -> None:
            invocation().store.set_value("account", "me")

        assert run("auth", "login").exit_code == 0
        assert cli.store.get_value("account") == "me"

    def test_a_known_error_is_reported_like_a_generated_command(self, cli, run):
        @cli.command("broken")
        def broken() -> None:
            raise CliUsageError("bad input")

        result = run("broken")

        assert result.exit_code == ExitCode.USAGE
        assert json.loads(result.stderr)["message"] == "bad input"

    def test_an_unknown_error_is_not_swallowed(self, cli, run):
        @cli.command("crash")
        def crash() -> None:
            raise RuntimeError("bug")

        result = run("crash")

        assert result.exit_code == 1
        assert "Error" not in result.stderr

    def test_a_taken_path_needs_replace(self, cli, run):
        with pytest.raises(ValueError, match="already exists"):
            cli.command("sources", "list")(lambda: None)

        @cli.command("sources", "list", replace=True)
        def listing() -> None:
            typer.echo("custom")

        assert run("sources", "list").stdout == "custom\n"

    def test_a_command_needs_a_name(self, cli):
        with pytest.raises(ValueError, match="needs a name"):
            cli.command()(lambda: None)


class TestAddTyper:
    """A whole Typer app mounts as a group."""

    def test_a_mounted_app(self, cli, run):
        local = typer.Typer(help="Work without the API.")

        @local.command("ping")
        def ping() -> None:
            typer.echo("pong")

        cli.add_typer(local, "local")

        assert run("local", "ping").stdout == "pong\n"
        assert ("local",) in cli.command_paths()

    def test_mounting_over_a_group_needs_replace(self, cli):
        with pytest.raises(ValueError, match="already exists"):
            cli.add_typer(typer.Typer(), "sources")


class TestBranch:
    """Only the branch the arguments name is built in full."""

    def test_unvisited_groups_are_empty(self, cli):
        app = cli.app(["session", "whoami"])

        assert _names(app) == {"session", "sources"}
        assert _names(app, "sources") == set()
        assert _names(app, "session") == {"whoami"}

    def test_root_value_options_are_skipped(self, cli):
        app = cli.app(["-o", "json", "--query", "items", "sources", "rules", "list"])

        assert _names(app, "sources", "rules") == {"list"}

    def test_the_full_tree_without_arguments(self, cli):
        assert _names(cli.app(), "sources") == {"apply", "delete", "deploy", "get", "list", "rules", "ship", "update"}

    def test_an_unknown_group_suggests_the_near_one(self, run):
        result = run("sourcez")

        assert result.exit_code == ExitCode.USAGE
        assert "Did you mean 'sources'" in result.stderr

    def test_the_operation_behind_a_command(self, cli):
        assert cli.operation_at("sources", "rules", "list").path == "/api/v1/sources/{source}/rules"
        assert cli.operation_at("nope", "list") is None
        assert cli.operation_at("sources", "nope") is None


class TestEntryPoint:
    """``main`` parses sys.argv-style arguments and exits."""

    def test_main_runs_and_exits(self, cli, capsys):
        with pytest.raises(SystemExit) as stopped:
            cli.main(["--version"])

        assert stopped.value.code == 0
        assert capsys.readouterr().out.strip() == "svc 1.2.3"

    def test_the_env_prefix_defaults_from_the_name(self, spec):
        assert SpecCli(spec, name="my-svc").env_prefix == "MY_SVC"
