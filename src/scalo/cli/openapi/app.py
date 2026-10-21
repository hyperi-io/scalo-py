#  Project:   scalo
#  File:      src/scalo/cli/openapi/app.py
#  Purpose:   SpecCli: build the command tree from a spec, take customisations, run it on Typer
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Build a CLI from an OpenAPI spec, after the AWS CLI's model-driven commands.

The tree is the spec's resource hierarchy: a group per resource level and a
command per verb, ``<prog> sources rules list --source syslog``. Hand-written
commands go on top through :meth:`SpecCli.command` and :meth:`SpecCli.add_typer`,
the way aws-cli layers its customisations over the generated commands.

Only the branch of the tree the command line names is built into Typer
commands: Typer converts every command it holds on each run, which costs about
400 ms for a 300-operation spec.
"""

import contextvars
import dataclasses
import functools
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, NoReturn
from urllib.parse import urlsplit

import typer

from scalo._openapi import wire_value

from .client import Client
from .config import Resolved, Store, config_home, resolve
from .errors import ApiError, CliConfigError, CliUsageError, report_for
from .layout import GLOBAL_HELP, Layout, OutputFormat, Slot, escape, layout_for
from .output import apply_query, default_format, render
from .paginate import collect, single_page
from .skeleton import load_input, parse_option, prune, read_text_argument, skeleton
from .spec import Operation, iter_operations, mapping, tag_descriptions
from .transport import Transport, UrllibTransport

# The root options that take a value, so the branch finder skips the value.
_ROOT_VALUE_FLAGS = frozenset({"--output", "-o", "--query", "--endpoint-url", "--profile"})

# Enough pages for any real list, and an end to one whose server never stops handing out tokens.
DEFAULT_MAX_PAGES = 10_000

_CURRENT: contextvars.ContextVar[Invocation | None] = contextvars.ContextVar("scalo_cli_invocation", default=None)


def _is_tty(stream: Any) -> bool:
    try:
        return bool(stream.isatty())
    except AttributeError, ValueError:
        return False


@dataclass(slots=True)
class Invocation:
    """One run of the CLI: the global options, and what they resolve to.

    A hand-written command reads it with :func:`invocation` to reach the same
    endpoint, credential and output handling the generated commands use.

    Attributes:
        cli: The CLI being run.
        output: ``--output``, ``None`` for the default.
        query: ``--query``.
        endpoint_url: ``--endpoint-url``.
        profile: ``--profile``.
        debug: ``--debug``.
        yes: ``--yes``.
        no_paginate: ``--no-paginate``.
        verbose: How many times ``--verbose`` was given.
        quiet: ``--quiet``.
        no_input: ``--no-input``.
    """

    cli: SpecCli
    output: str | None = None
    query: str | None = None
    endpoint_url: str | None = None
    profile: str | None = None
    debug: bool = False
    yes: bool = False
    no_paginate: bool = False
    verbose: int = 0
    quiet: bool = False
    no_input: bool = False

    @property
    def store(self) -> Store:
        """The profile and credential store."""
        return self.cli.store

    def with_overrides(self, values: Mapping[str, Any]) -> Invocation:
        """A copy with the global options a command was given after its name."""
        changes = {name: value for name, value in values.items() if value not in (None, False)}
        return dataclasses.replace(self, **changes)

    def resolved(self) -> Resolved:
        """The endpoint and credential this run uses."""
        return resolve(self.store, self.cli.env_prefix, url_override=self.endpoint_url, profile_override=self.profile)

    def client(self) -> Client:
        """A client for the resolved endpoint and credential.

        Raises:
            CliConfigError: When nothing names an endpoint.
        """
        resolved = self.resolved()
        prefix = self.cli.env_prefix
        if not resolved.url:
            raise CliConfigError(
                f"no endpoint: pass --endpoint-url, set {prefix}_API_URL, or set url in profile {resolved.profile!r}",
                suggestion=f"pass --endpoint-url, or set {prefix}_API_URL",
            )
        if resolved.credential is not None:
            profile_url = self.store.get_value("url", resolved.profile)
            target, stored = urlsplit(resolved.url).netloc, urlsplit(profile_url).netloc if profile_url else ""
            if stored and target and stored != target:
                self.warn(
                    f"warning: sending {resolved.credential.account} credentials to {target}, not the profile's {stored}"
                )
        return Client(
            resolved.url,
            resolved.credential,
            self.cli.transport,
            api_key_header=self.cli.api_key_header,
            timeout=self.cli.timeout,
            trace=_stderr if self.verbose else None,
        )

    def output_format(self, verb: str = "") -> str:
        """``--output``, else the default for the verb and the terminal."""
        return self.output or default_format(verb, is_tty=_is_tty(sys.stdout))

    def emit(self, data: Any, *, verb: str = "") -> None:
        """Print an answer: ``--query`` first, then the output format, or bare values under ``--quiet``.

        Raises:
            CliUsageError: On a bad ``--query`` or format.
        """
        selected = apply_query(data, self.query)
        bare = _bare_lines(selected) if self.quiet else None
        if bare is not None:
            typer.echo("".join(f"{line}\n" for line in bare), nl=False)
            return
        typer.echo(render(selected, self.output_format(verb)), nl=False)

    def warn(self, message: str) -> None:
        """Print a note on stderr, where it cannot corrupt the output, unless ``--quiet``."""
        if not self.quiet:
            _stderr(message)

    def fail(self, exc: BaseException, verb: str = "") -> NoReturn:
        """Print a known error as one report and exit with its code.

        Raises:
            typer.Exit: With the error's exit code.
            BaseException: ``exc`` itself, under ``--debug`` or when it is not a known error.
        """
        report = report_for(exc)
        if report is None or self.debug:
            raise exc
        typer.echo(report.render(as_json=self.output_format(verb) == "json"), err=True)
        raise typer.Exit(int(report.exit_code)) from None


def _stderr(message: str) -> None:
    typer.echo(message, err=True)


def _bare_lines(data: Any) -> list[str] | None:
    """A scalar or a list of scalars as lines for ``--quiet``, else ``None``."""
    values = data if isinstance(data, list) else [data]
    if any(isinstance(value, dict | list) for value in values):
        return None
    return ["" if value is None else str(wire_value(value)) for value in values]


def invocation(ctx: typer.Context | None = None) -> Invocation:
    """The current run's :class:`Invocation`, for a hand-written command.

    Raises:
        RuntimeError: Outside a command run by :class:`SpecCli`.
    """
    found = getattr(ctx, "obj", None) if ctx is not None else None
    if isinstance(found, Invocation):
        return found
    current = _CURRENT.get()
    if current is None:
        raise RuntimeError("no SpecCli invocation is running")
    return current


@dataclass(slots=True)
class _Command:
    operation: Operation | None = None
    function: Callable[..., Any] | None = None
    help: str | None = None
    hidden: bool = False


@dataclass(slots=True)
class _Group:
    help: str = ""
    groups: dict[str, _Group] = field(default_factory=dict)
    commands: dict[str, _Command] = field(default_factory=dict)
    typers: dict[str, typer.Typer] = field(default_factory=dict)

    def names(self) -> set[str]:
        return {*self.groups, *self.commands, *self.typers}

    def remove(self, name: str) -> None:
        self.groups.pop(name, None)
        self.commands.pop(name, None)
        self.typers.pop(name, None)


def _guarded[F: Callable[..., Any]](function: F) -> F:
    """Run a hand-written command, reporting the CLI's known errors the way generated ones do."""

    @functools.wraps(function)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            current = _CURRENT.get()
            if current is None or report_for(exc) is None:
                raise
            current.fail(exc)

    return run  # type: ignore[return-value]  # ty: ignore[invalid-return-type]


