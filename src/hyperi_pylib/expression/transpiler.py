# Project:   hyperi-pylib
# File:      expression/transpiler.py
# Purpose:   CEL-to-ClickHouse SQL transpilation
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""CEL-to-ClickHouse SQL transpiler.

Converts DFE profile CEL expressions into ClickHouse-compatible SQL
WHERE clauses for query pushdown. The expression is first validated
via :func:`validate` (CEL syntax + DFE profile), then tokenized,
parsed into an AST, and emitted as ClickHouse SQL.

Safety layers:
    1. CEL validation gate (syntax + DFE profile)
    2. String literal escaping (single-quote doubling)
    3. Identifier validation (alphanumeric + dots only)

Usage::

    from hyperi_pylib.expression import transpile_to_clickhouse

    sql = transpile_to_clickhouse('severity == "critical" && amount > 10000')
    # => "severity = 'critical' AND amount > 10000"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from __future__ import annotations

from .cel import ExpressionError, validate

__all__ = ["TranspileError", "transpile_to_clickhouse"]


# ── Errors ────────────────────────────────────────────────────────


class TranspileError(Exception):
    """Raised when a valid CEL expression cannot be transpiled to SQL."""


# ── AST ───────────────────────────────────────────────────────────


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


# ── Tokenizer ─────────────────────────────────────────────────────


class TT(Enum):
    """Token type."""
    STRING = auto()
    NUMBER = auto()
    IDENT = auto()
    OP = auto()       # ==, !=, <, <=, >, >=, &&, ||, +, -, *, /, %
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    DOT = auto()
    QUESTION = auto()
    COLON = auto()
    BANG = auto()      # !
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
            raise TranspileError(
                f"Unexpected character {expr[pos]!r} at position {pos}"
            )

    tokens.append(Token(TT.EOF, "", pos))
    return tokens


# ── Parser (Pratt) ────────────────────────────────────────────────

# Precedence levels (higher = tighter binding).
_PREC_TERNARY = 1
_PREC_OR = 2
_PREC_AND = 3
_PREC_COMPARISON = 4  # ==, !=, <, <=, >, >=, in
_PREC_ADDITIVE = 5    # +, -
_PREC_MULTIPLICATIVE = 6  # *, /, %
_PREC_UNARY = 7       # !, unary -
_PREC_POSTFIX = 8     # .method(), ()

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
    """Pratt parser for DFE profile CEL expressions."""

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
            raise TranspileError(
                f"Expected {tt.name}, got {tok.type.name} ({tok.value!r}) "
                f"at position {tok.pos}"
            )
        return tok

    def parse(self) -> Expr:
        """Parse the full expression."""
        expr = self._parse_expr(0)
        if self._peek().type != TT.EOF:
            tok = self._peek()
            raise TranspileError(
                f"Unexpected token {tok.value!r} at position {tok.pos}"
            )
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

        raise TranspileError(
            f"Unexpected token {tok.value!r} ({tok.type.name}) "
            f"at position {tok.pos}"
        )

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


# ── SQL Emitter ───────────────────────────────────────────────────

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")

# Binary operator mapping: CEL → ClickHouse SQL.
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

# Function call mapping: CEL function → ClickHouse function name.
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
    "=": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3, "IN": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5, "%": 5,
}


