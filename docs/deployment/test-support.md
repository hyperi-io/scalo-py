# Test support

`scalo.deployment.test_support` -- reusable helpers for the deployment-contract e2e suite. Beyond the standard library it imports `pytest`, and the Kafka fixtures import `confluent-kafka`. Consumers import these into their `tests/e2e/` modules, and the template lives at `tests/e2e/test_contract_artefacts.py`.

```python
from scalo.deployment.test_support import (
    SKIP_PREFIX,
    docker_available, docker_unreachable_reason, buildx_available, helm_available,
    kubeconform_available, kind_available, kubectl_available,
    docker_build_cmd, docker_env,
    tier_b_enabled,
    skip,
    docker_empty_creds_json,
    wait_until,
    KindClusterGuard, ensure_kind_cluster,
)
```

scalo-rs's `scalo::deployment::test_support` writes the same `HYPERCI-SKIP[contract-e2e][<tier>]:` skip line.

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
| `clickhouse_database` | test | a `Replicated` database for the test alone, made `ON CLUSTER` and dropped after |
| `shared_kafka` | session | `KafkaService`: bootstrap and the librdkafka `client_config` |
| `kafka_topics` | test | `make(label, partitions=3)` creating run-prefixed topics, deleted after |
| `kafka_group` | test | `kafka_group(label)` naming a run-prefixed consumer group, under the grant a pet broker enforces |
| `shared_openbao` | session | `OpenBaoService`: address and root token |

- The controller names the run, the first worker to ask starts each container under a lock in `<rootdir>/.tmp/shared-services/<run>/`, and the rest join it. The controller removes them at the end, and a watcher removes each one if the controller dies first.
- Ports bind 127.0.0.1 on the daemon host. An `ssh://` daemon gets an `ssh -L` tunnel per port, and a remote `tcp://` daemon needs `HYPERI_TEST_DOCKER_BIND`.
- The ClickHouse password and the OpenBao token are generated per run and never logged.
- Containers have `io.hyperi.test.*` owner labels, and each create removes the suite's containers whose owner has gone.
- ClickHouse and Kafka use the always-present pet named by `HYPERI_TEST_*` settings (the environment, then `.env`, then the file `HYPERI_TEST_ENV_FILE` names) when a quick probe answers, never in CI or under the full tier. A Kafka pet's groups take `HYPERI_TEST_KAFKA_GROUP_PREFIX`, else its topic prefix.
- Without Docker a test skips on a developer's machine, and fails in CI or under `HYPERCI_TEST_TIER=full`. `unavailable(reason)` applies the same rule to a test's prerequisites.
- POSIX only: process identity comes from `/proc` or `ps`, and the lock from `fcntl`.

A service the plugin does not cover takes a `ServiceSpec` (image, ports, env, `secret_env`, files, readiness by HTTP, log line or command) to `shared_service.acquire(suite_for(config), spec)`. A test that stops or reconfigures its server holds one alone with `start_alone(suite, spec, container_name(suite, test, service))`. The pinned images and their specs are `scalo.deployment.test_support.services`.

## Tool probes

The six probes are cached with `functools.cache`, so each tool shells out at most once per process. They return `True` when the binary is on `$PATH` AND its trivial `info`/`version` invocation returns zero within 10s.

| Probe | Checks |
|---|---|
| `docker_available()` | `which docker` + `docker version --format '{{.Server.Version}}'` (daemon must be reachable, not just CLI). Retries in CI and the full tier |
| `buildx_available()` | `which docker` + `docker buildx version` |
| `helm_available()` | `which helm` + `helm version` |
| `kubeconform_available()` | `which kubeconform` only (no execution) |
| `kind_available()` | `which kind` + `kind version` |
| `kubectl_available()` | `which kubectl` + `kubectl version --client` (no server needed) |

Probes never raise. A timeout, `FileNotFoundError` or other `OSError` returns `False`.

The first calls of a job can stall on a hosted runner's daemon. Under `CI` or `HYPERCI_TEST_TIER=full`, `docker_available()` asks again every 2 s until 30 s have passed, allowing 20 s a call. Elsewhere it asks once, allowing 10 s, so a stopped Docker Desktop does not stall every collection.

`docker_unreachable_reason()` returns why it said no (the exit status and last stderr line, or the timeout) and None when the daemon answers, so a skip reason can carry it. Call both from the test body, not at import, because a module-level `skipif` runs while every xdist worker is still collecting.

`docker_build_cmd(tag, *, dockerfile="Dockerfile", context=".", no_cache=False)` returns the build argv: `docker buildx build --load` when buildx answers, else `docker build`. Use it rather than a hand-written `["docker", "build", ...]`, because the legacy builder ignores the active `docker context`.

## Tier B env gate

Tier B (the cluster-creating tests) opts in through `E2E_CLUSTER`: `tier_b_enabled()` is true when it is `1`, `true`, `yes` or `on`, in any case. Once an env prefix is set, the variable read is `<PREFIX>_E2E_CLUSTER`. The default is off, so a local `pytest` run doesn't spin up kind clusters by accident, and nothing in scalo-py's CI sets it.

