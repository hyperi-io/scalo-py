# Harness

Subprocess and function execution with smart hang detection. Catches
processes that go silent without exiting (the most common CI failure
mode) by watching for activity — output, file modifications, success /
failure patterns — and terminating early when monitoring goes quiet.
Ships in the base package; uses only stdlib.

```python
from hyperi_pylib.harness import (
    run, smart_run, smart_run_function,
    ActivityIndicator, SmartTimeoutMonitor, FunctionTimeoutMonitor,
    HarnessResult, TerminationReason,
)
```

---

## Quick start

```python
from hyperi_pylib.harness import smart_run

result = smart_run(
    ["pytest", "tests/"],
    description="run pytest",
    activity_timeout=120,   # 2 minutes silent = hang
    total_timeout=1800,     # 30 minutes wall clock
)
if not result.success:
    print(f"terminated because: {result.termination_reason}")
```

---

## Why this exists

A wall-clock timeout alone doesn't catch the "process is alive but
isn't doing anything" failure mode. The harness watches three activity
signals — log output, file modifications, success/failure patterns —
and terminates the moment activity goes silent past
`activity_timeout`, even if `total_timeout` hasn't elapsed.

Use cases:

- Running pytest in CI without false-positive hangs swallowing the run
- Container build steps that go silent during slow layer pushes
- K8s deployment verification (`kubectl wait`)
- Anything that prints progress and hangs in known ways

---

## `run()` — straightforward subprocess

```python
from hyperi_pylib.harness import run

result = run(
    ["docker", "build", "-t", "myapp", "."],
    timeout=600,
    cwd="/build",
    log_file=Path("/tmp/build.log"),
    log_label="Container: myapp",
)
```

Thin wrapper over `subprocess.run` with optional logging to file. Useful
when you want a CompletedProcess back and don't need activity-based
monitoring. `pytest_fail=True` swaps `raise` for `pytest.fail(...)` —
saves a few lines in test helpers.

| Arg | Default | Meaning |
|-----|---------|---------|
| `timeout` | 30 | Wall-clock seconds. |
| `check` | True | Raise `CalledProcessError` on non-zero exit. |
| `cwd` | None | Working directory. |
| `log_file` | None | Append stdout/stderr/exit-code to this file with a label. |
| `log_label` | None | Header for the log section. |
| `pytest_fail` | False | Use `pytest.fail` instead of raising. |

---

## `smart_run()` — activity-aware subprocess

```python
from hyperi_pylib.harness import smart_run

result = smart_run(
    ["pytest", "-v", "tests/integration/"],
    description="integration suite",
    activity_timeout=120,
    total_timeout=1800,
    failure_patterns=[r"FAILED", r"Error:", r"Traceback"],
    success_patterns=[r"PASSED", r"passed in"],
    progress_patterns=[r"::test_", r"Running"],
)

if result.termination_reason == TerminationReason.NO_ACTIVITY:
    # process went silent for too long
    ...
elif result.termination_reason == TerminationReason.FAILURE_DETECTED:
    # one of failure_patterns matched in the output
    ...
```

`smart_run` ships with sensible default patterns covering Python
tracebacks (`TypeError:`, `ValueError:`, `Traceback (most recent call
last):`, etc.), generic failure markers (`FAILED`, `Error:`), success
markers (`PASSED`, `SUCCESS`, `completed successfully`, `✓`), and
progress markers (`Testing`, `Running`, `INFO`, `PROGRESS`). Override
any of them by passing your own list.

The watcher reads stdout (with stderr merged in) in real time so
patterns match as soon as they appear. The process is `terminate()`d
gracefully, then `kill()`d after 5 seconds if it ignores `SIGTERM`.

---

## `smart_run_function()` — same idea, for Python functions

