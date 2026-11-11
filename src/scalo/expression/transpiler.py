# Project:   scalo
# File:      expression/transpiler.py
# Purpose:   CEL-to-ClickHouse SQL transpilation
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""CEL-to-ClickHouse SQL transpiler.

Converts expression profile CEL expressions into ClickHouse-compatible SQL
WHERE clauses for query pushdown. The expression is first validated
via :func:`validate` (CEL syntax + expression profile), then tokenized,
parsed into an AST, and emitted as ClickHouse SQL.

Safety layers:
    1. CEL validation gate (syntax + expression profile)
    2. String literal escaping (single-quote doubling)
    3. Identifier validation (alphanumeric + dots only)

Usage::

    from scalo.expression import transpile_to_clickhouse

    sql = transpile_to_clickhouse('severity == "critical" && amount > 10000')
    # => "severity = 'critical' AND amount > 10000"
"""

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from enum import Enum, auto

from .cel import ExpressionError, validate
from .profile import ProfileConfig

__all__ = ["TranspileError", "transpile_to_clickhouse"]


# -- Errors --------------------------------------------------------


class TranspileError(Exception):
    """Raised when a valid CEL expression cannot be transpiled to SQL."""


# -- AST -----------------------------------------------------------


@dataclass
class Literal:
    """String, number, boolean, or null literal."""

    value: str | int | float | bool | None


@dataclass
class Ident:
    """Identifier, possibly dotted (e.g. ``event.user_id``)."""

    name: str


@dataclass
class BinaryOp:
    """Binary operator (``==``, ``&&``, ``in``, ``+``, etc.)."""

    op: str
    left: Expr
    right: Expr


@dataclass
class UnaryOp:
    """Unary operator (``!``, ``-``)."""

    op: str
    operand: Expr


@dataclass
class MethodCall:
    """Method-style call (``x.contains(y)``)."""

    target: Expr
    method: str
    args: list[Expr] = field(default_factory=list)


@dataclass
class FunctionCall:
    """Free function call (``has(x)``, ``size(x)``, ``int(x)``)."""

    name: str
    args: list[Expr] = field(default_factory=list)


@dataclass
class Ternary:
    """Ternary conditional (``a ? b : c``)."""

    condition: Expr
    true_expr: Expr
    false_expr: Expr


@dataclass
class ListExpr:
    """List literal (``[a, b, c]``)."""

    elements: list[Expr] = field(default_factory=list)


# Union of all AST node types.
Expr = Literal | Ident | BinaryOp | UnaryOp | MethodCall | FunctionCall | Ternary | ListExpr


# -- Tokenizer -----------------------------------------------------


class TT(Enum):
    """Token type."""

    STRING = auto()
    NUMBER = auto()
    IDENT = auto()
    OP = auto()  # ==, !=, <, <=, >, >=, &&, ||, +, -, *, /, %
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    DOT = auto()
    QUESTION = auto()
    COLON = auto()
    BANG = auto()  # !
    EOF = auto()


@dataclass
class Token:
    type: TT
    value: str
    pos: int = 0


# Ordered so longer patterns match first.
_TOKEN_PATTERNS: list[tuple[TT, re.Pattern[str]]] = [
    (TT.STRING, re.compile(r'"(?:[^"\\]|\\.)*"')),
    (TT.STRING, re.compile(r"'(?:[^'\\]|\\.)*'")),
    (TT.NUMBER, re.compile(r"\d+\.\d*|\.\d+|\d+")),
    (TT.OP, re.compile(r"==|!=|<=|>=|&&|\|\||[<>+\-*/%]")),
    (TT.IDENT, re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")),
    (TT.LPAREN, re.compile(r"\(")),
    (TT.RPAREN, re.compile(r"\)")),
    (TT.LBRACKET, re.compile(r"\[")),
    (TT.RBRACKET, re.compile(r"\]")),
    (TT.COMMA, re.compile(r",")),
    (TT.DOT, re.compile(r"\.")),
    (TT.QUESTION, re.compile(r"\?")),
    (TT.COLON, re.compile(r":")),
    (TT.BANG, re.compile(r"!")),
]

_WS = re.compile(r"\s+")


def _tokenize(expr: str) -> list[Token]:
    """Tokenize a CEL expression into a flat token list."""
    tokens: list[Token] = []
    pos = 0
    while pos < len(expr):
        # Skip whitespace
        m = _WS.match(expr, pos)
        if m:
            pos = m.end()
            continue

        matched = False
        for tt, pattern in _TOKEN_PATTERNS:
            m = pattern.match(expr, pos)
            if m:
                tokens.append(Token(tt, m.group(), pos))
                pos = m.end()
                matched = True
                break

        if not matched:
            raise TranspileError(f"Unexpected character {expr[pos]!r} at position {pos}")

    tokens.append(Token(TT.EOF, "", pos))
    return tokens


# -- Parser (Pratt) ------------------------------------------------

# Precedence levels (higher = tighter binding).
_PREC_TERNARY = 1
_PREC_OR = 2
_PREC_AND = 3
_PREC_COMPARISON = 4  # ==, !=, <, <=, >, >=, in
_PREC_ADDITIVE = 5  # +, -
_PREC_MULTIPLICATIVE = 6  # *, /, %
_PREC_UNARY = 7  # !, unary -
_PREC_POSTFIX = 8  # .method(), ()

_BINARY_PREC: dict[str, int] = {
    "||": _PREC_OR,
    "&&": _PREC_AND,
    "==": _PREC_COMPARISON,
    "!=": _PREC_COMPARISON,
    "<": _PREC_COMPARISON,
    "<=": _PREC_COMPARISON,
    ">": _PREC_COMPARISON,
    ">=": _PREC_COMPARISON,
    "in": _PREC_COMPARISON,
    "+": _PREC_ADDITIVE,
    "-": _PREC_ADDITIVE,
    "*": _PREC_MULTIPLICATIVE,
    "/": _PREC_MULTIPLICATIVE,
    "%": _PREC_MULTIPLICATIVE,
}


class _Parser:
    """Pratt parser for expression profile CEL expressions."""

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, tt: TT) -> Token:
        tok = self._advance()
        if tok.type != tt:
            raise TranspileError(f"Expected {tt.name}, got {tok.type.name} ({tok.value!r}) at position {tok.pos}")
        return tok

    def parse(self) -> Expr:
        """Parse the full expression."""
        expr = self._parse_expr(0)
        if self._peek().type != TT.EOF:
            tok = self._peek()
            raise TranspileError(f"Unexpected token {tok.value!r} at position {tok.pos}")
        return expr

    def _parse_expr(self, min_prec: int) -> Expr:
        """Pratt expression parser with minimum precedence."""
        left = self._parse_prefix()

        while True:
            tok = self._peek()

            # Ternary: ? ... : ...
            if tok.type == TT.QUESTION and min_prec <= _PREC_TERNARY:
                self._advance()  # consume ?
                true_expr = self._parse_expr(0)
                self._expect(TT.COLON)
                false_expr = self._parse_expr(_PREC_TERNARY)
                left = Ternary(left, true_expr, false_expr)
                continue

            # Dot access / method call
            if tok.type == TT.DOT:
                self._advance()  # consume .
                name_tok = self._expect(TT.IDENT)
                if self._peek().type == TT.LPAREN:
                    self._advance()  # consume (
                    args = self._parse_args()
                    self._expect(TT.RPAREN)
                    left = MethodCall(left, name_tok.value, args)
                else:
                    # Dotted identifier: a.b.c
                    if isinstance(left, Ident):
                        left = Ident(f"{left.name}.{name_tok.value}")
                    else:
                        left = MethodCall(left, name_tok.value, [])
                continue

            # Binary 'in' keyword
            if tok.type == TT.IDENT and tok.value == "in":
                prec = _BINARY_PREC["in"]
                if prec <= min_prec:
                    break
                self._advance()
                right = self._parse_expr(prec)
                left = BinaryOp("in", left, right)
                continue

            # Binary operators
            if tok.type == TT.OP and tok.value in _BINARY_PREC:
                prec = _BINARY_PREC[tok.value]
                if prec <= min_prec:
                    break
                self._advance()
                right = self._parse_expr(prec)
                left = BinaryOp(tok.value, left, right)
                continue

            break

        return left

    def _parse_prefix(self) -> Expr:
        """Parse a prefix expression (unary, literal, ident, grouping, list)."""
        tok = self._peek()

        # Unary !
        if tok.type == TT.BANG:
            self._advance()
            operand = self._parse_expr(_PREC_UNARY)
            return UnaryOp("!", operand)

        # Unary - (negative number)
        if tok.type == TT.OP and tok.value == "-":
            self._advance()
            operand = self._parse_expr(_PREC_UNARY)
            return UnaryOp("-", operand)

        # Parenthesized expression
        if tok.type == TT.LPAREN:
            self._advance()
            expr = self._parse_expr(0)
            self._expect(TT.RPAREN)
            return expr

        # List literal [a, b, c]
        if tok.type == TT.LBRACKET:
            self._advance()
            elements = self._parse_args()
            self._expect(TT.RBRACKET)
            return ListExpr(elements)

        # String literal
        if tok.type == TT.STRING:
            self._advance()
            # Strip quotes
            raw = tok.value[1:-1]
            # Unescape backslash sequences
            raw = raw.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
            return Literal(raw)

        # Number literal
        if tok.type == TT.NUMBER:
            self._advance()
            if "." in tok.value:
                return Literal(float(tok.value))
            return Literal(int(tok.value))

        # Identifier or function call or keyword literal
        if tok.type == TT.IDENT:
            self._advance()
            name = tok.value

            # Boolean / null literals
            if name == "true":
                return Literal(True)
            if name == "false":
                return Literal(False)
            if name == "null":
                return Literal(None)

            # Function call: name(args)
            if self._peek().type == TT.LPAREN:
                self._advance()  # consume (
                args = self._parse_args()
                self._expect(TT.RPAREN)
                return FunctionCall(name, args)

            return Ident(name)

        raise TranspileError(f"Unexpected token {tok.value!r} ({tok.type.name}) at position {tok.pos}")

    def _parse_args(self) -> list[Expr]:
        """Parse a comma-separated argument list (without enclosing parens/brackets)."""
        args: list[Expr] = []
        if self._peek().type in (TT.RPAREN, TT.RBRACKET):
            return args
        args.append(self._parse_expr(0))
        while self._peek().type == TT.COMMA:
            self._advance()
            args.append(self._parse_expr(0))
        return args


def _parse(expr: str) -> Expr:
    """Tokenize and parse a CEL expression into an AST."""
    tokens = _tokenize(expr)
    parser = _Parser(tokens)
    return parser.parse()


# -- SQL Emitter ---------------------------------------------------

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")

# Binary operator mapping: CEL -> ClickHouse SQL.
_OP_MAP: dict[str, str] = {
    "==": "=",
    "!=": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "&&": "AND",
    "||": "OR",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "%": "%",
}

# Function call mapping: CEL function -> ClickHouse function name.
_FUNC_MAP: dict[str, str] = {
    "size": "length",
    "int": "toInt64",
    "uint": "toUInt64",
    "double": "toFloat64",
    "string": "toString",
    "bool": "toBool",
}

# Operators that are word-based in SQL (need spaces around them).
_WORD_OPS = {"AND", "OR", "IN", "NOT"}

# Precedence for parenthesization in output.
_SQL_PREC: dict[str, int] = {
    "OR": 1,
    "AND": 2,
    "=": 3,
    "!=": 3,
    "<": 3,
    "<=": 3,
    ">": 3,
    ">=": 3,
    "IN": 3,
    "+": 4,
    "-": 4,
    "*": 5,
    "/": 5,
    "%": 5,
}


def _escape_string(s: str) -> str:
    """Escape a string for ClickHouse SQL (single-quoted)."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _static_type(node: Expr) -> str | None:
    """Return ``"int"`` or ``"double"`` when the expression alone fixes ``node``'s numeric type, else None.

    CEL never mixes the two in one operation, so a typed literal or conversion on
    either side fixes the type of the whole arithmetic around it.
    """
    if isinstance(node, Literal) and not isinstance(node.value, bool):
        if isinstance(node.value, int):
            return "int"
        if isinstance(node.value, float):
            return "double"
        return None
    if isinstance(node, UnaryOp) and node.op == "-":
        return _static_type(node.operand)
    if isinstance(node, BinaryOp) and node.op == "%":
        return "int"
    if isinstance(node, BinaryOp) and node.op in ("+", "-", "*", "/"):
        return _static_type(node.left) or _static_type(node.right)
    if isinstance(node, FunctionCall):
        return {"int": "int", "size": "int", "double": "double"}.get(node.name)
    return None


