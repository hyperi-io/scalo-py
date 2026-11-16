# Contributing

We welcome contributions to this project. By contributing, you agree to the
terms outlined below.

## Commit Message Format

HyperI projects use [Conventional Commits](https://www.conventionalcommits.org/)
and [semantic-release](https://semantic-release.gitbook.io/) for automated
versioning and changelog generation. All commits must follow this format:

```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | A new feature | Minor (0.X.0) |
| `fix` | A bug fix | Patch (0.0.X) |
| `docs` | Documentation only | None |
| `style` | Code style (formatting, semicolons, etc.) | None |
| `refactor` | Code change that neither fixes a bug nor adds a feature | None |
| `perf` | Performance improvement | Patch (0.0.X) |
| `test` | Adding or correcting tests | None |
| `build` | Changes to build system or dependencies | None |
| `ci` | Changes to CI configuration | None |
| `chore` | Other changes that don't modify src or test files | None |
| `revert` | Reverts a previous commit | Varies |

### Breaking Changes

For breaking changes that require a major version bump, add `!` after the type
or include `BREAKING CHANGE:` in the footer:

```text
feat!: remove deprecated API endpoints

BREAKING CHANGE: The /v1/users endpoint has been removed. Use /v2/users instead.
```

### Examples

```text
feat(auth): add OAuth2 support for Google login

fix(api): handle null response from upstream service

docs: update installation instructions for Windows

refactor(core)!: restructure module exports

BREAKING CHANGE: Named exports are now used instead of default exports.
```

### Scope

Scope is optional but recommended. Use it to indicate the area of the codebase
affected (e.g., `api`, `auth`, `core`, `cli`, `docs`).

## Semantic Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes that require users to modify their code
- **MINOR** (0.X.0): New features that are backwards-compatible
- **PATCH** (0.0.X): Bug fixes and minor improvements

Versions are automatically determined by semantic-release based on commit
messages. Do not manually update version numbers.

## License for Contributions

All contributions to this project are licensed under the Apache License,
Version 2.0 (Apache-2.0), the same license that covers the project. By
submitting a contribution you agree that it is provided under those terms.

## How to Contribute

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the commit message format above
3. **Test your changes** to ensure they work as expected
4. **Submit a pull request** with a clear description of what you've done

### Pull Request Checklist

- [ ] Commits follow the conventional commit format
- [ ] Tests pass (if applicable)
- [ ] Documentation is updated (if applicable)

## Run the checks locally before you push

HyperI projects gate every push through CI (lint, format, tests, secret scan,
dependency audit, build). Run the SAME checks locally first so your change lands
green instead of bouncing:

```bash
hyperi-ci check
```

`hyperi-ci` is the HyperI CI CLI (public on PyPI). If you do not have it, install
it once with `uv tool install hyperi-ci` (or `pipx install hyperi-ci`), or run it
ad hoc with `uvx hyperi-ci check`. It runs the project's local validation and reports
what to fix. [tests/TESTING.md](tests/TESTING.md) has the core and full test
tiers and when CI runs each. Run it before every push and before opening a
pull request. It is the single best way to give your change the best chance of
surviving CI.

## CI/CD Workflow

When your pull request is merged to `main`:

1. **semantic-release** analyses commit messages since the last release
2. Determines the next version number based on commit types
3. Generates/updates the CHANGELOG
4. Creates a new GitHub release with release notes
5. Publishes the package (if applicable)

This happens automatically - no manual intervention required.

## Questions

If you have questions about contributing, please open an issue or contact us.

## Context

### What this is

HyperI's shared Python library -- config cascade, logging, metrics, health,
secrets, Kafka and the deployment-contract generators -- published as `scalo` on
PyPI under Apache-2.0.

scalo-py and scalo-rs share conventions and have separate APIs and repositories, so check each API on its own. Where the two must agree, a shared corpus vendored from scalo-rs says so: credential masking is checked against `tests/fixtures/patterns/credential_masking_parity.json`, and the rules engine against `tests/fixtures/rules_corpus.json`.

### Where things live

| Path | What it holds |
|------|---------------|
| `src/scalo/<module>/` | One directory per module: `config`, `logger`, `metrics`, `health`, `http`, `kafka`, `secrets`, `deployment`, `cli` |
| `src/scalo/data/` | Vendored runtime pattern files, copied by `tools/vendor_patterns.sh` |
| `tests/{unit,integration,e2e,smoke}/` | Split by what each needs in order to run |
| `docs/architecture.md` | Layering, the module dependency graph, and what scalo-rs has that this does not |

### Commands that prove a change

```bash
make quality   # lint, type-check, security audit
make test      # the core test tier
make build     # the wheel
```

The core tier excludes tests marked `full`. [tests/TESTING.md](tests/TESTING.md)
has both tiers and what each needs on the box. Read the per-job CI result, never
a local summary. Coverage is gated in `.hyperi-ci.yaml`.

### What tends to bite

| Don't | Do | Why |
|-------|----|-----|
| Read a skip as a pass | Make a guard fail when what it guards is absent | A parity guard fails when its fixture file is missing, and an import guard names the symbols it imports so a renamed one fails rather than skips (`2ca8329`) |
| Copy an API name or an env var out of the docs | Check the `control_var` call sites and the module | The code is the source for names, and a doc can lag a rename (`da005a0`) |
| Assume a config key you added is read | Follow it to its reader | SIGHUP reload and polling are checked on their own, and a label key is unique in the OTel label map (`6a2b21b`) |

### Where this sits

Generated from `dfe-infra/suite.yaml` via `dfe-stack suite`. Nothing in the suite
feeds this repo -- it declares no inbound edges.

| Repo | Kind | Mechanism, outbound |
|------|------|---------------------|
| dfe-engine | `python-dep`, potential | Declares `scalo` by range in `pyproject.toml`, no upper bound |
| dfe-engine | `contract-guard`, lockstep | It overrides our runtime base image with its own literal, and its own test fails when its committed Dockerfile stops matching. The validator is ours, `scalo.deployment.validate_dockerfile` |
| culvert | `python-dep`, potential | Declares `scalo` by range. A second range, for the deployment-contract generators, is dev-only |
| vector-vrl | `python-dep`, potential | Build system only, not the published wheel |
