## [2.23.1](https://github.com/hyperi-io/hyperi-pylib/compare/v2.23.0...v2.23.1) (2026-02-28)


### Bug Fixes

* remove unused variable in version check test ([02eb683](https://github.com/hyperi-io/hyperi-pylib/commit/02eb68355ec41b70098e3491144372503def1996))

# [2.23.0](https://github.com/hyperi-io/hyperi-pylib/compare/v2.22.0...v2.23.0) (2026-02-28)


### Features

* startup version check module ([837c316](https://github.com/hyperi-io/hyperi-pylib/commit/837c3161a87ea27fe1cf5f7d11834e6425bcb4ff))

# [2.22.0](https://github.com/hyperi-io/hyperi-pylib/compare/v2.21.0...v2.22.0) (2026-02-28)


### Features

* align config cascade with hyperi-rustlib unified spec ([94255e5](https://github.com/hyperi-io/hyperi-pylib/commit/94255e5caf483bb3daaf0be6bdd49ae92f8110cb))

# [2.21.0](https://github.com/hyperi-io/hyperi-pylib/compare/v2.20.1...v2.21.0) (2026-02-28)


### Features

* align config cascade with hyperi-rustlib unified spec ([b126b7a](https://github.com/hyperi-io/hyperi-pylib/commit/b126b7a9f79b27ca3003e99d44a2bf23db222cce))

## [2.20.1](https://github.com/hyperi-io/hyperi-pylib/compare/v2.20.0...v2.20.1) (2026-02-18)


### Bug Fixes

* Update to use hyperi repo in jfrog ([8374992](https://github.com/hyperi-io/hyperi-pylib/commit/8374992f95f0fe9b31da6c42f095ef4b9ef42936))

# [2.20.0](https://github.com/hyperi-io/hyperi-pylib/compare/v2.19.1...v2.20.0) (2026-02-16)


### Features

* add subdirectory support to DirectoryConfigStore ([b20240a](https://github.com/hyperi-io/hyperi-pylib/commit/b20240ab335c83c5d4ebcb9a1d322056003fd9eb))

## [2.19.1](https://github.com/hyperi-io/hyperi-pylib/compare/v2.19.0...v2.19.1) (2026-02-16)


### Bug Fixes

* replace subprocess git with dulwich in DirectoryConfigStore ([08528a8](https://github.com/hyperi-io/hyperi-pylib/commit/08528a8c28d5ed38e5bde82cd61517cdbd62d23c))

# [2.19.0](https://github.com/hyperi-io/hyperi-pylib/compare/v2.18.1...v2.19.0) (2026-02-16)


### Features

* add DirectoryConfigStore and dual OTel+Prometheus metrics export ([5a15570](https://github.com/hyperi-io/hyperi-pylib/commit/5a155707d81305eebc02013534b96f4493704e8d))

## [2.18.1](https://github.com/hyperi-io/hyperi-pylib/compare/v2.18.0...v2.18.1) (2026-02-16)


### Bug Fixes

* use SPDX-compliant LicenseRef for FSL-1.1-ALv2 license expression ([efd44b2](https://github.com/hyperi-io/hyperi-pylib/commit/efd44b21deaf2306d860890f4aa33c3d63b1020d))

# [2.18.0](https://github.com/hyperi-io/hyperi-pylib/compare/v2.17.1...v2.18.0) (2026-02-10)


### Bug Fixes

* formatting and license header cleanup from rebrand ([e1eb045](https://github.com/hyperi-io/hyperi-pylib/commit/e1eb0452aaf5a5709f19c0aca84663d8608ede87))
* update GitHub org from hypersec-io to hyperi-io, fix database test env bleed ([5f65061](https://github.com/hyperi-io/hyperi-pylib/commit/5f65061af5d6e2f345b7cae29d56909478295eeb))


### Features

* rebrand from HyperSec/hs-pylib to HyperI/hyperi-pylib ([373eff7](https://github.com/hyperi-io/hyperi-pylib/commit/373eff72881a7ee45272ecff0e8318907d45888c))


### BREAKING CHANGES

* Package renamed from hs-pylib to hyperi-pylib.
All imports change from hs_pylib to hyperi_pylib.
All env vars renamed from HS_*/HYPERSEC_* to HYPERI_*.

- Change license from proprietary EULA to FSL-1.1-ALv2
- Add COMMERCIAL.md, CONTRIBUTING.md, SECURITY.md
- Rename package directory src/hs_pylib -> src/hyperi_pylib
- Update all imports, tests, configs, docker-compose files
- Rename env vars: HS_CONFIG_* -> HYPERI_CONFIG_*, HS_LIB_* -> HYPERI_LIB_*,
  HS_SECRETS_* -> HYPERI_SECRETS_*, HYPERSEC_LICENSE_* -> HYPERI_LICENSE_*
- Update brand text, emails (dev@hyperi.io), copyright (HYPERI PTY LIMITED)
- Rename Helm chart from hs-pylib-app to hyperi-pylib-app
- Update license defaults key to hyperi-default-license-key-v1
- Update license paths from /etc/hypersec/ to /etc/hyperi/

## [2.17.1](https://github.com/hypersec-io/hs-pylib/compare/v2.17.0...v2.17.1) (2026-02-03)


### Bug Fixes

* Fix flaky test_version_from_mtime test ([a8b5fdf](https://github.com/hypersec-io/hs-pylib/commit/a8b5fdf7d8e96121570cd1bba95abb13ac7a9c84))

# [2.17.0](https://github.com/hypersec-io/hs-pylib/compare/v2.16.0...v2.17.0) (2026-02-03)


### Features

* Add .env cascade loading for home and project directories ([f8c7168](https://github.com/hypersec-io/hs-pylib/commit/f8c71686aa4801ff29d81128ba8ca9777292faa5))
* Add unified secrets management module with multi-provider support ([a701143](https://github.com/hypersec-io/hs-pylib/commit/a70114377073d1310dee82d8c0dee1311f83318e))

# [2.16.0](https://github.com/hypersec-io/hs-pylib/compare/v2.15.7...v2.16.0) (2026-02-03)


### Features

* PostgreSQL config overrides files, add fallback file support ([f48f94e](https://github.com/hypersec-io/hs-pylib/commit/f48f94efae46985180fc1cc394910d479bafb2b0))

## [2.15.7](https://github.com/hypersec-io/hs-pylib/compare/v2.15.6...v2.15.7) (2026-01-24)


### Bug Fixes

* Add new function to init ([0f4e581](https://github.com/hypersec-io/hs-pylib/commit/0f4e581b99e648e7f0415725cdf0d4cdcaa19f53))

## [2.15.6](https://github.com/hypersec-io/hs-pylib/compare/v2.15.5...v2.15.6) (2026-01-24)


### Bug Fixes

* Remove custom emoji definition ([8f4bb88](https://github.com/hypersec-io/hs-pylib/commit/8f4bb886223b8782c3e78316f90732d9e572e7b4))

## [2.15.5](https://github.com/hypersec-io/hs-pylib/compare/v2.15.4...v2.15.5) (2026-01-24)


### Bug Fixes

* Enabled new custom log command ([aefe7f8](https://github.com/hypersec-io/hs-pylib/commit/aefe7f89c58eb2ce9d0158a0f45c1a8552208ef6))

## [2.15.4](https://github.com/hypersec-io/hs-pylib/compare/v2.15.3...v2.15.4) (2026-01-23)


### Bug Fixes

* Only adding extra space for warning ([3cd774b](https://github.com/hypersec-io/hs-pylib/commit/3cd774b36ba4f91694d41cc6b1595265b55b060d))

## [2.15.3](https://github.com/hypersec-io/hs-pylib/compare/v2.15.2...v2.15.3) (2026-01-22)


### Bug Fixes

* Logger emoji is using two whitespace chars ([c072f6b](https://github.com/hypersec-io/hs-pylib/commit/c072f6ba1d113720ecec3c29749e3d3e815fe98a))

## [2.15.2](https://github.com/hypersec-io/hs-pylib/compare/v2.15.1...v2.15.2) (2026-01-22)


### Bug Fixes

* Make subdir creation a param ([4a64cd5](https://github.com/hypersec-io/hs-pylib/commit/4a64cd52ba93bacd6ae0c8d08fd68acef99ae3c6))

## [2.15.1](https://github.com/hypersec-io/hs-pylib/compare/v2.15.0...v2.15.1) (2026-01-21)


### Bug Fixes

* Give ability to name config subdir ([428b1f2](https://github.com/hypersec-io/hs-pylib/commit/428b1f2a9bb502b446fda3ea83445df146bff386))

# [2.15.0](https://github.com/hypersec-io/hs-pylib/compare/v2.14.7...v2.15.0) (2026-01-20)


### Features

* add license module for cross-language license management ([6fdd5f1](https://github.com/hypersec-io/hs-pylib/commit/6fdd5f100ee49fb67d4a76d3ebae4cf52db3e442))

## [2.14.7](https://github.com/hypersec-io/hs-pylib/compare/v2.14.6...v2.14.7) (2026-01-19)


### Bug Fixes

* Remove redundant message appearing at import time ([185d64c](https://github.com/hypersec-io/hs-pylib/commit/185d64c120fa883cd56b11a1158f18d38d14c458))

## [2.14.6](https://github.com/hypersec-io/hs-pylib/compare/v2.14.5...v2.14.6) (2026-01-19)


### Bug Fixes

* Updating prometheus warning to a debug message ([23ddcc6](https://github.com/hypersec-io/hs-pylib/commit/23ddcc6880a400276f841bd1f4b01d9e207ff8ed))

## [2.14.5](https://github.com/hypersec-io/hs-pylib/compare/v2.14.4...v2.14.5) (2026-01-19)


### Bug Fixes

* Further fix of cyclicar imports ([2e0b867](https://github.com/hypersec-io/hs-pylib/commit/2e0b867ef7994033db8024420aeb7595c6ac8ea2))

## [2.14.4](https://github.com/hypersec-io/hs-pylib/compare/v2.14.3...v2.14.4) (2026-01-19)


### Bug Fixes

* Allow HS_LIB_DEBUG or LOG_LEVEL = DEBUG ([7593ecd](https://github.com/hypersec-io/hs-pylib/commit/7593ecd267f9f6a5e473150236ad0aefb9dfa93d))

## [2.14.3](https://github.com/hypersec-io/hs-pylib/compare/v2.14.2...v2.14.3) (2026-01-19)


### Bug Fixes

* Using lazy imports and a helper function on config to prevent use of print on cyclic functions ([0e6d6b9](https://github.com/hypersec-io/hs-pylib/commit/0e6d6b9162512579f2bf1b1bc180d78c187ab889))

## [2.14.2](https://github.com/hypersec-io/hs-pylib/compare/v2.14.1...v2.14.2) (2026-01-19)


### Bug Fixes

* move config away from using print and to the logger module ([ddf399f](https://github.com/hypersec-io/hs-pylib/commit/ddf399f0a9731f775abc67d0fff3ffaa94ea6a31))

## [2.14.1](https://github.com/hypersec-io/hs-pylib/compare/v2.14.0...v2.14.1) (2026-01-18)


### Bug Fixes

* replace examples with standalone projects using current API ([a9221f7](https://github.com/hypersec-io/hs-pylib/commit/a9221f73f2efee8e79518e805bfd532475fda7b5))

# [2.14.0](https://github.com/hypersec-io/hs-pylib/compare/v2.13.7...v2.14.0) (2026-01-15)


### Features

* add PostgreSQL cache and config backends for multi-pod deployments ([6d09b2d](https://github.com/hypersec-io/hs-pylib/commit/6d09b2d3e5b9601e9687162216625a082daad50a))

## [2.13.7](https://github.com/hypersec-io/hs-pylib/compare/v2.13.6...v2.13.7) (2025-12-30)


### Bug Fixes

* print_error stderr console and add CI mode logger ([73ef10e](https://github.com/hypersec-io/hs-pylib/commit/73ef10e705efaa5c0cb555e5e43bd88b80dcf37a))

## [2.13.6](https://github.com/hypersec-io/hs-pylib/compare/v2.13.5...v2.13.6) (2025-12-30)


### Bug Fixes

* remove unused application framework, add Kafka Docker testing ([c916a92](https://github.com/hypersec-io/hs-pylib/commit/c916a928965bcd2864ab7f28d6e431a4f75c91bf))


### BREAKING CHANGES

* Remove application framework (hs_pylib.application)
- Zero production usage, adds complexity without benefit
- Removed 2,656 lines of unused code and tests

Added:
- Docker Kafka for local integration testing (docker-compose.kafka.yml)
- Smart Kafka fixtures in conftest.py (remote fallback to local Docker)
- Unit tests for Kafka fixture logic (19 tests)
- Integration tests for Docker Kafka fallback

Changed:
- Kafka integration tests now auto-detect remote or local Kafka
- Docker container cleanup only stops what tests started
- Unique project name (hs-pylib-test) avoids conflicts

Python version policy: >=3.12 only

## [2.13.5](https://github.com/hypersec-io/hs-pylib/compare/v2.13.4...v2.13.5) (2025-12-29)


### Bug Fixes

* add faker to dev dependencies for integration tests ([ae3d339](https://github.com/hypersec-io/hs-pylib/commit/ae3d339f3163b746d6eacbd240edc893b79d26e2))

## [2.13.4](https://github.com/hypersec-io/hs-pylib/compare/v2.13.3...v2.13.4) (2025-12-29)


### Bug Fixes

* upgrade filelock and urllib3 to fix vulnerabilities ([7c99214](https://github.com/hypersec-io/hs-pylib/commit/7c9921459c2801daf8f5aa9fc77c8e60c5ff09e1))

## [2.13.3](https://github.com/hypersec-io/hs-pylib/compare/v2.13.2...v2.13.3) (2025-12-29)


### Bug Fixes

* combine nested if statements in schema.py (SIM102) ([4e44cdc](https://github.com/hypersec-io/hs-pylib/commit/4e44cdc32950c3be3b1b8eacca092bd8ca7f5303))

## [2.13.2](https://github.com/hypersec-io/hs-pylib/compare/v2.13.1...v2.13.2) (2025-12-29)


### Bug Fixes

* resolve ruff linting errors in kafka tests ([0bd3f5e](https://github.com/hypersec-io/hs-pylib/commit/0bd3f5ebc41ad8adb552119328bdf305c0fea459))

## [2.13.1](https://github.com/hypersec-io/hs-pylib/compare/v2.13.0...v2.13.1) (2025-12-29)


### Bug Fixes

* add SERVICE-ACCESS.md to gitleaks allowlist ([e4167a5](https://github.com/hypersec-io/hs-pylib/commit/e4167a5340f23619a361d35111e4bd8951a2804c))

# [2.13.0](https://github.com/hypersec-io/hs-pylib/compare/v2.12.5...v2.13.0) (2025-12-29)


### Features

* rename hs-lib to hs-pylib for multi-language consistency ([89df2f9](https://github.com/hypersec-io/hs-pylib/commit/89df2f9f061e70d4820863a64752c3375816c65f))


### BREAKING CHANGES

* Package renamed from hs-lib to hs-pylib

Changes:
- Rename package: hs-lib → hs-pylib (matches hs-golib, hs-rustlib)
- Rename imports: hs_lib → hs_pylib
- Update version: 2.12.4 → 2.13.0
- Require Python 3.12+ (drop 3.11 support)
- Kafka: remove idempotence, use at-least-once (acks=all + retries)
- GitHub repository renamed: hypersec-io/hs-lib → hypersec-io/hs-pylib

Migration:
1. Update pyproject.toml: hs-lib → hs-pylib
2. Update imports: from hs_lib → from hs_pylib
3. Run: uv lock --upgrade-package hs-pylib

## [2.12.4](https://github.com/hypersec-io/hs-pylib/compare/v2.12.3...v2.12.4) (2025-12-16)


### Bug Fixes

* update ci/ai submodules with auto-update config ([80891e0](https://github.com/hypersec-io/hs-pylib/commit/80891e069b89b17bce613e5d06c35629190f008c))

## [2.12.3](https://github.com/hypersec-io/hs-pylib/compare/v2.12.2...v2.12.3) (2025-12-08)


### Bug Fixes

* **harness:** add missing logger import ([e200336](https://github.com/hypersec-io/hs-pylib/commit/e200336ce686da9375e1b610cddea730c6e67b67))

## [2.12.2](https://github.com/hypersec-io/hs-pylib/compare/v2.12.1...v2.12.2) (2025-12-08)


### Bug Fixes

* **config:** only load default.yaml for app-specific config ([fdef692](https://github.com/hypersec-io/hs-pylib/commit/fdef69259a20d428f373fdf8bc1cd9f3c492ea1c))

## [2.12.1](https://github.com/hypersec-io/hs-pylib/compare/v2.12.0...v2.12.1) (2025-12-08)


### Bug Fixes

* **config:** stop at first matching config file instead of loading all ([caf9783](https://github.com/hypersec-io/hs-pylib/commit/caf978322190297f82fe7a886b3f8c7e9427c52f))

# [2.12.0](https://github.com/hypersec-io/hs-pylib/compare/v2.11.0...v2.12.0) (2025-12-07)


### Features

* **kafka:** add hs_pylib.kafka module specification (DFE-553) ([b1cd4ce](https://github.com/hypersec-io/hs-pylib/commit/b1cd4ce35b213e7d23fc2e1a50705aad12a9e984))
* **kafka:** add Kafka client library with corporate defaults ([7b72f0e](https://github.com/hypersec-io/hs-pylib/commit/7b72f0ec96acd8f62240d78091b577ecfce7b3e6))
* **kafka:** add Kafka client library with corporate defaults ([2a9b38b](https://github.com/hypersec-io/hs-pylib/commit/2a9b38b1b756920b90ec114629530035120877ba))

# [1.6.0](https://github.com/hypersec-io/hs-pylib/compare/v1.5.0...v1.6.0) (2025-12-04)


### Bug Fixes

* add --language python flag to bootstrap in CI workflow ([3ade9b1](https://github.com/hypersec-io/hs-pylib/commit/3ade9b1505a263b943b66946d28007a69726e051))
* add api extras to metrics test Dockerfile, remove orphaned jinja template ([08f1df4](https://github.com/hypersec-io/hs-pylib/commit/08f1df43af7bd764a3c64e16fba94f18c78e062b))
* add automatic cleanup of hung background processes in pytest ([c950958](https://github.com/hypersec-io/hs-pylib/commit/c9509589d017f1fa10509a2944651921a8bf0413))
* add cache_dir and run_dir to RuntimePaths, remove jinja templates ([40b94ff](https://github.com/hypersec-io/hs-pylib/commit/40b94ffbb9f7ba17579133e6c25ec4ad567bfbd1))
* add clean-commit action to remove AI attribution from commits ([490d9a3](https://github.com/hypersec-io/hs-pylib/commit/490d9a37ffa9aa55276d8b139724f373c8924fc6))
* add CLI utilities for faster development ([4feffbb](https://github.com/hypersec-io/hs-pylib/commit/4feffbb082b76293e3281a270e41f0449dd0f060))
* add ClickHouse database support to connection builder ([3fdae1c](https://github.com/hypersec-io/hs-pylib/commit/3fdae1cfeb71a4c3b4928477277f1fc1c8fa3b79))
* add comprehensive exception handling to config merge module ([7ac7dd3](https://github.com/hypersec-io/hs-pylib/commit/7ac7dd39edd3c4d61792710b8802d45b8e11c92a))
* add comprehensive self-documenting code to all hyperlib modules ([9a48e89](https://github.com/hypersec-io/hs-pylib/commit/9a48e89d1c6d3941560464906987588f5824c136))
* add configurable color schemes for logger ([2289931](https://github.com/hypersec-io/hs-pylib/commit/2289931a2b2173610459aff055b9ba842edccea4))
* add get_logger() to ci_lib.py with loguru and RFC 3339 timestamps ([4a552e9](https://github.com/hypersec-io/hs-pylib/commit/4a552e9ad39221bd0158f60760a749142abb4dec))
* add GH_PAT support and ci-local/.env for GitHub Actions ([1154265](https://github.com/hypersec-io/hs-pylib/commit/11542658eaa8454366b774103874edf117da7186))
* add GitHub release creation to ci-publish workflow ([a29a8d4](https://github.com/hypersec-io/hs-pylib/commit/a29a8d4436f9dca8bd5d7cfdda7dabec01880afe))
* add gitleaks allowlist for historical backup files ([1827657](https://github.com/hypersec-io/hs-pylib/commit/1827657db9dd25bedecb53ff2bc9ba65e16544c2))
* add HealthCheckMixin to Daemon and MCP applications ([b059150](https://github.com/hypersec-io/hs-pylib/commit/b059150ab0b9c7f3f040a6eff2c1c074fb6b2cfd))
* add httpx test dependency for FastAPI TestClient ([c7e94c0](https://github.com/hypersec-io/hs-pylib/commit/c7e94c0633303f483927a40bf87e2b364587bae6))
* add HYPERLIB_TEST labels to all K8s/Helm commands for cleanup ([0690fec](https://github.com/hypersec-io/hs-pylib/commit/0690fecaa8d3358847e7c256bf7f224aec5be4d8))
* add imagePullSecrets to all Helm pod/deployment templates ([234424f](https://github.com/hypersec-io/hs-pylib/commit/234424f2e015bf0cb63a7fae1f612119e2f0b010))
* add JFrog publishing controls with auto-detect and --no-publish flag ([4aaccac](https://github.com/hypersec-io/hs-pylib/commit/4aaccac04d75cef1e5d73d5a2beebb2f472a3dd6))
* add loguru and reduce CI tool dependencies to only what's used ([65e638c](https://github.com/hypersec-io/hs-pylib/commit/65e638cecb97610583f4a5354d2ed31019d18233))
* add MCPApplication to __init__.py exports ([091ef9f](https://github.com/hypersec-io/hs-pylib/commit/091ef9f4729b1aadfe876b7c5c3d0da1995aa11e))
* add missing LICENSE file (HyperSec EULA) ([842565c](https://github.com/hypersec-io/hs-pylib/commit/842565c5c559a2c6d0279a383c8b484071f5a008))
* add nosec B108 to /tmp paths (bandit warnings) ([a65f647](https://github.com/hypersec-io/hs-pylib/commit/a65f6476ea609b8b9118f78bfee3d559b5728ac8)), closes [#nosec](https://github.com/hypersec-io/hs-pylib/issues/nosec)
* add production-grade exception handling across core modules ([3ec18f2](https://github.com/hypersec-io/hs-pylib/commit/3ec18f28065011f864987da7c1c2947f9e634d6c))
* add Python venv setup step to workflow (workaround BUG-CI-001) ([e0c8c7c](https://github.com/hypersec-io/hs-pylib/commit/e0c8c7cec8397455408dd32567aa39c923011b0e))
* add typer to required dependencies and futureproof Python version requirements ([75183a9](https://github.com/hypersec-io/hs-pylib/commit/75183a999e8351ae80b98385a04ab4ce67db6d44))
* add uv installation to GitHub Actions workflow ([287aa7d](https://github.com/hypersec-io/hs-pylib/commit/287aa7d63b281c8313bfc174a40ad61ff3363b4f))
* add version management comment for clarity ([ff0bee2](https://github.com/hypersec-io/hs-pylib/commit/ff0bee2edac48f0a54cd43bdcb03cd650eea36c5))
* allowlist test fixture fake secrets in gitleaks ([957952b](https://github.com/hypersec-io/hs-pylib/commit/957952b4c089366c54621574e1fbfb27e5dbc9bf))
* allowlist test_logger_filters.py fake secrets ([f79718e](https://github.com/hypersec-io/hs-pylib/commit/f79718e3b7b94cdb0b1808b99fbdf2359319c405))
* API test route decorator, add comprehensive testing documentation ([7a2eda7](https://github.com/hypersec-io/hs-pylib/commit/7a2eda7684231cc6fb0198e4e5315c41d94c6e4c))
* apply Black formatting (dbconn, test_logger, config) ([81c9740](https://github.com/hypersec-io/hs-pylib/commit/81c9740c76a706dc690e2b8def7ef52d8561ce08))
* apply black formatting to custom_recognizers.py ([0aec5ed](https://github.com/hypersec-io/hs-pylib/commit/0aec5ed97642e6cd24c2ff7ff496de68c891d258))
* apply Black formatting to mcp.py ([40a39d9](https://github.com/hypersec-io/hs-pylib/commit/40a39d95c6c731120afaed0d457d2a81bc86d6a1))
* apply ruff auto-fixes (UP015, UP045, F541) ([4bc22b0](https://github.com/hypersec-io/hs-pylib/commit/4bc22b0d9dd80c6bb922f0874c27c87559c1eef8))
* apply ruff formatting fixes to application code and tests ([1925019](https://github.com/hypersec-io/hs-pylib/commit/1925019e538dd0321571abd366bd6de2c3e76538))
* auto-trigger CI publish on release tags (v*) ([59fe7dd](https://github.com/hypersec-io/hs-pylib/commit/59fe7dd3d61ea1ad2584da44c09ec440dbcfbde5))
* bootstrap now creates and manages both ci/.venv and .venv ([7775ef0](https://github.com/hypersec-io/hs-pylib/commit/7775ef0fd926f3c704143cb5947d5ac1ddcf5e5b))
* check for uv in .venv first, with system PATH as fallback ([c0dba6b](https://github.com/hypersec-io/hs-pylib/commit/c0dba6b983212896fd881f68cd459b6587461c7c))
* CI test for Nuitka + BuildJet verification 20251017-133530 ([1505d18](https://github.com/hypersec-io/hs-pylib/commit/1505d18f13f036e7016317343266492eaeba3b2f))
* CI test patch bump 20251017-121712 ([7c7c0c3](https://github.com/hypersec-io/hs-pylib/commit/7c7c0c33984854aa130f4f2fcf2f04e4cea8edfc))
* CI test patch bump 20251017-121752 ([881fd2d](https://github.com/hypersec-io/hs-pylib/commit/881fd2d8858fb423b3c715c8037156cc8833e859))
* CI test patch bump 20251017-121848 ([00bb60a](https://github.com/hypersec-io/hs-pylib/commit/00bb60a81fce014145ac381b909bde1a1828ed04))
* CI test patch bump 20251017-122104 ([6917bdd](https://github.com/hypersec-io/hs-pylib/commit/6917bdd5ca9b49db5eaaf1a5ce8f6268f2390c03))
* CI test patch bump 20251017-124536 ([61ccc8d](https://github.com/hypersec-io/hs-pylib/commit/61ccc8dec6d1b4713080c8f36afcef76bea55ce9))
* CI test patch bump 20251017-124613 ([a165022](https://github.com/hypersec-io/hs-pylib/commit/a1650229e9d869a6947cfede0715ca1cde784285))
* CI test patch bump 20251017-124644 ([a03ef23](https://github.com/hypersec-io/hs-pylib/commit/a03ef23cfc59896b5ca825f756a9ccb355885b5f))
* CI test patch bump 20251017-124723 ([5270963](https://github.com/hypersec-io/hs-pylib/commit/52709630e10e11db1093a81ec6c18110c2dc303c))
* CI test patch bump 20251017-124759 ([1efad52](https://github.com/hypersec-io/hs-pylib/commit/1efad5203fab640c7e2188caed495a63754f3326))
* CI test patch bump 20251017-124841 ([ab0825e](https://github.com/hypersec-io/hs-pylib/commit/ab0825e236e97d0615ed9faf8c6246b8c60b2571))
* clean all build artifacts before building to prevent duplicate versions ([ced0ac7](https://github.com/hypersec-io/hs-pylib/commit/ced0ac73060ecc84e95cbf3a130ae5db846f107c))
* clean ci.yaml and set fail_fast: true as default ([8b5b671](https://github.com/hypersec-io/hs-pylib/commit/8b5b6716534c5d5106253323be57ad8b267e1dfc))
* clean up logger API and fix test imports ([b694c51](https://github.com/hypersec-io/hs-pylib/commit/b694c5178fffa5a85bcc68016367920cd21ed816))
* clean up test infrastructure and timeout.py ([d5c6513](https://github.com/hypersec-io/hs-pylib/commit/d5c6513de365a100c9226234971dabd603166d18))
* code formatting and update hyperci submodule ([36da1ff](https://github.com/hypersec-io/hs-pylib/commit/36da1ff255f3703fc8b344826cf682d62f331b84))
* complete hyperlib to hs-pylib rename across entire codebase ([f95e46a](https://github.com/hypersec-io/hs-pylib/commit/f95e46ac7c38f9856b5c74aa76acf6465a46e011))
* complete Phase 6 testing and validation (all 6 phases done!) ([30d06dd](https://github.com/hypersec-io/hs-pylib/commit/30d06dda464d6ecaf9a4c86b2168d4d1507e4478))
* complete semantic-release VERSION sync - add tomli-w and fix regex ([826b807](https://github.com/hypersec-io/hs-pylib/commit/826b8075807dc39cda427c2394930f8954659f60))
* complete uv/pip JFrog integration with persistent .env configuration ([0028060](https://github.com/hypersec-io/hs-pylib/commit/0028060e1bb27564ecc8c619578729e383b27024))
* complete VERSION sync and env var standardization milestone ([038ca8c](https://github.com/hypersec-io/hs-pylib/commit/038ca8ca84330916c2a2ad12c83f715fbf22670c))
* comprehensive documentation restructure and application framework updates ([e6d2439](https://github.com/hypersec-io/hs-pylib/commit/e6d243934d05ce1eeb3c88181b7549f082424b45))
* configure JFrog publishing via GitHub Actions only ([1cef791](https://github.com/hypersec-io/hs-pylib/commit/1cef7910cc55982154d6f8b22f7a442d962e46c8))
* configure Minikube Docker to use Artifactory (conditional on .env) ([8e3ba36](https://github.com/hypersec-io/hs-pylib/commit/8e3ba366298131ee32869be87bd915f9a7fefc8a))
* configure Solarized colors for all log levels ([2a0d0ac](https://github.com/hypersec-io/hs-pylib/commit/2a0d0ac6a8aea2909b5e684ca961e455065ee586)), closes [#859900](https://github.com/hypersec-io/hs-pylib/issues/859900) [#2aa198](https://github.com/hypersec-io/hs-pylib/issues/2aa198) [#586e75](https://github.com/hypersec-io/hs-pylib/issues/586e75) [#268bd2](https://github.com/hypersec-io/hs-pylib/issues/268bd2) [#859900](https://github.com/hypersec-io/hs-pylib/issues/859900) [#b58900](https://github.com/hypersec-io/hs-pylib/issues/b58900) [#cb4b16](https://github.com/hypersec-io/hs-pylib/issues/cb4b16) [#dc322f](https://github.com/hypersec-io/hs-pylib/issues/dc322f)
* consolidate and document subprocess usage (Phase 3 pragmatic approach) ([ff8a697](https://github.com/hypersec-io/hs-pylib/commit/ff8a697f566057fc99168aa24a71321aa5b18f06))
* consolidate hyperlib test logs to /tests/logs/pytest/ ([8df9c91](https://github.com/hypersec-io/hs-pylib/commit/8df9c91258048f0e0d18034561d3d0e3cba12185))
* convert all bootstrap checks from bash to Python (Phase 4 complete) ([b1b3660](https://github.com/hypersec-io/hs-pylib/commit/b1b366033e603a34cec505266d7b43072ee0e7dc))
* convert all estimates to hours format with powers of 2 scaling ([f6b80ee](https://github.com/hypersec-io/hs-pylib/commit/f6b80ee4b4407723d7672ae13d2a3aa955f97231))
* correct bootstrap syntax in install.sh (install not --install) ([63e6764](https://github.com/hypersec-io/hs-pylib/commit/63e67644f8f0043157f72c10856e12c1c21d1fb2))
* correct ci-publish.yml syntax errors from merge ([882c30d](https://github.com/hypersec-io/hs-pylib/commit/882c30d42f1a0f119654185109bb4e2ce8e968a1))
* correct ci.yaml path in GitHub Actions workflow ([ceed452](https://github.com/hypersec-io/hs-pylib/commit/ceed4523e1bdbc1258034f4c7d2d902ec9ad5f62))
* correct decorator and CLI framework references in application docstrings ([be851a3](https://github.com/hypersec-io/hs-pylib/commit/be851a31b399676e90def6e0feee5ecb0551027e))
* correct GitHub Actions workflow syntax and language specification ([1bc3bee](https://github.com/hypersec-io/hs-pylib/commit/1bc3beee808a76cefda109735f4f8e103fe55862))
* correct GitHub Actions workflow trigger (on: not true:) ([21c1256](https://github.com/hypersec-io/hs-pylib/commit/21c12566d70b4f4083e4841aff91367860b474f8))
* correct HealthCheckMixin initialization order ([bbd8ae4](https://github.com/hypersec-io/hs-pylib/commit/bbd8ae42131a024620c5916e93bef843f5c6b57a))
* correct Minikube status check (JSON flag broken) ([b3a991e](https://github.com/hypersec-io/hs-pylib/commit/b3a991ecf4eeb90b28fb032a1d87f0d9dad13595))
* correct nosec comment placement (syntax error) ([6679d6f](https://github.com/hypersec-io/hs-pylib/commit/6679d6f7503fefe573ac0ca67c91217047450cd5))
* correct pyright configuration syntax ([0fe54c1](https://github.com/hypersec-io/hs-pylib/commit/0fe54c11204a5ab31ecd05093c75896a286cbe7d))
* correct version to 2.9.1 (rename was minor change, not breaking) ([1706874](https://github.com/hypersec-io/hs-pylib/commit/17068744e18ca5c4bfe1e199d73e79717bd228ea))
* create .env in project root (not ci-local/) ([03370a9](https://github.com/hypersec-io/hs-pylib/commit/03370a955f95437ebb4d9ef8ea459d101c7d6aa8))
* create patch commit in ci-local/ not .tmp/ ([f79f9a5](https://github.com/hypersec-io/hs-pylib/commit/f79f9a5f5754a46e508c58a1d09e7ca66bd0b59d))
* create pip.conf in .venv-ci for proper venv configuration ([61eef71](https://github.com/hypersec-io/hs-pylib/commit/61eef7130430627f3b86d3db4b17f4fa8ee911b6))
* create tests-passed marker instead of using CI_FORCE_RELEASE ([d6d2122](https://github.com/hypersec-io/hs-pylib/commit/d6d21223fd1f35dcf12b0c6c1abf06aca940f57f))
* default to BuildJet builds for releases ([896ce3c](https://github.com/hypersec-io/hs-pylib/commit/896ce3c272c966712db0ab3259d1020d3e981910))
* disable MCP in CI configuration (too complex for now) ([d2de9d6](https://github.com/hypersec-io/hs-pylib/commit/d2de9d66547271001cc241b41dd94cc5fc862e63))
* disable Nuitka builds for hyperlib (source-only library package) ([bb46baa](https://github.com/hypersec-io/hs-pylib/commit/bb46baaada3f2c8f0c8f54ba0e62cc2d1a57d00a))
* eliminate double-commit in semantic-release, let it handle VERSION completely ([bed9bef](https://github.com/hypersec-io/hs-pylib/commit/bed9bef47f8f4af3bb50b78d59d93b2cdf2d85ee))
* enable debug logging for all hyperlib tests ([c0cd980](https://github.com/hypersec-io/hs-pylib/commit/c0cd9802bce951e164124705f4fdc6a6f9445604))
* enforce tests must pass before semantic-release ([bbf11c8](https://github.com/hypersec-io/hs-pylib/commit/bbf11c8eb32aa70a808ad81bcd2e60a02845a9b1))
* enforce uv-only usage in .venv while allowing pip in ci/.venv ([7de2344](https://github.com/hypersec-io/hs-pylib/commit/7de2344d5b0ca2ac484c3728baee8726c4f0ef0e))
* exclude ci/ tests from parent project test runs ([33347a7](https://github.com/hypersec-io/hs-pylib/commit/33347a7751ce56357cc185d002ebc46fa6736ed2))
* explicitly specify Python 3.12 for bootstrap ([6f547a0](https://github.com/hypersec-io/hs-pylib/commit/6f547a0f507193f25913a747da2beca9b003a298))
* final cleanup - remove all JF_ references and add test cleanup ([b82460c](https://github.com/hypersec-io/hs-pylib/commit/b82460c4d4d025f5586f07ecaa74652e7d159a36))
* final Nuitka + BuildJet verification 20251017-134900 ([d800059](https://github.com/hypersec-io/hs-pylib/commit/d8000590a35a28100d0f227b2d241984fd0244c8))
* finalize CI and AI configuration (exclude credentials) ([0d62ec7](https://github.com/hypersec-io/hs-pylib/commit/0d62ec7136c367cfeef073ef2867f75907b98f88))
* force uv to use Python 3.12 via UV_PYTHON env var ([c5a7b68](https://github.com/hypersec-io/hs-pylib/commit/c5a7b6844d4f753b4ee1ef8d11fbf9f98914bcf4))
* format code with ruff ([8684e23](https://github.com/hypersec-io/hs-pylib/commit/8684e238d60496438d1173895e491672f22f5982))
* generalizepermissions for all CI commands and tests ([47215ba](https://github.com/hypersec-io/hs-pylib/commit/47215bae532d7781695be15539d9c7dc5b1df791))
* handle missing README.md gracefully in setup.py + update CI ([db4aa08](https://github.com/hypersec-io/hs-pylib/commit/db4aa08444fe0143f2cba08bc7dee5d011017ef7))
* handle pytest.skip exception in test runner ([f7cb8fa](https://github.com/hypersec-io/hs-pylib/commit/f7cb8fa8bb579c8bf7873670d72c89bf7c602549))
* implement CAG/RAG hybrid strategy for standards loading ([6975cee](https://github.com/hypersec-io/hs-pylib/commit/6975cee9be5ff77e79d81808e973caa8f87f6f9f))
* implement dual pre-sync strategy for VERSION file corruption prevention ([a03ff5e](https://github.com/hypersec-io/hs-pylib/commit/a03ff5e1e5818f74935f573fb1f0cb5e84b842f6))
* implement multi-layer venv protection strategy with shared CI utilities ([f39b104](https://github.com/hypersec-io/hs-pylib/commit/f39b104ac35c53f7a82e90166b6b59d887b95703))
* implement persistent UV/PIP index URLs and add .pip/ to gitignore ([c44ad68](https://github.com/hypersec-io/hs-pylib/commit/c44ad68177c9d6d04ca45aba72bbae7f16feaa6d))
* implement Phase 1 container-native patterns foundation ([6e47d64](https://github.com/hypersec-io/hs-pylib/commit/6e47d647d57771bab9eba41bed569913afeb7412))
* implement Phase 3 - enhanced HealthCheckMixin ([e078f9b](https://github.com/hypersec-io/hs-pylib/commit/e078f9bcf0981b5df19ed3566f70b5c0491704d8))
* implement proper MERGE behavior for standards files ([0e626a6](https://github.com/hypersec-io/hs-pylib/commit/0e626a62f77403675429755390358d016019f8f6))
* improve application test coverage with proper dependency detection ([7af3c0b](https://github.com/hypersec-io/hs-pylib/commit/7af3c0b92ae2ce00c3ffa361e538a6f050ac5bb7))
* improve README description to accurately reflect current features ([0dea473](https://github.com/hypersec-io/hs-pylib/commit/0dea47341d53578ed8f80770924c09bd5251a016))
* increase Helm timeout 60s→120s and fix Python f-string syntax ([f314a9a](https://github.com/hypersec-io/hs-pylib/commit/f314a9ac9d6478ec1bfa5532d83260984420975a))
* install twine in workflow (workaround BUG-CI-002) ([bb49af3](https://github.com/hypersec-io/hs-pylib/commit/bb49af3a23e428fad0995e45a968d44b8e06b361))
* install.sh should pass through arguments to bootstrap ([8e13dc5](https://github.com/hypersec-io/hs-pylib/commit/8e13dc5efd5ed161c10b884a6fffb1b516a92f9d))
* load .env file in pytest conftest for test credentials ([41da550](https://github.com/hypersec-io/hs-pylib/commit/41da5508dd0905339298c2a98c96a5fa1ce97c2f))
* make CI completely generic and portable to any Python project ([3177f54](https://github.com/hypersec-io/hs-pylib/commit/3177f544a2bad272ffcc448496ffd4e8d465e089))
* make ENV_PREFIX configurable via HYPERLIB_ENV_PREFIX ([6d9b763](https://github.com/hypersec-io/hs-pylib/commit/6d9b7632ce5f4d415368e0870a979cc82f923333))
* make GitHub Actions workflows manual-only, triggered by CI publish ([98ba4e1](https://github.com/hypersec-io/hs-pylib/commit/98ba4e1e2dfb6e4a43d9a81e9ee32506d1c0190b))
* make JFrog and hyperlib optional dependencies in CI ([6c552a5](https://github.com/hypersec-io/hs-pylib/commit/6c552a5485f5233c75524035f5cdc7ac73dbf2a7))
* map GitHub ARTIFACTORY secrets to JF_USER/JF_PASSWORD for bootstrap ([07ac86b](https://github.com/hypersec-io/hs-pylib/commit/07ac86b729882d6fa705c1e317a430cec8e08148))
* merge container-native patterns branch ([6d00a8f](https://github.com/hypersec-io/hs-pylib/commit/6d00a8f57bfa9717b4880cf4429169ff7bd28359))
* merge DFE-524 branch (ci workflow paths) ([a4f33cc](https://github.com/hypersec-io/hs-pylib/commit/a4f33ccf6233e9161c6946d9dd35aebacd877cc4))
* migrate to HyperCI modular architecture (DFE-523) ([4144c06](https://github.com/hypersec-io/hs-pylib/commit/4144c062b1645011195cd036c0a0ec9953d98344))
* migrate to separate ci and ai submodules ([1383870](https://github.com/hypersec-io/hs-pylib/commit/138387090031953b66c363f69db444b1c209c7cf))
* migrate to unified .venv environment (ONE .venv) ([5c3ed41](https://github.com/hypersec-io/hs-pylib/commit/5c3ed41ead202c28ac6c1355c04c16123a685bf7))
* minimal ci.yaml (remove all defaults including nuitka.enabled) ([313e586](https://github.com/hypersec-io/hs-pylib/commit/313e58632584ff991a557429d0ae4f4f03843198))
* modernize type hints to Python 3.10+ syntax ([71de984](https://github.com/hypersec-io/hs-pylib/commit/71de98465c1d970d7b155419c9f8b54d6087b000))
* move build_type to python section (applies to all builds) ([f68ddff](https://github.com/hypersec-io/hs-pylib/commit/f68ddffc9da5a04ee2da0f9f759e7e9575556de6))
* move Docker Hub credentials to root .env.sample (not ci-local) ([8db5d98](https://github.com/hypersec-io/hs-pylib/commit/8db5d9887092de76def7f0723cd39cf7a4f2c2ae))
* move Helm/Minikube availability checks to runtime (not decorator) ([af41d1c](https://github.com/hypersec-io/hs-pylib/commit/af41d1c8128fe87d0788c73644bbaaa50ec0f14d))
* move language-agnostic CI checks to common/ci.d/ ([ca16b63](https://github.com/hypersec-io/hs-pylib/commit/ca16b632ff0099f30936454ca14ae328cc1cec44))
* move tests to ci-local/tests and update ci submodule ([63eeee7](https://github.com/hypersec-io/hs-pylib/commit/63eeee7257f25fa1236fc976a6d942c213807ae3))
* move write-version.py to CI submodule tools directory ([6ffb23d](https://github.com/hypersec-io/hs-pylib/commit/6ffb23d132552e2dbb2a4104c1e8463f6eb68db5))
* move write-version.py to ci-local directory ([5b0c6e7](https://github.com/hypersec-io/hs-pylib/commit/5b0c6e78a76ea80ab845238c69af4afdf0b50231))
* only trigger Nuitka workflow on version tags ([7afb6af](https://github.com/hypersec-io/hs-pylib/commit/7afb6afeb4868e33d9942eedfc3d8ab50f0d9f3e))
* prepend Python 3.12 to PATH for bootstrap ([1fbbeda](https://github.com/hypersec-io/hs-pylib/commit/1fbbeda4d8c585411e11f9765f36c70a17b36195))
* private submodule access and add force_version bypass ([1620b57](https://github.com/hypersec-io/hs-pylib/commit/1620b5779953eac551aff5e6466037b1af424fa3))
* publish Nuitka wheels directly (don't rebuild) ([1b99ec1](https://github.com/hypersec-io/hs-pylib/commit/1b99ec1dfbca700f3f28c1c30230e4b69aab60be))
* Python f-string syntax error in Helm test fixture ([12f998e](https://github.com/hypersec-io/hs-pylib/commit/12f998e19261be9b82ae1dddc56ad896c10046dc))
* re-enable BuildJet after GitHub App reinstall ([04bcc7d](https://github.com/hypersec-io/hs-pylib/commit/04bcc7d2fca105b8b4d6186ba0dd043a9c75dbec))
* reduce excessive emoji use (CHARS-POLICY compliance) ([d48a7a9](https://github.com/hypersec-io/hs-pylib/commit/d48a7a949512d105989cac27f7d6d92d0bc86213))
* refine AI attribution detection to avoid false positives ([de7d61a](https://github.com/hypersec-io/hs-pylib/commit/de7d61ab6d2ac67e6b4702935a6c2afedb8e1d20))
* register shutdown handlers with FastAPI event system ([dee2ef1](https://github.com/hypersec-io/hs-pylib/commit/dee2ef19641c599b074ae64be5e04e0830855ddb))
* remediate security scanning alerts ([b4f9ede](https://github.com/hypersec-io/hs-pylib/commit/b4f9ede3c82824c78931f5e58751525353c8848e))
* remove --skip-existing flag (JFrog doesn't support it, uses overwrites) ([446288a](https://github.com/hypersec-io/hs-pylib/commit/446288afcb7b98c0bc5c59f73e8bd43da9fbc615))
* remove --wait from remaining Helm tests (prometheus + API) ([a38d6be](https://github.com/hypersec-io/hs-pylib/commit/a38d6beb14a1a7fce192dddf0898b50e46b6c78e))
* remove [@main](https://github.com/main) refs from local workflow paths ([e4e2a80](https://github.com/hypersec-io/hs-pylib/commit/e4e2a80396d2dbd248d84fed831cbf5a70e2015d))
* remove [skip ci] from release commits to enable auto-publish ([5f166c8](https://github.com/hypersec-io/hs-pylib/commit/5f166c8fb4b858ab43f5cf8bed9e55469e67f811))
* remove all hyperlib dependencies from CI, use ci_lib.logger everywhere ([af1c0e8](https://github.com/hypersec-io/hs-pylib/commit/af1c0e855df585ebfc82364c4a6bcdfb4c934705))
* remove broken git -C pattern from settings.json and update ci submodule ([2038241](https://github.com/hypersec-io/hs-pylib/commit/203824187d54e143a83ce60dfaa4b286cc916925))
* remove colors and emojis from CI logger, fix bootstrap get_logger reference ([01ea941](https://github.com/hypersec-io/hs-pylib/commit/01ea9410f2c0f8deada588fbeb65c311d58f66ab))
* remove configure_minikube_registry timeout (use pre-pulled images) ([490b26a](https://github.com/hypersec-io/hs-pylib/commit/490b26aef02db6a4bb041e7bc37ff1db7b1f9735))
* remove DEREK.md references from STATE.md ([9ffb4c6](https://github.com/hypersec-io/hs-pylib/commit/9ffb4c6f7269c6140fc3d06dc9886e25664a2889))
* remove double commas and apply Black formatting ([f990c2d](https://github.com/hypersec-io/hs-pylib/commit/f990c2d0797d381115ead2c4d4560fce121153a9))
* remove duplicate pytest markers in pyproject.toml ([8cdf0ae](https://github.com/hypersec-io/hs-pylib/commit/8cdf0ae84956bee1af1b07cb0409a2a8fba3c3e1))
* remove git config personalization from /start command and update ci submodule ([590f083](https://github.com/hypersec-io/hs-pylib/commit/590f083e5c9ed43d21cdf9699951a333e9c5762a))
* remove GitHub plugin from semantic-release for local runs ([b378192](https://github.com/hypersec-io/hs-pylib/commit/b37819291025a24876e8dc66329683a9759a48b1))
* remove health endpoint test, fix oneshot error type, fix Helm template syntax ([158d5dc](https://github.com/hypersec-io/hs-pylib/commit/158d5dc7fb8222b3c7f5a1ca3dccfc9cffe31987))
* remove Helm --wait for pods with restartPolicy: Never ([6339457](https://github.com/hypersec-io/hs-pylib/commit/6339457946cb68c8f4f5dca4ef98b9e6e649e04b))
* remove invalid [tool.uv] section from ci-local/pyproject.toml ([04ffdca](https://github.com/hypersec-io/hs-pylib/commit/04ffdca7c06cb45f79fa912b145f96bac18a7df7))
* remove leftover nosec comments (no longer needed) ([1ab544a](https://github.com/hypersec-io/hs-pylib/commit/1ab544ad2f7cfbc0ead1eba4ce77cd06eb61b26f))
* remove Minikube auto-start logic (KISS) ([0ca40d0](https://github.com/hypersec-io/hs-pylib/commit/0ca40d08218c6c7656ef02fb9daf8fe9bb559bde))
* remove non-existent --python-version flag from workflow ([61e7b3e](https://github.com/hypersec-io/hs-pylib/commit/61e7b3e55bed7a8ae34aa3f971543af96eb3210d))
* remove non-existent sampling module from import test ([09ebd9f](https://github.com/hypersec-io/hs-pylib/commit/09ebd9f8e79e8824d24d843fe93f86e4c2686b25))
* remove obsolete ci/migrate directory ([8b3cf17](https://github.com/hypersec-io/hs-pylib/commit/8b3cf170b64acb8e2d242a5a78f62a1ca686712f))
* remove RUN_E2E gating from e2e tests ([c7e9a80](https://github.com/hypersec-io/hs-pylib/commit/c7e9a8054480d9097623d0006c9e855bf36cef15))
* remove run-tests and fix bootstrap check scripts install action ([209352a](https://github.com/hypersec-io/hs-pylib/commit/209352a5a34ab5306796e381c93af618391d9b77))
* remove temporary CI refactoring documentation files ([ed7faf0](https://github.com/hypersec-io/hs-pylib/commit/ed7faf0c41c55a24cc97b46e15dd3dfd3b5a6aff))
* remove trailing whitespace in cache.py docstring [skip ci] ([920c3b6](https://github.com/hypersec-io/hs-pylib/commit/920c3b6710276b147ecaada1c7ed3e3e953b71ee))
* remove unapproved emojis per CHARS-POLICY.md ([2bf46a8](https://github.com/hypersec-io/hs-pylib/commit/2bf46a8b6f5b32098cd9253900d9611bec9890de))
* remove unused database dependencies and update STATE.md ([be2f085](https://github.com/hypersec-io/hs-pylib/commit/be2f08544db02794c7335c1950317e0aa06dcd4d))
* remove unused imports (ruff F401 compliance) ([3b54600](https://github.com/hypersec-io/hs-pylib/commit/3b546006401ed9af7962bf002c3bdec72f650347))
* remove version badge from README (versions in CHANGELOG only) ([1726ddd](https://github.com/hypersec-io/hs-pylib/commit/1726ddd30e15063f8587486160af4f9b9ed9f24d))
* rename check_docker_hub_rate_limit to check_container_registry_access ([917c3e4](https://github.com/hypersec-io/hs-pylib/commit/917c3e412d20017eac38f86f4f3d0fc6a4d0b5e8))
* rename package from hyperlib to hs-pylib for PyPI collision avoidance ([ae7c27b](https://github.com/hypersec-io/hs-pylib/commit/ae7c27b59a60d7ee83765d550a8f206fc7519d95))
* rename release.yml to publish.yml for consistency ([9dcf99b](https://github.com/hypersec-io/hs-pylib/commit/9dcf99bc66424e3c9cf348f85ba14b3e5aecaa68))
* replace hardcoded /tmp with tempfile.gettempdir() (security fix) ([faec7d7](https://github.com/hypersec-io/hs-pylib/commit/faec7d78f3e5d0ed0d585de73a7347fb218fe8b7))
* replace Node.js semantic-release with Python version and remove ci-actions ([b9a2098](https://github.com/hypersec-io/hs-pylib/commit/b9a20987ccc897590d7f69ee2b1551df5f3ebf65))
* replace wget with python for metrics endpoint test ([fc6bbbd](https://github.com/hypersec-io/hs-pylib/commit/fc6bbbd84c1a86a8c565d1c06cb55c33c6a855af))
* resolve all Medium and Low severity security issues ([c0e7fd9](https://github.com/hypersec-io/hs-pylib/commit/c0e7fd9adea833164099f37535eea1540cb44b84))
* resolve remaining ruff errors (SIM102, SIM117) ([71527e8](https://github.com/hypersec-io/hs-pylib/commit/71527e891617fe8c14c45a1a43e37c8f65db3a53))
* resolve ruff linting errors (UP035, ARG004, SIM103) ([ce7e0c9](https://github.com/hypersec-io/hs-pylib/commit/ce7e0c91f38d6bfac1e030b53cc9570cfc426bca))
* restore corrupted GitHub Actions workflow ([3ff6539](https://github.com/hypersec-io/hs-pylib/commit/3ff6539bcb1e417804c65baf74c960333d127a74))
* restructure CI into language-agnostic (common) and language-specific (python) directories ([ddb6d7c](https://github.com/hypersec-io/hs-pylib/commit/ddb6d7cb97c57b4fe03f36c4dc3f6b51f34d3a13))
* restructure CI to /ci directory with full self-containment ([6e9d487](https://github.com/hypersec-io/hs-pylib/commit/6e9d4870ef5c72cee5bc50edb0d9660a3277f5a2))
* revert incorrect health endpoint path changes (should be /health and /ready) ([d80e2f4](https://github.com/hypersec-io/hs-pylib/commit/d80e2f4ac0743d3fad3a686aae15ee2b32e3003e))
* revert to ubuntu-latest (BuildJet access issue) ([9eb434b](https://github.com/hypersec-io/hs-pylib/commit/9eb434b63fde5adf5baff59e1909d5c2eea9598a))
* ruff linting - combine nested if statements in health mixin ([47e9a46](https://github.com/hypersec-io/hs-pylib/commit/47e9a4641316e43523c5ca195d2815aa428eb62a))
* set CI=true in verification test and clean test files ([c54fd14](https://github.com/hypersec-io/hs-pylib/commit/c54fd14d1d1d32f109d2c32b06c30149f607593b))
* simplify bootstrap to be self-contained without hyperlib dependencies ([3966d76](https://github.com/hypersec-io/hs-pylib/commit/3966d76b032df69497e1d39c6ef2c3ea2fcc9115))
* simplify JFrog package verification using curl ([2cb966b](https://github.com/hypersec-io/hs-pylib/commit/2cb966b5e63be321ae9affcc919f7b6b0d6af406))
* simplify semantic-release to use Python CLI (53% code reduction) ([8f19daa](https://github.com/hypersec-io/hs-pylib/commit/8f19daa0515500697c44758c2096f897e3ed8926))
* skip branch checks in GitHub Actions publish (detached HEAD) ([31b10a2](https://github.com/hypersec-io/hs-pylib/commit/31b10a28f79fc6fd7f669aac38d17e28cb4f6eaf))
* sort imports in mcp.py (isort) ([68a5982](https://github.com/hypersec-io/hs-pylib/commit/68a598229d889f88764b2577bddba3d6472c3785))
* standardize all test fixtures to _N.txt format, fix Docker build context issues ([76f1539](https://github.com/hypersec-io/hs-pylib/commit/76f1539d0a6f1789ff4330c8d6bbfd047522db9b))
* standardize on pyright (remove mypy config) ([7d9c83f](https://github.com/hypersec-io/hs-pylib/commit/7d9c83f5154311862dc9c293fe247f5f09c101d3))
* support nuitka-only releases via config and --nuitka-only flag ([d379c03](https://github.com/hypersec-io/hs-pylib/commit/d379c03bee325a7897d66f61615463dcc9e8721d))
* suppress linter warnings for unused params and conditional imports ([b15fcfa](https://github.com/hypersec-io/hs-pylib/commit/b15fcfaea1b8acaad0d4fe5c8ef00e77578f6cac))
* sync VERSION file with semantic-release ([d1786ae](https://github.com/hypersec-io/hs-pylib/commit/d1786aed2ce1b8e458ae47cc4b124859a29cd508))
* sync version to v2.10.5 and update semantic-release config ([4451ae4](https://github.com/hypersec-io/hs-pylib/commit/4451ae483ad47b4df3c0ec711b5d9b80d172363e))
* test after ci.yaml path fix 20251017-134121 ([a060669](https://github.com/hypersec-io/hs-pylib/commit/a060669d21369f07cb78ad6ccc8a5f91afb4234c))
* tests required false by default (new projects have no tests) ([603be7d](https://github.com/hypersec-io/hs-pylib/commit/603be7d39cb1d5c8e900afb2769acf89e7909a5c))
* trigger semantic-release for e2e testing (DFE-524) ([fd02c17](https://github.com/hypersec-io/hs-pylib/commit/fd02c17c3fe7756c4a76b2255feb06fe86f7e5ee))
* untrack settings.local.json and remove obsolete gitignore rule ([6cfba5b](https://github.com/hypersec-io/hs-pylib/commit/6cfba5b158e828ad557be7ad2a1621fd927999ec))
* update all Python 3.11 references to 3.12 ([dcf74cb](https://github.com/hypersec-io/hs-pylib/commit/dcf74cbbe14bd26dde8ada2d2903695f7477250c))
* update badges with static version badge (no GitHub API) ([0e06946](https://github.com/hypersec-io/hs-pylib/commit/0e069469c838c12bb158f75129485aab78440a94))
* update bootstrap command (install not --install) ([bd861c3](https://github.com/hypersec-io/hs-pylib/commit/bd861c32b60f3db63f7f073bf44b99f542d553e9))
* update ci and fix dynaconf test ([4f02597](https://github.com/hypersec-io/hs-pylib/commit/4f0259791a665125fdc241bdb49293e4b775d393))
* update CI and regenerate publish workflow (DFE-539) ([4b25e01](https://github.com/hypersec-io/hs-pylib/commit/4b25e019db7cf9fd045e44e65dc317f269728fff))
* update ci submodule (.env location documentation fixes) ([02a8204](https://github.com/hypersec-io/hs-pylib/commit/02a820437ecebe9a56fed8aa22abbda064391872))
* update ci submodule (add UV_EXTRA_INDEX_URL for PyPI fallback) ([b6a37cb](https://github.com/hypersec-io/hs-pylib/commit/b6a37cbe126db18108541682c6ff26717367cacf))
* update ci submodule (CI-LOCAL.md replaced with symlinks) ([9ca239b](https://github.com/hypersec-io/hs-pylib/commit/9ca239bde017f258a57db857f81a79644b842fd9))
* update ci submodule (ENV moved to .bashrc) ([46bdddf](https://github.com/hypersec-io/hs-pylib/commit/46bdddff7a15ab828383411e629c11819d69a6ac))
* update ci submodule (colon syntax for all permissions, remove settings.local.json) ([a126050](https://github.com/hypersec-io/hs-pylib/commit/a12605094e3a596e75e7f99a53e2740751d6dec4))
* update ci submodule (complete pyproject.toml for new projects) ([0d771e8](https://github.com/hypersec-io/hs-pylib/commit/0d771e80b052ad3617226f25a2f01a03d13177f8))
* update ci submodule (comprehensive dual-pattern Bash permissions) ([ffec086](https://github.com/hypersec-io/hs-pylib/commit/ffec086a34635ee6301d0c1870a6952e13df30a1))
* update ci submodule (consolidate test logs) ([bc23522](https://github.com/hypersec-io/hs-pylib/commit/bc23522114e476f4ea5c583a464662f82929d9d9))
* update ci submodule (documentation aligned with hs-ci rename and Python 3.12) ([c71afaa](https://github.com/hypersec-io/hs-pylib/commit/c71afaad8f837414dde9a3a42570d0782300c9b8))
* update ci submodule (explicit TOML merge failure) ([ca9090e](https://github.com/hypersec-io/hs-pylib/commit/ca9090ed26d451851485d443c3e44584b0c08088))
* update ci submodule (fix pyproject.toml merge bug) ([c6b342c](https://github.com/hypersec-io/hs-pylib/commit/c6b342c51a82da60b53c20b460f5e0bc5bf8bfad))
* update ci submodule (fix Python version check bug) ([503c11c](https://github.com/hypersec-io/hs-pylib/commit/503c11c294a2b4cf7a33d569765ca94bb7cc12fe))
* update ci submodule (fix undefined logger in 10-check-git.py) ([05d5ddd](https://github.com/hypersec-io/hs-pylib/commit/05d5ddde41612f233dfe4dbceb413dbc4f997ab3))
* update ci submodule (GitHub Actions workflow fixes) ([5dbf0d1](https://github.com/hypersec-io/hs-pylib/commit/5dbf0d1ea1b7dcf5f42ecfade1f6b5bdcd6345d1))
* update ci submodule (HyperSec default values) ([379d8e3](https://github.com/hypersec-io/hs-pylib/commit/379d8e3d4481ab0a952f2161063f1a1a5050e9e8))
* update ci submodule (interrogate security exception added to defaults) ([b8e4093](https://github.com/hypersec-io/hs-pylib/commit/b8e4093dfd3f0d04ee2e2e596233105f3664a38f))
* update ci submodule (remove git config step from /start) ([be74d32](https://github.com/hypersec-io/hs-pylib/commit/be74d322bd4cfd79670990ca74d692b3b64c8d2c))
* update ci submodule (remove gitci, add semver pinning) ([42172a7](https://github.com/hypersec-io/hs-pylib/commit/42172a79d6b6ea1dc280db16bd27906acb947176))
* update ci submodule (remove merge_env dependency) ([5aa8aa4](https://github.com/hypersec-io/hs-pylib/commit/5aa8aa42e7ba3f9555026f2adacbe5749c25480a))
* update ci submodule (reusable workflows added) ([02d341b](https://github.com/hypersec-io/hs-pylib/commit/02d341bb87de31b1aa53551987053daa78ae695f))
* update ci submodule (reusable workflows in .github/workflows) ([e8ad27c](https://github.com/hypersec-io/hs-pylib/commit/e8ad27cfc6e5da5e8787be2e1ac702eb83fb8d70))
* update ci submodule (use git config for author defaults) ([5fd07e0](https://github.com/hypersec-io/hs-pylib/commit/5fd07e0c8e82f2c5b7aaa14800cad7415be201d2))
* update ci submodule (VSCode venv enforcement) ([f5a4fed](https://github.com/hypersec-io/hs-pylib/commit/f5a4fede0edf2b578f17d9c112fc816780089df6))
* update ci submodule and add git permissions to settings ([9db8bba](https://github.com/hypersec-io/hs-pylib/commit/9db8bba74520bd6bb6adda94fb2ae0989fc31b8e))
* update ci submodule and add missing dynaconf/pyright ([7a175ed](https://github.com/hypersec-io/hs-pylib/commit/7a175eddaf3dcf907054ece8ec02ee0b142ee397))
* update CI submodule and add test job to workflow (DFE-540) ([fa1c5a0](https://github.com/hypersec-io/hs-pylib/commit/fa1c5a079d630771eff2c4c8219a74d19b8b94b1))
* update ci submodule and config for E2E test infrastructure ([6c41cb8](https://github.com/hypersec-io/hs-pylib/commit/6c41cb84578d8bfd3c744105700e13b1245dbc69))
* update ci submodule and regenerate workflow from template ([ad7068b](https://github.com/hypersec-io/hs-pylib/commit/ad7068b288ca9b7586d5aefe99b05432a40118e7))
* update ci submodule to b620738 (CRITICAL get_project_root fix) ([e707e47](https://github.com/hypersec-io/hs-pylib/commit/e707e474acd1751768d3237f37692a18c735fb0e))
* update ci submodule to f780815 (81-publish.py unified build logic) ([f105b18](https://github.com/hypersec-io/hs-pylib/commit/f105b18602e80eff388a45932365ad488efb4002))
* update ci submodule to feat/DFE-523 dev branch ([f795a97](https://github.com/hypersec-io/hs-pylib/commit/f795a97a06c23e92bd628c0f79006962ae8c58dd))
* update CI submodule to latest with uv 0.9.11 support (DFE-524) ([a014818](https://github.com/hypersec-io/hs-pylib/commit/a01481840965eff681e969a5b7402d8f63407f90))
* update ci submodule to main (DFE-523 merged) ([16bae1c](https://github.com/hypersec-io/hs-pylib/commit/16bae1c8b0e5f0c80531ef7df802aa7e6edf3148))
* update ci submodule to v1.1.1 (release automation complete) ([e7307e1](https://github.com/hypersec-io/hs-pylib/commit/e7307e1f1b8d167adc1f253c7638ce57f486dc20))
* update ci submodule to v1.6.13 (Python 3.12 requirement and documentation updates) ([0aa628e](https://github.com/hypersec-io/hs-pylib/commit/0aa628e86d077fbe87b2f1c9b9fcb025597db7e3))
* update ci submodule to v2.0.0 (comprehensive permission improvements) ([1af6cbb](https://github.com/hypersec-io/hs-pylib/commit/1af6cbb23bdfbe0efaf1fe01c6d636e05b732592))
* update ci submodule URL to renamed hs-ci repository ([b5f3909](https://github.com/hypersec-io/hs-pylib/commit/b5f3909cb0828a6cae5afeb16d52db6bf282f342))
* update ci submodule with improved commit-msg hook ([7e3b663](https://github.com/hypersec-io/hs-pylib/commit/7e3b6632542a78ef7c276415a60ce5584b3318d6))
* update CI to hs-ci v1.31.0 with thin workflows ([af92044](https://github.com/hypersec-io/hs-pylib/commit/af92044608f8742488e7af5a28d169372cee552e))
* update CI to hs-ci v1.33.1 ([e159cd8](https://github.com/hypersec-io/hs-pylib/commit/e159cd84e436e7b42fd07443b028abb331b8183a))
* update CI to hs-ci v1.33.2 ([4261e8f](https://github.com/hypersec-io/hs-pylib/commit/4261e8f226ac6dda3dc720eb11201ab31a9b238f))
* update CI with thin publish.yml workflow ([ce0ea07](https://github.com/hypersec-io/hs-pylib/commit/ce0ea072bc7f40a73698031f2eb3e1ed069ea48f))
* update ci-publish workflow for new ci structure ([51333d4](https://github.com/hypersec-io/hs-pylib/commit/51333d4f2f2600585352349aac173f355747b498))
* update Dockerfile fixtures to use pyproject.toml optional extras ([ad3fc81](https://github.com/hypersec-io/hs-pylib/commit/ad3fc81e1410f5a9a781cea68c0ec7f70d859709))
* update E2E and integration tests for Typer CLI and container deployment ([ce4101c](https://github.com/hypersec-io/hs-pylib/commit/ce4101c33c1766e3c282b81ca12894fdaecf8e7a))
* update Nuitka multi-arch workflow for private repos and add active checking ([5580037](https://github.com/hypersec-io/hs-pylib/commit/55800372fe5f04a872ce0d01ca737d4864338a7a))
* update pyproject.toml - Python 3.11+, remove unused deps, add optional extras ([3ad89f2](https://github.com/hypersec-io/hs-pylib/commit/3ad89f289d40c048e79227e6b54c017e91c4765d))
* update pyproject.toml metadata - production status, accurate description and keywords ([be7ca68](https://github.com/hypersec-io/hs-pylib/commit/be7ca688b9c83e9045ee87c05980aedb2484d2df))
* update pyproject.toml to use JFrog virtual repository ([404e447](https://github.com/hypersec-io/hs-pylib/commit/404e44749e0821ffba5bbca5dfae5c322d5c847e))
* update README badges to reflect hs-pylib rename and Python 3.12 ([b07613c](https://github.com/hypersec-io/hs-pylib/commit/b07613c9202f1de4c8a39d1907aa5ac0ed747bf9))
* update semantic-release build command to use ci-local/.venv ([4c9fc4a](https://github.com/hypersec-io/hs-pylib/commit/4c9fc4ad1853fd3aced8423db310a0fb3e7d4866))
* update setup.py package name reference ([0e431ec](https://github.com/hypersec-io/hs-pylib/commit/0e431ec3998584bd1fd381df9607ea8d2fa3461a))
* update STATE.md for new CI architecture (hs-ci v1.19.x) ([7761e71](https://github.com/hypersec-io/hs-pylib/commit/7761e710d0bafe2b8f794a5dc9070abe2292546d))
* update test assertions and make verification test optional ([e61dda5](https://github.com/hypersec-io/hs-pylib/commit/e61dda5cd111247c8e9b9fccb517a4179f00d63c))
* update test to use build_type (not build_profile) ([0d44216](https://github.com/hypersec-io/hs-pylib/commit/0d442168bf23661ed26db02795ae31beb5fc48e1))
* update test_ci.py for ci.yaml at project root (submodule structure) ([cf9ad19](https://github.com/hypersec-io/hs-pylib/commit/cf9ad1940e46e76c58bfcd824f033272026f6abb))
* update tests for module restructuring (52 pre-existing failures) ([6cb7ada](https://github.com/hypersec-io/hs-pylib/commit/6cb7adac3c824fa9465df47b9a2011001ea7f946))
* update to new workflow paths (DFE-523) ([c3c7db9](https://github.com/hypersec-io/hs-pylib/commit/c3c7db96e95d45564c7eb11f2293b73a1bf44b38))
* update to Python 3.12 and remove duplicate pytest markers ([5159c37](https://github.com/hypersec-io/hs-pylib/commit/5159c37f9a0cb2fbbbdfe4d719bd71cb9c8f8514))
* update to Python 3.12 and sync with hs-ci v1.6.13 ([4289a92](https://github.com/hypersec-io/hs-pylib/commit/4289a92b2f4b104e68975feebcd2ea59a5eaa060))
* update TODO to reflect completed CI restructure ([8af162a](https://github.com/hypersec-io/hs-pylib/commit/8af162ae5e84624faee6b085303ecc0b151dbe3e))
* update TODO.md estimates to aggressive AI-assisted timeframes (Linear.app points) ([3d7ab63](https://github.com/hypersec-io/hs-pylib/commit/3d7ab6374c41a55fca007e0c2e594718692670e4))
* update workflow to call publish script directly ([cf8678a](https://github.com/hypersec-io/hs-pylib/commit/cf8678a27c7be8a3f915cd2387ad921fe68085bd))
* update workflows with checkout fix (DFE-539) ([7e434f0](https://github.com/hypersec-io/hs-pylib/commit/7e434f0fdc75dcd58cc9f06914b8898ec445600f))
* use ./ci/run publish in GitHub Actions workflow ([6b0a943](https://github.com/hypersec-io/hs-pylib/commit/6b0a94394fdb29fb941c7de62baecb3ff015b923))
* use BuildJet for ARM64 runners in private repos ([4d5325c](https://github.com/hypersec-io/hs-pylib/commit/4d5325c21e4a9f191ac0a7a9b48cf1420459353a))
* use BuildJet runners for all builds (standard + nuitka) ([aee575d](https://github.com/hypersec-io/hs-pylib/commit/aee575d454141d8e2fa048e4b0e21f4be253de8f))
* use CI_FORCE_RELEASE=1 in verification test ([5170999](https://github.com/hypersec-io/hs-pylib/commit/51709998278f7e56c5c8899d0734194425ffb131))
* use ci-local/ci.yaml in GitHub Actions workflow ([94a182e](https://github.com/hypersec-io/hs-pylib/commit/94a182e7a82d4ec354a6c48a79fbc4aa5dd4802f))
* use default=true for uv.index and clarify both uv/pip work with HyperCI ([0b4dd5b](https://github.com/hypersec-io/hs-pylib/commit/0b4dd5bf5b9e5e3105fe5da3c51e9fb6ecba392c))
* use JFrog virtual repository for all Python package installations ([4f7de72](https://github.com/hypersec-io/hs-pylib/commit/4f7de72670fe9c3bad9302c74b3900eab45fead0))
* use local ci/workflows path (DFE-523) ([af72571](https://github.com/hypersec-io/hs-pylib/commit/af725718d4fdc682fc5dfb24f050b12768555a1e))
* use proper Solarized color codes in logger format ([27045b6](https://github.com/hypersec-io/hs-pylib/commit/27045b656032baa88e59388bad39cb24e3d527fc)), closes [#859900](https://github.com/hypersec-io/hs-pylib/issues/859900) [#2aa198](https://github.com/hypersec-io/hs-pylib/issues/2aa198)
* use Python 3.12 in workflow (hs-pylib requires 3.12+) ([18000b4](https://github.com/hypersec-io/hs-pylib/commit/18000b4390d8123ecca0a9d0d47d86f3d9e9fc9f))
* use release_name for ConfigMap (not test_id) to match Helm template ([8a4f192](https://github.com/hypersec-io/hs-pylib/commit/8a4f1921cb9a2ea552f4f77249782f1ead81b724))
* use remote ci repository paths for reusable workflows ([65a0a6d](https://github.com/hypersec-io/hs-pylib/commit/65a0a6dba6f6d59f738d78c2a042a6981e2f882a))
* VERSION file uses standard plain format (git tag is source of truth) ([d2555b3](https://github.com/hypersec-io/hs-pylib/commit/d2555b357d2b07e59634f4954ac5d1b9b4c5c44f))
* wait for pod Ready before kubectl exec in test_helm_chart_deployment ([9da7b7b](https://github.com/hypersec-io/hs-pylib/commit/9da7b7b074536f0eedd56df0e64fda0fd3690571))


### Code Refactoring

* standardize env vars to ARTIFACTORY_* and improve CI testing ([668661f](https://github.com/hypersec-io/hs-pylib/commit/668661fcede1db10d39371200f7bac5e35fed4b2))


### Features

* add /ci/git tool to project ([9f61a65](https://github.com/hypersec-io/hs-pylib/commit/9f61a656b67d3c2c7e0fee26c2444f184d1ce415))
* add ai: section to ci-local/ci.yaml ([3991064](https://github.com/hypersec-io/hs-pylib/commit/3991064df8fb61ea4c8a8156ab1841fe024c3b75))
* add Application.mcp() for MCP server deployment type ([b3673bd](https://github.com/hypersec-io/hs-pylib/commit/b3673bd0b184a545dae6d54a9601965ccb045b82))
* add automatic sensitive data masking to logger ([2c06e01](https://github.com/hypersec-io/hs-pylib/commit/2c06e01c26fdc0e2cac29de816852a8eb912b2a2))
* add bash command execution policy and update ci submodule ([cc0f794](https://github.com/hypersec-io/hs-pylib/commit/cc0f794b23b540ebcba7e665c298425492865df4))
* add BuildJet configuration option to ci/ci.yaml ([faa9294](https://github.com/hypersec-io/hs-pylib/commit/faa9294daa4c856edf5105a4ed8fb9bcaa99996e))
* add CI_BUMP_PATCH=1 option to control patch commit ([a3777fb](https://github.com/hypersec-io/hs-pylib/commit/a3777fbc5db62f6c194bd6b3b3a147a49e3526e8))
* add settings merge to bootstrap (CI_MERGE) ([ebaafa4](https://github.com/hypersec-io/hs-pylib/commit/ebaafa46af764259161cab44b7fd2cd008330c3e))
* add CLI enhancements for multi-environment configuration ([bd5b40a](https://github.com/hypersec-io/hs-pylib/commit/bd5b40a0dea976bad341469d902b7b770a87bf51))
* add code header standards (REUSE/SPDX compliant) ([6e3e657](https://github.com/hypersec-io/hs-pylib/commit/6e3e657fe71b1afa7c1b9a98e68ddb5fe7206e35))
* add comprehensive JFrog publish and install test ([4ae373a](https://github.com/hypersec-io/hs-pylib/commit/4ae373aafcc04b4cbe785237e57b5d699029d3e5))
* add comprehensive Prometheus metrics module with custom metrics API ([ef01c96](https://github.com/hypersec-io/hs-pylib/commit/ef01c96e8eabf7e285b9fe2a04e701c5f429e230))
* add comprehensive security and quality checks to CI ([fd82dce](https://github.com/hypersec-io/hs-pylib/commit/fd82dceec7c042fb92980f91fc8cc05f52c51a75))
* add container registry throttling detection and Docker auth ([2ac560c](https://github.com/hypersec-io/hs-pylib/commit/2ac560ca7f214f533021f9d1cdfbfaa84ee7d802))
* add CONTAINER_BASE_PATH environment variable override ([43f0b64](https://github.com/hypersec-io/hs-pylib/commit/43f0b64f99e4094ba84dec56e6b5239b5cb5f992))
* add fast test mode to skip slow integration tests ([52ea1af](https://github.com/hypersec-io/hs-pylib/commit/52ea1afd1ac0edec8d915da5b55d8c07f521d311))
* add full publish verification test ([c064479](https://github.com/hypersec-io/hs-pylib/commit/c0644790ad32904905f8f998fa41f63f0622768b))
* add generic container registry auth (Docker + Artifactory precedence) ([ed0a9cc](https://github.com/hypersec-io/hs-pylib/commit/ed0a9cc827c9821fbdb1a062bca81d074743a9ae))
* add GitHub badges to README with automatic CI updates ([8c03174](https://github.com/hypersec-io/hs-pylib/commit/8c0317479980d9d98200c763d9ce4be6ed085ff4))
* add http, cache, and metrics modules ([7e3e437](https://github.com/hypersec-io/hs-pylib/commit/7e3e437abb049ed8ff68470e60dd2f154ddd1c41))
* add hyperlib-specific ci/ci.yaml and protect from subtree overwrites ([a54cd3d](https://github.com/hypersec-io/hs-pylib/commit/a54cd3d2edcd41b2ff3c690b9ce68f799d14f8d4))
* add hyperlib.application factory pattern ([341ba7a](https://github.com/hypersec-io/hs-pylib/commit/341ba7afa20573d789e99aa2cdc34462a82e2523))
* add idempotent TODO.md creation tosettings merge ([d76f83d](https://github.com/hypersec-io/hs-pylib/commit/d76f83d7e0bcd22190a0ca440811decfe77b0e41))
* add interactive prompt fortier selection ([081bef6](https://github.com/hypersec-io/hs-pylib/commit/081bef6b686489311be74c207e1ee10e4dddbd3f))
* add macOS ARM64 support to unified workflow ([d5dce8e](https://github.com/hypersec-io/hs-pylib/commit/d5dce8e1f79252bb7754144723aaa2ea7e1bbf41))
* add mergedeep library to CI tools ([23cd1c4](https://github.com/hypersec-io/hs-pylib/commit/23cd1c4a77224e01803570ef6ebe8af81cdf910c))
* add metrics backend abstraction for Prometheus and OpenTelemetry ([05b4e5d](https://github.com/hypersec-io/hs-pylib/commit/05b4e5d68e18db4c88e939c19cef6c75571adb6e))
* add missing enterprise features to application module ([18ea4de](https://github.com/hypersec-io/hs-pylib/commit/18ea4de998d2e438ef0ace8e70e45e1fb47d26a1))
* add Node.js/npx requirement check tosettings merge ([56fc1b5](https://github.com/hypersec-io/hs-pylib/commit/56fc1b5ecc0985a89b611cb5268551187c9eacec))
* add Nuitka Commercial detection, compiled wheel builds, and bootstrap restructuring ([d327e16](https://github.com/hypersec-io/hs-pylib/commit/d327e1657dded35068ff51ff523d6305febc032d))
* add Nuitka package mode with auto-detection and prevent JFrog sprawl ([4fb92e7](https://github.com/hypersec-io/hs-pylib/commit/4fb92e74b8f658857e2a03823d7c33896c4e9ef2))
* add opinionated anonymizer with Presidio integration ([a076756](https://github.com/hypersec-io/hs-pylib/commit/a07675639922cfce7c30828b65cfe0e6a664c978))
* add publish verification and update dependencies ([c2b9d43](https://github.com/hypersec-io/hs-pylib/commit/c2b9d43b8d46fcc27161402d43a1fdd24eea9fd3))
* add README.md for package distribution ([c4573da](https://github.com/hypersec-io/hs-pylib/commit/c4573da8274e6888aa4ab3714918069f7f1d42eb))
* add real language detection and TODO.md policy ([63b214f](https://github.com/hypersec-io/hs-pylib/commit/63b214f0be51f574a4b85a96d6d7b38f0b1c21d5))
* add router inclusion and generic middleware support to APIApplication ([3baa925](https://github.com/hypersec-io/hs-pylib/commit/3baa925af06f4e9a4e9dc24cd5ec1a4a0849d9ee))
* add selective test system and update CI ([2a08336](https://github.com/hypersec-io/hs-pylib/commit/2a0833630a295ee0c2912299e5b30960537d9f03))
* add smart auto-configuration to logger with opt-out ([b249cfa](https://github.com/hypersec-io/hs-pylib/commit/b249cfa4d7bc64945042f18dd9271440b20d882e))
* add test validation checklist and update ci submodule ([1a78fff](https://github.com/hypersec-io/hs-pylib/commit/1a78fff2f67032d1c75c64ac53d722a06f1a5b0a))
* add third-party runner support (BuildJet + Cirrus) for cost savings ([5b45685](https://github.com/hypersec-io/hs-pylib/commit/5b45685ddb212abf96ed1b039f2bb5c4ee704d84))
* add tool.uv config to enforce ci-local/.venv ([da85e8b](https://github.com/hypersec-io/hs-pylib/commit/da85e8b51384d2486605417746bc7406b33a96ec))
* add two-tier sensitive data anonymization (Presidio + regex) ([55cb29a](https://github.com/hypersec-io/hs-pylib/commit/55cb29aaf30299c5263ed94e86e862a24e967b17))
* add Typer as mandatory CLI standard for hyperlib ([959cca2](https://github.com/hypersec-io/hs-pylib/commit/959cca2d49a77231f0e9bd86212c5e49c39799f8))
* add unified runtime environment for container and local deployment ([5d109fd](https://github.com/hypersec-io/hs-pylib/commit/5d109fdc6bb9109f58d360ce545474f680b9fde6))
* add version check to prevent duplicate builds and remove schedule triggers ([152b53c](https://github.com/hypersec-io/hs-pylib/commit/152b53ce71d4e03b3f692337b5e5409c7e641ccd))
* add VERSION corruption recovery script (99-fix-version.py) ([7a8a33e](https://github.com/hypersec-io/hs-pylib/commit/7a8a33e66f63b24ce9068dce351469178031e25d))
* add version-exists check to prevent accidental republishing ([10d62c6](https://github.com/hypersec-io/hs-pylib/commit/10d62c6328bbdba98744e0ee761d776eb403df86))
* apply rationalized CI documentation to STATE.md and settings ([f0b313b](https://github.com/hypersec-io/hs-pylib/commit/f0b313bc040ebebf79bd33f25faf83eb5eaf7d73))
* capture Docker and K8s pod logs to /logs directory with timestamps ([77c44db](https://github.com/hypersec-io/hs-pylib/commit/77c44dbcac052f4262119df7ed249e79c6e5059e))
* clean commit without attribution ([34070b9](https://github.com/hypersec-io/hs-pylib/commit/34070b943fe01a60b1170bae33e338cfc6f8aa9c))
* code header and license system complete (REUSE/SPDX) ([51255ee](https://github.com/hypersec-io/hs-pylib/commit/51255ee6a8564748b1ec7adf200a318ae9f7e585))
* complete ci-local/.venv migration ([e8305ca](https://github.com/hypersec-io/hs-pylib/commit/e8305ca23517adc90a48b510e495aa8e3c7edf2a))
* complete setup with standards/ directory and force mode ([c52f5bb](https://github.com/hypersec-io/hs-pylib/commit/c52f5bbfe8273aacf47e67aac068776369dbe52c))
* completesettings merge implementation ([ddb705e](https://github.com/hypersec-io/hs-pylib/commit/ddb705e51dd034e902d737ca3a4df179f7973398))
* complete ENV standardization - clean CI_ prefix standard ([7b373e8](https://github.com/hypersec-io/hs-pylib/commit/7b373e829e5f2f4d754393d66a06ce8d8f999d75))
* complete ENV standardization with CI_ prefix ([bafdf28](https://github.com/hypersec-io/hs-pylib/commit/bafdf28d533f41644f37c6c75700f17617a4974e))
* config consolidation complete - all use ci_lib.py ([b746add](https://github.com/hypersec-io/hs-pylib/commit/b746add40b0cc7fa2c031d0619cd331eaa022382))
* configure Docker Hub imagePullSecrets in Helm test namespaces ([4f39783](https://github.com/hypersec-io/hs-pylib/commit/4f3978351a8fa0e2ec01f747c5af33c04db968ea))
* confirm template substitution works for MCP memory path ([e443c0a](https://github.com/hypersec-io/hs-pylib/commit/e443c0ada155a45c839ef68f0d04b10c6854f6b4))
* container-native application patterns (Phases 1-4) ([baad975](https://github.com/hypersec-io/hs-pylib/commit/baad975bb2e6db41641d8e7dd4588dc0e415f2f2))
* convert hyperci to git submodule for version control ([1ec480b](https://github.com/hypersec-io/hs-pylib/commit/1ec480bb3bde9487aea0935957fa8bbbf5be36c7))
* create /ci/ai tool foundation (Phase 1 start) ([609d37e](https://github.com/hypersec-io/hs-pylib/commit/609d37eccceead046195c36a7f1c36dbfd55424b))
* document hyperci subtree architecture and usage ([0f9eeee](https://github.com/hypersec-io/hs-pylib/commit/0f9eeee97fa90185a6cba590fa157b824b9bc18a))
* enforce .venv-ci for all CI scripts (FAIL HARD) ([9f5050d](https://github.com/hypersec-io/hs-pylib/commit/9f5050d09414bb131fbc97b294312e3c7b9d8c23))
* enforce CHARS-POLICY.md in logger with terminal detection ([84181e6](https://github.com/hypersec-io/hs-pylib/commit/84181e6d681998c3408261fa3bdf93b14b288f51))
* enhance container detection with 7-layer strategy ([6c19eaa](https://github.com/hypersec-io/hs-pylib/commit/6c19eaa14d95cb9a5a0e29f1430d0963c6faf76d)), closes [hi#confidence](https://github.com/hi/issues/confidence)
* implement template substitution for reliable MCP memory path ([2cfbd62](https://github.com/hypersec-io/hs-pylib/commit/2cfbd624e8e347e296be2cdeee1470a13e64e7dc))
* integrate harness.run() into tests for centralized logging ([f83f9a0](https://github.com/hypersec-io/hs-pylib/commit/f83f9a0b2ab64230874a2acf8151d31bb909fb92))
* migrate CLIApplication from Click to Typer (mandatory standard) ([b537325](https://github.com/hypersec-io/hs-pylib/commit/b537325e52d9b5270ecc0500f9da14f81bed9f15))
* move ci_lib to common, add structure validators, document dependencies ([9d4229c](https://github.com/hypersec-io/hs-pylib/commit/9d4229ccfbba623b14144763e84a27705983524c))
* move ci.yaml to project root with auto-creation and comprehensive docs ([a0a2b16](https://github.com/hypersec-io/hs-pylib/commit/a0a2b16870ffd54fd054a736b5096ae02f668683))
* path standardization and Pro default complete ([eb2f401](https://github.com/hypersec-io/hs-pylib/commit/eb2f4017b5d547491ff9ad095cf61fb70ae73222))
* Phase 1 complete - /ci/ai modular tool replaces monolithic script ([d18aa1b](https://github.com/hypersec-io/hs-pylib/commit/d18aa1b4ee69fb7bcb51141ad9335a34ec9957c2))
* Pro Max verified with merge default ([45b6d96](https://github.com/hypersec-io/hs-pylib/commit/45b6d96caec28282ceb1645ec6e0b6a2c6036a9f))
* remove hardcoded values - all config in ci.yaml ([826d303](https://github.com/hypersec-io/hs-pylib/commit/826d3031d766f29d8d68735042a19cb8410bce45))
* restore simplified Nuitka workflow using ci/ scripts directly ([9259671](https://github.com/hypersec-io/hs-pylib/commit/92596711d847479398395d4fe18058710edb7b5f))
* session complete - /ci/ai verified working ([4998a0f](https://github.com/hypersec-io/hs-pylib/commit/4998a0f5f8b7cd5dc94ac58ac724311b2c68fca3))
* simplify GitHub Actions to use ci/ infrastructure directly ([22f157d](https://github.com/hypersec-io/hs-pylib/commit/22f157ddb247c70cde02069c2230dfbcc2d17e07))
* unified CI Publish workflow - ONE workflow for everything ([4d9378e](https://github.com/hypersec-io/hs-pylib/commit/4d9378e4a05d718e154ec8b0b83ddf791592dd77))
* update ci submodule (merge_env implementation) ([ca2b163](https://github.com/hypersec-io/hs-pylib/commit/ca2b163bd27113ac843424c04f66ba8446c63d5d))
* update ci submodule to v1.8.0 (add --python-version flag) ([f9fd6ae](https://github.com/hypersec-io/hs-pylib/commit/f9fd6aec853d9be24076422aa86fc4ee4606b152))
* update ci submodule with version pinning and install script ([b088f79](https://github.com/hypersec-io/hs-pylib/commit/b088f792730cdc2fb9cd7415e006e33bb5334280))
* update ci submodule with VSCode multi-language template split ([1e1352a](https://github.com/hypersec-io/hs-pylib/commit/1e1352a727f2ad61d93b7c59975db7db996911f7))
* update GitHub Actions workflows for submodule pattern ([c06cff7](https://github.com/hypersec-io/hs-pylib/commit/c06cff7d7cbedd422dd316a9ecb8bc2b82aa5a70))
* update hyperci with native uv mode support (uv sync, uv build) ([82b6a8e](https://github.com/hypersec-io/hs-pylib/commit/82b6a8ef588f874f1ff9a6fef396daa84f5f1ac0))
* update memory MCP server to mcp-knowledge-graph ([b469411](https://github.com/hypersec-io/hs-pylib/commit/b469411265a0d3710338c18ded63e957eef7546e))
* update to uv-managed Python (no system Python dependency) ([e9b8375](https://github.com/hypersec-io/hs-pylib/commit/e9b8375cfeb8871a3338b00ff99b116e3dd8f8df))


### Reverts

* remove pushd/popd guidance (doesn't work across Bash subprocesses) ([184e148](https://github.com/hypersec-io/hs-pylib/commit/184e148b847f01b9edce2fbefe69e24185af758f))


### BREAKING CHANGES

* note: Projects using CLIApplication must install Typer:
  pip install hyperlib[cli]

This enforces the hyperlib CLI standard across all applications.
* All CI tools now in ci-local/.venv (not ci/.venv)

Changes:
- Updated ci submodule to dda545b (ci-local/.venv support)
- Added dynaconf to ci-local/pyproject.toml
- Regenerated ci-local/uv.lock with dynaconf
- Updated workflows to use ci-local/.venv
- Rewrote test_ci.py to test REAL ci/ infrastructure
- Updated STATE.md with ci-local/.venv documentation

Benefits:
- ci/ is now 100% READ-ONLY (git submodule best practice)
- All writable state in ci-local/ (venv, configs, credentials)
- Unified configuration with dynaconf (ENV + CLI + file)
- Same scripts work locally and in GitHub Actions

Next: rm -rf ci/.venv && ci/bootstrap --install
* Removed all JF_* environment variable backward compatibility.
Only ARTIFACTORY_* variables are supported now (matching GitHub Actions secrets).

Major changes:
- BuildJet now used for BOTH x64 and ARM64 Linux builds (50% cost savings)
  - Enabled by default via buildjet.enabled: true
  - x64: /bin/bash.004/min (vs GitHub /bin/bash.008/min)
  - ARM64: /bin/bash.004/min (vs GitHub N/A for private repos)

- Cirrus Runners added for macOS builds (95% cost savings)
  - Enabled by default via cirrus.enabled: true
  - macOS: /bin/bash.015/min effective (vs GitHub /bin/bash.16/min)
  - Uses M4 Pro chips with better performance
  - Requires setup: https://cirrus-runners.app/setup/

- Cost comparison with defaults:
  - Linux x64 + ARM64: /bin/bash.056/release (was /bin/bash.084)
  - All platforms: /bin/bash.161/release (was .26)
  - Monthly savings: ~88% for all platforms

- Workflow intelligently falls back to GitHub runners when disabled:
  - BuildJet disabled: Uses GitHub for Linux (2x cost, no ARM64 for private)
  - Cirrus disabled: Uses GitHub for macOS (10x cost)

- Removed migrate_env.py - clean slate with ARTIFACTORY_* variables only
- Updated all bootstrap scripts to use only ARTIFACTORY_* env vars
* Environment variable names have been standardized to match GitHub Actions secrets.
Old JF_* variables are no longer supported. Use ARTIFACTORY_* variables instead.

Changes:
- Replace all JF_* env vars with ARTIFACTORY_* (matches GitHub secrets)
  - JF_USER → ARTIFACTORY_USERNAME
  - JF_PASSWORD → ARTIFACTORY_PASSWORD
  - JF_TOKEN → ARTIFACTORY_TOKEN
  - JF_TOKEN_USER → ARTIFACTORY_TOKEN_USER
  - JF_PYPI_HOST → ARTIFACTORY_PYPI_HOST

- Update bootstrap script to use only ARTIFACTORY_* vars (no backward compat)
- Update .env.sample with new variable names
- Add migrate_env.py utility to help users migrate existing .env files

- Replace tests/ci/test_nuitka_build.py with comprehensive test_ci.py that:
  - Creates virtual project environment for testing
  - Tests complete CI pipeline (bootstrap, build, publish)
  - Waits for JFrog publication before testing installation
  - Tests Nuitka compiled wheels with git import verification
  - Verifies both standard and compiled packages work correctly

- Update documentation in STATE.md for new env var naming
- Add test artifacts to .gitignore

Migration guide:
1. Run: python migrate_env.py
2. Test: ./ci/bootstrap --install
3. Delete backup files once confirmed working
* Complete CI infrastructure reorganization for better isolation

## Changes

### Directory Structure
- Renamed `/scripts` → `/ci` (clearer naming)
- Renamed `scripts/ci` → `ci/run` (more intuitive)
- Moved `.venv-ci` → `ci/.venv` (full self-containment)
- Everything CI-related now lives in `/ci` directory

### New Structure
```
/ci/                 # All CI infrastructure
├── .venv/          # CI virtual environment (was .venv-ci at root)
├── bootstrap       # Creates ci/.venv
├── run             # Main CI runner (was ci)
├── bootstrap.d/    # Bootstrap scripts
├── ci.d/           # CI task scripts
└── ci_lib.py       # Shared CI utilities
```

### pyproject.toml Cleanup (Option A: Pure Python Lists)
- Removed CI tools from `[project.optional-dependencies] dev`
- CI dependencies now exclusively in `ci/bootstrap.d/20-python-tools.py`
- `dev` extras now only contains local development tools (pre-commit, isort)
- Zero pollution of project dependencies with CI infrastructure

### Path Updates
- All scripts updated: `.venv-ci` → `ci/.venv`
- All scripts updated: `scripts/` → `ci/`
- Bootstrap creates `ci/.venv` instead of `.venv-ci`
- CI runner uses `ci/.venv/bin/python` explicitly
- Documentation updated across all .md files

### Benefits
- ✅ True isolation: All CI infrastructure in one directory
- ✅ Portable: Can copy/zip `ci/` and it works standalone
- ✅ Simpler naming: Just `.venv` inside `ci/` (context is clear)
- ✅ Cleaner root: Only `.venv` (dev) at root, not `.venv-ci`
- ✅ Conceptually clear: "Everything in `ci/` is for CI"
- ✅ Better dependency management: CI tools separate from project deps

### Forge Template Benefit
Other projects can adopt this clean, self-contained CI structure.

Tested:
- ./ci/bootstrap (check mode) ✓
- ./ci/run --script 10-branch-name.py check ✓





# [1.6.0](https://github.com/hypersec-io/hs-pylib/compare/v1.5.0...v1.6.0) (2025-12-04)


### Bug Fixes

* add --language python flag to bootstrap in CI workflow ([3ade9b1](https://github.com/hypersec-io/hs-pylib/commit/3ade9b1505a263b943b66946d28007a69726e051))
* add api extras to metrics test Dockerfile, remove orphaned jinja template ([08f1df4](https://github.com/hypersec-io/hs-pylib/commit/08f1df43af7bd764a3c64e16fba94f18c78e062b))
* add automatic cleanup of hung background processes in pytest ([c950958](https://github.com/hypersec-io/hs-pylib/commit/c9509589d017f1fa10509a2944651921a8bf0413))
* add cache_dir and run_dir to RuntimePaths, remove jinja templates ([40b94ff](https://github.com/hypersec-io/hs-pylib/commit/40b94ffbb9f7ba17579133e6c25ec4ad567bfbd1))
* add clean-commit action to remove AI attribution from commits ([490d9a3](https://github.com/hypersec-io/hs-pylib/commit/490d9a37ffa9aa55276d8b139724f373c8924fc6))
* add CLI utilities for faster development ([4feffbb](https://github.com/hypersec-io/hs-pylib/commit/4feffbb082b76293e3281a270e41f0449dd0f060))
* add ClickHouse database support to connection builder ([3fdae1c](https://github.com/hypersec-io/hs-pylib/commit/3fdae1cfeb71a4c3b4928477277f1fc1c8fa3b79))
* add comprehensive exception handling to config merge module ([7ac7dd3](https://github.com/hypersec-io/hs-pylib/commit/7ac7dd39edd3c4d61792710b8802d45b8e11c92a))
* add comprehensive self-documenting code to all hyperlib modules ([9a48e89](https://github.com/hypersec-io/hs-pylib/commit/9a48e89d1c6d3941560464906987588f5824c136))
* add configurable color schemes for logger ([2289931](https://github.com/hypersec-io/hs-pylib/commit/2289931a2b2173610459aff055b9ba842edccea4))
* add get_logger() to ci_lib.py with loguru and RFC 3339 timestamps ([4a552e9](https://github.com/hypersec-io/hs-pylib/commit/4a552e9ad39221bd0158f60760a749142abb4dec))
* add GH_PAT support and ci-local/.env for GitHub Actions ([1154265](https://github.com/hypersec-io/hs-pylib/commit/11542658eaa8454366b774103874edf117da7186))
* add GitHub release creation to ci-publish workflow ([a29a8d4](https://github.com/hypersec-io/hs-pylib/commit/a29a8d4436f9dca8bd5d7cfdda7dabec01880afe))
* add gitleaks allowlist for historical backup files ([1827657](https://github.com/hypersec-io/hs-pylib/commit/1827657db9dd25bedecb53ff2bc9ba65e16544c2))
* add HealthCheckMixin to Daemon and MCP applications ([b059150](https://github.com/hypersec-io/hs-pylib/commit/b059150ab0b9c7f3f040a6eff2c1c074fb6b2cfd))
* add httpx test dependency for FastAPI TestClient ([c7e94c0](https://github.com/hypersec-io/hs-pylib/commit/c7e94c0633303f483927a40bf87e2b364587bae6))
* add HYPERLIB_TEST labels to all K8s/Helm commands for cleanup ([0690fec](https://github.com/hypersec-io/hs-pylib/commit/0690fecaa8d3358847e7c256bf7f224aec5be4d8))
* add imagePullSecrets to all Helm pod/deployment templates ([234424f](https://github.com/hypersec-io/hs-pylib/commit/234424f2e015bf0cb63a7fae1f612119e2f0b010))
* add JFrog publishing controls with auto-detect and --no-publish flag ([4aaccac](https://github.com/hypersec-io/hs-pylib/commit/4aaccac04d75cef1e5d73d5a2beebb2f472a3dd6))
* add loguru and reduce CI tool dependencies to only what's used ([65e638c](https://github.com/hypersec-io/hs-pylib/commit/65e638cecb97610583f4a5354d2ed31019d18233))
* add MCPApplication to __init__.py exports ([091ef9f](https://github.com/hypersec-io/hs-pylib/commit/091ef9f4729b1aadfe876b7c5c3d0da1995aa11e))
* add missing LICENSE file (HyperSec EULA) ([842565c](https://github.com/hypersec-io/hs-pylib/commit/842565c5c559a2c6d0279a383c8b484071f5a008))
* add nosec B108 to /tmp paths (bandit warnings) ([a65f647](https://github.com/hypersec-io/hs-pylib/commit/a65f6476ea609b8b9118f78bfee3d559b5728ac8)), closes [#nosec](https://github.com/hypersec-io/hs-pylib/issues/nosec)
* add production-grade exception handling across core modules ([3ec18f2](https://github.com/hypersec-io/hs-pylib/commit/3ec18f28065011f864987da7c1c2947f9e634d6c))
* add Python venv setup step to workflow (workaround BUG-CI-001) ([e0c8c7c](https://github.com/hypersec-io/hs-pylib/commit/e0c8c7cec8397455408dd32567aa39c923011b0e))
* add typer to required dependencies and futureproof Python version requirements ([75183a9](https://github.com/hypersec-io/hs-pylib/commit/75183a999e8351ae80b98385a04ab4ce67db6d44))
* add uv installation to GitHub Actions workflow ([287aa7d](https://github.com/hypersec-io/hs-pylib/commit/287aa7d63b281c8313bfc174a40ad61ff3363b4f))
* add version management comment for clarity ([ff0bee2](https://github.com/hypersec-io/hs-pylib/commit/ff0bee2edac48f0a54cd43bdcb03cd650eea36c5))
* allowlist test fixture fake secrets in gitleaks ([957952b](https://github.com/hypersec-io/hs-pylib/commit/957952b4c089366c54621574e1fbfb27e5dbc9bf))
* allowlist test_logger_filters.py fake secrets ([f79718e](https://github.com/hypersec-io/hs-pylib/commit/f79718e3b7b94cdb0b1808b99fbdf2359319c405))
* API test route decorator, add comprehensive testing documentation ([7a2eda7](https://github.com/hypersec-io/hs-pylib/commit/7a2eda7684231cc6fb0198e4e5315c41d94c6e4c))
* apply Black formatting (dbconn, test_logger, config) ([81c9740](https://github.com/hypersec-io/hs-pylib/commit/81c9740c76a706dc690e2b8def7ef52d8561ce08))
* apply black formatting to custom_recognizers.py ([0aec5ed](https://github.com/hypersec-io/hs-pylib/commit/0aec5ed97642e6cd24c2ff7ff496de68c891d258))
* apply Black formatting to mcp.py ([40a39d9](https://github.com/hypersec-io/hs-pylib/commit/40a39d95c6c731120afaed0d457d2a81bc86d6a1))
* apply ruff auto-fixes (UP015, UP045, F541) ([4bc22b0](https://github.com/hypersec-io/hs-pylib/commit/4bc22b0d9dd80c6bb922f0874c27c87559c1eef8))
* apply ruff formatting fixes to application code and tests ([1925019](https://github.com/hypersec-io/hs-pylib/commit/1925019e538dd0321571abd366bd6de2c3e76538))
* auto-trigger CI publish on release tags (v*) ([59fe7dd](https://github.com/hypersec-io/hs-pylib/commit/59fe7dd3d61ea1ad2584da44c09ec440dbcfbde5))
* bootstrap now creates and manages both ci/.venv and .venv ([7775ef0](https://github.com/hypersec-io/hs-pylib/commit/7775ef0fd926f3c704143cb5947d5ac1ddcf5e5b))
* check for uv in .venv first, with system PATH as fallback ([c0dba6b](https://github.com/hypersec-io/hs-pylib/commit/c0dba6b983212896fd881f68cd459b6587461c7c))
* CI test for Nuitka + BuildJet verification 20251017-133530 ([1505d18](https://github.com/hypersec-io/hs-pylib/commit/1505d18f13f036e7016317343266492eaeba3b2f))
* CI test patch bump 20251017-121712 ([7c7c0c3](https://github.com/hypersec-io/hs-pylib/commit/7c7c0c33984854aa130f4f2fcf2f04e4cea8edfc))
* CI test patch bump 20251017-121752 ([881fd2d](https://github.com/hypersec-io/hs-pylib/commit/881fd2d8858fb423b3c715c8037156cc8833e859))
* CI test patch bump 20251017-121848 ([00bb60a](https://github.com/hypersec-io/hs-pylib/commit/00bb60a81fce014145ac381b909bde1a1828ed04))
* CI test patch bump 20251017-122104 ([6917bdd](https://github.com/hypersec-io/hs-pylib/commit/6917bdd5ca9b49db5eaaf1a5ce8f6268f2390c03))
* CI test patch bump 20251017-124536 ([61ccc8d](https://github.com/hypersec-io/hs-pylib/commit/61ccc8dec6d1b4713080c8f36afcef76bea55ce9))
* CI test patch bump 20251017-124613 ([a165022](https://github.com/hypersec-io/hs-pylib/commit/a1650229e9d869a6947cfede0715ca1cde784285))
* CI test patch bump 20251017-124644 ([a03ef23](https://github.com/hypersec-io/hs-pylib/commit/a03ef23cfc59896b5ca825f756a9ccb355885b5f))
* CI test patch bump 20251017-124723 ([5270963](https://github.com/hypersec-io/hs-pylib/commit/52709630e10e11db1093a81ec6c18110c2dc303c))
* CI test patch bump 20251017-124759 ([1efad52](https://github.com/hypersec-io/hs-pylib/commit/1efad5203fab640c7e2188caed495a63754f3326))
* CI test patch bump 20251017-124841 ([ab0825e](https://github.com/hypersec-io/hs-pylib/commit/ab0825e236e97d0615ed9faf8c6246b8c60b2571))
* clean all build artifacts before building to prevent duplicate versions ([ced0ac7](https://github.com/hypersec-io/hs-pylib/commit/ced0ac73060ecc84e95cbf3a130ae5db846f107c))
* clean ci.yaml and set fail_fast: true as default ([8b5b671](https://github.com/hypersec-io/hs-pylib/commit/8b5b6716534c5d5106253323be57ad8b267e1dfc))
* clean up logger API and fix test imports ([b694c51](https://github.com/hypersec-io/hs-pylib/commit/b694c5178fffa5a85bcc68016367920cd21ed816))
* clean up test infrastructure and timeout.py ([d5c6513](https://github.com/hypersec-io/hs-pylib/commit/d5c6513de365a100c9226234971dabd603166d18))
* code formatting and update hyperci submodule ([36da1ff](https://github.com/hypersec-io/hs-pylib/commit/36da1ff255f3703fc8b344826cf682d62f331b84))
* complete hyperlib to hs-pylib rename across entire codebase ([f95e46a](https://github.com/hypersec-io/hs-pylib/commit/f95e46ac7c38f9856b5c74aa76acf6465a46e011))
* complete Phase 6 testing and validation (all 6 phases done!) ([30d06dd](https://github.com/hypersec-io/hs-pylib/commit/30d06dda464d6ecaf9a4c86b2168d4d1507e4478))
* complete semantic-release VERSION sync - add tomli-w and fix regex ([826b807](https://github.com/hypersec-io/hs-pylib/commit/826b8075807dc39cda427c2394930f8954659f60))
* complete uv/pip JFrog integration with persistent .env configuration ([0028060](https://github.com/hypersec-io/hs-pylib/commit/0028060e1bb27564ecc8c619578729e383b27024))
* complete VERSION sync and env var standardization milestone ([038ca8c](https://github.com/hypersec-io/hs-pylib/commit/038ca8ca84330916c2a2ad12c83f715fbf22670c))
* comprehensive documentation restructure and application framework updates ([e6d2439](https://github.com/hypersec-io/hs-pylib/commit/e6d243934d05ce1eeb3c88181b7549f082424b45))
* configure JFrog publishing via GitHub Actions only ([1cef791](https://github.com/hypersec-io/hs-pylib/commit/1cef7910cc55982154d6f8b22f7a442d962e46c8))
* configure Minikube Docker to use Artifactory (conditional on .env) ([8e3ba36](https://github.com/hypersec-io/hs-pylib/commit/8e3ba366298131ee32869be87bd915f9a7fefc8a))
* configure Solarized colors for all log levels ([2a0d0ac](https://github.com/hypersec-io/hs-pylib/commit/2a0d0ac6a8aea2909b5e684ca961e455065ee586)), closes [#859900](https://github.com/hypersec-io/hs-pylib/issues/859900) [#2aa198](https://github.com/hypersec-io/hs-pylib/issues/2aa198) [#586e75](https://github.com/hypersec-io/hs-pylib/issues/586e75) [#268bd2](https://github.com/hypersec-io/hs-pylib/issues/268bd2) [#859900](https://github.com/hypersec-io/hs-pylib/issues/859900) [#b58900](https://github.com/hypersec-io/hs-pylib/issues/b58900) [#cb4b16](https://github.com/hypersec-io/hs-pylib/issues/cb4b16) [#dc322f](https://github.com/hypersec-io/hs-pylib/issues/dc322f)
* consolidate and document subprocess usage (Phase 3 pragmatic approach) ([ff8a697](https://github.com/hypersec-io/hs-pylib/commit/ff8a697f566057fc99168aa24a71321aa5b18f06))
* consolidate hyperlib test logs to /tests/logs/pytest/ ([8df9c91](https://github.com/hypersec-io/hs-pylib/commit/8df9c91258048f0e0d18034561d3d0e3cba12185))
* convert all bootstrap checks from bash to Python (Phase 4 complete) ([b1b3660](https://github.com/hypersec-io/hs-pylib/commit/b1b366033e603a34cec505266d7b43072ee0e7dc))
* convert all estimates to hours format with powers of 2 scaling ([f6b80ee](https://github.com/hypersec-io/hs-pylib/commit/f6b80ee4b4407723d7672ae13d2a3aa955f97231))
* correct bootstrap syntax in install.sh (install not --install) ([63e6764](https://github.com/hypersec-io/hs-pylib/commit/63e67644f8f0043157f72c10856e12c1c21d1fb2))
* correct ci-publish.yml syntax errors from merge ([882c30d](https://github.com/hypersec-io/hs-pylib/commit/882c30d42f1a0f119654185109bb4e2ce8e968a1))
* correct ci.yaml path in GitHub Actions workflow ([ceed452](https://github.com/hypersec-io/hs-pylib/commit/ceed4523e1bdbc1258034f4c7d2d902ec9ad5f62))
* correct decorator and CLI framework references in application docstrings ([be851a3](https://github.com/hypersec-io/hs-pylib/commit/be851a31b399676e90def6e0feee5ecb0551027e))
* correct GitHub Actions workflow syntax and language specification ([1bc3bee](https://github.com/hypersec-io/hs-pylib/commit/1bc3beee808a76cefda109735f4f8e103fe55862))
* correct GitHub Actions workflow trigger (on: not true:) ([21c1256](https://github.com/hypersec-io/hs-pylib/commit/21c12566d70b4f4083e4841aff91367860b474f8))
* correct HealthCheckMixin initialization order ([bbd8ae4](https://github.com/hypersec-io/hs-pylib/commit/bbd8ae42131a024620c5916e93bef843f5c6b57a))
* correct Minikube status check (JSON flag broken) ([b3a991e](https://github.com/hypersec-io/hs-pylib/commit/b3a991ecf4eeb90b28fb032a1d87f0d9dad13595))
* correct nosec comment placement (syntax error) ([6679d6f](https://github.com/hypersec-io/hs-pylib/commit/6679d6f7503fefe573ac0ca67c91217047450cd5))
* correct pyright configuration syntax ([0fe54c1](https://github.com/hypersec-io/hs-pylib/commit/0fe54c11204a5ab31ecd05093c75896a286cbe7d))
* correct version to 2.9.1 (rename was minor change, not breaking) ([1706874](https://github.com/hypersec-io/hs-pylib/commit/17068744e18ca5c4bfe1e199d73e79717bd228ea))
* create .env in project root (not ci-local/) ([03370a9](https://github.com/hypersec-io/hs-pylib/commit/03370a955f95437ebb4d9ef8ea459d101c7d6aa8))
* create patch commit in ci-local/ not .tmp/ ([f79f9a5](https://github.com/hypersec-io/hs-pylib/commit/f79f9a5f5754a46e508c58a1d09e7ca66bd0b59d))
* create pip.conf in .venv-ci for proper venv configuration ([61eef71](https://github.com/hypersec-io/hs-pylib/commit/61eef7130430627f3b86d3db4b17f4fa8ee911b6))
* create tests-passed marker instead of using CI_FORCE_RELEASE ([d6d2122](https://github.com/hypersec-io/hs-pylib/commit/d6d21223fd1f35dcf12b0c6c1abf06aca940f57f))
* default to BuildJet builds for releases ([896ce3c](https://github.com/hypersec-io/hs-pylib/commit/896ce3c272c966712db0ab3259d1020d3e981910))
* disable MCP in CI configuration (too complex for now) ([d2de9d6](https://github.com/hypersec-io/hs-pylib/commit/d2de9d66547271001cc241b41dd94cc5fc862e63))
* disable Nuitka builds for hyperlib (source-only library package) ([bb46baa](https://github.com/hypersec-io/hs-pylib/commit/bb46baaada3f2c8f0c8f54ba0e62cc2d1a57d00a))
* eliminate double-commit in semantic-release, let it handle VERSION completely ([bed9bef](https://github.com/hypersec-io/hs-pylib/commit/bed9bef47f8f4af3bb50b78d59d93b2cdf2d85ee))
* enable debug logging for all hyperlib tests ([c0cd980](https://github.com/hypersec-io/hs-pylib/commit/c0cd9802bce951e164124705f4fdc6a6f9445604))
* enforce tests must pass before semantic-release ([bbf11c8](https://github.com/hypersec-io/hs-pylib/commit/bbf11c8eb32aa70a808ad81bcd2e60a02845a9b1))
* enforce uv-only usage in .venv while allowing pip in ci/.venv ([7de2344](https://github.com/hypersec-io/hs-pylib/commit/7de2344d5b0ca2ac484c3728baee8726c4f0ef0e))
* exclude ci/ tests from parent project test runs ([33347a7](https://github.com/hypersec-io/hs-pylib/commit/33347a7751ce56357cc185d002ebc46fa6736ed2))
* explicitly specify Python 3.12 for bootstrap ([6f547a0](https://github.com/hypersec-io/hs-pylib/commit/6f547a0f507193f25913a747da2beca9b003a298))
* final cleanup - remove all JF_ references and add test cleanup ([b82460c](https://github.com/hypersec-io/hs-pylib/commit/b82460c4d4d025f5586f07ecaa74652e7d159a36))
* final Nuitka + BuildJet verification 20251017-134900 ([d800059](https://github.com/hypersec-io/hs-pylib/commit/d8000590a35a28100d0f227b2d241984fd0244c8))
* finalize CI and AI configuration (exclude credentials) ([0d62ec7](https://github.com/hypersec-io/hs-pylib/commit/0d62ec7136c367cfeef073ef2867f75907b98f88))
* force uv to use Python 3.12 via UV_PYTHON env var ([c5a7b68](https://github.com/hypersec-io/hs-pylib/commit/c5a7b6844d4f753b4ee1ef8d11fbf9f98914bcf4))
* format code with ruff ([8684e23](https://github.com/hypersec-io/hs-pylib/commit/8684e238d60496438d1173895e491672f22f5982))
* generalizepermissions for all CI commands and tests ([47215ba](https://github.com/hypersec-io/hs-pylib/commit/47215bae532d7781695be15539d9c7dc5b1df791))
* handle missing README.md gracefully in setup.py + update CI ([db4aa08](https://github.com/hypersec-io/hs-pylib/commit/db4aa08444fe0143f2cba08bc7dee5d011017ef7))
* handle pytest.skip exception in test runner ([f7cb8fa](https://github.com/hypersec-io/hs-pylib/commit/f7cb8fa8bb579c8bf7873670d72c89bf7c602549))
* implement CAG/RAG hybrid strategy for standards loading ([6975cee](https://github.com/hypersec-io/hs-pylib/commit/6975cee9be5ff77e79d81808e973caa8f87f6f9f))
* implement dual pre-sync strategy for VERSION file corruption prevention ([a03ff5e](https://github.com/hypersec-io/hs-pylib/commit/a03ff5e1e5818f74935f573fb1f0cb5e84b842f6))
* implement multi-layer venv protection strategy with shared CI utilities ([f39b104](https://github.com/hypersec-io/hs-pylib/commit/f39b104ac35c53f7a82e90166b6b59d887b95703))
* implement persistent UV/PIP index URLs and add .pip/ to gitignore ([c44ad68](https://github.com/hypersec-io/hs-pylib/commit/c44ad68177c9d6d04ca45aba72bbae7f16feaa6d))
* implement Phase 1 container-native patterns foundation ([6e47d64](https://github.com/hypersec-io/hs-pylib/commit/6e47d647d57771bab9eba41bed569913afeb7412))
* implement Phase 3 - enhanced HealthCheckMixin ([e078f9b](https://github.com/hypersec-io/hs-pylib/commit/e078f9bcf0981b5df19ed3566f70b5c0491704d8))
* implement proper MERGE behavior for standards files ([0e626a6](https://github.com/hypersec-io/hs-pylib/commit/0e626a62f77403675429755390358d016019f8f6))
* improve application test coverage with proper dependency detection ([7af3c0b](https://github.com/hypersec-io/hs-pylib/commit/7af3c0b92ae2ce00c3ffa361e538a6f050ac5bb7))
* improve README description to accurately reflect current features ([0dea473](https://github.com/hypersec-io/hs-pylib/commit/0dea47341d53578ed8f80770924c09bd5251a016))
* increase Helm timeout 60s→120s and fix Python f-string syntax ([f314a9a](https://github.com/hypersec-io/hs-pylib/commit/f314a9ac9d6478ec1bfa5532d83260984420975a))
* install twine in workflow (workaround BUG-CI-002) ([bb49af3](https://github.com/hypersec-io/hs-pylib/commit/bb49af3a23e428fad0995e45a968d44b8e06b361))
* install.sh should pass through arguments to bootstrap ([8e13dc5](https://github.com/hypersec-io/hs-pylib/commit/8e13dc5efd5ed161c10b884a6fffb1b516a92f9d))
* load .env file in pytest conftest for test credentials ([41da550](https://github.com/hypersec-io/hs-pylib/commit/41da5508dd0905339298c2a98c96a5fa1ce97c2f))
* make CI completely generic and portable to any Python project ([3177f54](https://github.com/hypersec-io/hs-pylib/commit/3177f544a2bad272ffcc448496ffd4e8d465e089))
* make ENV_PREFIX configurable via HYPERLIB_ENV_PREFIX ([6d9b763](https://github.com/hypersec-io/hs-pylib/commit/6d9b7632ce5f4d415368e0870a979cc82f923333))
* make GitHub Actions workflows manual-only, triggered by CI publish ([98ba4e1](https://github.com/hypersec-io/hs-pylib/commit/98ba4e1e2dfb6e4a43d9a81e9ee32506d1c0190b))
* make JFrog and hyperlib optional dependencies in CI ([6c552a5](https://github.com/hypersec-io/hs-pylib/commit/6c552a5485f5233c75524035f5cdc7ac73dbf2a7))
* map GitHub ARTIFACTORY secrets to JF_USER/JF_PASSWORD for bootstrap ([07ac86b](https://github.com/hypersec-io/hs-pylib/commit/07ac86b729882d6fa705c1e317a430cec8e08148))
* merge container-native patterns branch ([6d00a8f](https://github.com/hypersec-io/hs-pylib/commit/6d00a8f57bfa9717b4880cf4429169ff7bd28359))
* merge DFE-524 branch (ci workflow paths) ([a4f33cc](https://github.com/hypersec-io/hs-pylib/commit/a4f33ccf6233e9161c6946d9dd35aebacd877cc4))
* migrate to HyperCI modular architecture (DFE-523) ([4144c06](https://github.com/hypersec-io/hs-pylib/commit/4144c062b1645011195cd036c0a0ec9953d98344))
* migrate to separate ci and ai submodules ([1383870](https://github.com/hypersec-io/hs-pylib/commit/138387090031953b66c363f69db444b1c209c7cf))
* migrate to unified .venv environment (ONE .venv) ([5c3ed41](https://github.com/hypersec-io/hs-pylib/commit/5c3ed41ead202c28ac6c1355c04c16123a685bf7))
* minimal ci.yaml (remove all defaults including nuitka.enabled) ([313e586](https://github.com/hypersec-io/hs-pylib/commit/313e58632584ff991a557429d0ae4f4f03843198))
* modernize type hints to Python 3.10+ syntax ([71de984](https://github.com/hypersec-io/hs-pylib/commit/71de98465c1d970d7b155419c9f8b54d6087b000))
* move build_type to python section (applies to all builds) ([f68ddff](https://github.com/hypersec-io/hs-pylib/commit/f68ddffc9da5a04ee2da0f9f759e7e9575556de6))
* move Docker Hub credentials to root .env.sample (not ci-local) ([8db5d98](https://github.com/hypersec-io/hs-pylib/commit/8db5d9887092de76def7f0723cd39cf7a4f2c2ae))
* move Helm/Minikube availability checks to runtime (not decorator) ([af41d1c](https://github.com/hypersec-io/hs-pylib/commit/af41d1c8128fe87d0788c73644bbaaa50ec0f14d))
* move language-agnostic CI checks to common/ci.d/ ([ca16b63](https://github.com/hypersec-io/hs-pylib/commit/ca16b632ff0099f30936454ca14ae328cc1cec44))
* move tests to ci-local/tests and update ci submodule ([63eeee7](https://github.com/hypersec-io/hs-pylib/commit/63eeee7257f25fa1236fc976a6d942c213807ae3))
* move write-version.py to CI submodule tools directory ([6ffb23d](https://github.com/hypersec-io/hs-pylib/commit/6ffb23d132552e2dbb2a4104c1e8463f6eb68db5))
* move write-version.py to ci-local directory ([5b0c6e7](https://github.com/hypersec-io/hs-pylib/commit/5b0c6e78a76ea80ab845238c69af4afdf0b50231))
* only trigger Nuitka workflow on version tags ([7afb6af](https://github.com/hypersec-io/hs-pylib/commit/7afb6afeb4868e33d9942eedfc3d8ab50f0d9f3e))
* prepend Python 3.12 to PATH for bootstrap ([1fbbeda](https://github.com/hypersec-io/hs-pylib/commit/1fbbeda4d8c585411e11f9765f36c70a17b36195))
* private submodule access and add force_version bypass ([1620b57](https://github.com/hypersec-io/hs-pylib/commit/1620b5779953eac551aff5e6466037b1af424fa3))
* publish Nuitka wheels directly (don't rebuild) ([1b99ec1](https://github.com/hypersec-io/hs-pylib/commit/1b99ec1dfbca700f3f28c1c30230e4b69aab60be))
* Python f-string syntax error in Helm test fixture ([12f998e](https://github.com/hypersec-io/hs-pylib/commit/12f998e19261be9b82ae1dddc56ad896c10046dc))
* re-enable BuildJet after GitHub App reinstall ([04bcc7d](https://github.com/hypersec-io/hs-pylib/commit/04bcc7d2fca105b8b4d6186ba0dd043a9c75dbec))
* reduce excessive emoji use (CHARS-POLICY compliance) ([d48a7a9](https://github.com/hypersec-io/hs-pylib/commit/d48a7a949512d105989cac27f7d6d92d0bc86213))
* refine AI attribution detection to avoid false positives ([de7d61a](https://github.com/hypersec-io/hs-pylib/commit/de7d61ab6d2ac67e6b4702935a6c2afedb8e1d20))
* register shutdown handlers with FastAPI event system ([dee2ef1](https://github.com/hypersec-io/hs-pylib/commit/dee2ef19641c599b074ae64be5e04e0830855ddb))
* remediate security scanning alerts ([b4f9ede](https://github.com/hypersec-io/hs-pylib/commit/b4f9ede3c82824c78931f5e58751525353c8848e))
* remove --skip-existing flag (JFrog doesn't support it, uses overwrites) ([446288a](https://github.com/hypersec-io/hs-pylib/commit/446288afcb7b98c0bc5c59f73e8bd43da9fbc615))
* remove --wait from remaining Helm tests (prometheus + API) ([a38d6be](https://github.com/hypersec-io/hs-pylib/commit/a38d6beb14a1a7fce192dddf0898b50e46b6c78e))
* remove [@main](https://github.com/main) refs from local workflow paths ([e4e2a80](https://github.com/hypersec-io/hs-pylib/commit/e4e2a80396d2dbd248d84fed831cbf5a70e2015d))
* remove [skip ci] from release commits to enable auto-publish ([5f166c8](https://github.com/hypersec-io/hs-pylib/commit/5f166c8fb4b858ab43f5cf8bed9e55469e67f811))
* remove all hyperlib dependencies from CI, use ci_lib.logger everywhere ([af1c0e8](https://github.com/hypersec-io/hs-pylib/commit/af1c0e855df585ebfc82364c4a6bcdfb4c934705))
* remove broken git -C pattern from settings.json and update ci submodule ([2038241](https://github.com/hypersec-io/hs-pylib/commit/203824187d54e143a83ce60dfaa4b286cc916925))
* remove colors and emojis from CI logger, fix bootstrap get_logger reference ([01ea941](https://github.com/hypersec-io/hs-pylib/commit/01ea9410f2c0f8deada588fbeb65c311d58f66ab))
* remove configure_minikube_registry timeout (use pre-pulled images) ([490b26a](https://github.com/hypersec-io/hs-pylib/commit/490b26aef02db6a4bb041e7bc37ff1db7b1f9735))
* remove DEREK.md references from STATE.md ([9ffb4c6](https://github.com/hypersec-io/hs-pylib/commit/9ffb4c6f7269c6140fc3d06dc9886e25664a2889))
* remove double commas and apply Black formatting ([f990c2d](https://github.com/hypersec-io/hs-pylib/commit/f990c2d0797d381115ead2c4d4560fce121153a9))
* remove duplicate pytest markers in pyproject.toml ([8cdf0ae](https://github.com/hypersec-io/hs-pylib/commit/8cdf0ae84956bee1af1b07cb0409a2a8fba3c3e1))
* remove git config personalization from /start command and update ci submodule ([590f083](https://github.com/hypersec-io/hs-pylib/commit/590f083e5c9ed43d21cdf9699951a333e9c5762a))
* remove GitHub plugin from semantic-release for local runs ([b378192](https://github.com/hypersec-io/hs-pylib/commit/b37819291025a24876e8dc66329683a9759a48b1))
* remove health endpoint test, fix oneshot error type, fix Helm template syntax ([158d5dc](https://github.com/hypersec-io/hs-pylib/commit/158d5dc7fb8222b3c7f5a1ca3dccfc9cffe31987))
* remove Helm --wait for pods with restartPolicy: Never ([6339457](https://github.com/hypersec-io/hs-pylib/commit/6339457946cb68c8f4f5dca4ef98b9e6e649e04b))
* remove invalid [tool.uv] section from ci-local/pyproject.toml ([04ffdca](https://github.com/hypersec-io/hs-pylib/commit/04ffdca7c06cb45f79fa912b145f96bac18a7df7))
* remove leftover nosec comments (no longer needed) ([1ab544a](https://github.com/hypersec-io/hs-pylib/commit/1ab544ad2f7cfbc0ead1eba4ce77cd06eb61b26f))
* remove Minikube auto-start logic (KISS) ([0ca40d0](https://github.com/hypersec-io/hs-pylib/commit/0ca40d08218c6c7656ef02fb9daf8fe9bb559bde))
* remove non-existent --python-version flag from workflow ([61e7b3e](https://github.com/hypersec-io/hs-pylib/commit/61e7b3e55bed7a8ae34aa3f971543af96eb3210d))
* remove non-existent sampling module from import test ([09ebd9f](https://github.com/hypersec-io/hs-pylib/commit/09ebd9f8e79e8824d24d843fe93f86e4c2686b25))
* remove obsolete ci/migrate directory ([8b3cf17](https://github.com/hypersec-io/hs-pylib/commit/8b3cf170b64acb8e2d242a5a78f62a1ca686712f))
* remove RUN_E2E gating from e2e tests ([c7e9a80](https://github.com/hypersec-io/hs-pylib/commit/c7e9a8054480d9097623d0006c9e855bf36cef15))
* remove run-tests and fix bootstrap check scripts install action ([209352a](https://github.com/hypersec-io/hs-pylib/commit/209352a5a34ab5306796e381c93af618391d9b77))
* remove temporary CI refactoring documentation files ([ed7faf0](https://github.com/hypersec-io/hs-pylib/commit/ed7faf0c41c55a24cc97b46e15dd3dfd3b5a6aff))
* remove trailing whitespace in cache.py docstring [skip ci] ([920c3b6](https://github.com/hypersec-io/hs-pylib/commit/920c3b6710276b147ecaada1c7ed3e3e953b71ee))
* remove unapproved emojis per CHARS-POLICY.md ([2bf46a8](https://github.com/hypersec-io/hs-pylib/commit/2bf46a8b6f5b32098cd9253900d9611bec9890de))
* remove unused database dependencies and update STATE.md ([be2f085](https://github.com/hypersec-io/hs-pylib/commit/be2f08544db02794c7335c1950317e0aa06dcd4d))
* remove unused imports (ruff F401 compliance) ([3b54600](https://github.com/hypersec-io/hs-pylib/commit/3b546006401ed9af7962bf002c3bdec72f650347))
* remove version badge from README (versions in CHANGELOG only) ([1726ddd](https://github.com/hypersec-io/hs-pylib/commit/1726ddd30e15063f8587486160af4f9b9ed9f24d))
* rename check_docker_hub_rate_limit to check_container_registry_access ([917c3e4](https://github.com/hypersec-io/hs-pylib/commit/917c3e412d20017eac38f86f4f3d0fc6a4d0b5e8))
* rename package from hyperlib to hs-pylib for PyPI collision avoidance ([ae7c27b](https://github.com/hypersec-io/hs-pylib/commit/ae7c27b59a60d7ee83765d550a8f206fc7519d95))
* rename release.yml to publish.yml for consistency ([9dcf99b](https://github.com/hypersec-io/hs-pylib/commit/9dcf99bc66424e3c9cf348f85ba14b3e5aecaa68))
* replace hardcoded /tmp with tempfile.gettempdir() (security fix) ([faec7d7](https://github.com/hypersec-io/hs-pylib/commit/faec7d78f3e5d0ed0d585de73a7347fb218fe8b7))
* replace Node.js semantic-release with Python version and remove ci-actions ([b9a2098](https://github.com/hypersec-io/hs-pylib/commit/b9a20987ccc897590d7f69ee2b1551df5f3ebf65))
* replace wget with python for metrics endpoint test ([fc6bbbd](https://github.com/hypersec-io/hs-pylib/commit/fc6bbbd84c1a86a8c565d1c06cb55c33c6a855af))
* resolve all Medium and Low severity security issues ([c0e7fd9](https://github.com/hypersec-io/hs-pylib/commit/c0e7fd9adea833164099f37535eea1540cb44b84))
* resolve remaining ruff errors (SIM102, SIM117) ([71527e8](https://github.com/hypersec-io/hs-pylib/commit/71527e891617fe8c14c45a1a43e37c8f65db3a53))
* resolve ruff linting errors (UP035, ARG004, SIM103) ([ce7e0c9](https://github.com/hypersec-io/hs-pylib/commit/ce7e0c91f38d6bfac1e030b53cc9570cfc426bca))
* restore corrupted GitHub Actions workflow ([3ff6539](https://github.com/hypersec-io/hs-pylib/commit/3ff6539bcb1e417804c65baf74c960333d127a74))
* restructure CI into language-agnostic (common) and language-specific (python) directories ([ddb6d7c](https://github.com/hypersec-io/hs-pylib/commit/ddb6d7cb97c57b4fe03f36c4dc3f6b51f34d3a13))
* restructure CI to /ci directory with full self-containment ([6e9d487](https://github.com/hypersec-io/hs-pylib/commit/6e9d4870ef5c72cee5bc50edb0d9660a3277f5a2))
* revert incorrect health endpoint path changes (should be /health and /ready) ([d80e2f4](https://github.com/hypersec-io/hs-pylib/commit/d80e2f4ac0743d3fad3a686aae15ee2b32e3003e))
* revert to ubuntu-latest (BuildJet access issue) ([9eb434b](https://github.com/hypersec-io/hs-pylib/commit/9eb434b63fde5adf5baff59e1909d5c2eea9598a))
* ruff linting - combine nested if statements in health mixin ([47e9a46](https://github.com/hypersec-io/hs-pylib/commit/47e9a4641316e43523c5ca195d2815aa428eb62a))
* set CI=true in verification test and clean test files ([c54fd14](https://github.com/hypersec-io/hs-pylib/commit/c54fd14d1d1d32f109d2c32b06c30149f607593b))
* simplify bootstrap to be self-contained without hyperlib dependencies ([3966d76](https://github.com/hypersec-io/hs-pylib/commit/3966d76b032df69497e1d39c6ef2c3ea2fcc9115))
* simplify JFrog package verification using curl ([2cb966b](https://github.com/hypersec-io/hs-pylib/commit/2cb966b5e63be321ae9affcc919f7b6b0d6af406))
* simplify semantic-release to use Python CLI (53% code reduction) ([8f19daa](https://github.com/hypersec-io/hs-pylib/commit/8f19daa0515500697c44758c2096f897e3ed8926))
* skip branch checks in GitHub Actions publish (detached HEAD) ([31b10a2](https://github.com/hypersec-io/hs-pylib/commit/31b10a28f79fc6fd7f669aac38d17e28cb4f6eaf))
* sort imports in mcp.py (isort) ([68a5982](https://github.com/hypersec-io/hs-pylib/commit/68a598229d889f88764b2577bddba3d6472c3785))
* standardize all test fixtures to _N.txt format, fix Docker build context issues ([76f1539](https://github.com/hypersec-io/hs-pylib/commit/76f1539d0a6f1789ff4330c8d6bbfd047522db9b))
* standardize on pyright (remove mypy config) ([7d9c83f](https://github.com/hypersec-io/hs-pylib/commit/7d9c83f5154311862dc9c293fe247f5f09c101d3))
* support nuitka-only releases via config and --nuitka-only flag ([d379c03](https://github.com/hypersec-io/hs-pylib/commit/d379c03bee325a7897d66f61615463dcc9e8721d))
* suppress linter warnings for unused params and conditional imports ([b15fcfa](https://github.com/hypersec-io/hs-pylib/commit/b15fcfaea1b8acaad0d4fe5c8ef00e77578f6cac))
* sync VERSION file with semantic-release ([d1786ae](https://github.com/hypersec-io/hs-pylib/commit/d1786aed2ce1b8e458ae47cc4b124859a29cd508))
* sync version to v2.10.5 and update semantic-release config ([4451ae4](https://github.com/hypersec-io/hs-pylib/commit/4451ae483ad47b4df3c0ec711b5d9b80d172363e))
* test after ci.yaml path fix 20251017-134121 ([a060669](https://github.com/hypersec-io/hs-pylib/commit/a060669d21369f07cb78ad6ccc8a5f91afb4234c))
* tests required false by default (new projects have no tests) ([603be7d](https://github.com/hypersec-io/hs-pylib/commit/603be7d39cb1d5c8e900afb2769acf89e7909a5c))
* trigger semantic-release for e2e testing (DFE-524) ([fd02c17](https://github.com/hypersec-io/hs-pylib/commit/fd02c17c3fe7756c4a76b2255feb06fe86f7e5ee))
* untrack settings.local.json and remove obsolete gitignore rule ([6cfba5b](https://github.com/hypersec-io/hs-pylib/commit/6cfba5b158e828ad557be7ad2a1621fd927999ec))
* update all Python 3.11 references to 3.12 ([dcf74cb](https://github.com/hypersec-io/hs-pylib/commit/dcf74cbbe14bd26dde8ada2d2903695f7477250c))
* update badges with static version badge (no GitHub API) ([0e06946](https://github.com/hypersec-io/hs-pylib/commit/0e069469c838c12bb158f75129485aab78440a94))
* update bootstrap command (install not --install) ([bd861c3](https://github.com/hypersec-io/hs-pylib/commit/bd861c32b60f3db63f7f073bf44b99f542d553e9))
* update ci and fix dynaconf test ([4f02597](https://github.com/hypersec-io/hs-pylib/commit/4f0259791a665125fdc241bdb49293e4b775d393))
* update CI and regenerate publish workflow (DFE-539) ([4b25e01](https://github.com/hypersec-io/hs-pylib/commit/4b25e019db7cf9fd045e44e65dc317f269728fff))
* update ci submodule (.env location documentation fixes) ([02a8204](https://github.com/hypersec-io/hs-pylib/commit/02a820437ecebe9a56fed8aa22abbda064391872))
* update ci submodule (add UV_EXTRA_INDEX_URL for PyPI fallback) ([b6a37cb](https://github.com/hypersec-io/hs-pylib/commit/b6a37cbe126db18108541682c6ff26717367cacf))
* update ci submodule (CI-LOCAL.md replaced with symlinks) ([9ca239b](https://github.com/hypersec-io/hs-pylib/commit/9ca239bde017f258a57db857f81a79644b842fd9))
* update ci submodule (ENV moved to .bashrc) ([46bdddf](https://github.com/hypersec-io/hs-pylib/commit/46bdddff7a15ab828383411e629c11819d69a6ac))
* update ci submodule (colon syntax for all permissions, remove settings.local.json) ([a126050](https://github.com/hypersec-io/hs-pylib/commit/a12605094e3a596e75e7f99a53e2740751d6dec4))
* update ci submodule (complete pyproject.toml for new projects) ([0d771e8](https://github.com/hypersec-io/hs-pylib/commit/0d771e80b052ad3617226f25a2f01a03d13177f8))
* update ci submodule (comprehensive dual-pattern Bash permissions) ([ffec086](https://github.com/hypersec-io/hs-pylib/commit/ffec086a34635ee6301d0c1870a6952e13df30a1))
* update ci submodule (consolidate test logs) ([bc23522](https://github.com/hypersec-io/hs-pylib/commit/bc23522114e476f4ea5c583a464662f82929d9d9))
* update ci submodule (documentation aligned with hs-ci rename and Python 3.12) ([c71afaa](https://github.com/hypersec-io/hs-pylib/commit/c71afaad8f837414dde9a3a42570d0782300c9b8))
* update ci submodule (explicit TOML merge failure) ([ca9090e](https://github.com/hypersec-io/hs-pylib/commit/ca9090ed26d451851485d443c3e44584b0c08088))
* update ci submodule (fix pyproject.toml merge bug) ([c6b342c](https://github.com/hypersec-io/hs-pylib/commit/c6b342c51a82da60b53c20b460f5e0bc5bf8bfad))
* update ci submodule (fix Python version check bug) ([503c11c](https://github.com/hypersec-io/hs-pylib/commit/503c11c294a2b4cf7a33d569765ca94bb7cc12fe))
* update ci submodule (fix undefined logger in 10-check-git.py) ([05d5ddd](https://github.com/hypersec-io/hs-pylib/commit/05d5ddde41612f233dfe4dbceb413dbc4f997ab3))
* update ci submodule (GitHub Actions workflow fixes) ([5dbf0d1](https://github.com/hypersec-io/hs-pylib/commit/5dbf0d1ea1b7dcf5f42ecfade1f6b5bdcd6345d1))
* update ci submodule (HyperSec default values) ([379d8e3](https://github.com/hypersec-io/hs-pylib/commit/379d8e3d4481ab0a952f2161063f1a1a5050e9e8))
* update ci submodule (interrogate security exception added to defaults) ([b8e4093](https://github.com/hypersec-io/hs-pylib/commit/b8e4093dfd3f0d04ee2e2e596233105f3664a38f))
* update ci submodule (remove git config step from /start) ([be74d32](https://github.com/hypersec-io/hs-pylib/commit/be74d322bd4cfd79670990ca74d692b3b64c8d2c))
* update ci submodule (remove gitci, add semver pinning) ([42172a7](https://github.com/hypersec-io/hs-pylib/commit/42172a79d6b6ea1dc280db16bd27906acb947176))
* update ci submodule (remove merge_env dependency) ([5aa8aa4](https://github.com/hypersec-io/hs-pylib/commit/5aa8aa42e7ba3f9555026f2adacbe5749c25480a))
* update ci submodule (reusable workflows added) ([02d341b](https://github.com/hypersec-io/hs-pylib/commit/02d341bb87de31b1aa53551987053daa78ae695f))
* update ci submodule (reusable workflows in .github/workflows) ([e8ad27c](https://github.com/hypersec-io/hs-pylib/commit/e8ad27cfc6e5da5e8787be2e1ac702eb83fb8d70))
* update ci submodule (use git config for author defaults) ([5fd07e0](https://github.com/hypersec-io/hs-pylib/commit/5fd07e0c8e82f2c5b7aaa14800cad7415be201d2))
* update ci submodule (VSCode venv enforcement) ([f5a4fed](https://github.com/hypersec-io/hs-pylib/commit/f5a4fede0edf2b578f17d9c112fc816780089df6))
* update ci submodule and add git permissions to settings ([9db8bba](https://github.com/hypersec-io/hs-pylib/commit/9db8bba74520bd6bb6adda94fb2ae0989fc31b8e))
* update ci submodule and add missing dynaconf/pyright ([7a175ed](https://github.com/hypersec-io/hs-pylib/commit/7a175eddaf3dcf907054ece8ec02ee0b142ee397))
* update CI submodule and add test job to workflow (DFE-540) ([fa1c5a0](https://github.com/hypersec-io/hs-pylib/commit/fa1c5a079d630771eff2c4c8219a74d19b8b94b1))
* update ci submodule and config for E2E test infrastructure ([6c41cb8](https://github.com/hypersec-io/hs-pylib/commit/6c41cb84578d8bfd3c744105700e13b1245dbc69))
* update ci submodule and regenerate workflow from template ([ad7068b](https://github.com/hypersec-io/hs-pylib/commit/ad7068b288ca9b7586d5aefe99b05432a40118e7))
* update ci submodule to b620738 (CRITICAL get_project_root fix) ([e707e47](https://github.com/hypersec-io/hs-pylib/commit/e707e474acd1751768d3237f37692a18c735fb0e))
* update ci submodule to f780815 (81-publish.py unified build logic) ([f105b18](https://github.com/hypersec-io/hs-pylib/commit/f105b18602e80eff388a45932365ad488efb4002))
* update ci submodule to feat/DFE-523 dev branch ([f795a97](https://github.com/hypersec-io/hs-pylib/commit/f795a97a06c23e92bd628c0f79006962ae8c58dd))
* update CI submodule to latest with uv 0.9.11 support (DFE-524) ([a014818](https://github.com/hypersec-io/hs-pylib/commit/a01481840965eff681e969a5b7402d8f63407f90))
* update ci submodule to main (DFE-523 merged) ([16bae1c](https://github.com/hypersec-io/hs-pylib/commit/16bae1c8b0e5f0c80531ef7df802aa7e6edf3148))
* update ci submodule to v1.1.1 (release automation complete) ([e7307e1](https://github.com/hypersec-io/hs-pylib/commit/e7307e1f1b8d167adc1f253c7638ce57f486dc20))
* update ci submodule to v1.6.13 (Python 3.12 requirement and documentation updates) ([0aa628e](https://github.com/hypersec-io/hs-pylib/commit/0aa628e86d077fbe87b2f1c9b9fcb025597db7e3))
* update ci submodule to v2.0.0 (comprehensive permission improvements) ([1af6cbb](https://github.com/hypersec-io/hs-pylib/commit/1af6cbb23bdfbe0efaf1fe01c6d636e05b732592))
* update ci submodule URL to renamed hs-ci repository ([b5f3909](https://github.com/hypersec-io/hs-pylib/commit/b5f3909cb0828a6cae5afeb16d52db6bf282f342))
* update ci submodule with improved commit-msg hook ([7e3b663](https://github.com/hypersec-io/hs-pylib/commit/7e3b6632542a78ef7c276415a60ce5584b3318d6))
* update CI to hs-ci v1.31.0 with thin workflows ([af92044](https://github.com/hypersec-io/hs-pylib/commit/af92044608f8742488e7af5a28d169372cee552e))
* update CI to hs-ci v1.33.1 ([e159cd8](https://github.com/hypersec-io/hs-pylib/commit/e159cd84e436e7b42fd07443b028abb331b8183a))
* update CI to hs-ci v1.33.2 ([4261e8f](https://github.com/hypersec-io/hs-pylib/commit/4261e8f226ac6dda3dc720eb11201ab31a9b238f))
* update CI with thin publish.yml workflow ([ce0ea07](https://github.com/hypersec-io/hs-pylib/commit/ce0ea072bc7f40a73698031f2eb3e1ed069ea48f))
* update ci-publish workflow for new ci structure ([51333d4](https://github.com/hypersec-io/hs-pylib/commit/51333d4f2f2600585352349aac173f355747b498))
* update Dockerfile fixtures to use pyproject.toml optional extras ([ad3fc81](https://github.com/hypersec-io/hs-pylib/commit/ad3fc81e1410f5a9a781cea68c0ec7f70d859709))
* update E2E and integration tests for Typer CLI and container deployment ([ce4101c](https://github.com/hypersec-io/hs-pylib/commit/ce4101c33c1766e3c282b81ca12894fdaecf8e7a))
* update Nuitka multi-arch workflow for private repos and add active checking ([5580037](https://github.com/hypersec-io/hs-pylib/commit/55800372fe5f04a872ce0d01ca737d4864338a7a))
* update pyproject.toml - Python 3.11+, remove unused deps, add optional extras ([3ad89f2](https://github.com/hypersec-io/hs-pylib/commit/3ad89f289d40c048e79227e6b54c017e91c4765d))
* update pyproject.toml metadata - production status, accurate description and keywords ([be7ca68](https://github.com/hypersec-io/hs-pylib/commit/be7ca688b9c83e9045ee87c05980aedb2484d2df))
* update pyproject.toml to use JFrog virtual repository ([404e447](https://github.com/hypersec-io/hs-pylib/commit/404e44749e0821ffba5bbca5dfae5c322d5c847e))
* update README badges to reflect hs-pylib rename and Python 3.12 ([b07613c](https://github.com/hypersec-io/hs-pylib/commit/b07613c9202f1de4c8a39d1907aa5ac0ed747bf9))
* update semantic-release build command to use ci-local/.venv ([4c9fc4a](https://github.com/hypersec-io/hs-pylib/commit/4c9fc4ad1853fd3aced8423db310a0fb3e7d4866))
* update setup.py package name reference ([0e431ec](https://github.com/hypersec-io/hs-pylib/commit/0e431ec3998584bd1fd381df9607ea8d2fa3461a))
* update STATE.md for new CI architecture (hs-ci v1.19.x) ([7761e71](https://github.com/hypersec-io/hs-pylib/commit/7761e710d0bafe2b8f794a5dc9070abe2292546d))
* update test assertions and make verification test optional ([e61dda5](https://github.com/hypersec-io/hs-pylib/commit/e61dda5cd111247c8e9b9fccb517a4179f00d63c))
* update test to use build_type (not build_profile) ([0d44216](https://github.com/hypersec-io/hs-pylib/commit/0d442168bf23661ed26db02795ae31beb5fc48e1))
* update test_ci.py for ci.yaml at project root (submodule structure) ([cf9ad19](https://github.com/hypersec-io/hs-pylib/commit/cf9ad1940e46e76c58bfcd824f033272026f6abb))
* update tests for module restructuring (52 pre-existing failures) ([6cb7ada](https://github.com/hypersec-io/hs-pylib/commit/6cb7adac3c824fa9465df47b9a2011001ea7f946))
* update to new workflow paths (DFE-523) ([c3c7db9](https://github.com/hypersec-io/hs-pylib/commit/c3c7db96e95d45564c7eb11f2293b73a1bf44b38))
* update to Python 3.12 and remove duplicate pytest markers ([5159c37](https://github.com/hypersec-io/hs-pylib/commit/5159c37f9a0cb2fbbbdfe4d719bd71cb9c8f8514))
* update to Python 3.12 and sync with hs-ci v1.6.13 ([4289a92](https://github.com/hypersec-io/hs-pylib/commit/4289a92b2f4b104e68975feebcd2ea59a5eaa060))
* update TODO to reflect completed CI restructure ([8af162a](https://github.com/hypersec-io/hs-pylib/commit/8af162ae5e84624faee6b085303ecc0b151dbe3e))
* update TODO.md estimates to aggressive AI-assisted timeframes (Linear.app points) ([3d7ab63](https://github.com/hypersec-io/hs-pylib/commit/3d7ab6374c41a55fca007e0c2e594718692670e4))
* update workflow to call publish script directly ([cf8678a](https://github.com/hypersec-io/hs-pylib/commit/cf8678a27c7be8a3f915cd2387ad921fe68085bd))
* update workflows with checkout fix (DFE-539) ([7e434f0](https://github.com/hypersec-io/hs-pylib/commit/7e434f0fdc75dcd58cc9f06914b8898ec445600f))
* use ./ci/run publish in GitHub Actions workflow ([6b0a943](https://github.com/hypersec-io/hs-pylib/commit/6b0a94394fdb29fb941c7de62baecb3ff015b923))
* use BuildJet for ARM64 runners in private repos ([4d5325c](https://github.com/hypersec-io/hs-pylib/commit/4d5325c21e4a9f191ac0a7a9b48cf1420459353a))
* use BuildJet runners for all builds (standard + nuitka) ([aee575d](https://github.com/hypersec-io/hs-pylib/commit/aee575d454141d8e2fa048e4b0e21f4be253de8f))
* use CI_FORCE_RELEASE=1 in verification test ([5170999](https://github.com/hypersec-io/hs-pylib/commit/51709998278f7e56c5c8899d0734194425ffb131))
* use ci-local/ci.yaml in GitHub Actions workflow ([94a182e](https://github.com/hypersec-io/hs-pylib/commit/94a182e7a82d4ec354a6c48a79fbc4aa5dd4802f))
* use default=true for uv.index and clarify both uv/pip work with HyperCI ([0b4dd5b](https://github.com/hypersec-io/hs-pylib/commit/0b4dd5bf5b9e5e3105fe5da3c51e9fb6ecba392c))
* use JFrog virtual repository for all Python package installations ([4f7de72](https://github.com/hypersec-io/hs-pylib/commit/4f7de72670fe9c3bad9302c74b3900eab45fead0))
* use local ci/workflows path (DFE-523) ([af72571](https://github.com/hypersec-io/hs-pylib/commit/af725718d4fdc682fc5dfb24f050b12768555a1e))
* use proper Solarized color codes in logger format ([27045b6](https://github.com/hypersec-io/hs-pylib/commit/27045b656032baa88e59388bad39cb24e3d527fc)), closes [#859900](https://github.com/hypersec-io/hs-pylib/issues/859900) [#2aa198](https://github.com/hypersec-io/hs-pylib/issues/2aa198)
* use Python 3.12 in workflow (hs-pylib requires 3.12+) ([18000b4](https://github.com/hypersec-io/hs-pylib/commit/18000b4390d8123ecca0a9d0d47d86f3d9e9fc9f))
* use release_name for ConfigMap (not test_id) to match Helm template ([8a4f192](https://github.com/hypersec-io/hs-pylib/commit/8a4f1921cb9a2ea552f4f77249782f1ead81b724))
* use remote ci repository paths for reusable workflows ([65a0a6d](https://github.com/hypersec-io/hs-pylib/commit/65a0a6dba6f6d59f738d78c2a042a6981e2f882a))
* VERSION file uses standard plain format (git tag is source of truth) ([d2555b3](https://github.com/hypersec-io/hs-pylib/commit/d2555b357d2b07e59634f4954ac5d1b9b4c5c44f))
* wait for pod Ready before kubectl exec in test_helm_chart_deployment ([9da7b7b](https://github.com/hypersec-io/hs-pylib/commit/9da7b7b074536f0eedd56df0e64fda0fd3690571))


### Code Refactoring

* standardize env vars to ARTIFACTORY_* and improve CI testing ([668661f](https://github.com/hypersec-io/hs-pylib/commit/668661fcede1db10d39371200f7bac5e35fed4b2))


### Features

* add /ci/git tool to project ([9f61a65](https://github.com/hypersec-io/hs-pylib/commit/9f61a656b67d3c2c7e0fee26c2444f184d1ce415))
* add ai: section to ci-local/ci.yaml ([3991064](https://github.com/hypersec-io/hs-pylib/commit/3991064df8fb61ea4c8a8156ab1841fe024c3b75))
* add Application.mcp() for MCP server deployment type ([b3673bd](https://github.com/hypersec-io/hs-pylib/commit/b3673bd0b184a545dae6d54a9601965ccb045b82))
* add automatic sensitive data masking to logger ([2c06e01](https://github.com/hypersec-io/hs-pylib/commit/2c06e01c26fdc0e2cac29de816852a8eb912b2a2))
* add bash command execution policy and update ci submodule ([cc0f794](https://github.com/hypersec-io/hs-pylib/commit/cc0f794b23b540ebcba7e665c298425492865df4))
* add BuildJet configuration option to ci/ci.yaml ([faa9294](https://github.com/hypersec-io/hs-pylib/commit/faa9294daa4c856edf5105a4ed8fb9bcaa99996e))
* add CI_BUMP_PATCH=1 option to control patch commit ([a3777fb](https://github.com/hypersec-io/hs-pylib/commit/a3777fbc5db62f6c194bd6b3b3a147a49e3526e8))
* add settings merge to bootstrap (CI_MERGE) ([ebaafa4](https://github.com/hypersec-io/hs-pylib/commit/ebaafa46af764259161cab44b7fd2cd008330c3e))
* add CLI enhancements for multi-environment configuration ([bd5b40a](https://github.com/hypersec-io/hs-pylib/commit/bd5b40a0dea976bad341469d902b7b770a87bf51))
* add code header standards (REUSE/SPDX compliant) ([6e3e657](https://github.com/hypersec-io/hs-pylib/commit/6e3e657fe71b1afa7c1b9a98e68ddb5fe7206e35))
* add comprehensive config file merge module with 39 passing tests ([f4f53d9](https://github.com/hypersec-io/hs-pylib/commit/f4f53d9bd3cc240af666ab935d84dd00b99ec856))
* add comprehensive JFrog publish and install test ([4ae373a](https://github.com/hypersec-io/hs-pylib/commit/4ae373aafcc04b4cbe785237e57b5d699029d3e5))
* add comprehensive Prometheus metrics module with custom metrics API ([ef01c96](https://github.com/hypersec-io/hs-pylib/commit/ef01c96e8eabf7e285b9fe2a04e701c5f429e230))
* add comprehensive security and quality checks to CI ([fd82dce](https://github.com/hypersec-io/hs-pylib/commit/fd82dceec7c042fb92980f91fc8cc05f52c51a75))
* add container registry throttling detection and Docker auth ([2ac560c](https://github.com/hypersec-io/hs-pylib/commit/2ac560ca7f214f533021f9d1cdfbfaa84ee7d802))
* add CONTAINER_BASE_PATH environment variable override ([43f0b64](https://github.com/hypersec-io/hs-pylib/commit/43f0b64f99e4094ba84dec56e6b5239b5cb5f992))
* add fast test mode to skip slow integration tests ([52ea1af](https://github.com/hypersec-io/hs-pylib/commit/52ea1afd1ac0edec8d915da5b55d8c07f521d311))
* add full publish verification test ([c064479](https://github.com/hypersec-io/hs-pylib/commit/c0644790ad32904905f8f998fa41f63f0622768b))
* add generic container registry auth (Docker + Artifactory precedence) ([ed0a9cc](https://github.com/hypersec-io/hs-pylib/commit/ed0a9cc827c9821fbdb1a062bca81d074743a9ae))
* add GitHub badges to README with automatic CI updates ([8c03174](https://github.com/hypersec-io/hs-pylib/commit/8c0317479980d9d98200c763d9ce4be6ed085ff4))
* add hyperlib-specific ci/ci.yaml and protect from subtree overwrites ([a54cd3d](https://github.com/hypersec-io/hs-pylib/commit/a54cd3d2edcd41b2ff3c690b9ce68f799d14f8d4))
* add hyperlib.application factory pattern ([341ba7a](https://github.com/hypersec-io/hs-pylib/commit/341ba7afa20573d789e99aa2cdc34462a82e2523))
* add idempotent TODO.md creation tosettings merge ([d76f83d](https://github.com/hypersec-io/hs-pylib/commit/d76f83d7e0bcd22190a0ca440811decfe77b0e41))
* add interactive prompt fortier selection ([081bef6](https://github.com/hypersec-io/hs-pylib/commit/081bef6b686489311be74c207e1ee10e4dddbd3f))
* add macOS ARM64 support to unified workflow ([d5dce8e](https://github.com/hypersec-io/hs-pylib/commit/d5dce8e1f79252bb7754144723aaa2ea7e1bbf41))
* add mergedeep library to CI tools ([23cd1c4](https://github.com/hypersec-io/hs-pylib/commit/23cd1c4a77224e01803570ef6ebe8af81cdf910c))
* add metrics backend abstraction for Prometheus and OpenTelemetry ([05b4e5d](https://github.com/hypersec-io/hs-pylib/commit/05b4e5d68e18db4c88e939c19cef6c75571adb6e))
* add missing enterprise features to application module ([18ea4de](https://github.com/hypersec-io/hs-pylib/commit/18ea4de998d2e438ef0ace8e70e45e1fb47d26a1))
* add Node.js/npx requirement check tosettings merge ([56fc1b5](https://github.com/hypersec-io/hs-pylib/commit/56fc1b5ecc0985a89b611cb5268551187c9eacec))
* add Nuitka Commercial detection, compiled wheel builds, and bootstrap restructuring ([d327e16](https://github.com/hypersec-io/hs-pylib/commit/d327e1657dded35068ff51ff523d6305febc032d))
* add Nuitka package mode with auto-detection and prevent JFrog sprawl ([4fb92e7](https://github.com/hypersec-io/hs-pylib/commit/4fb92e74b8f658857e2a03823d7c33896c4e9ef2))
* add opinionated anonymizer with Presidio integration ([a076756](https://github.com/hypersec-io/hs-pylib/commit/a07675639922cfce7c30828b65cfe0e6a664c978))
* add publish verification and update dependencies ([c2b9d43](https://github.com/hypersec-io/hs-pylib/commit/c2b9d43b8d46fcc27161402d43a1fdd24eea9fd3))
* add README.md for package distribution ([c4573da](https://github.com/hypersec-io/hs-pylib/commit/c4573da8274e6888aa4ab3714918069f7f1d42eb))
* add real language detection and TODO.md policy ([63b214f](https://github.com/hypersec-io/hs-pylib/commit/63b214f0be51f574a4b85a96d6d7b38f0b1c21d5))
* add router inclusion and generic middleware support to APIApplication ([3baa925](https://github.com/hypersec-io/hs-pylib/commit/3baa925af06f4e9a4e9dc24cd5ec1a4a0849d9ee))
* add selective test system and update CI ([2a08336](https://github.com/hypersec-io/hs-pylib/commit/2a0833630a295ee0c2912299e5b30960537d9f03))
* add smart auto-configuration to logger with opt-out ([b249cfa](https://github.com/hypersec-io/hs-pylib/commit/b249cfa4d7bc64945042f18dd9271440b20d882e))
* add test validation checklist and update ci submodule ([1a78fff](https://github.com/hypersec-io/hs-pylib/commit/1a78fff2f67032d1c75c64ac53d722a06f1a5b0a))
* add third-party runner support (BuildJet + Cirrus) for cost savings ([5b45685](https://github.com/hypersec-io/hs-pylib/commit/5b45685ddb212abf96ed1b039f2bb5c4ee704d84))
* add tool.uv config to enforce ci-local/.venv ([da85e8b](https://github.com/hypersec-io/hs-pylib/commit/da85e8b51384d2486605417746bc7406b33a96ec))
* add two-tier sensitive data anonymization (Presidio + regex) ([55cb29a](https://github.com/hypersec-io/hs-pylib/commit/55cb29aaf30299c5263ed94e86e862a24e967b17))
* add Typer as mandatory CLI standard for hyperlib ([959cca2](https://github.com/hypersec-io/hs-pylib/commit/959cca2d49a77231f0e9bd86212c5e49c39799f8))
* add unified runtime environment for container and local deployment ([5d109fd](https://github.com/hypersec-io/hs-pylib/commit/5d109fdc6bb9109f58d360ce545474f680b9fde6))
* add version check to prevent duplicate builds and remove schedule triggers ([152b53c](https://github.com/hypersec-io/hs-pylib/commit/152b53ce71d4e03b3f692337b5e5409c7e641ccd))
* add VERSION corruption recovery script (99-fix-version.py) ([7a8a33e](https://github.com/hypersec-io/hs-pylib/commit/7a8a33e66f63b24ce9068dce351469178031e25d))
* add version-exists check to prevent accidental republishing ([10d62c6](https://github.com/hypersec-io/hs-pylib/commit/10d62c6328bbdba98744e0ee761d776eb403df86))
* apply rationalized CI documentation to STATE.md and settings ([f0b313b](https://github.com/hypersec-io/hs-pylib/commit/f0b313bc040ebebf79bd33f25faf83eb5eaf7d73))
* capture Docker and K8s pod logs to /logs directory with timestamps ([77c44db](https://github.com/hypersec-io/hs-pylib/commit/77c44dbcac052f4262119df7ed249e79c6e5059e))
* clean commit without attribution ([34070b9](https://github.com/hypersec-io/hs-pylib/commit/34070b943fe01a60b1170bae33e338cfc6f8aa9c))
* code header and license system complete (REUSE/SPDX) ([51255ee](https://github.com/hypersec-io/hs-pylib/commit/51255ee6a8564748b1ec7adf200a318ae9f7e585))
* complete ci-local/.venv migration ([e8305ca](https://github.com/hypersec-io/hs-pylib/commit/e8305ca23517adc90a48b510e495aa8e3c7edf2a))
* complete setup with standards/ directory and force mode ([c52f5bb](https://github.com/hypersec-io/hs-pylib/commit/c52f5bbfe8273aacf47e67aac068776369dbe52c))
* completesettings merge implementation ([ddb705e](https://github.com/hypersec-io/hs-pylib/commit/ddb705e51dd034e902d737ca3a4df179f7973398))
* complete ENV standardization - clean CI_ prefix standard ([7b373e8](https://github.com/hypersec-io/hs-pylib/commit/7b373e829e5f2f4d754393d66a06ce8d8f999d75))
* complete ENV standardization with CI_ prefix ([bafdf28](https://github.com/hypersec-io/hs-pylib/commit/bafdf28d533f41644f37c6c75700f17617a4974e))
* config consolidation complete - all use ci_lib.py ([b746add](https://github.com/hypersec-io/hs-pylib/commit/b746add40b0cc7fa2c031d0619cd331eaa022382))
* configure Docker Hub imagePullSecrets in Helm test namespaces ([4f39783](https://github.com/hypersec-io/hs-pylib/commit/4f3978351a8fa0e2ec01f747c5af33c04db968ea))
* confirm template substitution works for MCP memory path ([e443c0a](https://github.com/hypersec-io/hs-pylib/commit/e443c0ada155a45c839ef68f0d04b10c6854f6b4))
* container-native application patterns (Phases 1-4) ([baad975](https://github.com/hypersec-io/hs-pylib/commit/baad975bb2e6db41641d8e7dd4588dc0e415f2f2))
* convert hyperci to git submodule for version control ([1ec480b](https://github.com/hypersec-io/hs-pylib/commit/1ec480bb3bde9487aea0935957fa8bbbf5be36c7))
* create /ci/ai tool foundation (Phase 1 start) ([609d37e](https://github.com/hypersec-io/hs-pylib/commit/609d37eccceead046195c36a7f1c36dbfd55424b))
* document hyperci subtree architecture and usage ([0f9eeee](https://github.com/hypersec-io/hs-pylib/commit/0f9eeee97fa90185a6cba590fa157b824b9bc18a))
* enforce .venv-ci for all CI scripts (FAIL HARD) ([9f5050d](https://github.com/hypersec-io/hs-pylib/commit/9f5050d09414bb131fbc97b294312e3c7b9d8c23))
* enforce CHARS-POLICY.md in logger with terminal detection ([84181e6](https://github.com/hypersec-io/hs-pylib/commit/84181e6d681998c3408261fa3bdf93b14b288f51))
* enhance container detection with 7-layer strategy ([6c19eaa](https://github.com/hypersec-io/hs-pylib/commit/6c19eaa14d95cb9a5a0e29f1430d0963c6faf76d)), closes [hi#confidence](https://github.com/hi/issues/confidence)
* implement template substitution for reliable MCP memory path ([2cfbd62](https://github.com/hypersec-io/hs-pylib/commit/2cfbd624e8e347e296be2cdeee1470a13e64e7dc))
* integrate harness.run() into tests for centralized logging ([f83f9a0](https://github.com/hypersec-io/hs-pylib/commit/f83f9a0b2ab64230874a2acf8151d31bb909fb92))
* migrate CLIApplication from Click to Typer (mandatory standard) ([b537325](https://github.com/hypersec-io/hs-pylib/commit/b537325e52d9b5270ecc0500f9da14f81bed9f15))
* move ci_lib to common, add structure validators, document dependencies ([9d4229c](https://github.com/hypersec-io/hs-pylib/commit/9d4229ccfbba623b14144763e84a27705983524c))
* move ci.yaml to project root with auto-creation and comprehensive docs ([a0a2b16](https://github.com/hypersec-io/hs-pylib/commit/a0a2b16870ffd54fd054a736b5096ae02f668683))
* path standardization and Pro default complete ([eb2f401](https://github.com/hypersec-io/hs-pylib/commit/eb2f4017b5d547491ff9ad095cf61fb70ae73222))
* Phase 1 complete - /ci/ai modular tool replaces monolithic script ([d18aa1b](https://github.com/hypersec-io/hs-pylib/commit/d18aa1b4ee69fb7bcb51141ad9335a34ec9957c2))
* Pro Max verified with merge default ([45b6d96](https://github.com/hypersec-io/hs-pylib/commit/45b6d96caec28282ceb1645ec6e0b6a2c6036a9f))
* remove hardcoded values - all config in ci.yaml ([826d303](https://github.com/hypersec-io/hs-pylib/commit/826d3031d766f29d8d68735042a19cb8410bce45))
* restore simplified Nuitka workflow using ci/ scripts directly ([9259671](https://github.com/hypersec-io/hs-pylib/commit/92596711d847479398395d4fe18058710edb7b5f))
* session complete - /ci/ai verified working ([4998a0f](https://github.com/hypersec-io/hs-pylib/commit/4998a0f5f8b7cd5dc94ac58ac724311b2c68fca3))
* simplify GitHub Actions to use ci/ infrastructure directly ([22f157d](https://github.com/hypersec-io/hs-pylib/commit/22f157ddb247c70cde02069c2230dfbcc2d17e07))
* unified CI Publish workflow - ONE workflow for everything ([4d9378e](https://github.com/hypersec-io/hs-pylib/commit/4d9378e4a05d718e154ec8b0b83ddf791592dd77))
* update ci submodule (merge_env implementation) ([ca2b163](https://github.com/hypersec-io/hs-pylib/commit/ca2b163bd27113ac843424c04f66ba8446c63d5d))
* update ci submodule to v1.8.0 (add --python-version flag) ([f9fd6ae](https://github.com/hypersec-io/hs-pylib/commit/f9fd6aec853d9be24076422aa86fc4ee4606b152))
* update ci submodule with version pinning and install script ([b088f79](https://github.com/hypersec-io/hs-pylib/commit/b088f792730cdc2fb9cd7415e006e33bb5334280))
* update ci submodule with VSCode multi-language template split ([1e1352a](https://github.com/hypersec-io/hs-pylib/commit/1e1352a727f2ad61d93b7c59975db7db996911f7))
* update GitHub Actions workflows for submodule pattern ([c06cff7](https://github.com/hypersec-io/hs-pylib/commit/c06cff7d7cbedd422dd316a9ecb8bc2b82aa5a70))
* update hyperci with native uv mode support (uv sync, uv build) ([82b6a8e](https://github.com/hypersec-io/hs-pylib/commit/82b6a8ef588f874f1ff9a6fef396daa84f5f1ac0))
* update memory MCP server to mcp-knowledge-graph ([b469411](https://github.com/hypersec-io/hs-pylib/commit/b469411265a0d3710338c18ded63e957eef7546e))
* update to uv-managed Python (no system Python dependency) ([e9b8375](https://github.com/hypersec-io/hs-pylib/commit/e9b8375cfeb8871a3338b00ff99b116e3dd8f8df))


### Reverts

* remove pushd/popd guidance (doesn't work across Bash subprocesses) ([184e148](https://github.com/hypersec-io/hs-pylib/commit/184e148b847f01b9edce2fbefe69e24185af758f))


### BREAKING CHANGES

* note: Projects using CLIApplication must install Typer:
  pip install hyperlib[cli]

This enforces the hyperlib CLI standard across all applications.
* All CI tools now in ci-local/.venv (not ci/.venv)

Changes:
- Updated ci submodule to dda545b (ci-local/.venv support)
- Added dynaconf to ci-local/pyproject.toml
- Regenerated ci-local/uv.lock with dynaconf
- Updated workflows to use ci-local/.venv
- Rewrote test_ci.py to test REAL ci/ infrastructure
- Updated STATE.md with ci-local/.venv documentation

Benefits:
- ci/ is now 100% READ-ONLY (git submodule best practice)
- All writable state in ci-local/ (venv, configs, credentials)
- Unified configuration with dynaconf (ENV + CLI + file)
- Same scripts work locally and in GitHub Actions

Next: rm -rf ci/.venv && ci/bootstrap --install
* Removed all JF_* environment variable backward compatibility.
Only ARTIFACTORY_* variables are supported now (matching GitHub Actions secrets).

Major changes:
- BuildJet now used for BOTH x64 and ARM64 Linux builds (50% cost savings)
  - Enabled by default via buildjet.enabled: true
  - x64: /bin/bash.004/min (vs GitHub /bin/bash.008/min)
  - ARM64: /bin/bash.004/min (vs GitHub N/A for private repos)

- Cirrus Runners added for macOS builds (95% cost savings)
  - Enabled by default via cirrus.enabled: true
  - macOS: /bin/bash.015/min effective (vs GitHub /bin/bash.16/min)
  - Uses M4 Pro chips with better performance
  - Requires setup: https://cirrus-runners.app/setup/

- Cost comparison with defaults:
  - Linux x64 + ARM64: /bin/bash.056/release (was /bin/bash.084)
  - All platforms: /bin/bash.161/release (was .26)
  - Monthly savings: ~88% for all platforms

- Workflow intelligently falls back to GitHub runners when disabled:
  - BuildJet disabled: Uses GitHub for Linux (2x cost, no ARM64 for private)
  - Cirrus disabled: Uses GitHub for macOS (10x cost)

- Removed migrate_env.py - clean slate with ARTIFACTORY_* variables only
- Updated all bootstrap scripts to use only ARTIFACTORY_* env vars
* Environment variable names have been standardized to match GitHub Actions secrets.
Old JF_* variables are no longer supported. Use ARTIFACTORY_* variables instead.

Changes:
- Replace all JF_* env vars with ARTIFACTORY_* (matches GitHub secrets)
  - JF_USER → ARTIFACTORY_USERNAME
  - JF_PASSWORD → ARTIFACTORY_PASSWORD
  - JF_TOKEN → ARTIFACTORY_TOKEN
  - JF_TOKEN_USER → ARTIFACTORY_TOKEN_USER
  - JF_PYPI_HOST → ARTIFACTORY_PYPI_HOST

- Update bootstrap script to use only ARTIFACTORY_* vars (no backward compat)
- Update .env.sample with new variable names
- Add migrate_env.py utility to help users migrate existing .env files

- Replace tests/ci/test_nuitka_build.py with comprehensive test_ci.py that:
  - Creates virtual project environment for testing
  - Tests complete CI pipeline (bootstrap, build, publish)
  - Waits for JFrog publication before testing installation
  - Tests Nuitka compiled wheels with git import verification
  - Verifies both standard and compiled packages work correctly

- Update documentation in STATE.md for new env var naming
- Add test artifacts to .gitignore

Migration guide:
1. Run: python migrate_env.py
2. Test: ./ci/bootstrap --install
3. Delete backup files once confirmed working
* Complete CI infrastructure reorganization for better isolation

## Changes

### Directory Structure
- Renamed `/scripts` → `/ci` (clearer naming)
- Renamed `scripts/ci` → `ci/run` (more intuitive)
- Moved `.venv-ci` → `ci/.venv` (full self-containment)
- Everything CI-related now lives in `/ci` directory

### New Structure
```
/ci/                 # All CI infrastructure
├── .venv/          # CI virtual environment (was .venv-ci at root)
├── bootstrap       # Creates ci/.venv
├── run             # Main CI runner (was ci)
├── bootstrap.d/    # Bootstrap scripts
├── ci.d/           # CI task scripts
└── ci_lib.py       # Shared CI utilities
```

### pyproject.toml Cleanup (Option A: Pure Python Lists)
- Removed CI tools from `[project.optional-dependencies] dev`
- CI dependencies now exclusively in `ci/bootstrap.d/20-python-tools.py`
- `dev` extras now only contains local development tools (pre-commit, isort)
- Zero pollution of project dependencies with CI infrastructure

### Path Updates
- All scripts updated: `.venv-ci` → `ci/.venv`
- All scripts updated: `scripts/` → `ci/`
- Bootstrap creates `ci/.venv` instead of `.venv-ci`
- CI runner uses `ci/.venv/bin/python` explicitly
- Documentation updated across all .md files

### Benefits
- ✅ True isolation: All CI infrastructure in one directory
- ✅ Portable: Can copy/zip `ci/` and it works standalone
- ✅ Simpler naming: Just `.venv` inside `ci/` (context is clear)
- ✅ Cleaner root: Only `.venv` (dev) at root, not `.venv-ci`
- ✅ Conceptually clear: "Everything in `ci/` is for CI"
- ✅ Better dependency management: CI tools separate from project deps

### Forge Template Benefit
Other projects can adopt this clean, self-contained CI structure.

Tested:
- ./ci/bootstrap (check mode) ✓
- ./ci/run --script 10-branch-name.py check ✓





## [2.10.15](https://github.com/hypersec-io/hs-pylib/compare/v2.10.14...v2.10.15) (2025-11-28)


### Bug Fixes

* update CI to hs-ci v1.33.2 ([85b5380](https://github.com/hypersec-io/hs-pylib/commit/85b5380e966da6c49dae23301808299fb64feba0))

## [2.10.14](https://github.com/hypersec-io/hs-pylib/compare/v2.10.13...v2.10.14) (2025-11-28)


### Bug Fixes

* update CI to hs-ci v1.33.1 ([50049d4](https://github.com/hypersec-io/hs-pylib/commit/50049d4929fed6ba8a1edbad4804797c5b2e93d5))

## [2.10.13](https://github.com/hypersec-io/hs-pylib/compare/v2.10.12...v2.10.13) (2025-11-28)


### Bug Fixes

* update CI with thin publish.yml workflow ([c7b8732](https://github.com/hypersec-io/hs-pylib/commit/c7b873293080947819d8172d681bc5e7588f1213))

## [2.10.12](https://github.com/hypersec-io/hs-pylib/compare/v2.10.11...v2.10.12) (2025-11-28)


### Bug Fixes

* allowlist test_logger_filters.py fake secrets ([342d3c8](https://github.com/hypersec-io/hs-pylib/commit/342d3c8fee2dbf78e5fa341e2128e7ef3af85d40))

## [2.10.11](https://github.com/hypersec-io/hs-pylib/compare/v2.10.10...v2.10.11) (2025-11-28)


### Bug Fixes

* allowlist test fixture fake secrets in gitleaks ([b5c74c6](https://github.com/hypersec-io/hs-pylib/commit/b5c74c6e903eac5b5fe5e902cc4a524475758722))

## [2.10.10](https://github.com/hypersec-io/hs-pylib/compare/v2.10.9...v2.10.10) (2025-11-28)


### Bug Fixes

* add gitleaks allowlist for historical backup files ([4ace591](https://github.com/hypersec-io/hs-pylib/commit/4ace59115ddfb3dfe27cf9cbeddcf78b4d946577))

## [2.10.9](https://github.com/hypersec-io/hs-pylib/compare/v2.10.8...v2.10.9) (2025-11-27)


### Bug Fixes

* update CI to hs-ci v1.31.0 with thin workflows ([e82ae7a](https://github.com/hypersec-io/hs-pylib/commit/e82ae7af3b56e8787521ca49b3f1b0277b496436))

## [2.10.8](https://github.com/hypersec-io/hs-pylib/compare/v2.10.7...v2.10.8) (2025-11-26)


### Bug Fixes

* update STATE.md for new CI architecture (hs-ci v1.19.x) ([4c3fff7](https://github.com/hypersec-io/hs-pylib/commit/4c3fff7eaa5661b638ca189d10a99128f178ae91))

## [2.10.7](https://github.com/hypersec-io/hs-pylib/compare/v2.10.6...v2.10.7) (2025-11-26)


### Bug Fixes

* format code with ruff ([9eff58d](https://github.com/hypersec-io/hs-pylib/commit/9eff58d85d5b987258c99d93d5c78d2242d950c0))

## [2.10.6](https://github.com/hypersec-io/hs-pylib/compare/v2.10.5...v2.10.6) (2025-11-25)


### Bug Fixes

* sync version to v2.10.5 and update semantic-release config ([cc5aa84](https://github.com/hypersec-io/hs-pylib/commit/cc5aa844f19798df27dd7adb58204accd80be9fa))

## [2.10.5](https://github.com/hypersec-io/hs-pylib/compare/v2.10.4...v2.10.5) (2025-11-25)


### Bug Fixes

* remove duplicate pytest markers in pyproject.toml ([121952e](https://github.com/hypersec-io/hs-pylib/commit/121952e7e7786181931f26ae8ac199812cba8cc9))

## [2.10.4](https://github.com/hypersec-io/hs-pylib/compare/v2.10.3...v2.10.4) (2025-11-25)


### Bug Fixes

* update ci submodule with improved commit-msg hook ([52829a0](https://github.com/hypersec-io/hs-pylib/commit/52829a03494c9e645a5d07ed7632be4013cfaf94))

## [2.10.3](https://github.com/hypersec-io/hs-pylib/compare/v2.10.2...v2.10.3) (2025-11-25)


### Bug Fixes

* update CI submodule and add test job to workflow (DFE-540) ([380a56b](https://github.com/hypersec-io/hs-pylib/commit/380a56be6749dcb2011818fc26adb57db001e5d1))

## [2.10.2](https://github.com/hypersec-io/hs-pylib/compare/v2.10.1...v2.10.2) (2025-11-25)


### Bug Fixes

* add Python venv setup step to workflow (workaround BUG-CI-001) ([2d4423a](https://github.com/hypersec-io/hs-pylib/commit/2d4423a05a5c64178d18396219cc4e8cf8209b44))
* clean ci.yaml and set fail_fast: true as default ([455d90b](https://github.com/hypersec-io/hs-pylib/commit/455d90b54478d1d5277bd3f45336c0cfb7e7881d))
* create .env in project root (not ci-local/) ([8176984](https://github.com/hypersec-io/hs-pylib/commit/817698436d05a311d5a63da8d0c3b6be685b25be))
* explicitly specify Python 3.12 for bootstrap ([646be96](https://github.com/hypersec-io/hs-pylib/commit/646be96f6ed604a6299660986f3d4ef931989a7f))
* force uv to use Python 3.12 via UV_PYTHON env var ([200ed61](https://github.com/hypersec-io/hs-pylib/commit/200ed6129b8a1d9718866add18f0a9e916af8c8a))
* install twine in workflow (workaround BUG-CI-002) ([e153fdd](https://github.com/hypersec-io/hs-pylib/commit/e153fdddf2ea7832a3dbed79acfc6bd38aea93b0))
* merge DFE-524 branch (ci workflow paths) ([b2c039f](https://github.com/hypersec-io/hs-pylib/commit/b2c039f02b6f7ebcb889eb6c2129c59f42059c6d))
* migrate to HyperCI modular architecture (DFE-523) ([132b8d0](https://github.com/hypersec-io/hs-pylib/commit/132b8d0d1ca78481b2fd870968b652c1ba2fe6e3))
* migrate to separate ci and ai submodules ([ffd9b25](https://github.com/hypersec-io/hs-pylib/commit/ffd9b25b63d17912e13a8f54317e4b4fab5f5f5e))
* minimal ci.yaml (remove all defaults including nuitka.enabled) ([e3273d9](https://github.com/hypersec-io/hs-pylib/commit/e3273d9e235a10994d08f19f8d7cf0fce5f9e867))
* move build_type to python section (applies to all builds) ([ba05c2f](https://github.com/hypersec-io/hs-pylib/commit/ba05c2fbacee231da09e6ec21a791c5aeb993e3a))
* prepend Python 3.12 to PATH for bootstrap ([1f71b81](https://github.com/hypersec-io/hs-pylib/commit/1f71b815f4a1d6e230d58878498894c92ec7f28b))
* re-enable BuildJet after GitHub App reinstall ([d1f159f](https://github.com/hypersec-io/hs-pylib/commit/d1f159f23b8434690babf2c6749fa08dc632cc12))
* remove [@main](https://github.com/main) refs from local workflow paths ([32b93d4](https://github.com/hypersec-io/hs-pylib/commit/32b93d4a12a35c4fe0a2dd5b5c88c8752dd4823b))
* remove non-existent --python-version flag from workflow ([5d40934](https://github.com/hypersec-io/hs-pylib/commit/5d40934b720d961271567317a97a9eaf63e40ea2))
* rename release.yml to publish.yml for consistency ([dc52bc2](https://github.com/hypersec-io/hs-pylib/commit/dc52bc29e041bd5b8ac3465d0d9e094ca66323e4))
* revert to ubuntu-latest (BuildJet access issue) ([25be898](https://github.com/hypersec-io/hs-pylib/commit/25be898da75a6e7ce9f92f50a64ee84dfdd7cb2e))
* trigger semantic-release for e2e testing (DFE-524) ([ff83b58](https://github.com/hypersec-io/hs-pylib/commit/ff83b58c4906d01c7404260bf403a6e9f94810fc))
* update CI and regenerate publish workflow (DFE-539) ([6658871](https://github.com/hypersec-io/hs-pylib/commit/6658871337222a78b7e323dc5d8f805cb59ae80f))
* update ci submodule (fix pyproject.toml merge bug) ([826878d](https://github.com/hypersec-io/hs-pylib/commit/826878d7bf13940756cac8037dd90b09bdab5ea3))
* update ci submodule (reusable workflows added) ([e5d47c5](https://github.com/hypersec-io/hs-pylib/commit/e5d47c5d81da87e53bd23df8102a11413585bda9))
* update ci submodule (reusable workflows in .github/workflows) ([3dad6ef](https://github.com/hypersec-io/hs-pylib/commit/3dad6ef0b98a3f9cab4b43d929b35f864cfc284d))
* update ci submodule to feat/DFE-523 dev branch ([daa4820](https://github.com/hypersec-io/hs-pylib/commit/daa48205958a8d64895fb58aa4a989669c8f6fe9))
* update CI submodule to latest with uv 0.9.11 support (DFE-524) ([ecc7eb2](https://github.com/hypersec-io/hs-pylib/commit/ecc7eb2742a00462855648b5416de64b3998c6c4))
* update ci submodule to main (DFE-523 merged) ([1da83fe](https://github.com/hypersec-io/hs-pylib/commit/1da83feedb59028ce09c7638a4d54832e1c31243))
* update ci-publish workflow for new ci structure ([6f7801a](https://github.com/hypersec-io/hs-pylib/commit/6f7801a23d15ce404678a16f252e2aa9e7e9ce16))
* update to new workflow paths (DFE-523) ([0490701](https://github.com/hypersec-io/hs-pylib/commit/0490701563db1cde2e9433f3888da1ad0487e459))
* update workflows with checkout fix (DFE-539) ([7d711e5](https://github.com/hypersec-io/hs-pylib/commit/7d711e507cf237d317f017325a2a687ccba71e0c))
* use local ci/workflows path (DFE-523) ([ce9daa1](https://github.com/hypersec-io/hs-pylib/commit/ce9daa155418c2af9595eee63b558e348874d2cb))
* use Python 3.12 in workflow (hs-pylib requires 3.12+) ([d6b01fd](https://github.com/hypersec-io/hs-pylib/commit/d6b01fdd427774e81f868c0d80c595467473a9ab))
* use remote ci repository paths for reusable workflows ([d0462cd](https://github.com/hypersec-io/hs-pylib/commit/d0462cddca99152962c16ae8682fd94fb7a058a4))

# [3.0.0](https://github.com/hypersec-io/hs-pylib/compare/v2.8.8...v3.0.0) (2025-11-13)


## BREAKING CHANGES

### Package Renamed: hyperlib → hs-pylib

The package has been renamed to avoid collision with existing PyPI packages and ensure rename-safety:

- **PyPI package name**: `hyperlib` → `hs-pylib`
- **Python import name**: `hyperlib` → `hs_pylib`
- **GitHub repositories**:
  - `hypersec-io/hyperlib` → `hypersec-io/hs-pylib`
  - `hypersec-io/hyperci` → `hypersec-io/hs-ci`

### Migration Required

**Update your code:**

```python
# OLD
from hyperlib import Application, logger
import hyperlib

# NEW
from hs_pylib import Application, logger
import hs_pylib
```

**Update dependencies:**

```toml
# pyproject.toml
dependencies = [
    "hs-pylib>=3.0.0",  # was: hyperlib>=2.8.8
]
```

```bash
# Install commands
pip install hs-pylib       # was: pip install hyperlib
uv add hs-pylib            # was: uv add hyperlib
```

**Update git remotes (if using submodules):**

```bash
# .gitmodules
[submodule "ci"]
    url = https://github.com/hypersec-io/hs-ci.git  # was: hyperci
```

### Rationale

- **Collision avoidance**: Existing "hyperlib" package on public PyPI
- **Rename-safe**: HS = HyperSec, HyperStack, HyperSolutions (future-proof)
- **Short and memorable**: 1-2 syllables, easy to type

### What's Unchanged

- All functionality remains identical
- API is 100% compatible (only import paths changed)
- Version numbering continues from 2.8.8
- All features, tests, and documentation preserved

### Bug Fixes

* rename package from hyperlib to hs-pylib for PyPI collision avoidance ([bc4dacd](https://github.com/hypersec-io/hs-pylib/commit/bc4dacd))
* update repository URLs after renaming to hs-pylib and hs-ci ([9fd2e75](https://github.com/hypersec-io/hs-pylib/commit/9fd2e75))
* update ci submodule URL to renamed hs-ci repository ([9fd2e75](https://github.com/hypersec-io/hs-pylib/commit/9fd2e75))

---

# [1.6.0](https://github.com/hypersec-io/hyperlib/compare/v1.5.5...v1.6.0) (2025-10-10)


### Bug Fixes

* add api extras to metrics test Dockerfile, remove orphaned jinja template ([152c2a2](https://github.com/hypersec-io/hyperlib/commit/152c2a25ba5c3a0e4500e75a75ac713492d89082))
* add cache_dir and run_dir to RuntimePaths, remove jinja templates ([5af078d](https://github.com/hypersec-io/hyperlib/commit/5af078d9a9b020a8e250daf155ae13b8db50be6e))
* API test route decorator, add comprehensive testing documentation ([eb2e504](https://github.com/hypersec-io/hyperlib/commit/eb2e50425337caae022134f815201e8230f6c9ad))
* apply ruff formatting fixes to application code and tests ([88d01a7](https://github.com/hypersec-io/hyperlib/commit/88d01a760ba24d9dd1cbc6e0c71c04b235519772))
* clean up test infrastructure and timeout.py ([0a55a30](https://github.com/hypersec-io/hyperlib/commit/0a55a3079440b6a38ce7b45a531b80332dd8ddca))
* eliminate double-commit in semantic-release, let it handle VERSION completely ([6990646](https://github.com/hypersec-io/hyperlib/commit/6990646ee6140fe658ce52ab7cec201e858225f4))
* implement multi-layer venv protection strategy with shared CI utilities ([f13e7a1](https://github.com/hypersec-io/hyperlib/commit/f13e7a13ce11c6f5a3c47faf350f61d46e057a58))
* improve application test coverage with proper dependency detection ([0e04294](https://github.com/hypersec-io/hyperlib/commit/0e0429449cbe690486bfde42ca04aa09c07d919a))
* improve README description to accurately reflect current features ([66817ea](https://github.com/hypersec-io/hyperlib/commit/66817ea680ca67d91f6fe6df16c024cbcba62594))
* remove health endpoint test, fix oneshot error type, fix Helm template syntax ([bf1b3f2](https://github.com/hypersec-io/hyperlib/commit/bf1b3f298a0f627cc772a55b07a309741001b8ae))
* simplify bootstrap to be self-contained without hyperlib dependencies ([885ba79](https://github.com/hypersec-io/hyperlib/commit/885ba79109826c5c3ca30bd27cb65b8759f47615))
* standardize all test fixtures to _N.txt format, fix Docker build context issues ([6b45b07](https://github.com/hypersec-io/hyperlib/commit/6b45b0771e5e584c719d3f0dcd93a6fdaee1e7cb))
* update Dockerfile fixtures to use pyproject.toml optional extras ([210edea](https://github.com/hypersec-io/hyperlib/commit/210edeada520153ad89da95f7faafc0da2f6413a))
* update pyproject.toml - Python 3.11+, remove unused deps, add optional extras ([21572f9](https://github.com/hypersec-io/hyperlib/commit/21572f90589785c83826194d345c813a545696b4))
* update pyproject.toml metadata - production status, accurate description and keywords ([4536222](https://github.com/hypersec-io/hyperlib/commit/4536222c9b0b450b1fed7c812b6cee140dd330ad))


### Features

* add CLI enhancements for multi-environment configuration ([aedff4f](https://github.com/hypersec-io/hyperlib/commit/aedff4f08c2029a934b2eab000fcaaf9d47ce4d8))
* add comprehensive Prometheus metrics module with custom metrics API ([7d54416](https://github.com/hypersec-io/hyperlib/commit/7d544169c21d37b5efdb507a6c35839eb4b848ca))
* add hyperlib.application factory pattern ([e583cca](https://github.com/hypersec-io/hyperlib/commit/e583ccab486c0eac180fa8901428ee0999308aa3))
* add missing enterprise features to application module ([96615d4](https://github.com/hypersec-io/hyperlib/commit/96615d46672c8d1f857f8ccdf7751236fd7639c1))
* add router inclusion and generic middleware support to APIApplication ([ccaa071](https://github.com/hypersec-io/hyperlib/commit/ccaa07193c4f3f4b522afd982de92825d07fa1a2))
* add unified runtime environment for container and local deployment ([d9ab1b1](https://github.com/hypersec-io/hyperlib/commit/d9ab1b18f6bebb34f26312d803d1c5914b4ebaa0))
* capture Docker and K8s pod logs to /logs directory with timestamps ([213cba0](https://github.com/hypersec-io/hyperlib/commit/213cba012e69af372021aacce6a654c7a76ed124))
* enforce ci/.venv for all CI scripts (FAIL HARD) ([8d1c1a1](https://github.com/hypersec-io/hyperlib/commit/8d1c1a112789d028ae728ec0435ac2f0140a5e75))
* enforce CHARS-POLICY.md in logger with terminal detection ([fbcb44c](https://github.com/hypersec-io/hyperlib/commit/fbcb44c0513eb1755c211844ca66c4fb431fec9d))
* enhance container detection with 7-layer strategy ([5b3d298](https://github.com/hypersec-io/hyperlib/commit/5b3d2981efa42830dc82a78915abd1e63c7efd94))
* integrate harness.run() into tests for centralized logging ([f606605](https://github.com/hypersec-io/hyperlib/commit/f60660593610372190ccf62a59d0b174c5ed1081))

# [1.6.0](https://github.com/hypersec-io/hyperlib/compare/v1.5.5...v1.6.0) (2025-10-10)


### Bug Fixes

* add api extras to metrics test Dockerfile, remove orphaned jinja template ([152c2a2](https://github.com/hypersec-io/hyperlib/commit/152c2a25ba5c3a0e4500e75a75ac713492d89082))
* add cache_dir and run_dir to RuntimePaths, remove jinja templates ([5af078d](https://github.com/hypersec-io/hyperlib/commit/5af078d9a9b020a8e250daf155ae13b8db50be6e))
* API test route decorator, add comprehensive testing documentation ([eb2e504](https://github.com/hypersec-io/hyperlib/commit/eb2e50425337caae022134f815201e8230f6c9ad))
* apply ruff formatting fixes to application code and tests ([88d01a7](https://github.com/hypersec-io/hyperlib/commit/88d01a760ba24d9dd1cbc6e0c71c04b235519772))
* clean up test infrastructure and timeout.py ([0a55a30](https://github.com/hypersec-io/hyperlib/commit/0a55a3079440b6a38ce7b45a531b80332dd8ddca))
* improve application test coverage with proper dependency detection ([0e04294](https://github.com/hypersec-io/hyperlib/commit/0e0429449cbe690486bfde42ca04aa09c07d919a))
* improve README description to accurately reflect current features ([66817ea](https://github.com/hypersec-io/hyperlib/commit/66817ea680ca67d91f6fe6df16c024cbcba62594))
* remove health endpoint test, fix oneshot error type, fix Helm template syntax ([bf1b3f2](https://github.com/hypersec-io/hyperlib/commit/bf1b3f298a0f627cc772a55b07a309741001b8ae))
* simplify bootstrap to be self-contained without hyperlib dependencies ([885ba79](https://github.com/hypersec-io/hyperlib/commit/885ba79109826c5c3ca30bd27cb65b8759f47615))
* standardize all test fixtures to _N.txt format, fix Docker build context issues ([6b45b07](https://github.com/hypersec-io/hyperlib/commit/6b45b0771e5e584c719d3f0dcd93a6fdaee1e7cb))
* update Dockerfile fixtures to use pyproject.toml optional extras ([210edea](https://github.com/hypersec-io/hyperlib/commit/210edeada520153ad89da95f7faafc0da2f6413a))
* update pyproject.toml - Python 3.11+, remove unused deps, add optional extras ([21572f9](https://github.com/hypersec-io/hyperlib/commit/21572f90589785c83826194d345c813a545696b4))
* update pyproject.toml metadata - production status, accurate description and keywords ([4536222](https://github.com/hypersec-io/hyperlib/commit/4536222c9b0b450b1fed7c812b6cee140dd330ad))


### Features

* add CLI enhancements for multi-environment configuration ([aedff4f](https://github.com/hypersec-io/hyperlib/commit/aedff4f08c2029a934b2eab000fcaaf9d47ce4d8))
* add comprehensive Prometheus metrics module with custom metrics API ([7d54416](https://github.com/hypersec-io/hyperlib/commit/7d544169c21d37b5efdb507a6c35839eb4b848ca))
* add hyperlib.application factory pattern ([e583cca](https://github.com/hypersec-io/hyperlib/commit/e583ccab486c0eac180fa8901428ee0999308aa3))
* add missing enterprise features to application module ([96615d4](https://github.com/hypersec-io/hyperlib/commit/96615d46672c8d1f857f8ccdf7751236fd7639c1))
* add router inclusion and generic middleware support to APIApplication ([ccaa071](https://github.com/hypersec-io/hyperlib/commit/ccaa07193c4f3f4b522afd982de92825d07fa1a2))
* add unified runtime environment for container and local deployment ([d9ab1b1](https://github.com/hypersec-io/hyperlib/commit/d9ab1b18f6bebb34f26312d803d1c5914b4ebaa0))
* capture Docker and K8s pod logs to /logs directory with timestamps ([213cba0](https://github.com/hypersec-io/hyperlib/commit/213cba012e69af372021aacce6a654c7a76ed124))
* enforce ci/.venv for all CI scripts (FAIL HARD) ([8d1c1a1](https://github.com/hypersec-io/hyperlib/commit/8d1c1a112789d028ae728ec0435ac2f0140a5e75))
* enforce CHARS-POLICY.md in logger with terminal detection ([fbcb44c](https://github.com/hypersec-io/hyperlib/commit/fbcb44c0513eb1755c211844ca66c4fb431fec9d))
* enhance container detection with 7-layer strategy ([5b3d298](https://github.com/hypersec-io/hyperlib/commit/5b3d2981efa42830dc82a78915abd1e63c7efd94))
* integrate harness.run() into tests for centralized logging ([f606605](https://github.com/hypersec-io/hyperlib/commit/f60660593610372190ccf62a59d0b174c5ed1081))

## [1.5.5](https://github.com/hypersec-io/hyperlib/compare/v1.5.4...v1.5.5) (2025-10-07)


### Bug Fixes

* add configurable color schemes for logger ([b4fd16d](https://github.com/hypersec-io/hyperlib/commit/b4fd16ded352973d8105cd0de17daf3c6c814a90))
* configure Solarized colors for all log levels ([2f84974](https://github.com/hypersec-io/hyperlib/commit/2f8497454b52c7ed17dce0402f103e3c5e7ede2f)), closes [#859900](https://github.com/hypersec-io/hyperlib/issues/859900) [#2aa198](https://github.com/hypersec-io/hyperlib/issues/2aa198) [#586e75](https://github.com/hypersec-io/hyperlib/issues/586e75) [#268bd2](https://github.com/hypersec-io/hyperlib/issues/268bd2) [#859900](https://github.com/hypersec-io/hyperlib/issues/859900) [#b58900](https://github.com/hypersec-io/hyperlib/issues/b58900) [#cb4b16](https://github.com/hypersec-io/hyperlib/issues/cb4b16) [#dc322](https://github.com/hypersec-io/hyperlib/issues/dc322)
* remove trailing whitespace in cache.py docstring [skip ci] ([3c1ac67](https://github.com/hypersec-io/hyperlib/commit/3c1ac678506480918775fc14f2331ab1eeb48e74))
* use proper Solarized color codes in logger format ([5f068eb](https://github.com/hypersec-io/hyperlib/commit/5f068ebb68247b6e1a6e36b655b1a95dc7fa514a)), closes [#859900](https://github.com/hypersec-io/hyperlib/issues/859900) [#2aa198](https://github.com/hypersec-io/hyperlib/issues/2aa198)

## [1.5.4](https://github.com/hypersec-io/hyperlib/compare/v1.5.3...v1.5.4) (2025-10-07)


### Bug Fixes

* create pip.conf in ci/.venv for proper venv configuration ([5752dc5](https://github.com/hypersec-io/hyperlib/commit/5752dc59320280f73ba2829c1fcf060dd0799150))
* simplify JFrog package verification using curl ([30b40ba](https://github.com/hypersec-io/hyperlib/commit/30b40ba6abcc7f6360fd8f11e19db18ce4e4d04c))

## [1.5.2](https://github.com/hypersec-io/hyperlib/compare/v1.5.1...v1.5.2) (2025-10-07)


### Bug Fixes

* clean all build artifacts before building to prevent duplicate versions ([3b24743](https://github.com/hypersec-io/hyperlib/commit/3b24743cf6b40bd70762ba5e82f5d2635ac2c833))

## [1.5.1](https://github.com/hypersec-io/hyperlib/compare/v1.5.0...v1.5.1) (2025-10-07)


### Bug Fixes

* make ENV_PREFIX configurable via HYPERLIB_ENV_PREFIX ([2703e7e](https://github.com/hypersec-io/hyperlib/commit/2703e7e748d6e6d5720b181f0c209acf51b1c2eb))

# [1.5.0](https://github.com/hypersec-io/hyperlib/compare/v1.4.0...v1.5.0) (2025-10-01)


### Features

* sync CI script with publish command from forge-core ([5904b99](https://github.com/hypersec-io/hyperlib/commit/5904b996800316bba7ed132b352b419932ff3a62))

# [1.4.0](https://github.com/hypersec-io/hyperlib/compare/v1.3.0...v1.4.0) (2025-10-01)


### Bug Fixes

* make build/deploy scripts handle all action types gracefully ([cb7078b](https://github.com/hypersec-io/hyperlib/commit/cb7078b4e0d6dd8c7ffce1d23b48ccc2aa629174))


### Features

* **ci:** add comprehensive CI commands for build/deploy workflow ([7f17a42](https://github.com/hypersec-io/hyperlib/commit/7f17a421838c2c78f17366230c522929ba925620))
* sync CI scripts with --push flag support from forge-core ([09225c7](https://github.com/hypersec-io/hyperlib/commit/09225c7360234a220bff9bfd8794214da8ee1405))


### Reverts

* Revert "chore: convert universal CI scripts to symlinks (branch-name, chars-policy, semantic-release from forge-core; version-sync from forge-python)" ([ac0f505](https://github.com/hypersec-io/hyperlib/commit/ac0f505fb01630db20d1911f93c7b839da813da5))

# [1.3.0](https://github.com/hypersec-io/hyperlib/compare/v1.2.1...v1.3.0) (2025-10-01)


### Bug Fixes

* **ci:** semantic-release should not overwrite version files ([e106474](https://github.com/hypersec-io/hyperlib/commit/e106474ffd00a84cd86b0eca86b8139862ce5333))


### Features

* **ci:** add automatic JFrog publishing to semantic-release ([fd4622c](https://github.com/hypersec-io/hyperlib/commit/fd4622c9034444927defbe032bd2bde65760d19e))

## [1.2.1](https://github.com/hypersec-io/hyperlib/compare/v1.2.0...v1.2.1) (2025-10-01)


### Bug Fixes

* **ci:** semantic-release now updates __init__.py and uses tomllib ([ca5ba93](https://github.com/hypersec-io/hyperlib/commit/ca5ba93a50d126cf417472d5ea8d13c5c67786ef))
* **ci:** use ci/.venv python for semantic-release build command ([9a8487d](https://github.com/hypersec-io/hyperlib/commit/9a8487d4ad8809110427c753518b65aa4c7a527f))

## [1.2.1](https://github.com/hypersec-io/hyperlib/compare/v1.2.0...v1.2.1) (2025-10-01)


### Bug Fixes

* **ci:** semantic-release now updates __init__.py and uses tomllib ([ca5ba93](https://github.com/hypersec-io/hyperlib/commit/ca5ba93a50d126cf417472d5ea8d13c5c67786ef))
* **ci:** use ci/.venv python for semantic-release build command ([9a8487d](https://github.com/hypersec-io/hyperlib/commit/9a8487d4ad8809110427c753518b65aa4c7a527f))

## [1.2.1](https://github.com/hypersec-io/hyperlib/compare/v1.2.0...v1.2.1) (2025-10-01)


### Bug Fixes

* **ci:** semantic-release now updates __init__.py and uses tomllib ([ca5ba93](https://github.com/hypersec-io/hyperlib/commit/ca5ba93a50d126cf417472d5ea8d13c5c67786ef))
* **ci:** use ci/.venv python for semantic-release build command ([9a8487d](https://github.com/hypersec-io/hyperlib/commit/9a8487d4ad8809110427c753518b65aa4c7a527f))

# [1.2.0](https://github.com/hypersec-io/hyperlib/compare/v1.1.2...v1.2.0) (2025-10-01)


### Bug Fixes

* **ci:** make pytest work without pytest-cov ([17004da](https://github.com/hypersec-io/hyperlib/commit/17004dabfe6e6c3e848bafbad53a97f92c34eb3a))
* **ci:** replace template rendering script with package testing script ([9eb0eba](https://github.com/hypersec-io/hyperlib/commit/9eb0eba608482722c6e8144979367f6914047464))
* **tests:** add missing temp_dir fixture for bootstrap tests ([b9ebab0](https://github.com/hypersec-io/hyperlib/commit/b9ebab0091198467bbf21aeaf6d0bbfc780b88ab))
* **tests:** fix test_ensure_dependency_check_mode test ([719cfa3](https://github.com/hypersec-io/hyperlib/commit/719cfa3bbf459af34e62b6fd342ea0ad5e996937))


### Features

* add comprehensive bootstrap tests ([94b9d62](https://github.com/hypersec-io/hyperlib/commit/94b9d6278b3490318ae07902602854993eb4c60f))
* add JFrog token authentication support ([8bddc5d](https://github.com/hypersec-io/hyperlib/commit/8bddc5d973b9bf327f2168f29caedc898ab60b57))

# [4.1.0](https://github.com/hypersec-io/hypersec-forge/compare/v4.0.0...v4.1.0) (2025-10-01)


### Bug Fixes

* **hyperlib:** add K8s standard logging environment variables ([9d9d3c5](https://github.com/hypersec-io/hypersec-forge/commit/9d9d3c50cd744c7896c250210d264e32a96b7e39))


### Features

* **ci:** enforce PyPI-installed hyperlib for all CI and add .env symlinks ([f7245f5](https://github.com/hypersec-io/hypersec-forge/commit/f7245f56f8459d2a8ba1ba7c63532e47f9711784))

# Changelog

All notable changes to testproject will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial package structure
- Basic CLI interface
- Development tooling setup
