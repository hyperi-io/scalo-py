## [2.10.14](https://github.com/hypersec-io/hs-lib/compare/v2.10.13...v2.10.14) (2025-11-28)


### Bug Fixes

* update CI to hs-ci v1.33.1 ([50049d4](https://github.com/hypersec-io/hs-lib/commit/50049d4929fed6ba8a1edbad4804797c5b2e93d5))

## [2.10.13](https://github.com/hypersec-io/hs-lib/compare/v2.10.12...v2.10.13) (2025-11-28)


### Bug Fixes

* update CI with thin publish.yml workflow ([c7b8732](https://github.com/hypersec-io/hs-lib/commit/c7b873293080947819d8172d681bc5e7588f1213))

## [2.10.12](https://github.com/hypersec-io/hs-lib/compare/v2.10.11...v2.10.12) (2025-11-28)


### Bug Fixes

* allowlist test_logger_filters.py fake secrets ([342d3c8](https://github.com/hypersec-io/hs-lib/commit/342d3c8fee2dbf78e5fa341e2128e7ef3af85d40))

## [2.10.11](https://github.com/hypersec-io/hs-lib/compare/v2.10.10...v2.10.11) (2025-11-28)


### Bug Fixes

* allowlist test fixture fake secrets in gitleaks ([b5c74c6](https://github.com/hypersec-io/hs-lib/commit/b5c74c6e903eac5b5fe5e902cc4a524475758722))

## [2.10.10](https://github.com/hypersec-io/hs-lib/compare/v2.10.9...v2.10.10) (2025-11-28)


### Bug Fixes

* add gitleaks allowlist for historical backup files ([4ace591](https://github.com/hypersec-io/hs-lib/commit/4ace59115ddfb3dfe27cf9cbeddcf78b4d946577))

## [2.10.9](https://github.com/hypersec-io/hs-lib/compare/v2.10.8...v2.10.9) (2025-11-27)


### Bug Fixes

* update CI to hs-ci v1.31.0 with thin workflows ([e82ae7a](https://github.com/hypersec-io/hs-lib/commit/e82ae7af3b56e8787521ca49b3f1b0277b496436))

## [2.10.8](https://github.com/hypersec-io/hs-lib/compare/v2.10.7...v2.10.8) (2025-11-26)


### Bug Fixes

* update STATE.md for new CI architecture (hs-ci v1.19.x) ([4c3fff7](https://github.com/hypersec-io/hs-lib/commit/4c3fff7eaa5661b638ca189d10a99128f178ae91))

## [2.10.7](https://github.com/hypersec-io/hs-lib/compare/v2.10.6...v2.10.7) (2025-11-26)


### Bug Fixes

* format code with ruff ([9eff58d](https://github.com/hypersec-io/hs-lib/commit/9eff58d85d5b987258c99d93d5c78d2242d950c0))

## [2.10.6](https://github.com/hypersec-io/hs-lib/compare/v2.10.5...v2.10.6) (2025-11-25)


### Bug Fixes

* sync version to v2.10.5 and update semantic-release config ([cc5aa84](https://github.com/hypersec-io/hs-lib/commit/cc5aa844f19798df27dd7adb58204accd80be9fa))

## [2.10.5](https://github.com/hypersec-io/hs-lib/compare/v2.10.4...v2.10.5) (2025-11-25)


### Bug Fixes

* remove duplicate pytest markers in pyproject.toml ([121952e](https://github.com/hypersec-io/hs-lib/commit/121952e7e7786181931f26ae8ac199812cba8cc9))

## [2.10.4](https://github.com/hypersec-io/hs-lib/compare/v2.10.3...v2.10.4) (2025-11-25)


### Bug Fixes

* update ci submodule with improved commit-msg hook ([52829a0](https://github.com/hypersec-io/hs-lib/commit/52829a03494c9e645a5d07ed7632be4013cfaf94))

## [2.10.3](https://github.com/hypersec-io/hs-lib/compare/v2.10.2...v2.10.3) (2025-11-25)


### Bug Fixes

* update CI submodule and add test job to workflow (DFE-540) ([380a56b](https://github.com/hypersec-io/hs-lib/commit/380a56be6749dcb2011818fc26adb57db001e5d1))

## [2.10.2](https://github.com/hypersec-io/hs-lib/compare/v2.10.1...v2.10.2) (2025-11-25)


### Bug Fixes

* add Python venv setup step to workflow (workaround BUG-CI-001) ([2d4423a](https://github.com/hypersec-io/hs-lib/commit/2d4423a05a5c64178d18396219cc4e8cf8209b44))
* clean ci.yaml and set fail_fast: true as default ([455d90b](https://github.com/hypersec-io/hs-lib/commit/455d90b54478d1d5277bd3f45336c0cfb7e7881d))
* create .env in project root (not ci-local/) ([8176984](https://github.com/hypersec-io/hs-lib/commit/817698436d05a311d5a63da8d0c3b6be685b25be))
* explicitly specify Python 3.12 for bootstrap ([646be96](https://github.com/hypersec-io/hs-lib/commit/646be96f6ed604a6299660986f3d4ef931989a7f))
* force uv to use Python 3.12 via UV_PYTHON env var ([200ed61](https://github.com/hypersec-io/hs-lib/commit/200ed6129b8a1d9718866add18f0a9e916af8c8a))
* install twine in workflow (workaround BUG-CI-002) ([e153fdd](https://github.com/hypersec-io/hs-lib/commit/e153fdddf2ea7832a3dbed79acfc6bd38aea93b0))
* merge DFE-524 branch (ci workflow paths) ([b2c039f](https://github.com/hypersec-io/hs-lib/commit/b2c039f02b6f7ebcb889eb6c2129c59f42059c6d))
* migrate to HyperCI modular architecture (DFE-523) ([132b8d0](https://github.com/hypersec-io/hs-lib/commit/132b8d0d1ca78481b2fd870968b652c1ba2fe6e3))
* migrate to separate ci and ai submodules ([ffd9b25](https://github.com/hypersec-io/hs-lib/commit/ffd9b25b63d17912e13a8f54317e4b4fab5f5f5e))
* minimal ci.yaml (remove all defaults including nuitka.enabled) ([e3273d9](https://github.com/hypersec-io/hs-lib/commit/e3273d9e235a10994d08f19f8d7cf0fce5f9e867))
* move build_type to python section (applies to all builds) ([ba05c2f](https://github.com/hypersec-io/hs-lib/commit/ba05c2fbacee231da09e6ec21a791c5aeb993e3a))
* prepend Python 3.12 to PATH for bootstrap ([1f71b81](https://github.com/hypersec-io/hs-lib/commit/1f71b815f4a1d6e230d58878498894c92ec7f28b))
* re-enable BuildJet after GitHub App reinstall ([d1f159f](https://github.com/hypersec-io/hs-lib/commit/d1f159f23b8434690babf2c6749fa08dc632cc12))
* remove [@main](https://github.com/main) refs from local workflow paths ([32b93d4](https://github.com/hypersec-io/hs-lib/commit/32b93d4a12a35c4fe0a2dd5b5c88c8752dd4823b))
* remove non-existent --python-version flag from workflow ([5d40934](https://github.com/hypersec-io/hs-lib/commit/5d40934b720d961271567317a97a9eaf63e40ea2))
* rename release.yml to publish.yml for consistency ([dc52bc2](https://github.com/hypersec-io/hs-lib/commit/dc52bc29e041bd5b8ac3465d0d9e094ca66323e4))
* revert to ubuntu-latest (BuildJet access issue) ([25be898](https://github.com/hypersec-io/hs-lib/commit/25be898da75a6e7ce9f92f50a64ee84dfdd7cb2e))
* trigger semantic-release for e2e testing (DFE-524) ([ff83b58](https://github.com/hypersec-io/hs-lib/commit/ff83b58c4906d01c7404260bf403a6e9f94810fc))
* update CI and regenerate publish workflow (DFE-539) ([6658871](https://github.com/hypersec-io/hs-lib/commit/6658871337222a78b7e323dc5d8f805cb59ae80f))
* update ci submodule (fix pyproject.toml merge bug) ([826878d](https://github.com/hypersec-io/hs-lib/commit/826878d7bf13940756cac8037dd90b09bdab5ea3))
* update ci submodule (reusable workflows added) ([e5d47c5](https://github.com/hypersec-io/hs-lib/commit/e5d47c5d81da87e53bd23df8102a11413585bda9))
* update ci submodule (reusable workflows in .github/workflows) ([3dad6ef](https://github.com/hypersec-io/hs-lib/commit/3dad6ef0b98a3f9cab4b43d929b35f864cfc284d))
* update ci submodule to feat/DFE-523 dev branch ([daa4820](https://github.com/hypersec-io/hs-lib/commit/daa48205958a8d64895fb58aa4a989669c8f6fe9))
* update CI submodule to latest with uv 0.9.11 support (DFE-524) ([ecc7eb2](https://github.com/hypersec-io/hs-lib/commit/ecc7eb2742a00462855648b5416de64b3998c6c4))
* update ci submodule to main (DFE-523 merged) ([1da83fe](https://github.com/hypersec-io/hs-lib/commit/1da83feedb59028ce09c7638a4d54832e1c31243))
* update ci-publish workflow for new ci structure ([6f7801a](https://github.com/hypersec-io/hs-lib/commit/6f7801a23d15ce404678a16f252e2aa9e7e9ce16))
* update to new workflow paths (DFE-523) ([0490701](https://github.com/hypersec-io/hs-lib/commit/0490701563db1cde2e9433f3888da1ad0487e459))
* update workflows with checkout fix (DFE-539) ([7d711e5](https://github.com/hypersec-io/hs-lib/commit/7d711e507cf237d317f017325a2a687ccba71e0c))
* use local ci/workflows path (DFE-523) ([ce9daa1](https://github.com/hypersec-io/hs-lib/commit/ce9daa155418c2af9595eee63b558e348874d2cb))
* use Python 3.12 in workflow (hs-lib requires 3.12+) ([d6b01fd](https://github.com/hypersec-io/hs-lib/commit/d6b01fdd427774e81f868c0d80c595467473a9ab))
* use remote ci repository paths for reusable workflows ([d0462cd](https://github.com/hypersec-io/hs-lib/commit/d0462cddca99152962c16ae8682fd94fb7a058a4))

# [3.0.0](https://github.com/hypersec-io/hs-lib/compare/v2.8.8...v3.0.0) (2025-11-13)


## BREAKING CHANGES

### Package Renamed: hyperlib → hs-lib

The package has been renamed to avoid collision with existing PyPI packages and ensure rename-safety:

- **PyPI package name**: `hyperlib` → `hs-lib`
- **Python import name**: `hyperlib` → `hs_lib`
- **GitHub repositories**:
  - `hypersec-io/hyperlib` → `hypersec-io/hs-lib`
  - `hypersec-io/hyperci` → `hypersec-io/hs-ci`

### Migration Required

**Update your code:**

```python
# OLD
from hyperlib import Application, logger
import hyperlib

# NEW
from hs_lib import Application, logger
import hs_lib
```

**Update dependencies:**

```toml
# pyproject.toml
dependencies = [
    "hs-lib>=3.0.0",  # was: hyperlib>=2.8.8
]
```

```bash
# Install commands
pip install hs-lib       # was: pip install hyperlib
uv add hs-lib            # was: uv add hyperlib
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

* rename package from hyperlib to hs-lib for PyPI collision avoidance ([bc4dacd](https://github.com/hypersec-io/hs-lib/commit/bc4dacd))
* update repository URLs after renaming to hs-lib and hs-ci ([9fd2e75](https://github.com/hypersec-io/hs-lib/commit/9fd2e75))
* update ci submodule URL to renamed hs-ci repository ([9fd2e75](https://github.com/hypersec-io/hs-lib/commit/9fd2e75))

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
