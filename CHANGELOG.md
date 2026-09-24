# Changelog

Rendered by CI and committed back at the end of a release -- do not edit by
hand. Release notes also appear on the GitHub Releases page, one per tag.

## [2.30.2](https://github.com/hyperi-io/scalo-py/compare/v2.30.1...v2.30.2) (2026-09-24)

### Bug Fixes

* **kafka:** derive internal group ids from config ([#39](https://github.com/hyperi-io/scalo-py/issues/39)) ([114717d](https://github.com/hyperi-io/scalo-py/commit/114717d3aee5cea0f2bcf2b81ad8ad45764200b8)), closes [#171](https://github.com/hyperi-io/scalo-py/issues/171)
* **scrub:** exclude one gitleaks rule by id ([#37](https://github.com/hyperi-io/scalo-py/issues/37)) ([be94253](https://github.com/hyperi-io/scalo-py/commit/be9425327d43fc5e22d59242060a93f84db26022)), closes [hyperi-io/hyperi-ci#255](https://github.com/hyperi-io/hyperi-ci/issues/255)

## [2.30.1](https://github.com/hyperi-io/scalo-py/compare/v2.30.0...v2.30.1) (2026-09-23)

### Bug Fixes

* **docs:** add the README Context section and lowercase the architecture doc ([#35](https://github.com/hyperi-io/scalo-py/issues/35)) ([c4fdc8f](https://github.com/hyperi-io/scalo-py/commit/c4fdc8fd341de3cb522e8e060acdcbc17739c3f2)), closes [#28](https://github.com/hyperi-io/scalo-py/issues/28)
* lead with the hero line, and cut the README to it ([#36](https://github.com/hyperi-io/scalo-py/issues/36)) ([e0fa31e](https://github.com/hyperi-io/scalo-py/commit/e0fa31ef65d81f6a8eac0ff3948024eab980d55d))
* raise the Python floor to 3.14 ([0c4c138](https://github.com/hyperi-io/scalo-py/commit/0c4c138effa044ded33f3e27332b6547c3ef2b84))

## [2.30.0](https://github.com/hyperi-io/scalo-py/compare/v2.29.18...v2.30.0) (2026-08-27)

### Features

* version check on by default with app-supplied endpoint defaults ([3f76051](https://github.com/hyperi-io/scalo-py/commit/3f760519c561d68f8610439f83b37f70a69f930c))

## [2.29.18](https://github.com/hyperi-io/scalo-py/compare/v2.29.17...v2.29.18) (2026-08-27)

### Bug Fixes

* platform-derived version-check instance id, shared contract with scalo-rs ([d459b63](https://github.com/hyperi-io/scalo-py/commit/d459b635c654be25889baa6c4a6b76ab82e554a8))

## [2.29.17](https://github.com/hyperi-io/scalo-py/compare/v2.29.16...v2.29.17) (2026-08-26)

### Bug Fixes

* **ddl:** pick the ClickHouse table engine by sensing the server ([#21](https://github.com/hyperi-io/scalo-py/issues/21)) ([17e6597](https://github.com/hyperi-io/scalo-py/commit/17e6597558ead638189af8189b42abb3c294fece))

## [2.29.16](https://github.com/hyperi-io/scalo-py/compare/v2.29.15...v2.29.16) (2026-08-23)

### Bug Fixes

* **logger:** unset log format derives from otel presence ([#19](https://github.com/hyperi-io/scalo-py/issues/19)) ([5e1e6c2](https://github.com/hyperi-io/scalo-py/commit/5e1e6c264e6ca5bcfe138a5136b635052c95eea8)), closes [scalo-rs#38](https://github.com/hyperi-io/scalo-rs/issues/38)

## [2.29.15](https://github.com/hyperi-io/scalo-py/compare/v2.29.14...v2.29.15) (2026-08-22)

### Bug Fixes

* **deps:** bump the pip override to the PYSEC-2026-3721 fix ([2492922](https://github.com/hyperi-io/scalo-py/commit/24929222e123d99edd9ed1fda12d65dfdc854e1d))
* **metrics:** make [metrics] install the default dual-export backend ([5a426c1](https://github.com/hyperi-io/scalo-py/commit/5a426c19aaf7c5fc4ba107e905f7222ce8d2ceb3))

## [2.29.14](https://github.com/hyperi-io/scalo-py/compare/v2.29.13...v2.29.14) (2026-08-18)

### Bug Fixes

* **cli:** load config before the logger, and export OTLP by default ([b61e433](https://github.com/hyperi-io/scalo-py/commit/b61e433c365b452057a3a87ce3f945fd6e7ae759))
* **deployment:** pin the Confluent signing key before the build trusts it ([eee8a71](https://github.com/hyperi-io/scalo-py/commit/eee8a7190cf5c5208a662e99a4b36b74293b3716))
* **docs:** name scalo and scalo-rs, and the env vars that actually exist ([da005a0](https://github.com/hyperi-io/scalo-py/commit/da005a0d430bb742ed8d92508d8609778b1c5d9b)), closes [#7](https://github.com/hyperi-io/scalo-py/issues/7) [#7](https://github.com/hyperi-io/scalo-py/issues/7)
* **repo:** take the security releases, and fix a gitignore that ignored nothing ([1dc0aeb](https://github.com/hyperi-io/scalo-py/commit/1dc0aeb0d84957cfabbbbab723b9ccaf443690c8)), closes [PKCS#7](https://github.com/hyperi-io/PKCS/issues/7)
* **test:** fail the build on a circular import at startup ([b5df93a](https://github.com/hyperi-io/scalo-py/commit/b5df93ae2d7ee986d100c9d724edd70181d9634b))

## [2.29.13](https://github.com/hyperi-io/scalo-py/compare/v2.29.12...v2.29.13) (2026-08-03)

# Changelog

`scalo` continues the version line of `hyperi-pylib`, the library it was
renamed from; release notes from before the port live in that project's
history. This file is managed by semantic-release -- the first `scalo`
release and every change after it are recorded above this baseline entry.

## 2.28.6

Port baseline: `hyperi-pylib` renamed and de-branded to `scalo`, continuing
the v2.28.x version line (no version reset).
