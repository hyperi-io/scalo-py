#  Project:   scalo
#  File:      tests/unit/cli_openapi/test_fixture_spec.py
#  Purpose:   The whole command tree a committed spec in scalo.api's shape gives, nothing fetched
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Build the whole CLI from ``tests/fixtures/openapi/projects.yaml``, a spec written for these tests.

It carries the shapes scalo.api writes: ``x-scalo`` on every operation, nested
resources, path-item parameters, preconditions, ``dry_run``, paged lists, a hidden
operation, an alias, a positional parameter and a verb that collides with a group.
Options are read from the Click commands themselves, never from rendered help,
whose colouring changes with the terminal and the CI environment.
"""

from pathlib import Path
from typing import Any

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from scalo.cli.openapi import SpecCli, Store, load_spec
from scalo.cli.openapi.layout import layout_for

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "openapi" / "projects.yaml"


@pytest.fixture(scope="module")
def projects(tmp_path_factory: pytest.TempPathFactory) -> SpecCli:
    return SpecCli(load_spec(FIXTURE), name="pm", store=Store(tmp_path_factory.mktemp("pm")))


def _command(cli: SpecCli, path: tuple[str, ...]) -> Any:
    """The Click command a path names, from an app built for that path."""
    node: Any = get_command(cli.app([*path, "--help"]))
    for name in path:
        node = node.commands[name]
    return node


def _flags(command: Any) -> set[str]:
    return {flag for param in command.params for flag in (*param.opts, *param.secondary_opts)}


class TestTree:
    """Every operation reaches the tree, placed by its x-scalo hierarchy."""

    def test_every_visible_operation_is_one_command(self, projects):
        visible = [operation for operation in projects.operations if not operation.hidden]

        assert len(visible) == 17
        assert len(projects.command_paths()) == len(visible)

    def test_every_command_is_its_operation_id_or_a_displaced_verb(self, projects):
        for path in projects.command_paths():
            operation = projects.operation_at(*path)
            assert operation is not None, path
            assert ".".join(path) == operation.operation_id or path[-1].endswith("-cmd"), path

    def test_a_verb_that_names_a_group_moves_aside(self, projects):
        assert projects.operation_at("projects", "tasks-cmd").operation_id == "projects.tasks"
        assert ("projects", "tasks", "list") in projects.command_paths()

    def test_the_hidden_operation_has_no_command(self, projects):
        assert not [path for path in projects.command_paths() if path[0] == "maintenance"]


class TestCommands:
    """The generated commands parse, take their options and show help."""

    def test_the_full_tree_converts(self, projects):
        group: Any = get_command(projects.app())

        assert set(group.commands) == {"projects", "users"}

    @pytest.mark.parametrize("ci", [False, True], ids=["terminal", "github-actions"])
    def test_every_command_takes_its_options_and_shows_help(self, projects, monkeypatch, ci):
        if ci:
            monkeypatch.setenv("GITHUB_ACTIONS", "true")
            monkeypatch.setenv("FORCE_COLOR", "1")
        runner = CliRunner()
        for path in projects.command_paths():
            flags = _flags(_command(projects, path))
            assert {"--generate-cli-skeleton", "--output", "--cli-input-yaml"} <= flags, path

            args = [*path, "--help"]
            result = runner.invoke(projects.app(args), args, prog_name="pm")
            assert result.exit_code == 0, (path, result.output)

    def test_every_precondition_and_dry_run_becomes_an_option(self, projects):
        for operation in projects.operations:
            flags = {slot.flag for slot in layout_for(operation).by_kind("field")}
            names = {(field.location, field.name) for field in operation.parameters}
            if ("header", "If-Match") in names:
                assert "--if-match" in flags, operation.operation_id
            if ("query", "dry_run") in names:
                assert "--dry-run" in flags, operation.operation_id

    def test_a_paged_list_takes_the_pagination_options(self, projects):
        flags = _flags(_command(projects, ("projects", "tasks", "comments", "list")))

        assert {"--max-items", "--starting-token", "--page-size", "--no-paginate", "--project", "--task"} <= flags
        assert "--page-token" not in flags

    def test_read_only_properties_are_not_options(self, projects):
        assert "--created" not in _flags(_command(projects, ("projects", "create")))
        assert "--id" not in _flags(_command(projects, ("projects", "tasks", "create")))
        assert "--author" not in _flags(_command(projects, ("projects", "tasks", "comments", "create")))
        assert "--title" in _flags(_command(projects, ("projects", "tasks", "create")))