```python
from hyperi_pylib.harness import smart_run_function

def run_baseline():
    from dfe_ai.vector.parser.vrl import generate
    return generate(logs, device_type="ssh")

result = smart_run_function(
    func=run_baseline,
    description="VRL baseline generation",
    activity_timeout=120,
    total_timeout=600,
    capture_output=True,
)
```

Runs the function in a monitoring thread. `capture_output=True` (the
default) collects stdout/stderr written from inside the function. The
`HarnessResult` shape matches `smart_run` — same fields, same
`TerminationReason` enum.

---

## `ActivityIndicator` — explicit activity definitions

```python
from hyperi_pylib.harness import ActivityIndicator, SmartTimeoutMonitor

indicators = ActivityIndicator(
    log_patterns=[r"PROGRESS:", r"step \d+/"],
    file_monitors=["/build/output.log", "/build/manifest.json"],
    output_monitors=[r"compiling", r"linking"],
)

monitor = SmartTimeoutMonitor(activity_timeout=60, total_timeout=600)
result = monitor.run_with_smart_timeout(
    command=["./build.sh"],
    activity_indicators=indicators,
)
```

Activity sources are OR-combined — any match resets the no-activity
timer. `log_patterns` and `output_monitors` are regexes against
stdout/stderr; `file_monitors` is a list of paths whose mtime is
polled. Use this when the high-level `smart_run` defaults don't fit
(e.g., a build script that emits a custom progress format).

---

## Result types

`HarnessResult`:

| Field | Type | What |
|-------|------|------|
| `success` | `bool` | Process completed with zero exit code (or function returned without exception). |
| `termination_reason` | `TerminationReason` | Why monitoring stopped. |
| `total_duration` | `float` | Seconds from start to termination. |
| `last_activity_time` | `float` | Seconds since the last activity detection. |
| `activity_count` | `int` | Total number of activity events observed. |
| `final_output` | `str` | Captured stdout/stderr (or function output). |
| `return_code` | `int \| None` | Process exit code (subprocess only). |
| `error_message` | `str \| None` | Exception message if `MANUAL_STOP`. |

`TerminationReason`:

| Value | Cause |
|-------|-------|
| `COMPLETED` | Process exited / function returned normally. |
| `NO_ACTIVITY` | `activity_timeout` elapsed without any activity event. |
| `TOTAL_EXECUTION` | `total_timeout` wall-clock budget exceeded. |
| `FAILURE_DETECTED` | A `failure_patterns` regex matched in the output. |
| `MANUAL_STOP` | Unhandled exception or explicit termination. |

---

## Choosing timeouts

Two ratios that work in practice:

| Workload | `activity_timeout` | `total_timeout` |
|----------|--------------------|-----------------|
| Fast unit tests | 30 s | 300 s |
| Integration tests | 120 s | 1800 s |
| Container build | 180 s | 3600 s |
| K8s rollout wait | 60 s | 600 s |

The activity timeout should be longer than the longest legitimate quiet
period (a slow test, a docker layer push). The total timeout is a
generous backstop for the case where activity keeps triggering but
nothing's actually progressing.

---

## Helpers in the same module

The `harness.harness` module also exposes:

- `container_registry_login()` — `docker login` from
  `REGISTRY_URL/USERNAME/PASSWORD` (or `ARTIFACTORY_*`) env vars.
- `check_registry_throttling(namespace)` — inspect K8s events and pod
  statuses for `ImagePullBackOff` / rate-limit indicators. Useful for
  skipping flaky pulls in CI.
- `check_container_registry_access()` — `docker manifest inspect` against
  a probe image (default `library/busybox:latest`, override with
  `REGISTRY_PROBE_IMAGE`).

These are container-CI specific — separated out so a service-level
harness call doesn't pull in `kubectl` or `docker` shell-outs.

---

## Related

- [CONCURRENCY.md](CONCURRENCY.md)
- [RESILIENCE.md](RESILIENCE.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
- [../deployment/TEST-SUPPORT.md](../deployment/TEST-SUPPORT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [CLI.md](CLI.md)