def _escape_string(s: str) -> str:
    """Escape a string for ClickHouse SQL (single-quoted)."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _emit(node: Expr, parent_prec: int = 0) -> str:
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
            inner = _emit(node.operand, _PREC_UNARY)
            return f"NOT {inner}"
        if node.op == "-":
            inner = _emit(node.operand, _PREC_UNARY)
            return f"-{inner}"
        raise TranspileError(f"Unsupported unary operator: {node.op!r}")

    if isinstance(node, BinaryOp):
        sql_op = _OP_MAP.get(node.op)
        if sql_op is None and node.op == "in":
            sql_op = "IN"
        if sql_op is None:
            raise TranspileError(f"Unsupported operator: {node.op!r}")

        my_prec = _SQL_PREC.get(sql_op, 0)
        left_sql = _emit(node.left, my_prec)
        right_sql = _emit(node.right, my_prec)

        # 'in' with list: x IN (a, b, c)
        if node.op == "in" and isinstance(node.right, ListExpr):
            elems = ", ".join(_emit(e) for e in node.right.elements)
            result = f"{left_sql} IN ({elems})"
        else:
            result = f"{left_sql} {sql_op} {right_sql}"

        if my_prec < parent_prec:
            return f"({result})"
        return result

    if isinstance(node, MethodCall):
        target_sql = _emit(node.target)

        if node.method == "contains":
            if len(node.args) != 1:
                raise TranspileError("contains() requires exactly 1 argument")
            arg_sql = _emit(node.args[0])
            return f"position({target_sql}, {arg_sql}) > 0"

        if node.method == "startsWith":
            if len(node.args) != 1:
                raise TranspileError("startsWith() requires exactly 1 argument")
            arg_sql = _emit(node.args[0])
            return f"startsWith({target_sql}, {arg_sql})"

        if node.method == "endsWith":
            if len(node.args) != 1:
                raise TranspileError("endsWith() requires exactly 1 argument")
            arg_sql = _emit(node.args[0])
            return f"endsWith({target_sql}, {arg_sql})"

        if node.method == "matches":
            if len(node.args) != 1:
                raise TranspileError("matches() requires exactly 1 argument")
            arg_sql = _emit(node.args[0])
            return f"match({target_sql}, {arg_sql})"

        raise TranspileError(f"Unsupported method: {node.method!r}")

    if isinstance(node, FunctionCall):
        # has(x) → x IS NOT NULL
        if node.name == "has":
            if len(node.args) != 1:
                raise TranspileError("has() requires exactly 1 argument")
            arg_sql = _emit(node.args[0])
            result = f"{arg_sql} IS NOT NULL"
            if parent_prec > _SQL_PREC.get("=", 0):
                return f"({result})"
            return result

        # Mapped functions: size → length, int → toInt64, etc.
        ch_name = _FUNC_MAP.get(node.name)
        if ch_name is not None:
            args_sql = ", ".join(_emit(a) for a in node.args)
            return f"{ch_name}({args_sql})"

        raise TranspileError(f"Unsupported function: {node.name!r}")

    if isinstance(node, Ternary):
        cond_sql = _emit(node.condition)
        true_sql = _emit(node.true_expr)
        false_sql = _emit(node.false_expr)
        return f"if({cond_sql}, {true_sql}, {false_sql})"

    if isinstance(node, ListExpr):
        # Standalone list (not part of 'in') — emit as tuple
        elems = ", ".join(_emit(e) for e in node.elements)
        return f"({elems})"

    raise TranspileError(f"Unsupported AST node: {type(node).__name__}")


# ── Public API ────────────────────────────────────────────────────


def transpile_to_clickhouse(expr: str) -> str:
    """Transpile a CEL expression to a ClickHouse SQL WHERE clause.

    The expression is first validated against the DFE profile (syntax +
    allowed functions), then parsed and emitted as ClickHouse SQL.

    Args:
        expr: CEL expression string.

    Returns:
        ClickHouse SQL WHERE clause fragment.

    Raises:
        ExpressionError: If expression is invalid or violates DFE profile.
        TranspileError: If a valid CEL construct cannot be transpiled to SQL.

    Examples::

        >>> transpile_to_clickhouse('severity == "critical"')
        "severity = 'critical'"
        >>> transpile_to_clickhouse('amount > 10000 && !is_test')
        'amount > 10000 AND NOT is_test'
        >>> transpile_to_clickhouse('status in ["active", "pending"]')
        "status IN ('active', 'pending')"
    """
    # Gate: validate CEL syntax + DFE profile.
    errors = validate(expr)
    if errors:
        raise ExpressionError(errors)

    # Parse and emit.
    ast = _parse(expr)
    return _emit(ast)
