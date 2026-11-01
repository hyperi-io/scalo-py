# Test support

`scalo.deployment.test_support` -- reusable helpers for the
deployment-contract e2e suite. Std-library only; no new runtime deps.
Consumers import these into their own `tests/e2e/` modules; the
canonical template lives at `tests/e2e/test_contract_artefacts.py`.

```python
from scalo.deployment.test_support import (
    SKIP_PREFIX,
    docker_available, helm_available, kubeconform_available,
    kind_available, kubectl_available,
    tier_b_enabled,
    skip,
    docker_empty_creds_json,
    wait_until,
    KindClusterGuard, ensure_kind_cluster,
)
```

Mirrors `scalo::deployment::test_support` once that lands;
both emit the same `HYPERCI-SKIP[contract-e2e][...]:` prefix so the
hyperi-ci runner aggregates skip counts uniformly.

---

## Shared test services

One ClickHouse, Kafka and OpenBao per pytest run, shared by every xdist worker, the way scalo-rs's `deployment::test_support::shared_service` does it for nextest. Load the plugin from the root `conftest.py` and name the repo for container names and labels:

```python
# conftest.py
pytest_plugins = ["scalo.deployment.test_support.pytest_plugin"]
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
shared_service_repo = "my-app"
```

| Fixture | Scope | Gives |
|---|---|---|
| `shared_clickhouse` | session | `ClickHouseService`: host, ports, user, password, cluster, and `execute(sql, params)` over HTTP |
| `clickhouse_database` | test | a `Replicated` database of the test's own, made `ON CLUSTER` and dropped after |
| `shared_kafka` | session | `KafkaService`: bootstrap and the librdkafka `client_config` |
| `kafka_topics` | test | `make(label, partitions=3)` creating run-prefixed topics, deleted after |
| `shared_openbao` | session | `OpenBaoService`: address and root token |

- The controller names the run, the first worker to ask starts each container under a lock in `<rootdir>/.tmp/shared-services/<run>/`, and the rest join it. The controller removes them at the end, and a watcher removes each one if the controller dies first.
- Ports bind 127.0.0.1 on the daemon host. An `ssh://` daemon gets an `ssh -L` tunnel per port, and a remote `tcp://` daemon needs `HYPERI_TEST_DOCKER_BIND`.
- The ClickHouse password and the OpenBao token are generated per run and never logged.
- Containers carry `io.hyperi.test.*` owner labels, and each create removes the suite's containers whose owner has gone.
- ClickHouse and Kafka use the always-present pet named by `HYPERI_TEST_*` settings (the environment, then `.env`, then the file `HYPERI_TEST_ENV_FILE` names) when a quick probe answers, never in CI or under the full tier.
- Without Docker a test skips on a developer's machine, and fails in CI or under `HYPERCI_TEST_TIER=full`. `unavailable(reason)` applies the same rule to a test's own prerequisites.

A service the plugin does not cover takes a `ServiceSpec` (image, ports, env, `secret_env`, files, readiness by HTTP, log line or command) to `shared_service.acquire(suite_for(config), spec)`. A test that stops or reconfigures its server holds one alone with `start_alone(suite, spec, container_name(suite, test, service))`. The pinned images and their specs are `scalo.deployment.test_support.services`.

---

## Tool probes

All five probes are `@lru_cache`d -- each tool shells out at most
once per process. They return `True` when the binary is on `$PATH`
AND its trivial `--version`/`info`/`version --client` invocation
returns zero within 10s.

| Probe | Checks |
|---|---|
| `docker_available()` | `which docker` + `docker info` (daemon must be reachable, not just CLI) |
| `helm_available()` | `which helm` + `helm version` |
| `kubeconform_available()` | `which kubeconform` only (no execution) |
| `kind_available()` | `which kind` + `kind version` |
| `kubectl_available()` | `which kubectl` + `kubectl version --client` (no server needed) |

Probes never raise. A timeout or `FileNotFoundError` returns `False`.

---

## Tier B env gate

```python
def tier_b_enabled() -> bool:
    raw = os.environ.get("E2E_CLUSTER", "").lower()
    return raw in ("1", "true", "yes", "on")
```

Tier B (the cluster-creating tests) opts in via the `E2E_CLUSTER`
env var. The default is off so local `pytest` runs don't spin up
kind clusters by accident. CI sets it explicitly on the e2e job.

---

## `skip(tier, test_name, reason)`

Canonical skip helper. Writes the line:

```text
HYPERCI-SKIP[contract-e2e][<tier>]: <test_name>: <reason>
```

to `sys.stderr` AND appends it to a side-channel log, then calls
`pytest.skip(reason)` (which raises -- callers don't need a trailing
`return`).

`tier` must be `"tier-a"` or `"tier-b"`; other values raise
`ValueError`. The greppable prefix is exposed as
`SKIP_PREFIX = "HYPERCI-SKIP[contract-e2e]"` for runner-side
aggregation.

### Side-channel log path

