# Test support

`hyperi_pylib.deployment.test_support` -- reusable helpers for the
deployment-contract e2e suite. Std-library only; no new runtime deps.
Consumers import these into their own `tests/e2e/` modules; the
canonical template lives at `tests/e2e/test_contract_artefacts.py`.

```python
from hyperi_pylib.deployment.test_support import (
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

Mirrors `hyperi_rustlib::deployment::test_support` once that lands;
both emit the same `HYPERCI-SKIP[contract-e2e][...]:` prefix so the
hyperi-ci runner aggregates skip counts uniformly.

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
    raw = os.environ.get("HYPERI_E2E_CLUSTER", "").lower()
    return raw in ("1", "true", "yes", "on")
```

Tier B (the cluster-creating tests) opts in via the `HYPERI_E2E_CLUSTER`
env var. The default is off so local `pytest` runs don't spin up
kind clusters by accident. CI sets it explicitly on the e2e job.

---

## `skip(tier, test_name, reason)`

Canonical skip helper. Writes the line:

```
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
| Linux / macOS / WSL / Git Bash | `~/.cache/hyperi-ai/contract-e2e-skips.log` |
| Native Windows | `%LOCALAPPDATA%\hyperi-ai\Cache\contract-e2e-skips.log` |

NEVER `/tmp` -- AGENT-RULES Rule 4. The parent dir is mkdir-p'd on
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

- Cluster name = `f"pylib-e2e-{sha256(test_name)[:12]}"` -- 12-char
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
guard = ensure_kind_cluster("test_tier_b_helm_install_on_kind")
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
pylib's own deployment subsystem AND serves as the template Python
DFE consumers copy into their own `tests/e2e/`. Five test functions:

### Tier A (cluster-less; runs anywhere the tool is present)

| Test | Exercises | Tool required |
|---|---|---|
| `test_tier_a_dockerfile_builds_and_image_runs` | identity `LABEL`s survive `docker build` -> `docker inspect` round-trip | `docker` |
| `test_tier_a_chart_lint_and_template` | `helm template` renders the chart; `Chart.yaml` annotations carry identity | `helm` |
| `test_tier_a_argocd_application_kubeconform` | `kubeconform -strict` accepts the generated Application; YAML re-parse shows identity annotations | `kubeconform` |

Each test calls `skip("tier-a", test_name, reason)` when its tool is
missing -- never silently passes.

### Tier B (env-gated; brings up a real kind cluster)

| Test | Exercises | Tools required |
|---|---|---|
| `test_tier_b_helm_install_on_kind` | full `helm install` on a kind cluster with a public canary image (`public.ecr.aws/docker/library/nginx:alpine` -- no creds needed) | `helm` + `kind` + `kubectl` + `HYPERI_E2E_CLUSTER=1` |
| `test_tier_b_argocd_application_sync_on_kind` | `kubectl apply` the generated Application against a kind cluster with ArgoCD installed; round-trip the identity annotations through `kubectl get application -o jsonpath` | `kubectl` + `kind` + `HYPERI_E2E_CLUSTER=1` |

The ArgoCD install manifest is pinned to a specific upstream tag --
consumers updating that should bump intentionally.

---

## Markers + tier mapping

The template uses two pytest markers, declared in `pyproject.toml`:

- `@pytest.mark.integration` -- Tier A. Runs in CI's integration job
  with docker-compose services available.
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
3. Replace `_make_contract()` / `_make_argo()` with your actual
   contract + ArgoCD config.
4. Keep `VALID_SHA` / `VALID_REF` constants -- they're test
   placeholders, not production values.
5. Wire the e2e job in your CI to set `HYPERI_E2E_CLUSTER=1` and
   install `kind` + `kubectl` + `helm` + `kubeconform`.

---

## Related

- [IDENTITY.md](IDENTITY.md)
- [ARTEFACTS.md](ARTEFACTS.md)
- [CONTRACT.md](CONTRACT.md)
- [KEDA.md](KEDA.md)
- [NATIVE-DEPS.md](NATIVE-DEPS.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../README.md](../README.md)
