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

## Developer Certificate of Origin

This project uses the Developer Certificate of Origin (DCO) to ensure that
contributors have the right to submit their contributions.

By making a contribution to this project, you certify that:

1. The contribution was created in whole or in part by you and you have the
   right to submit it under the license indicated in the file; or

2. The contribution is based upon previous work that, to the best of your
   knowledge, is covered under an appropriate open source license and you
   have the right under that license to submit that work with modifications;
   or

3. The contribution was provided directly to me by some other person who
   certified (1), (2) or (3) and you have not modified it.

4. You understand and agree that this project and the contribution are public
   and that a record of the contribution (including all personal information
   you submit with it, including your sign-off) is maintained indefinitely
   and may be redistributed consistent with this project or the license(s)
   involved.

## How to Sign Off Your Commits

You must sign off each commit to indicate your acceptance of the DCO. Combine
the signoff with your conventional commit message:

```bash
git commit --signoff -m "feat(auth): add two-factor authentication"
```

This produces:

```text
feat(auth): add two-factor authentication

Signed-off-by: Your Name <your.email@example.com>
```

Make sure your Git configuration has your correct name and email:

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## License for Contributions

All contributions to this project are licensed under the Apache License,
Version 2.0 (Apache-2.0), the same license that covers the project. By
submitting a contribution you agree that it is provided under those terms.

## How to Contribute

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the commit message format above
3. **Sign off your commits** with the DCO
4. **Test your changes** to ensure they work as expected
5. **Submit a pull request** with a clear description of what you've done

### Pull Request Checklist

- [ ] Commits follow the conventional commit format
- [ ] All commits are signed off (DCO)
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
ad hoc with `uvx hyperi-ci check`. It runs the project's full local validation --
the same suite CI runs -- and reports what to fix. Run it before every push and before opening a
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

It is scalo-rs's SISTER, not its twin: same conventions, DIFFERENT API, separate repo. Never assume parity. Where the two must agree, a shared corpus vendored from scalo-rs says so: credential masking is checked against `tests/fixtures/patterns/credential_masking_parity.json`, and the rules engine against `tests/fixtures/rules_corpus.json`.

### Where things live

| Path | What it holds |
|------|---------------|
| `src/scalo/<module>/` | One directory per module: `config`, `logger`, `metrics`, `health`, `http`, `kafka`, `secrets`, `deployment`, `cli` |
| `src/scalo/data/` | Vendored corpora and rule files, landed by `tools/vendor_patterns.sh` |
| `tests/{unit,integration,e2e,smoke}/` | Split by what each needs in order to run |
| `docs/architecture.md` | Layering, the module dependency graph, and what scalo-rs has that this does not |

### Commands that prove a change

```bash
make quality   # lint, type-check, security audit
make test      # the suite
make build     # the wheel
```

`addopts` deselects no markers, so `make test` runs integration and e2e as well,
and on a developer box that is not green. This run was 9 failed, 2552 passed, 31
skipped in 7m01s -- 6 GCP secrets tests wanting `gcloud auth
application-default login`, 2 CLI tests binding a fixed `0.0.0.0:9090`, and one
Dockerfile build. Read the per-job CI result, never a local summary. Coverage is
gated in `.hyperi-ci.yaml`.

### What tends to bite

| Don't | Do | Why |
|-------|----|-----|
| Read a skip as a pass | Make a guard fail when what it guards is absent | Both parity modules read fixtures from a `scalo-spec` checkout that never existed, so every case skipped everywhere including CI -- and the canary was itself `skipif(not path.exists())`, its skip condition being its own assertion negated. Tightening the import guards then caught `test_import_http` importing `create_client`, which does not exist (`2ca8329`) |
| Copy an API name or an env var out of the docs | Check the `control_var` call sites and the module | The docs named `for_pylib_extras` and `for_rustlib_features`, really `for_scalo_extras` and `for_scalo_features`, plus eight `HYPERI_*` variables removed with no fallback (`da005a0`) |
| Assume a config key you added is read | Follow it to its reader | `enable_sighup` was honoured only when `poll_interval > 0`, so "reload on SIGHUP, never poll" registered no handler. A duplicate `status` key in the OTel label map exported every HTTP metric as `task.status` (`6a2b21b`) |

### Where this sits

Generated from `dfe-infra/suite.yaml` via `dfe-stack suite`. Nothing in the suite
feeds this repo -- it declares no inbound edges.

| Repo | Kind | Mechanism, outbound |
|------|------|---------------------|
| dfe-engine | `python-dep`, potential | Declares `scalo` by range in `pyproject.toml`, no upper bound |
| dfe-engine | `contract-guard`, lockstep | It overrides our runtime base image with its own literal, and its own test fails when its committed Dockerfile stops matching. The validator is ours, `scalo.deployment.validate_dockerfile` |
| culvert | `python-dep`, potential | Declares `scalo` by range. A second range, for the deployment-contract generators, is dev-only |
| vector-vrl | `python-dep`, potential | Build system only, not the published wheel |