# ClickHouse infers a JSON number as Int64, as UInt64 past Int64's range, or as Float64.
_JSON_TYPES: dict[str, tuple[str, ...]] = {
    "number": ("Int64", "UInt64", "Float64"),
    "string": ("String",),
    "bool": ("Bool",),
}

# A comparison read with its operands swapped.
_FLIPPED: dict[str, str] = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}

# CEL conversions of a JSON path, built from the typed sub-columns the conversion accepts.
_JSON_CONVERSIONS: dict[str, str] = {
    "size": "coalesce(lengthUTF8({p}.:String), JSONArrayLength(toJSONString({p})))",
    "int": "coalesce({p}.:Int64, accurateCastOrNull(trunc({p}.:Float64), 'Int64'), toInt64OrNull({p}.:String))",
    "uint": (
        "coalesce({p}.:UInt64, accurateCastOrNull({p}.:Int64, 'UInt64'),"
        " accurateCastOrNull(trunc({p}.:Float64), 'UInt64'), toUInt64OrNull({p}.:String))"
    ),
    "double": "coalesce({p}.:Float64, toFloat64({p}.:Int64), toFloat64({p}.:UInt64), toFloat64OrNull({p}.:String))",
    "string": "if({p} IS NULL, NULL, toString({p}))",
}

