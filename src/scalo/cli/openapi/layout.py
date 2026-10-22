#  Project:   scalo
#  File:      src/scalo/cli/openapi/layout.py
#  Purpose:   Lay one operation out as typed Typer options: names, types, panels and collisions
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The options one generated command takes, and the function signature Typer reads them from.

Every path, query and header parameter and every top-level body property becomes
a long option named after it in kebab-case. A parameter listed in
``x-scalo.cli.positional`` is an argument instead. Each command also takes the
input options (``--body``, ``--cli-input-json``, ``--cli-input-yaml``,
``--generate-cli-skeleton``), the pagination options on a paged list, and the
global options, so they work after the command as well as before it.

A name already taken goes to the later field as ``--<location>-<name>``. Nothing
is marked required for the parser, because ``--cli-input-*`` may supply it: the
command checks after merging and says what is missing.
"""

import inspect
import keyword
import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import typer

from .naming import kebab
from .output import FORMATS
from .spec import Field, Operation

OutputFormat = Literal["json", "yaml", "table", "text"]

PANEL_PARAMETERS = "Parameters"
PANEL_BODY = "Request body"
PANEL_INPUT = "Input"
PANEL_PAGINATION = "Pagination"
PANEL_GLOBAL = "Global options"

_NON_OPTION = re.compile(r"[^a-z0-9-]+")
_SCALARS: dict[str, Any] = {"bool": bool | None, "int": int | None, "float": float | None}
_LISTS: dict[str, Any] = {"str": list[str] | None, "int": list[int] | None, "float": list[float] | None}

# Short flags the HyperI CLI family reserves, so no generated option takes one.
_RESERVED_SHORT = ("-h", "-o", "-d", "-y", "-n", "-V", "-v", "-q", "-f", "-c")

GLOBAL_HELP = {
    "output": f"Output format: {', '.join(FORMATS)}. Default: json off a terminal, else yaml for get, table for list.",
    "query": "JMESPath expression applied to the answer before it is printed.",
    "endpoint_url": "The API's base URL, over the environment and the profile.",
    "profile": "Named profile to read the endpoint and credential from.",
    "debug": "Show tracebacks instead of one-line errors.",
    "yes": "Skip the confirmation a delete asks for.",
    "no_paginate": "Fetch one page instead of following next_page_token.",
    "verbose": "Print each request and its answer's status on stderr.",
    "quiet": "Print no warnings, and a value or list of values bare, one per line.",
    "no_input": "Never prompt: refuse a delete that has no --yes, even at a terminal.",
}


def escape(text: str) -> str:
    """Help text with Rich markup brackets escaped, so spec prose prints as written."""
    return text.replace("[", r"\[")


@dataclass(frozen=True, slots=True)
class Slot:
    """One parameter of a generated command's function.

    Attributes:
        param: The Python parameter name Typer passes the value under.
        kind: ``field``, ``body``, ``cli_input_json``, ``cli_input_yaml``,
            ``skeleton``, ``max_items``, ``starting_token`` or ``global``.
        flag: The option as typed, such as ``--source``, for messages.
        field: The field it sets, for a ``field`` slot.
        positional: Taken as an argument rather than an option.
    """

    param: str
    kind: str
    flag: str
    field: Field | None = None
    positional: bool = False


@dataclass(frozen=True, slots=True)
class Layout:
    """A generated command's slots and the signature that declares them.

    Attributes:
        slots: Every slot, in signature order after ``ctx``.
        signature: The function signature Typer reads.
        annotations: The same parameters' annotations.
    """

    slots: tuple[Slot, ...]
    signature: inspect.Signature
    annotations: dict[str, Any]

    def by_kind(self, kind: str) -> list[Slot]:
        """Every slot of one kind."""
        return [slot for slot in self.slots if slot.kind == kind]

    def first(self, kind: str) -> Slot | None:
        """The slot of one kind, if the command has it."""
        return next((slot for slot in self.slots if slot.kind == kind), None)


def option_name(name: str) -> str:
    """A wire name as a long option's name: ``If-Match`` -> ``if-match``, ``pageSize`` -> ``page-size``."""
    cleaned = _NON_OPTION.sub("-", kebab(name).lower()).strip("-")
    return re.sub("-{2,}", "-", cleaned) or "value"


def _identifier(option: str) -> str:
    name = option.replace("-", "_")
    if not name[:1].isalpha():
        name = f"arg_{name}"
    return f"{name}_" if keyword.iskeyword(name) or name == "ctx" else name


