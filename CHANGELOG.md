# Changelog

Rendered by CI and committed back at the end of a release -- do not edit by
hand. Release notes also appear on the GitHub Releases page, one per tag.

## [2.31.1](https://github.com/hyperi-io/scalo-py/compare/v2.31.0...v2.31.1) (2026-10-06)

### Bug Fixes

* **deps:** update dependencies for GA ([#76](https://github.com/hyperi-io/scalo-py/issues/76)) ([8012067](https://github.com/hyperi-io/scalo-py/commit/80120672f9bf29f426cc17c88a0d088cdb737d47))

## [2.31.0](https://github.com/hyperi-io/scalo-py/compare/v2.30.7...v2.31.0) (2026-10-05)

### Features

* **contract:** no vendor or product defaults ([#63](https://github.com/hyperi-io/scalo-py/issues/63)) ([cc75b0f](https://github.com/hyperi-io/scalo-py/commit/cc75b0f9f5c4af2119a8786957ae8050df58710e))

### Bug Fixes

* allowlist the masking corpus at its tests/fixtures path ([#75](https://github.com/hyperi-io/scalo-py/issues/75)) ([fc45b2f](https://github.com/hyperi-io/scalo-py/commit/fc45b2f4affea0d031bdd0d6d5f37fe99b045630)), closes [#68](https://github.com/hyperi-io/scalo-py/issues/68)
* bind DDL name, CPU seconds parity, CI notices ([#70](https://github.com/hyperi-io/scalo-py/issues/70)) ([9a13f5b](https://github.com/hyperi-io/scalo-py/commit/9a13f5bb52ae82f0c26e24d811d25db3d2f0dfc3)), closes [#33](https://github.com/hyperi-io/scalo-py/issues/33) [#59](https://github.com/hyperi-io/scalo-py/issues/59) [#15](https://github.com/hyperi-io/scalo-py/issues/15)
* bump pyjwt and virtualenv for pip-audit advisories ([#60](https://github.com/hyperi-io/scalo-py/issues/60)) ([655eae6](https://github.com/hyperi-io/scalo-py/commit/655eae632699220ed4fd01956b7e2cad2873e4a9))
* correct three file headers to Apache-2.0 ([#73](https://github.com/hyperi-io/scalo-py/issues/73)) ([07e6fcf](https://github.com/hyperi-io/scalo-py/commit/07e6fcf948bf98fcaf93d87116ba12e59405e155))
* **deps:** raise dulwich to 1.2.15 for four advisories ([301eee5](https://github.com/hyperi-io/scalo-py/commit/301eee59237bb1728d873cc05844c7fa004d9c6c))
* **docs:** say which logging keys setup() does not read ([2fd8d6f](https://github.com/hyperi-io/scalo-py/commit/2fd8d6f772565af10cc56820c36c6d6c54e1d336))
* **docs:** setup() says which config keys never reach it ([#66](https://github.com/hyperi-io/scalo-py/issues/66)) ([5f6d7bd](https://github.com/hyperi-io/scalo-py/commit/5f6d7bd5266b940aa2fea86993d8eb98aff2a73b))
* drop DFE and HyperI names left in scalo-py ([#67](https://github.com/hyperi-io/scalo-py/issues/67)) ([22ade53](https://github.com/hyperi-io/scalo-py/commit/22ade53363519b30ed90ad6c0b891b829d2d2fed))
* drop DFE-internal references from public docs and comments ([#72](https://github.com/hyperi-io/scalo-py/issues/72)) ([71d1c28](https://github.com/hyperi-io/scalo-py/commit/71d1c283b97ffeaab302d52c7dde48e5ad72bdbc))
* keep the parity test corpora out of the wheel ([#68](https://github.com/hyperi-io/scalo-py/issues/68)) ([9ee02f0](https://github.com/hyperi-io/scalo-py/commit/9ee02f04387874901b817e4d9c21b68d1ed6d11c))
* **logger:** harden the scrub filter ([#62](https://github.com/hyperi-io/scalo-py/issues/62)) ([2384795](https://github.com/hyperi-io/scalo-py/commit/23847959999d1bd7c903e34c33c93341b6f688d7))
* **logger:** render fields and honour auto format ([#61](https://github.com/hyperi-io/scalo-py/issues/61)) ([113f172](https://github.com/hyperi-io/scalo-py/commit/113f172d9cfc7376a928e58e89186b7d923b1430))
* suppress the false alert on AWS batch logging ([#56](https://github.com/hyperi-io/scalo-py/issues/56)) ([cf73c5d](https://github.com/hyperi-io/scalo-py/commit/cf73c5d78cf2bc3303fe3e9d95e63579e361694d)), closes [#23](https://github.com/hyperi-io/scalo-py/issues/23)
* trim the app environment and skip blank values ([#55](https://github.com/hyperi-io/scalo-py/issues/55)) ([ac0ee9b](https://github.com/hyperi-io/scalo-py/commit/ac0ee9ba1ed71c876764c244c9046cf767ccee5f))
* type the deployment import stub as NoReturn ([#71](https://github.com/hyperi-io/scalo-py/issues/71)) ([c428fe9](https://github.com/hyperi-io/scalo-py/commit/c428fe9e3b005b2aa09dc0b5a77aaf63e6e77a60)), closes [#48](https://github.com/hyperi-io/scalo-py/issues/48)

## [2.30.7](https://github.com/hyperi-io/scalo-py/compare/v2.30.6...v2.30.7) (2026-09-30)

### Bug Fixes

* **deps:** require pyjwt 2.14.0 for ten new CVEs ([547369b](https://github.com/hyperi-io/scalo-py/commit/547369b220ee81e7008ffd31755085a0565c64d2))
* **metrics:** export gauges on every collection ([8e1f994](https://github.com/hyperi-io/scalo-py/commit/8e1f99450537b32f4daa2b70e95a2628369dbcd7))
* **metrics:** resource gauges, HTTP server metrics, real buckets ([6380960](https://github.com/hyperi-io/scalo-py/commit/63809601f486967288fc91ef5917ec75e4db2a3f))

## [2.30.5](https://github.com/hyperi-io/scalo-py/compare/v2.30.4...v2.30.5) (2026-09-27)

### Bug Fixes

* clear the charset, sha1 and hadolint warnings ([#49](https://github.com/hyperi-io/scalo-py/issues/49)) ([06d18cc](https://github.com/hyperi-io/scalo-py/commit/06d18cc2a3abd0228d776262e7c9b119dfb98460))
* config-check checks what run will actually do ([#43](https://github.com/hyperi-io/scalo-py/issues/43)) ([8df7d67](https://github.com/hyperi-io/scalo-py/commit/8df7d671df6a2f858227970c3fd6f59af530ea53)), closes [#29](https://github.com/hyperi-io/scalo-py/issues/29) [#24](https://github.com/hyperi-io/scalo-py/issues/24) [#31](https://github.com/hyperi-io/scalo-py/issues/31) [#25](https://github.com/hyperi-io/scalo-py/issues/25)
* **kafka:** default the producer codec to zstd, not lz4 ([#44](https://github.com/hyperi-io/scalo-py/issues/44)) ([42c722e](https://github.com/hyperi-io/scalo-py/commit/42c722e7be560478fc4426833394ee9ddbeacc36))
* **logger:** cap the AWS SDK loggers so DEBUG never logs a secret ([58c1fde](https://github.com/hyperi-io/scalo-py/commit/58c1fdefdcd1b6ba08ffde2fc900f22eea07970e))
* resolve the code-scanning alerts and the AWS batch-fetch KeyError ([#45](https://github.com/hyperi-io/scalo-py/issues/45)) ([efab823](https://github.com/hyperi-io/scalo-py/commit/efab823abc02ceb1ec34ca63074b59216ab95e7e))
* stop the test suite killing other processes, clear semgrep, re-vendor the patterns ([#50](https://github.com/hyperi-io/scalo-py/issues/50)) ([9c8f5d6](https://github.com/hyperi-io/scalo-py/commit/9c8f5d638822509ba4fff61083078d916c83bfdc))

## [2.30.4](https://github.com/hyperi-io/scalo-py/compare/v2.30.3...v2.30.4) (2026-09-24)

### Bug Fixes

* drop Redis from env detection and examples ([136dc16](https://github.com/hyperi-io/scalo-py/commit/136dc16e087c573bef7a28c66fa72af4773e06ef))

## [2.30.3](https://github.com/hyperi-io/scalo-py/compare/v2.30.2...v2.30.3) (2026-09-24)

### Bug Fixes

* **scrub:** mask env-style and TOML keys in L2 ([#40](https://github.com/hyperi-io/scalo-py/issues/40)) ([dd97c60](https://github.com/hyperi-io/scalo-py/commit/dd97c605a5dcab0b1627fec47ac57b9bb40441cc))

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
