# contract-parity golden fixtures

## deployment-contract.json

A deployment contract scalo-rs emitted, copied verbatim from `hyperi-io/scalo-rs:tests/fixtures/contract-parity/deployment-contract.json`. scalo-rs pins it from its own serialiser in `tests/integration/contract_parity.rs`, which sets every optional field so none is left out of the file. `tests/unit/deployment/test_contract_parity.py` parses it with scalo-py's models, re-emits it and checks nothing was dropped or changed.

After a contract change in scalo-rs, regenerate it there (the module docs of `contract_parity.rs` give the command) and copy the file here unchanged.

## v1-output.txt

`v1-output.txt` is the cross-language byte-equivalence reference for the **Contract Identity Annotation Scheme v1** (`<namespace>.contract.*`), rendered under the default label namespace `io.scalo` (`DEFAULT_LABEL_NAMESPACE`).

### What it contains

Four sections, separated by `=== <section-name> ===` headers:

| Section | Source |
|---|---|
| `dockerfile-labels` | `ContractIdentity.as_dockerfile_labels("io.scalo")` |
| `yaml-annotations-indent-0` | `ContractIdentity.as_yaml_annotations("io.scalo", indent=0)` |
| `yaml-annotations-indent-2` | `ContractIdentity.as_yaml_annotations("io.scalo", indent=2)` |
| `yaml-annotations-indent-4` | `ContractIdentity.as_yaml_annotations("io.scalo", indent=4)` |

All sections use the canonical test inputs:

```text
source_commit = "0123456789abcdef0123456789abcdef01234567"
image_ref     = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"
```

### Status

**Vendored copy.** The canonical source will eventually live at
`hyperi-io/hyperi-ci:tests/fixtures/contract-parity/v1-output.txt` so
scalo-rs and scalo-py consume from one place.

Until that lands this file is the scalo-py-authored reference. scalo-rs
ships `deployment::contract_identity` but has not published a golden
fixture, so copy its file here verbatim and repoint this README when it
does.

### Drift detection

`tests/unit/deployment/test_contract_identity_parity.py` asserts that `ContractIdentity` produces byte-identical output to each section of this file. Any divergence is a generator regression OR a deliberate spec change -- if deliberate, update this file AND scalo-rs's copy, and bump `VERSION` in `contract_identity.py` when the scheme itself breaks.

The other side is
`hyperi-io/scalo-rs:tests/fixtures/contract-parity/v1-output.txt`. When
a clone of scalo-rs is on disk the parity test additionally diffs the
two copies and a mismatch fails the suite with the diff. That file does
not exist yet, so today the cross-repo check always skips -- and says so
rather than reporting green.

### File format invariants

- LF line endings (`newline="\n"`).
- UTF-8 encoded.
- Trailing newline at end of file (POSIX-standard).
- Each section's content is terminated by the next `===` header OR EOF.
- No blank lines inside a section's content block.