## `skip(tier, test_name, reason)`

Canonical skip helper. Writes the line:

```text
HYPERCI-SKIP[contract-e2e][<tier>]: <test_name>: <reason>
```

to `sys.stderr` AND appends it to a side-channel log, then calls
`pytest.skip(reason)` (which raises -- callers don't need a trailing
`return`).

`tier` must be `"tier-a"` or `"tier-b"`, and any other value raises `ValueError`. The greppable prefix is exposed as `SKIP_PREFIX = "HYPERCI-SKIP[contract-e2e]"`. A log write that fails with `OSError` is dropped, and the skip still happens.

### Side-channel log path

| Platform | Path |
|---|---|
| Linux / macOS / WSL / Git Bash | `~/.cache/scalo/contract-e2e-skips.log` |
| Native Windows | `%LOCALAPPDATA%\scalo\Cache\contract-e2e-skips.log` |

Never `/tmp`, which is world-readable and cleaned unpredictably. The parent dir is mkdir-p'd on
first write. File mode is append, UTF-8, LF newlines.

## `docker_empty_creds_json()`

Returns a Docker `config.json` with empty `auths`, so public base images pull anonymously whatever credential helper the host has. It has `cliPluginsExtraDirs` for every CLI plugin directory that exists, so `docker buildx` still resolves under the new config directory.

`docker_env(config_dir)` returns the environment to build with: `DOCKER_CONFIG` set to `config_dir`, and `DOCKER_HOST` set to the active context's endpoint, which a new config directory would otherwise lose. The template's Tier A build uses both:

```python
with tempfile.TemporaryDirectory() as cfg_dir:
    (Path(cfg_dir) / "config.json").write_text(docker_empty_creds_json(), encoding="utf-8")
    env = docker_env(cfg_dir)
    subprocess.run(docker_build_cmd(tag), cwd=build_dir, env=env, check=True)
```

## `wait_until(deadline_seconds, interval_seconds, predicate)`

Generic poll helper. Calls `predicate()` until it returns `True` or `deadline_seconds` elapses, sleeping `interval_seconds` between calls. Returns `predicate()`'s final value: it re-evaluates once at the deadline, so a transition that lands on the boundary isn't missed. Uses `time.monotonic()`, so a clock change does not move the deadline.

## `KindClusterGuard`

```python
@dataclass
class KindClusterGuard:
    test_name: str
    kubeconfig: Path | None = None
```

A context manager for the lifecycle of a uniquely-named kind cluster.

- Cluster name = `f"scalo-py-e2e-{sha256(test_name)[:12]}"` -- 12-char
  digest keeps it under K8s 63-char name limits and gives parallel
  pytest-xdist workers distinct clusters.
- `__enter__` raises `RuntimeError` when a prereq is missing, else returns `self`. The cluster
  itself is brought up by the test body via `subprocess.run(["kind",
  "create", "cluster", "--name", guard.name, ...])` so individual
  tests can pass their `--image` / `--config` flags.
- `__exit__` runs `kind delete cluster --name <name>` with
  `check=False` and a 60s timeout -- a failing test doesn't suppress
  cleanup.

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

## The e2e template

`tests/e2e/test_contract_artefacts.py` is dual-purpose: it self-tests scalo-py's deployment subsystem AND is the template Python consumers copy into their `tests/e2e/`. One test function:

| Test | Exercises | Tool required |
|---|---|---|
| `test_tier_a_dockerfile_builds_and_image_runs` | identity `LABEL`s survive `docker build` -> `docker inspect` round-trip | `docker` |

It calls `skip("tier-a", test_name, reason)` when docker is missing --
never silently passes. The Kubernetes objects come from the
scalo-service library chart in scalo-rs, whose tests render and
validate them, so the template has no chart or cluster test. The
Tier B helpers above stay for a consumer that brings up its cluster.

## Markers + tier mapping

scalo-py's `pyproject.toml` declares the markers, among them `integration` (Docker required), `e2e` (a cluster required) and `full`. Its `addopts` passes `-m 'not full'`.

The template's test has `@pytest.mark.integration` and `@pytest.mark.full`, so it runs only in hyperi-ci's full tier. hyperi-ci's `core` tier keeps the project's `addopts -m`, and its `full` tier passes `-m <test.full.python.markers>` instead, every test by default. Under `full` a skip fails the run unless its reason matches `test.full.python.allow_skip`.

## Consumer copy-paste recipe

1. Copy `tests/e2e/test_contract_artefacts.py` into your repo at the
   same path.
2. Replace `_mock_binary_script()` with your entrypoint (e.g.
   `pip install -e .` in the build context + invoke your
   console-script via `--entrypoint`).
3. Replace the hand-built `Dockerfile` in the test body with your app's
   generated one (`generate_dockerfile(contract, identity=identity)`).
4. Keep `VALID_SHA` / `VALID_REF` constants -- they're test
   placeholders, not production values.
