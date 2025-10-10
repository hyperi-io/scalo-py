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
* enforce .venv-ci for all CI scripts (FAIL HARD) ([8d1c1a1](https://github.com/hypersec-io/hyperlib/commit/8d1c1a112789d028ae728ec0435ac2f0140a5e75))
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

* create pip.conf in .venv-ci for proper venv configuration ([5752dc5](https://github.com/hypersec-io/hyperlib/commit/5752dc59320280f73ba2829c1fcf060dd0799150))
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
* **ci:** use .venv-ci python for semantic-release build command ([9a8487d](https://github.com/hypersec-io/hyperlib/commit/9a8487d4ad8809110427c753518b65aa4c7a527f))

## [1.2.1](https://github.com/hypersec-io/hyperlib/compare/v1.2.0...v1.2.1) (2025-10-01)


### Bug Fixes

* **ci:** semantic-release now updates __init__.py and uses tomllib ([ca5ba93](https://github.com/hypersec-io/hyperlib/commit/ca5ba93a50d126cf417472d5ea8d13c5c67786ef))
* **ci:** use .venv-ci python for semantic-release build command ([9a8487d](https://github.com/hypersec-io/hyperlib/commit/9a8487d4ad8809110427c753518b65aa4c7a527f))

## [1.2.1](https://github.com/hypersec-io/hyperlib/compare/v1.2.0...v1.2.1) (2025-10-01)


### Bug Fixes

* **ci:** semantic-release now updates __init__.py and uses tomllib ([ca5ba93](https://github.com/hypersec-io/hyperlib/commit/ca5ba93a50d126cf417472d5ea8d13c5c67786ef))
* **ci:** use .venv-ci python for semantic-release build command ([9a8487d](https://github.com/hypersec-io/hyperlib/commit/9a8487d4ad8809110427c753518b65aa4c7a527f))

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
