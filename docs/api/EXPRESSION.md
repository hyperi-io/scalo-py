# Expression

CEL (Common Expression Language) evaluation backed by the
`common-expression-language` package, which wraps the Rust `cel` crate (formerly `cel-interpreter`) via PyO3. The Rust crate is the same one used by the `scalo` crate, so Python and Rust services parse and evaluate expressions identically. The extra needs 0.10.0 or later, the first release built on cel-rust 0.14.5 that also imports in a clean install.

```bash
pip install scalo[expression]
```

---

## Quick start

```python
from scalo.expression import evaluate, validate

errors = validate('severity == "critical" && amount > 10000')
assert errors == []

result = evaluate('amount > 10000', {"amount": 15000})
assert result is True
```

---

## Why CEL, why this wrapper

- CEL has known costs, no side effects, terminates by construction —
  safe to evaluate untrusted operator-supplied rules.
- One Rust implementation means a rule that scores `true` in Python
  scores `true` in Rust. No "the Python and Rust scorers disagree"
  outages.
- This wrapper adds the **expression profile**, the subset of CEL with a bounded cost per record. Regex, per-element iteration and time functions are refused until the app unlocks them, see [The expression profile](#the-expression-profile).

---

## API

| Function | Returns | Use for |
|----------|---------|---------|
| `validate(expr, profile=None)` | `list[str]` (empty if valid) | UI pre-submit, config validation |
| `diagnose(expr, profile=None)` | `list[Diagnostic]` (empty if valid) | an editor that underlines the call or token at fault |
| `evaluate(expr, ctx)` | the typed result | one-shot evaluation |
| `evaluate_condition(expr, ctx)` | `bool` | scoring conditions, alert triggers (missing fields -> `False`) |
| `compile_expression(expr, profile=None)` | `cel.Program` | hot-path reuse: compile once, execute many |
| `transpile_to_clickhouse(expr, profile=None)` | `str` (SQL) | push CEL filters down into ClickHouse queries |

`profile=None` enforces the profile the config cascade sets, and `evaluate` and `evaluate_condition` always do. `compile_expression`, `evaluate` and `transpile_to_clickhouse` raise `ExpressionError` on profile violations or syntax errors, with an `errors: list[str]` attribute carrying every diagnostic. [RULES.md](RULES.md) builds ordered first-match rule sets on top.

---

## Validating

```python
from scalo.expression import validate

errors = validate('amount > 10000 && severity == "critical"')
assert errors == []

errors = validate('items.map(x, x.size)')
# ["Function 'map()' is not allowed in the expression profile. Per-element
#   iteration has O(n) cost proportional to collection size. Set
#   allow_iteration: true in expression config to permit."]
```

Returns a list rather than raising, so a UI renders every error at once. A function name inside a quoted string is data, so `msg.contains("map(x)")` validates clean. Whitespace between a name and its `(`, a tab or a newline included, does not hide a call.

---

## Locating a problem

`diagnose` finds what `validate` finds, each as a `Diagnostic` with a `message` and a `span`. The span is a byte range into the UTF-8 text, `end` exclusive, so `expr.encode()[span.start:span.end]` is the text at fault:

```python
from scalo.expression import diagnose

found = diagnose('severity == "high" && host.matches("^w")')
found[0].span    # Span(start=27, end=34), the name "matches"

found = diagnose("severity == && x")
found[0].message  # "Syntax error: extraneous input '&&' expecting ..."
found[0].span     # Span(start=12, end=13), where the parser stopped
```

An editor that indexes strings by character or by UTF-16 code unit, as JavaScript does, converts the span against the same text:

```python
expr = 'label == "été 😀" && x.map(a, a)'
span = diagnose(expr)[0].span   # Span(start=27, end=30), bytes
span.char_offsets(expr)         # (22, 25), so expr[22:25] == "map"
span.utf16_offsets(expr)        # (23, 26), the emoji counts as two units
```

Both raise `ValueError` for a span outside the text or one that ends inside a character.

A profile finding spans the function name, and the profile is checked before the expression is parsed. A syntax error spans the character the parser stopped at, one diagnostic per parser error. An empty expression has no span. `scan_profile(expr, profile=None)` runs only the profile check, and `check_profile` is the same without spans.

---

## One-shot evaluation

```python
from scalo.expression import evaluate

result = evaluate('severity == "critical"', {"severity": "critical"})
assert result is True

result = evaluate('size(tags) > 0', {"tags": ["foo", "bar"]})
assert result is True
```

`evaluate` compiles every call — fine for occasional checks, wasteful
for repeated evaluation against many records.

---

## Hot-path compilation

When the same expression runs against millions of records:

```python
from scalo.expression import compile_expression

program = compile_expression("amount > threshold")
for record in stream:
    if program.execute(record):
        forward(record)
```

`compile_expression` validates against the profile and compiles once.
`program.execute(ctx)` is the per-record hot path — no parsing, no
profile checks.

---

## Safe boolean evaluation

`evaluate_condition` is the right shape for routing rules, alert
triggers, and `when:` clauses. Missing fields return `False` instead
of raising:

```python
from scalo.expression import evaluate_condition

evaluate_condition('severity == "critical"', {})        # False
evaluate_condition('severity == "critical"', {"severity": "info"})  # False
evaluate_condition('severity == "critical"', {"severity": "critical"})  # True
evaluate_condition('user.role == "admin"', {"user": {}})  # False
```

An invalid expression returns `False`, and so does every error the cel package raises while evaluating: a missing variable or map key, a type mismatch, division by zero, an index out of range, an overflow. Each distinct expression is compiled once and kept, up to 1,024 of them with the least recently used dropped first, so calling it per record with the same few conditions compiles nothing after the first call.

---

## The expression profile

Allowed functions (frozenset, exposed as `ALLOWED_FUNCTIONS`):

- String methods: `contains`, `startsWith`, `endsWith`
- Size / existence: `size`, `has`
- Type casts: `int`, `uint`, `double`, `string`, `bool`, `bytes`
- Type introspection: `type`, `dyn`
- Timestamp accessors: `getFullYear`, `getHours` and the rest of the `get*` family

A function in neither list is refused, so a misspelt name fails validation rather than evaluation.

Restricted categories, each refused until its flag is set (`DISALLOWED_FUNCTIONS` is all three):

| Category | Functions | Flag | Why |
|---|---|---|---|
| `RESTRICTED_REGEX` | `matches` | `allow_regex` | regex cost per record is unbounded |
| `RESTRICTED_ITERATION` | `map`, `filter`, `exists`, `exists_one`, `all` | `allow_iteration` | cost grows with the collection |
| `RESTRICTED_TIME` | `timestamp`, `duration` | `allow_time` | keeps a result independent of when the pipeline ran it |

An app sets the flags under `expression` in its config, and every call with `profile=None` reads them from there:

```yaml
expression:
  allow_regex: true
```

`ProfileConfig(allow_regex=True)` passed as `profile=` overrides the cascade for one call. The first clean read of the cascade is kept for the life of the process, and a flag that is not `true` or `false` leaves every restriction on.

---

## Transpile to ClickHouse SQL

```python
from scalo.expression import transpile_to_clickhouse

sql_where = transpile_to_clickhouse('severity == "critical" && amount > 10000')
# Returns the ClickHouse WHERE-clause fragment
```

Use this when you have a CEL rule the operator defined, and you want
to push the filter down into a ClickHouse `WHERE` clause instead of
fetching every row and filtering in Python. Raises `TranspileError` for
constructs that don't map to SQL. `matches()` transpiles to `match()` only under a profile that allows regex.

---

## Result types

CEL types map to Python types directly: `bool`, `int`, `float`, `str`,
`list`, `dict`. Numeric operations follow CEL's type promotion rules —
`evaluate('1 + 1.0')` returns `2.0`.

---

## Errors

| Exception | When |
|-----------|------|
| `ExpressionError(errors=[...])` | Profile violation or parse error. `errors` is the list returned by `validate`. |
| `RuntimeError` | Evaluation failed at runtime (missing field with unsafe access, type mismatch). |
| `TranspileError` | `transpile_to_clickhouse` couldn't lower this construct. |

---

## Cross-language parity

```python
# Python — scalo
from scalo.expression import evaluate
evaluate('amount > threshold', {"amount": 15000, "threshold": 10000})  # True
```

```rust
// Rust — the scalo crate
use scalo::expression::evaluate;
evaluate("amount > threshold", &ctx)?  // also true
```

Same crate, same parser, same evaluator — a CEL test suite that passes
on one passes on the other.

---

## Related

- [RULES.md](RULES.md) -- ordered first-match rules with native tests and CEL conditions
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [DIRECTORY-CONFIG.md](DIRECTORY-CONFIG.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
- [../INTEGRATION.md](../INTEGRATION.md)
