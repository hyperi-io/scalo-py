# contract-parity golden fixture

`v1-output.txt` is the cross-language byte-equivalence reference for the
**Contract Identity Annotation Scheme v1** (`io.hyperi.contract.*`).

## What it contains

Four sections, separated by `=== <section-name> ===` headers:

| Section | Source |
|---|---|
| `dockerfile-labels` | `ContractIdentity.as_dockerfile_labels()` |
| `yaml-annotations-indent-0` | `ContractIdentity.as_yaml_annotations(indent=0)` |
| `yaml-annotations-indent-2` | `ContractIdentity.as_yaml_annotations(indent=2)` |
| `yaml-annotations-indent-4` | `ContractIdentity.as_yaml_annotations(indent=4)` |

All sections use the canonical test inputs:

```
source_commit = "0123456789abcdef0123456789abcdef01234567"
image_ref     = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"
```

## Status

**Vendored copy.** The canonical source will eventually live at
`hyperi-ci/tests/fixtures/contract-parity/v1-output.txt` so both
rustlib and pylib consume from one place.

Until that lands, this file is the pylib-authored reference. When
rustlib publishes its `contract_identity` module, copy its golden file
verbatim and update this README to point at it.

## Drift detection

`tests/unit/deployment/test_contract_identity_parity.py` asserts that
`ContractIdentity` produces byte-identical output to each section of
this file. Any divergence is a generator regression OR a deliberate
spec change -- if deliberate, update this file AND rustlib's copy AND
bump `KEY_PREFIX` / `VERSION` in `contract_identity.py`.

When a local `/projects/hyperi-rustlib/tests/fixtures/contract-parity/v1-output.txt`
exists, the parity test additionally diffs the two copies; mismatch
fails the suite (with the diff in the assertion message).

## File format invariants

- LF line endings (`newline="\n"`).
- UTF-8 encoded.
- Trailing newline at end of file (POSIX-standard).
- Each section's content is terminated by the next `===` header OR EOF.
- No blank lines inside a section's content block.
