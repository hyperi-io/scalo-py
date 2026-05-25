# Expression

CEL (Common Expression Language) evaluation backed by the
`common-expression-language` package, which wraps the Rust
`cel-interpreter` crate via PyO3. The Rust crate is the same one used
by `hyperi-rustlib` — Python and Rust services parse and evaluate
expressions identically. Zero behavioural drift.

```
pip install hyperi-pylib[expression]
```

---

## Quick start

```python
from hyperi_pylib.expression import evaluate, validate

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
- This wrapper adds the **DFE expression profile** — a hard-coded
  subset of CEL that excludes per-element iteration (`map`, `filter`,
  `exists`, `all`) and time functions (`timestamp`, `duration`) because
  they have unpredictable performance on large data-pipeline records.

---

## API

| Function | Returns | Use for |
|----------|---------|---------|
| `validate(expr)` | `list[str]` (empty if valid) | UI pre-submit, config validation |
| `evaluate(expr, ctx)` | the typed result | one-shot evaluation |
| `evaluate_condition(expr, ctx)` | `bool` | scoring conditions, alert triggers (missing fields → `False`) |
| `compile_expression(expr)` | `cel.Program` | hot-path reuse — compile once, execute many |
| `transpile_to_clickhouse(expr)` | `str` (SQL) | push CEL filters down into ClickHouse queries |

All raise `ExpressionError` on profile violations or syntax errors,
with an `errors: list[str]` attribute carrying every diagnostic.

---

## Validating

```python
from hyperi_pylib.expression import validate

errors = validate('amount > 10000 && severity == "critical"')
assert errors == []

errors = validate('items.map(x, x.size)')
# ["Function 'map()' is not allowed in the DFE expression profile.
#   Excluded for performance: per-element iteration or time functions."]
```

Returns a list rather than raising — UIs can render every error at once
without playing exception ping-pong.

---

## One-shot evaluation

```python
from hyperi_pylib.expression import evaluate

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
from hyperi_pylib.expression import compile_expression

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
from hyperi_pylib.expression import evaluate_condition

evaluate_condition('severity == "critical"', {})        # False
evaluate_condition('severity == "critical"', {"severity": "info"})  # False
evaluate_condition('severity == "critical"', {"severity": "critical"})  # True
```

Catches `RuntimeError`, `ValueError`, `TypeError`, and
`ExpressionError` — anything else propagates.

---

## The DFE profile

Allowed functions (frozenset, exposed as `ALLOWED_FUNCTIONS`):

- String methods: `contains`, `startsWith`, `endsWith`, `matches`
- Size / existence: `size`, `has`
- Type casts: `int`, `uint`, `double`, `string`, `bool`

Disallowed (frozenset, exposed as `DISALLOWED_FUNCTIONS`):

- Per-element iteration: `map`, `filter`, `exists`, `exists_one`, `all`
- Time: `timestamp`, `duration`

The "no time functions" rule keeps expressions deterministic — the same
expression against the same record produces the same answer regardless
of when the pipeline ran it.

---

## Transpile to ClickHouse SQL

```python
from hyperi_pylib.expression import transpile_to_clickhouse

sql_where = transpile_to_clickhouse('severity == "critical" && amount > 10000')
# Returns the ClickHouse WHERE-clause fragment
```

Use this when you have a CEL rule the operator defined, and you want
to push the filter down into a ClickHouse `WHERE` clause instead of
fetching every row and filtering in Python. Raises `TranspileError` for
constructs that don't map to SQL.

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
# Python — hyperi-pylib
from hyperi_pylib.expression import evaluate
evaluate('amount > threshold', {"amount": 15000, "threshold": 10000})  # True
```

```rust
// Rust — hyperi-rustlib
use hyperi_rustlib::expression::evaluate;
evaluate("amount > threshold", &ctx)?  // also true
```

Same crate, same parser, same evaluator — a CEL test suite that passes
on one passes on the other.

---

## Related

- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [DIRECTORY-CONFIG.md](DIRECTORY-CONFIG.md)
- [DATABASE.md](DATABASE.md)
- [CACHE.md](CACHE.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
- [../INTEGRATION.md](../INTEGRATION.md)
