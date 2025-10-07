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
