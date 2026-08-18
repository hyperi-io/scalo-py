# Changelog

Rendered by CI and committed back at the end of a release -- do not edit by
hand. Release notes also appear on the GitHub Releases page, one per tag.

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