# CEL string methods as ClickHouse functions of the target and the argument.
_STRING_METHODS: dict[str, str] = {
    "contains": "position({0}, {1}) > 0",
    "startsWith": "startsWith({0}, {1})",
    "endsWith": "endsWith({0}, {1})",
    "matches": "match({0}, {1})",
}


def _value_kind(node: Expr) -> str | None:
    """Return ``"number"``, ``"string"`` or ``"bool"`` when ``node`` has that CEL type whatever the data, else None."""
    if isinstance(node, Literal):
        if isinstance(node.value, bool):
            return "bool"
        if isinstance(node.value, str):
            return "string"
        return None if node.value is None else "number"
    if isinstance(node, FunctionCall) and node.name in ("string", "bool"):
        return node.name
    if isinstance(node, FunctionCall) and node.name == "uint":
        return "number"
    return "number" if _static_type(node) is not None else None


@dataclass(frozen=True, slots=True)
class _Emitter:
    """Emit ClickHouse SQL for an AST, reading each path under a JSON column through its typed sub-columns.

    A dynamic JSON path holds whatever type each row sent, and comparing it as one type
    fails the query once another type lands there. The typed sub-column ``path.:T`` is
    NULL in every row holding another type, so a test on it is CEL's answer for that
    type and NULL, which no row matches, for the rest.
    """

    json_columns: frozenset[str] = frozenset()

    def json_path(self, node: Expr) -> str | None:
        """Return ``node``'s SQL when it is a path under a JSON column, else None."""
        if not isinstance(node, Ident):
            return None
        root, dot, _ = node.name.partition(".")
        if not dot or root not in self.json_columns:
            return None
        return self.emit(node)

    def boolean(self, node: Expr, parent_prec: int = 0) -> str:
        """Emit ``node`` where CEL needs a bool."""
        path = self.json_path(node)
        return f"{path}.:Bool" if path is not None else self.emit(node, parent_prec)

    def string(self, node: Expr) -> str:
        """Emit ``node`` where CEL needs a string."""
        path = self.json_path(node)
        return f"{path}.:String" if path is not None else self.emit(node)

    def arithmetic(self, node: Expr, kind: str | None, parent_prec: int) -> str:
        """Emit an operand of arithmetic whose type is ``kind`` (``"int"``, ``"double"`` or None).

        Raises:
            TranspileError: The operand is a JSON path and nothing in the arithmetic fixes its type.
        """
        path = self.json_path(node)
        if path is None:
            return self.emit(node, parent_prec)
        if kind is None:
            raise TranspileError(
                f"arithmetic on `{path}` has no fixed type, so it is not pushed down: "
                "give it one with int() or double(), or a typed literal"
            )
        return f"{path}.:{'Int64' if kind == 'int' else 'Float64'}"

    def division(self, node: BinaryOp) -> str:
        """Emit ``/`` as CEL means it: integer division truncating toward zero, or double division.

        Raises:
            TranspileError: Neither operand fixes the type, so only the data decides which division CEL does.
        """
        kind = _static_type(node)
        if kind is None:
            raise TranspileError(
                "`/` between operands with no fixed type divides as int or as double depending on the data, "
                "so it is not pushed down: evaluate it in process, or give an operand a type with int() or double()"
            )
        my_prec = _SQL_PREC["/"]
        if kind == "int":
            # ClickHouse's intDiv truncates toward zero, as CEL does. Its `/` always returns a double.
            return f"intDiv({self.arithmetic(node.left, kind, 0)}, {self.arithmetic(node.right, kind, 0)})"
        return f"{self.arithmetic(node.left, kind, my_prec)} / {self.arithmetic(node.right, kind, my_prec + 1)}"

    def json_comparison(self, node: BinaryOp, parent_prec: int) -> str | None:
        """Emit a comparison or ``in`` on a JSON path, or return None when it has none to type.

        Raises:
            TranspileError: The path is compared with a value whose type depends on the data.
        """
        if node.op not in _FLIPPED and node.op != "in":
            return None
        left_path = self.json_path(node.left)
        right_path = self.json_path(node.right)
        if node.op == "in":
            if left_path is None or not isinstance(node.right, ListExpr):
                return None
            return self._json_in(left_path, node.right.elements)
        if left_path is not None and right_path is not None:
            raise TranspileError(
                f"`{left_path}` and `{right_path}` are both JSON paths, so their types depend on the data "
                "and the comparison is not pushed down: compare one with a literal or a converted value"
            )
        if left_path is not None:
            path, other, op = left_path, node.right, node.op
        elif right_path is not None:
            path, other, op = right_path, node.left, _FLIPPED[node.op]
        else:
            return None
        if isinstance(other, Literal) and other.value is None:
            return None
        kind = _value_kind(other)
        if kind is None:
            raise TranspileError(
                f"`{path}` is compared with a value of no fixed type, so the comparison is not pushed down: "
                "compare it with a literal, or convert the other side with int(), double() or string()"
            )
        other_sql = self.emit(other, _SQL_PREC["="] + 1)
        tests = [f"{path}.:{typed} {_OP_MAP[op]} {other_sql}" for typed in _JSON_TYPES[kind]]
        if op in ("==", "!="):
            tests.append(_when_present(path, op == "!="))
        if len(tests) > 1:
            return f"coalesce({', '.join(tests)})"
        return f"({tests[0]})" if _SQL_PREC["="] < parent_prec else tests[0]

    def _json_in(self, path: str, elements: list[Expr]) -> str:
        """Emit ``path in [...]``, testing each element against the sub-columns of its own type."""
        by_kind: dict[str, list[str]] = {}
        for element in elements:
            kind = _value_kind(element)
            if kind is None:
                raise TranspileError(f"`{path} in [...]` lists a value of no fixed type, so it is not pushed down")
            by_kind.setdefault(kind, []).append(self.emit(element))
        tests: list[str] = []
        for kind, values in by_kind.items():
            listed = ", ".join(values)
            tests.extend(f"{path}.:{typed} IN ({listed})" for typed in _JSON_TYPES[kind])
        tests.append(_when_present(path, False))
        return f"coalesce({', '.join(tests)})"

    def emit(self, node: Expr, parent_prec: int = 0) -> str:
        """Emit a ClickHouse SQL string from an AST node."""
        if isinstance(node, Literal):
            if node.value is None:
                return "NULL"
            if isinstance(node.value, bool):
                return "1" if node.value else "0"
            if isinstance(node.value, str):
                return _escape_string(node.value)
            if isinstance(node.value, float):
                return repr(node.value)
            return str(node.value)

        if isinstance(node, Ident):
            if not _IDENT_RE.match(node.name):
                raise TranspileError(f"Invalid identifier: {node.name!r}")
            return node.name

        if isinstance(node, UnaryOp):
            if node.op == "!":
                return f"NOT {self.boolean(node.operand, _PREC_UNARY)}"
            if node.op == "-":
                return f"-{self.arithmetic(node.operand, _static_type(node), _PREC_UNARY)}"
            raise TranspileError(f"Unsupported unary operator: {node.op!r}")

        if isinstance(node, BinaryOp):
            return self._binary(node, parent_prec)

        if isinstance(node, MethodCall):
            template = _STRING_METHODS.get(node.method)
            if template is None:
                raise TranspileError(f"Unsupported method: {node.method!r}")
            if len(node.args) != 1:
                raise TranspileError(f"{node.method}() requires exactly 1 argument")
            return template.format(self.string(node.target), self.string(node.args[0]))

        if isinstance(node, FunctionCall):
            return self._function(node, parent_prec)

        if isinstance(node, Ternary):
            cond_sql = self.boolean(node.condition)
            true_sql = self.emit(node.true_expr)
            false_sql = self.emit(node.false_expr)
            return f"if({cond_sql}, {true_sql}, {false_sql})"

        if isinstance(node, ListExpr):
            # Standalone list (not part of 'in') -- emit as tuple
            elems = ", ".join(self.emit(e) for e in node.elements)
            return f"({elems})"

        raise TranspileError(f"Unsupported AST node: {type(node).__name__}")

    def _binary(self, node: BinaryOp, parent_prec: int) -> str:
        sql_op = _OP_MAP.get(node.op)
        if sql_op is None and node.op == "in":
            sql_op = "IN"
        if sql_op is None:
            raise TranspileError(f"Unsupported operator: {node.op!r}")

        my_prec = _SQL_PREC.get(sql_op, 0)
        if node.op == "/":
            divided = self.division(node)
            return f"({divided})" if my_prec < parent_prec else divided
        json_sql = self.json_comparison(node, parent_prec)
        if json_sql is not None:
            return json_sql
        # SQL groups equal-precedence operators from the left, so a right operand at
        # this precedence keeps its parentheses: a - (b - c) is not a - b - c. A
        # comparison does not chain, so its left operand keeps them as well.
        comparison = my_prec == _SQL_PREC["="]
        left_prec = my_prec + 1 if comparison else my_prec
        if node.op in ("&&", "||"):
            left_sql = self.boolean(node.left, left_prec)
            right_sql = self.boolean(node.right, my_prec + 1)
        elif node.op in ("+", "-", "*", "%"):
            kind = _static_type(node)
            left_sql = self.arithmetic(node.left, kind, left_prec)
            right_sql = self.arithmetic(node.right, kind, my_prec + 1)
        else:
            left_sql = self.emit(node.left, left_prec)
            right_sql = self.emit(node.right, my_prec + 1)

        # NULL comparisons need IS NULL / IS NOT NULL semantics in
        # ClickHouse -- `x = NULL` always returns NULL (never true), and
        # `x != NULL` likewise. CEL's `x == null` / `x != null` is meant
        # to test for null-ness, so emit the IS [NOT] NULL form when
        # either operand is the literal NULL.
        if node.op == "==" and (left_sql == "NULL" or right_sql == "NULL"):
            target = right_sql if left_sql == "NULL" else left_sql
            result = f"{target} IS NULL"
        elif node.op == "!=" and (left_sql == "NULL" or right_sql == "NULL"):
            target = right_sql if left_sql == "NULL" else left_sql
            result = f"{target} IS NOT NULL"
        # 'in' with list: x IN (a, b, c)
        elif node.op == "in" and isinstance(node.right, ListExpr):
            elems = ", ".join(self.emit(e) for e in node.right.elements)
            result = f"{left_sql} IN ({elems})"
        else:
            result = f"{left_sql} {sql_op} {right_sql}"

        if my_prec < parent_prec:
            return f"({result})"
        return result

    def _function(self, node: FunctionCall, parent_prec: int) -> str:
        # has(x) -> x IS NOT NULL
        if node.name == "has":
            if len(node.args) != 1:
                raise TranspileError("has() requires exactly 1 argument")
            arg_sql = self.emit(node.args[0])
            result = f"{arg_sql} IS NOT NULL"
            if parent_prec > _SQL_PREC.get("=", 0):
                return f"({result})"
            return result

        path = self.json_path(node.args[0]) if len(node.args) == 1 else None
        if path is not None and node.name in _JSON_CONVERSIONS:
            return _JSON_CONVERSIONS[node.name].format(p=path)

        # Mapped functions: size -> length, int -> toInt64, etc.
        ch_name = _FUNC_MAP.get(node.name)
        if ch_name is not None:
            args_sql = ", ".join(self.emit(a) for a in node.args)
            return f"{ch_name}({args_sql})"

        raise TranspileError(f"Unsupported function: {node.name!r}")