| Platform | Path |
|---|---|
| Linux / macOS / WSL / Git Bash | `~/.cache/scalo/contract-e2e-skips.log` |
| Native Windows | `%LOCALAPPDATA%\scalo\Cache\contract-e2e-skips.log` |

Never `/tmp`, which is world-readable and cleaned unpredictably. The parent dir is mkdir-p'd on
first write. File mode is append, UTF-8, LF newlines.

---

## `docker_empty_creds_json()`

Returns `'{"auths": {}}'`. Write it into a tempdir's `config.json`
and point Docker at it via `DOCKER_CONFIG=<tempdir>` to bypass
credential helpers that don't exist in CI (`docker-credential-*`
binaries on minimal images). The Tier A Docker build test in the
template uses this to keep `docker build` working without registry
auth.

```python
with tempfile.TemporaryDirectory() as cfg_dir:
    (Path(cfg_dir) / "config.json").write_text(docker_empty_creds_json())
    env = {**os.environ, "DOCKER_CONFIG": cfg_dir}
    subprocess.run(["docker", "build", ...], env=env, check=True)
```

---

## `wait_until(deadline_seconds, interval_seconds, predicate)`

Generic poll helper. Calls `predicate()` until it returns `True` or
`deadline_seconds` elapses; sleeps `interval_seconds` between calls.
Returns `predicate()`'s final value (re-evaluates once at deadline
expiry so a transition that lands exactly on the boundary isn't
missed). Uses `time.monotonic()` for clock-skew immunity.

---

## `KindClusterGuard`

```python
@dataclass
class KindClusterGuard:
    test_name: str
    kubeconfig: Path | None = None
```

A context-manager-shaped lifecycle wrapper for a uniquely-named kind
cluster.

- Cluster name = `f"scalo-py-e2e-{sha256(test_name)[:12]}"` -- 12-char
  digest keeps it under K8s 63-char name limits and gives parallel
  pytest-xdist workers distinct clusters.
- `__enter__` validates prereqs and returns `self`. The cluster
  itself is brought up by the test body via `subprocess.run(["kind",
  "create", "cluster", "--name", guard.name, ...])` so individual
  tests can pass their own `--image` / `--config` flags.
- `__exit__` runs `kind delete cluster --name <name>` with
  `check=False` and a 60s timeout -- a failing test doesn't suppress
  cleanup.

---

## `ensure_kind_cluster(test_name)`

The factory consumers actually call. Checks all three Tier B prereqs
(`kind_available`, `kubectl_available`, `tier_b_enabled`) and either
returns an entered `KindClusterGuard` or calls `skip(...)` with a
detailed reason listing the missing pieces:

```python
guard = ensure_kind_cluster("test_tier_b_service_starts_on_kind")
if guard is None:
    return  # unreachable -- ensure_kind_cluster raised pytest.skip
try:
    # bring cluster up via `kind create cluster --name guard.name ...`
    # exercise the assertion
    ...
finally:
    guard.__exit__(None, None, None)
```

---

## The e2e template

`tests/e2e/test_contract_artefacts.py` is dual-purpose: it self-tests
scalo-py's own deployment subsystem AND serves as the template Python
consumers copy into their own `tests/e2e/`. One test function:

| Test | Exercises | Tool required |
|---|---|---|
| `test_tier_a_dockerfile_builds_and_image_runs` | identity `LABEL`s survive `docker build` -> `docker inspect` round-trip | `docker` |

It calls `skip("tier-a", test_name, reason)` when docker is missing --
never silently passes. The Kubernetes objects come from the
scalo-service library chart in scalo-rs, whose own tests render and
validate them, so the template carries no chart or cluster test. The
Tier B helpers above stay for a consumer that brings up its own cluster.

---

## Markers + tier mapping

Two pytest markers, declared in `pyproject.toml`, map to the tiers:

- `@pytest.mark.integration` -- Tier A, which the template uses. Runs
  wherever Docker is, against the shared services above.
- `@pytest.mark.e2e` -- Tier B. Env-gated and only runs in the
  dedicated e2e job that has kind installed.

Map your consumer tests to the same markers; `hyperi-ci`'s test
runner already knows how to split them into the right CI jobs.

---

## Consumer copy-paste recipe

1. Copy `tests/e2e/test_contract_artefacts.py` into your repo at the
   same path.
2. Replace `_mock_binary_script()` with your real entrypoint (e.g.
   `pip install -e .` in the build context + invoke your
   console-script via `--entrypoint`).
3. Replace the hand-built `Dockerfile` in the test body with your app's
   generated one (`generate_dockerfile(contract, identity=identity)`).
4. Keep `VALID_SHA` / `VALID_REF` constants -- they're test
   placeholders, not production values.

---

## Related

- [identity.md](identity.md)
- [artefacts.md](artefacts.md)
- [contract.md](contract.md)
- [keda.md](keda.md)
- [native-deps.md](native-deps.md)
- [../integration.md](../integration.md)
- [../README.md](../README.md)
