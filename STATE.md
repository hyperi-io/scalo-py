# hs-pylib - Project State

**Repository**: <https://github.com/hypersec-io/hs-pylib>
**Type**: Python package (shared library)
**Purpose**: Enterprise infrastructure for all HyperSec Python projects

---

## Session Management

**New session?** Run `/start` to initialise (reads STATE.md, TODO.md, standards)
**Save progress:** Run `/save` to checkpoint

---

## Current Status (2025-12-05)

**Versions:**

- hs-pylib: v2.13.0
- hs-ci: v1.37.0 (GitHub Actions architecture)

**Build type:** Native wheel only (no Nuitka)

---

## Latest Session (2025-12-05)

### Completed: hs_pylib.kafka Module

**Branch:** `feat/DFE-553/add-kafka-library`
**Commit:** `2a9b38b`
**Files:** 16 files, 7505 insertions

Implemented complete Kafka client library:

- **Core clients:** KafkaClient, KafkaConsumer, KafkaProducer
- **Async variants:** AsyncKafkaClient, AsyncKafkaConsumer, AsyncKafkaProducer
- **Admin (KafkaAdmin):** Topic config, retention, cleanup, partition management
- **Offset reset:** `reset_offsets_to_timestamp()`, `reset_offsets_to_earliest()`, `reset_offsets_to_latest()`
- **Utilities:** SchemaAnalyser (JSON inference), sampling (reservoir, time-bounded)
- **Metrics:** KafkaMetricsCollector (librdkafka stats → Prometheus)
- **Config:** File loading (.properties, .json, .yaml, .ini), env vars (KAFKA_*)

**Tests:** 160 unit tests + 19 integration tests (faker data)

**Backlog documented:** JSON key-value offset seek (in admin.py:552-582)

---

## Active Work Scope

**Source:** `/projects/dfe-control-plane/HS-LIB-UPDATE.md`

This file is the **living scope document** for hs-pylib improvements. It is maintained in the dfe-control-plane project during integration testing and will be updated as work progresses.

**Current priorities (from HS-LIB-UPDATE.md):**

1. `hs_pylib.http` - HttpClient with Stamina retries (solves B113, adds observability)
2. `hs_pylib.metrics.fastapi` - Middleware + router for standard /metrics
3. `hs_pylib.metrics.db` - DB query metrics helpers
4. `hs_pylib.cache` - Deferred until needed

**Always re-read HS-LIB-UPDATE.md at session start** - it may have changed.

---

## CI Architecture (hs-ci v1.37.x)

**IMPORTANT:** hs-ci was completely rewritten. No more `./ci/run` scripts.

### Key Changes from Old CI

| Old (v1.11.x) | New (v1.19.x) |
|---------------|---------------|
| `./ci/run check` | GitHub Actions workflows |
| `./ci/run build` | GitHub Actions workflows |
| `./ci/bootstrap install` | GitHub Actions setup actions |
| `ci.yaml` | `.hypersec-ci.yaml` |
| Python scripts in `modules/` | Composable GitHub Actions in `actions/` |

### Configuration

**Single source:** `.hypersec-ci.yaml` (not `ci.yaml`, not `pyproject.toml`)

**Precedence:** env vars (`HYPERCI_*`) > `.hypersec-ci.yaml` > `ci/defaults.yaml`

**Current hs-pylib config:**

```yaml
language: python
quality:
  enabled: true
test:
  enabled: true
  coverage: true
build:
  enabled: true
  strategies:
    - native    # Standard wheel only, no Nuitka
publish:
  enabled: true
python:
  source_dir: src
```

### Local Development

No `./ci/run` anymore. Use standard tools directly:

```bash
# Quality checks
ruff check src/ tests/
ruff format src/ tests/

# Tests
pytest tests/

# Build
uv build
```

### CI Pipeline Flow

```text
push → CI workflow (quality → test → build)
tag  → Semantic Release → Publish workflow
```

### Attach/Update CI

```bash
# Update ci submodule
git -C ci fetch origin main
git -C ci reset --hard origin/main
git add ci && git commit -m "chore: update ci submodule"

# Regenerate workflows
./ci/attach.sh --force
```

---

## Architecture Notes

### hs-ci Release System

**hs-ci itself:** semantic-release CLI + .releaserc.json (Node.js)
**Projects using hs-ci:** GitHub Actions workflows (ci.yml, publish.yml, semantic-release.yml)

### Test Projects

- `/projects/ci/tests/external/projects/python/` - Python test projects
- ci-test-simple-cli, ci-test-simple-package

---

## Quick Reference

**Python requirement:** 3.12+

**Local commands:**

```bash
ruff check src/ tests/       # Lint
ruff format src/ tests/      # Format
pytest tests/                # Test
uv build                     # Build wheel
```

**Update ci submodule:**

```bash
git -C ci reset --hard origin/main
./ci/attach.sh --force
git add ci .github/ .hypersec-ci.yaml .releaserc.json
git commit -m "chore: update ci submodule to vX.Y.Z"
```

---

**Last Updated:** 2025-12-05