def _when_present(path: str, value: bool) -> str:
    """Return ``value`` where ``path`` holds anything, else NULL, as CEL errors on a missing field."""
    return f"if({path} IS NULL, NULL, {'true' if value else 'false'})"


# -- Public API ----------------------------------------------------


def transpile_to_clickhouse(
    expr: str,
    profile: ProfileConfig | None = None,
    *,
    json_columns: Collection[str] = (),
) -> str:
    """Transpile a CEL expression to a ClickHouse SQL WHERE clause.

    The expression is first validated against the expression profile (syntax +
    allowed functions), then parsed and emitted as ClickHouse SQL.

    Args:
        expr: CEL expression string.
        profile: The profile to enforce. ``None`` means the cascade's, which refuses
            ``matches()`` unless ``expression.allow_regex`` is set.
        json_columns: Names of ClickHouse ``JSON`` columns. A dotted identifier under
            one of them is a dynamic path, read through the typed sub-column the
            other operand's type picks, so a path holding numbers in some rows and
            strings in others compares as CEL compares it.

    Returns:
        ClickHouse SQL WHERE clause fragment.

    Raises:
        ExpressionError: If expression is invalid or violates expression profile.
        TranspileError: If a valid CEL construct cannot be transpiled to SQL.

    Examples::

        >>> transpile_to_clickhouse('severity == "critical"')
        "severity = 'critical'"
        >>> transpile_to_clickhouse('amount > 10000 && !is_test')
        'amount > 10000 AND NOT is_test'
        >>> transpile_to_clickhouse('status in ["active", "pending"]')
        "status IN ('active', 'pending')"
        >>> transpile_to_clickhouse('doc.port > 1024', json_columns=["doc"])
        'coalesce(doc.port.:Int64 > 1024, doc.port.:UInt64 > 1024, doc.port.:Float64 > 1024)'
    """
    # Gate: validate CEL syntax + expression profile.
    errors = validate(expr, profile)
    if errors:
        raise ExpressionError(errors)

    # Parse and emit.
    ast = _parse(expr)
    return _Emitter(frozenset(json_columns)).boolean(ast)