def _field_type(field: Field) -> Any:
    """The annotation Typer converts a field's value with, ``None`` allowed for unset."""
    if field.type in _SCALARS:
        return _SCALARS[field.type]
    if field.type == "array" and field.item_type in _LISTS:
        return _LISTS[field.item_type]
    if field.type == "str" and field.enum and all(isinstance(value, str) for value in field.enum):
        # Typer reads choices from a Literal, and these come from the spec at run time.
        return Literal[tuple(field.enum)] | None  # ty: ignore[invalid-type-form]
    return str | None


def _field_help(field: Field) -> str:
    parts = [field.description.strip()] if field.description.strip() else []
    if field.type == "object" or (field.type == "array" and field.item_type not in _LISTS):
        parts.append("JSON or YAML, or file://<path>.")
    if field.enum and _field_type(field) in (int | None, float | None, str | None):
        parts.append(f"One of: {', '.join(str(value) for value in field.enum)}.")
    if field.required:
        parts.append("Required.")
    return escape(" ".join(parts))


class _Builder:
    """Accumulates slots, keeping option and parameter names unique."""

    def __init__(self) -> None:
        self.flags: set[str] = set(_RESERVED_SHORT) | {"--help"}
        self.params: set[str] = {"ctx"}
        self.slots: list[Slot] = []
        self.parameters: list[inspect.Parameter] = []
        self.annotations: dict[str, Any] = {"ctx": typer.Context}

    def claim(self, preferred: str, fallback: str) -> str:
        """A free long option name: ``preferred``, else ``fallback``, else ``fallback-2`` and on."""
        for candidate in (preferred, fallback):
            if f"--{candidate}" not in self.flags and f"--no-{candidate}" not in self.flags:
                return candidate
        index = 2
        while f"--{fallback}-{index}" in self.flags:
            index += 1
        return f"{fallback}-{index}"

    def add(self, slot: Slot, annotation: Any, *, default: Any = None, positional: bool = False) -> None:
        kind = inspect.Parameter.POSITIONAL_OR_KEYWORD if positional else inspect.Parameter.KEYWORD_ONLY
        self.parameters.append(inspect.Parameter(slot.param, kind, default=default, annotation=annotation))
        self.annotations[slot.param] = annotation
        self.slots.append(slot)
        self.params.add(slot.param)
        self.flags.add(slot.flag)

    def option(
        self,
        kind: str,
        flags: tuple[str, ...],
        annotation: Any,
        *,
        help: str,
        panel: str,
        default: Any = None,
        **extra: Any,
    ) -> None:
        param = _identifier(flags[0].lstrip("-"))
        while param in self.params:
            param = f"{param}_"
        info = typer.Option(*flags, help=help, rich_help_panel=panel, show_default=False, **extra)
        self.add(Slot(param, kind, flags[0]), Annotated[annotation, info], default=default)
        self.flags.update(flags)

    def layout(self) -> Layout:
        ctx = inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=typer.Context)
        positional = [p for p in self.parameters if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
        keyword_only = [p for p in self.parameters if p.kind is inspect.Parameter.KEYWORD_ONLY]
        signature = inspect.Signature([ctx, *positional, *keyword_only])
        order = {p.name: index for index, p in enumerate(signature.parameters.values())}
        slots = tuple(sorted(self.slots, key=lambda slot: order[slot.param]))
        return Layout(slots=slots, signature=signature, annotations={**self.annotations, "return": None})


def _add_globals(builder: _Builder, *, paginated: bool) -> None:
    builder.option("global", ("--output", "-o"), OutputFormat | None, help=GLOBAL_HELP["output"], panel=PANEL_GLOBAL)
    builder.option("global", ("--query",), str | None, help=GLOBAL_HELP["query"], panel=PANEL_GLOBAL)
    builder.option("global", ("--endpoint-url",), str | None, help=GLOBAL_HELP["endpoint_url"], panel=PANEL_GLOBAL)
    builder.option("global", ("--profile",), str | None, help=GLOBAL_HELP["profile"], panel=PANEL_GLOBAL)
    builder.option("global", ("--debug", "-d"), bool, help=GLOBAL_HELP["debug"], panel=PANEL_GLOBAL, default=False)
    builder.option("global", ("--yes", "-y"), bool, help=GLOBAL_HELP["yes"], panel=PANEL_GLOBAL, default=False)
    builder.option(
        "global", ("--verbose", "-v"), int, help=GLOBAL_HELP["verbose"], panel=PANEL_GLOBAL, default=0, count=True
    )
    builder.option("global", ("--quiet", "-q"), bool, help=GLOBAL_HELP["quiet"], panel=PANEL_GLOBAL, default=False)
    builder.option("global", ("--no-input",), bool, help=GLOBAL_HELP["no_input"], panel=PANEL_GLOBAL, default=False)
    if paginated:
        help_text = GLOBAL_HELP["no_paginate"]
        builder.option("global", ("--no-paginate",), bool, help=help_text, panel=PANEL_PAGINATION, default=False)


def _add_input(builder: _Builder, operation: Operation) -> None:
    if operation.body_schema is not None:
        builder.option(
            "body",
            ("--body",),
            str | None,
            help=escape("The whole request body as JSON or YAML, or file://<path>. Field options override it."),
            panel=PANEL_INPUT,
        )
    document = "Every input as one document with path, query, header and body sections, or file://<path>."
    builder.option(
        "cli_input_json", ("--cli-input-json",), str | None, help=escape(f"{document} JSON."), panel=PANEL_INPUT
    )
    builder.option(
        "cli_input_yaml", ("--cli-input-yaml",), str | None, help=escape(f"{document} YAML."), panel=PANEL_INPUT
    )
    builder.option(
        "skeleton",
        ("--generate-cli-skeleton",),
        bool,
        help="Print the input document with placeholder values, as JSON or with --output yaml as YAML, and send nothing.",
        panel=PANEL_INPUT,
        default=False,
    )


def _add_pagination(builder: _Builder) -> None:
    builder.option(
        "max_items",
        ("--max-items",),
        int | None,
        help="Most items to print. A cut-short list ends with a next_page_token.",
        panel=PANEL_PAGINATION,
        min=1,
    )
    builder.option(
        "starting_token",
        ("--starting-token",),
        str | None,
        help="Resume from the next_page_token an earlier call printed.",
        panel=PANEL_PAGINATION,
    )


def _add_field(builder: _Builder, field: Field, *, positional: bool, paginated: bool) -> None:
    name = option_name(field.name)
    claimed = builder.claim(name, f"{field.location}-{name}")
    flag = f"--{claimed}"
    param = _identifier(claimed)
    while param in builder.params:
        param = f"{param}_"
    annotation = _field_type(field)
    panel = PANEL_BODY if field.location == "body" else PANEL_PARAMETERS
    if paginated and field.location == "query" and field.name == "page_size":
        panel = PANEL_PAGINATION
    slot = Slot(param, "field", flag, field, positional=positional)
    if positional:
        builder.add(
            slot, Annotated[annotation, typer.Argument(help=_field_help(field), show_default=False)], positional=True
        )
        return
    if field.type == "bool":
        flags = (flag, "-n") if field.location == "query" and field.name == "dry_run" else (f"{flag}/--no-{claimed}",)
        info = typer.Option(*flags, help=_field_help(field), rich_help_panel=panel, show_default=False)
        builder.add(slot, Annotated[annotation, info])
        builder.flags.update({flag, f"--no-{claimed}", *flags})
        return
    info = typer.Option(flag, help=_field_help(field), rich_help_panel=panel, show_default=False)
    builder.add(slot, Annotated[annotation, info])


def layout_for(operation: Operation, *, skip_headers: frozenset[str] = frozenset()) -> Layout:
    """The slots and signature of one operation's command.

    Args:
        operation: The operation.
        skip_headers: Header parameters the client sets itself, lower case, such
            as the API key header.

    Returns:
        The layout.
    """
    builder = _Builder()
    _add_globals(builder, paginated=operation.paginated)
    _add_input(builder, operation)
    if operation.paginated:
        _add_pagination(builder)
    positional = {name: index for index, name in enumerate(operation.positional)}
    fields = [
        field
        for field in operation.parameters
        if not (field.location == "header" and field.name.lower() in skip_headers)
        and not (operation.paginated and field.location == "query" and field.name == "page_token")
    ]
    ordered = sorted(fields, key=lambda field: positional.get(field.name, len(positional)))
    for field in ordered:
        _add_field(builder, field, positional=field.name in positional, paginated=operation.paginated)
    for field in operation.body:
        _add_field(builder, field, positional=False, paginated=False)
    return builder.layout()