def _help_for(operation: Operation) -> tuple[str, str]:
    """``(help, short_help)`` from the operation's summary and description."""
    summary = operation.summary.strip() or f"{operation.method.upper()} {operation.path}"
    text = summary if not operation.description.strip() else f"{summary}\n\n{operation.description.strip()}"
    if operation.aliases:
        text += f"\n\nAliases: {', '.join(operation.aliases)}."
    return escape(text), escape(summary)


class SpecCli:
    """A command-line interface generated from one OpenAPI spec.

    Args:
        spec: The OpenAPI document, such as :func:`scalo.cli.openapi.load_spec`'s answer.
        name: The program name.
        env_prefix: Prefix of the environment variables (``<PREFIX>_API_URL``,
            ``_API_KEY``, ``_API_TOKEN``, ``_PROFILE``, ``_OUTPUT``,
            ``_CONFIG_HOME``). Defaults to ``name`` upper-cased.
        help: The root help text. Defaults to the spec's title and description.
        version: Printed by ``--version``. ``None`` leaves the option hidden.
        base_path: Prefix path-derived names leave out. See :func:`iter_operations`.
        transport: Sends the requests. Defaults to :class:`UrllibTransport`.
        store: Profiles and credentials. Defaults to ``~/.config/<name>``.
        api_key_header: The header an API key goes in.
        timeout: Seconds to wait for each answer.
        max_pages: Most pages one list follows before it stops and prints where to resume.

    Example::

        cli = SpecCli(load_spec("openapi.json"), name="svc", version="1.2.3")

        @cli.command("auth", "whoami")
        def whoami(ctx: typer.Context) -> None:
            run = invocation(ctx)
            run.emit(run.client().send("GET", "/api/v1/auth/me").json())

        def main() -> None:
            cli.main()
    """

    def __init__(
        self,
        spec: Mapping[str, Any],
        *,
        name: str,
        env_prefix: str | None = None,
        help: str | None = None,
        version: str | None = None,
        base_path: str | None = None,
        transport: Transport | None = None,
        store: Store | None = None,
        api_key_header: str = "X-API-Key",
        timeout: float = 30.0,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self.spec = spec
        self.name = name
        self.env_prefix = env_prefix or "".join(c if c.isalnum() else "_" for c in name.upper())
        info = mapping(spec.get("info"))
        self.help = help if help is not None else str(info.get("description") or info.get("title") or name)
        self.version = version
        self.transport: Transport = transport or UrllibTransport()
        self.store = store or Store(config_home(name, self.env_prefix))
        self.api_key_header = api_key_header
        self.timeout = timeout
        self.max_pages = max_pages
        self.operations = tuple(iter_operations(spec, base_path=base_path))
        self._tree = self._build_tree(tag_descriptions(spec))

    def _build_tree(self, tags: Mapping[str, str]) -> _Group:
        root = _Group()
        for operation in sorted(self.operations, key=lambda op: (op.hierarchy, op.verb, op.method)):
            if operation.hidden:
                continue
            group = self._ensure(root, operation.hierarchy)
            if not group.help and operation.tags:
                group.help = tags.get(operation.tags[0], "")
            name = operation.verb
            if name in group.names():
                # Two operations named alike: the method tells them apart, then a count.
                name = f"{operation.verb}-{operation.method}"
                index = 2
                while name in group.names():
                    name = f"{operation.verb}-{operation.method}-{index}"
                    index += 1
            group.commands[name] = _Command(operation=operation)
            for alias in operation.aliases:
                if alias not in group.names():
                    group.commands[alias] = _Command(operation=operation, hidden=True)
        return root

    @staticmethod
    def _ensure(root: _Group, path: Sequence[str]) -> _Group:
        """The group at ``path``, created as needed.

        A command already holding a name a group needs moves to ``<name>-cmd``, so
        neither is lost.
        """
        node = root
        for segment in path:
            if segment not in node.groups:
                displaced = node.commands.pop(segment, None)
                if displaced is not None:
                    node.commands[f"{segment}-cmd"] = displaced
                node.groups[segment] = _Group()
            node = node.groups[segment]
        return node

    def _slot_for(self, path: Sequence[str], replace: bool) -> tuple[_Group, str]:
        if not path:
            raise ValueError("a command needs a name")
        *groups, name = path
        node = self._ensure(self._tree, groups)
        if name in node.names():
            if not replace:
                raise ValueError(f"{' '.join(path)!r} already exists: pass replace=True to replace it")
            node.remove(name)
        return node, name

    def command(
        self, *path: str, replace: bool = False, hidden: bool = False, help: str | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a hand-written command, Typer-style, at a path in the tree.

        Args:
            *path: The groups, then the command's name. Missing groups are created.
            replace: Replace a generated command or group already at the path.
            hidden: Leave it out of help listings.
            help: Help text. Defaults to the function's docstring.

        Returns:
            A decorator that registers the function and returns it unchanged.

        Raises:
            ValueError: When the path is taken and ``replace`` is False.
        """

        def register(function: Callable[..., Any]) -> Callable[..., Any]:
            node, name = self._slot_for(path, replace)
            node.commands[name] = _Command(function=_guarded(function), help=help, hidden=hidden)
            return function

        return register

    def add_typer(self, app: typer.Typer, *path: str, replace: bool = False) -> None:
        """Mount a hand-written Typer app as a group at a path in the tree.

        Args:
            app: The app, its own help and commands intact.
            *path: The groups, then the mounted group's name.
            replace: Replace a generated command or group already at the path.

        Raises:
            ValueError: When the path is taken and ``replace`` is False.
        """
        node, name = self._slot_for(path, replace)
        node.typers[name] = app

    def command_paths(self) -> list[tuple[str, ...]]:
        """Every listed command and mounted group, as typed after the program name."""
        found: list[tuple[str, ...]] = []

        def walk(node: _Group, prefix: tuple[str, ...]) -> None:
            for name, command in node.commands.items():
                if not command.hidden:
                    found.append((*prefix, name))
            found.extend((*prefix, name) for name in node.typers)
            for name, child in node.groups.items():
                walk(child, (*prefix, name))

        walk(self._tree, ())
        return sorted(found)

    def operation_at(self, *path: str) -> Operation | None:
        """The operation a generated command calls, ``None`` for any other path."""
        *groups, name = path
        node: _Group | None = self._tree
        for segment in groups:
            node = node.groups.get(segment) if node is not None else None
        command = node.commands.get(name) if node is not None else None
        return command.operation if command is not None else None

    def _branch(self, argv: Sequence[str]) -> list[str]:
        """The group and command names an argument list selects, root options skipped."""
        names: list[str] = []
        node: _Group | None = self._tree
        skip = False
        for arg in argv:
            if skip:
                skip = False
                continue
            if arg == "--":
                break
            if arg.startswith("-"):
                skip = not names and arg in _ROOT_VALUE_FLAGS
                continue
            names.append(arg)
            node = node.groups.get(arg) if node is not None else None
            if node is None:
                break
        return names

    def app(self, argv: Sequence[str] | None = None) -> typer.Typer:
        """The Typer app, built for one argument list or, with ``None``, in full.

        Args:
            argv: The arguments the app will parse. Groups they do not enter are
                built empty, which is all their help listing needs.

        Returns:
            The app.
        """
        branch = None if argv is None else self._branch(argv)
        root = typer.Typer(
            name=self.name,
            help=escape(self.help),
            no_args_is_help=True,
            add_completion=False,
            rich_markup_mode="rich",
            pretty_exceptions_show_locals=False,
            context_settings={"help_option_names": ["-h", "--help"]},
        )
        root.callback()(self._root_callback())
        self._fill(root, self._tree, branch, 0)
        return root

    def main(self, argv: Sequence[str] | None = None) -> None:
        """Parse the arguments and run the command they name, then exit.

        Args:
            argv: The arguments, ``sys.argv[1:]`` by default.
        """
        args = list(sys.argv[1:] if argv is None else argv)
        self.app(args)(args=args, prog_name=self.name)

    def _fill(self, app: typer.Typer, node: _Group, branch: list[str] | None, depth: int) -> None:
        for name, command in node.commands.items():
            if command.operation is not None:
                self._add_generated(app, name, command.operation, command.hidden)
            elif command.function is not None:
                app.command(name=name, help=command.help, hidden=command.hidden)(command.function)
        for name, mounted in node.typers.items():
            app.add_typer(mounted, name=name)
        for name, child in node.groups.items():
            sub = typer.Typer(name=name, help=escape(child.help), no_args_is_help=True, rich_markup_mode="rich")
            if branch is None or (depth < len(branch) and branch[depth] == name):
                self._fill(sub, child, branch, depth + 1)
            app.add_typer(sub, name=name, help=escape(child.help) or None)

    def _example(self, operation: Operation, layout: Layout) -> str:
        """A command line naming every required parameter, for the help epilog."""
        words = [self.name, *operation.command_path]
        for slot in layout.by_kind("field"):
            if slot.field is None or not slot.field.required or slot.field.location == "body":
                continue
            placeholder = f"<{slot.flag.removeprefix('--')}>"
            words.append(placeholder if slot.positional else f"{slot.flag} {placeholder}")
        return " ".join(words)

    def _add_generated(self, app: typer.Typer, name: str, operation: Operation, hidden: bool) -> None:
        layout = layout_for(operation, skip_headers=frozenset({self.api_key_header.lower()}))
        cli = self

        def run(ctx: typer.Context, **values: Any) -> None:
            base = invocation(ctx)
            overrides = {slot.param: values.pop(slot.param, None) for slot in layout.by_kind("global")}
            current = base.with_overrides(overrides)
            _CURRENT.set(current)
            try:
                if current.verbose and current.quiet:
                    raise CliUsageError("--verbose and --quiet cannot be used together")
                cli._execute(current, operation, layout, values)
            except Exception as exc:
                current.fail(exc, operation.verb)

        run.__signature__ = layout.signature  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        run.__annotations__ = layout.annotations
        help_text, short_help = _help_for(operation)
        epilog = escape(
            f"Example: {self._example(operation, layout)}\n\nCalls {operation.method.upper()} {operation.path}."
        )
        app.command(name=name, help=help_text, short_help=short_help, epilog=epilog, hidden=hidden)(run)

    def _root_callback(self) -> Callable[..., None]:
        cli = self
        prefix = self.env_prefix

        def show_version(value: bool) -> None:
            if value:
                typer.echo(f"{cli.name} {cli.version or 'unknown'}")
                raise typer.Exit()

        def root(
            ctx: typer.Context,
            output: Annotated[
                OutputFormat | None,
                typer.Option("--output", "-o", envvar=f"{prefix}_OUTPUT", help=GLOBAL_HELP["output"]),
            ] = None,
            query: Annotated[str | None, typer.Option("--query", help=GLOBAL_HELP["query"])] = None,
            endpoint_url: Annotated[
                str | None, typer.Option("--endpoint-url", help=GLOBAL_HELP["endpoint_url"])
            ] = None,
            profile: Annotated[str | None, typer.Option("--profile", help=GLOBAL_HELP["profile"])] = None,
            debug: Annotated[bool, typer.Option("--debug", "-d", help=GLOBAL_HELP["debug"])] = False,
            yes: Annotated[bool, typer.Option("--yes", "-y", help=GLOBAL_HELP["yes"])] = False,
            no_paginate: Annotated[bool, typer.Option("--no-paginate", help=GLOBAL_HELP["no_paginate"])] = False,
            verbose: Annotated[int, typer.Option("--verbose", "-v", count=True, help=GLOBAL_HELP["verbose"])] = 0,
            quiet: Annotated[bool, typer.Option("--quiet", "-q", help=GLOBAL_HELP["quiet"])] = False,
            no_input: Annotated[bool, typer.Option("--no-input", help=GLOBAL_HELP["no_input"])] = False,
            version: Annotated[
                bool,
                typer.Option(
                    "--version",
                    "-V",
                    is_eager=True,
                    callback=show_version,
                    hidden=cli.version is None,
                    help="Print the version.",
                ),
            ] = False,
        ) -> None:
            if verbose and quiet:
                raise typer.BadParameter("--verbose and --quiet cannot be used together")
            current = Invocation(
                cli,
                output=output,
                query=query,
                endpoint_url=endpoint_url,
                profile=profile,
                debug=debug,
                yes=yes,
                no_paginate=no_paginate,
                verbose=verbose,
                quiet=quiet,
                no_input=no_input,
            )
            ctx.obj = current
            _CURRENT.set(current)

        return root

    def _execute(self, run: Invocation, operation: Operation, layout: Layout, values: dict[str, Any]) -> None:
        """Turn one generated command's options into a call, and print the answer."""
        if _value(layout.first("skeleton"), values):
            document = skeleton(operation, self.spec)
            typer.echo(render(document, "yaml" if run.output == "yaml" else "json"), nl=False)
            return
        request = _request(operation, layout, values)
        _confirm(run, operation, request)
        client = run.client()
        try:
            data = self._call(run, client, operation, layout, request, values)
        except ApiError as exc:
            echoed = {**request["path"], **request["query"]}
            suggestion = self._suggestion(operation, layout, exc.response.status)
            raise ApiError(exc.response, input=echoed, suggestion=suggestion) from exc
        if data is not None:
            run.emit(data, verb=operation.verb)

    def _call(
        self,
        run: Invocation,
        client: Client,
        operation: Operation,
        layout: Layout,
        request: dict[str, Any],
        values: Mapping[str, Any],
    ) -> Any:
        """The answer to one call, every page of it for a paged list."""
        if not operation.paginated:
            return client.call(operation, request)
        starting = _value(layout.first("starting_token"), values) or request["query"].pop("page_token", None)
        max_items = _value(layout.first("max_items"), values)

        def fetch(token: str | None) -> Any:
            query = {**request["query"], "page_token": token}
            return client.call(operation, {**request, "query": query})

        if run.no_paginate:
            if max_items is not None:
                raise CliUsageError("--max-items follows pages, so it cannot be used with --no-paginate")
            return single_page(fetch, starting_token=starting)
        return collect(fetch, max_items=max_items, starting_token=starting, warn=run.warn, max_pages=self.max_pages)

    def _suggestion(self, operation: Operation, layout: Layout, status: int) -> str | None:
        """What to try after the API refused a call, ``None`` when nothing useful can be said."""
        flags = {
            (slot.field.location, slot.field.name.lower()): slot.flag
            for slot in layout.by_kind("field")
            if slot.field is not None
        }
        if_match, if_none_match = flags.get(("header", "if-match")), flags.get(("header", "if-none-match"))
        if status == 401:
            return f"pass a credential: set {self.env_prefix}_API_TOKEN or {self.env_prefix}_API_KEY, or use --profile"
        if status == 403:
            return "use a credential allowed to call this operation"
        if status == 404 and operation.hierarchy and self.operation_at(*operation.hierarchy, "list") is not None:
            return f"run '{' '.join((self.name, *operation.hierarchy, 'list'))}' to see what exists"
        if status == 412 and if_match:
            return f"get the resource again and pass its current ETag as {if_match}"
        if status == 428 and if_match and if_none_match:
            return f"pass {if_match} with the current ETag, or {if_none_match} '*' to create"
        if status == 429 or status >= 500:
            return "retry later"
        return None


def _value(slot: Slot | None, values: Mapping[str, Any]) -> Any:
    return None if slot is None else values.get(slot.param)


def _converted(slot: Slot, value: Any) -> Any:
    """A field's option value as the API takes it, ``None`` when it was not given."""
    field_ = slot.field
    if field_ is None or value is None or (isinstance(value, list | tuple) and not value):
        return None
    if isinstance(value, list | tuple):
        return list(value)
    nested = field_.type == "object" or (field_.type == "array" and field_.item_type not in ("str", "int", "float"))
    if nested and isinstance(value, str):
        parsed = parse_option(read_text_argument(value, slot.flag), option=slot.flag, yaml_allowed=True)
        if field_.type == "array" and not isinstance(parsed, list):
            raise CliUsageError(f"{slot.flag} must be a list")
        return parsed
    return value


def _request(operation: Operation, layout: Layout, values: Mapping[str, Any]) -> dict[str, Any]:
    """The input document: ``--cli-input-*`` first, then ``--body``, then each option.

    A ``null`` anywhere in the document, as ``--generate-cli-skeleton`` prints
    every value, counts as not given, and so does an empty parameter. ``--body``
    is sent as written, so a merge patch can still carry an explicit ``null``.

    Raises:
        CliUsageError: On bad input, or a required parameter nothing supplied.
    """
    document = load_input(
        _value(layout.first("cli_input_json"), values), _value(layout.first("cli_input_yaml"), values)
    )
    request: dict[str, Any] = {}
    for section in ("path", "query", "header"):
        given = prune(document.get(section)) or {}
        request[section] = {name: value for name, value in given.items() if value != ""}
    body = prune(document.get("body"))
    body_text = _value(layout.first("body"), values)
    if body_text is not None:
        body = parse_option(read_text_argument(body_text, "--body"), option="--body", yaml_allowed=True)
    for slot in layout.by_kind("field"):
        value = _converted(slot, values.get(slot.param))
        if value is None or slot.field is None:
            continue
        if slot.field.location != "body":
            request[slot.field.location][slot.field.name] = value
            continue
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise CliUsageError(f"{slot.flag} sets a body field, but the body given is not an object")
        body[slot.field.name] = value
    missing = [
        slot.flag
        for slot in layout.by_kind("field")
        if slot.field is not None
        and slot.field.required
        and slot.field.location != "body"
        and request[slot.field.location].get(slot.field.name) in (None, "")
    ]
    if missing:
        raise CliUsageError(
            f"missing required {', '.join(missing)}",
            input={"missing": missing},
            suggestion=f"pass {', '.join(missing)}",
        )
    request["body"] = body
    return request


def _confirm(run: Invocation, operation: Operation, request: Mapping[str, Any]) -> None:
    """Ask before a delete on a terminal, and refuse one without ``--yes`` off a terminal or under ``--no-input``.

    Raises:
        CliUsageError: Off a terminal, or under ``--no-input``, without ``--yes``.
        typer.Abort: When the answer is no.
    """
    if operation.method != "delete" or run.yes or request["query"].get("dry_run") is True:
        return
    names = " ".join(f"{name}={value}" for name, value in request["path"].items())
    target = " ".join([*operation.hierarchy, names]).strip()
    if not run.no_input and _is_tty(sys.stdin) and _is_tty(sys.stdout):
        if not typer.confirm(f"Delete {target}? This cannot be undone."):
            raise typer.Abort()
        return
    reason = "with --no-input" if run.no_input else "without a terminal to confirm on"
    raise CliUsageError(f"refusing to delete {target} {reason}", input=request["path"], suggestion="pass --yes")
