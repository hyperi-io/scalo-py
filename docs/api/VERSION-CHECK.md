# Version check

Non-blocking startup probe that asks `https://releases.hyperi.io` whether
a newer version of your service is available, and logs the result.
Daemon thread, fire-and-forget — never blocks startup, never raises,
never affects exit code. Ships in the base package; needs `httpx` to
actually make the call (otherwise silently skipped).

```python
from scalo.version_check import check_on_startup
```

---

## Quick start

```python
from scalo.version_check import check_on_startup

check_on_startup("dfe-receiver", "1.2.0", deployment="k8s")
# Returns immediately. The check runs in a background daemon thread.
```

If a newer version is found:

```
INFO  new version available: dfe-receiver (current: 1.2.0, latest: 1.3.1)
      [released 12 days ago] — https://releases.hyperi.io/dfe-receiver/1.3.1
```

If you're up to date, the log goes out at DEBUG.

---

## Why this exists

- Operators forget to check for updates. A startup line that says
  "you're three months behind" beats an outage caused by a known bug.
- It runs in a daemon thread so a hung HTTP server, broken DNS, or
  network egress block never delays your service starting.
- It posts a stable per-host anonymous instance ID so the release
  service can show install counts without identifying anyone.

---

## API

```python
def check_on_startup(
    product: str,
    version: str,
    *,
    deployment: str | None = None,
    config: VersionCheckConfig | None = None,
) -> threading.Thread | None:
```

| Arg | Meaning |
|-----|---------|
| `product` | Stable identifier (e.g. `"dfe-receiver"`). |
| `version` | Current version string (e.g. `"1.2.0"`). |
| `deployment` | Optional context (`"k8s"`, `"docker"`, `"systemd"`). Appears in usage stats. |
| `config` | Optional `VersionCheckConfig` override. |

Returns the spawned `threading.Thread` if a check was kicked off, or
`None` when the check was skipped (disabled, product missing, version
missing). Production code can ignore the return value; tests use it to
`.join()` deterministically instead of `time.sleep`.

---

## Configuration

```python
from scalo.version_check.checker import VersionCheckConfig

cfg = VersionCheckConfig(
    api_url="https://releases.internal.hyperi.io/api/v1/check",
    timeout=5.0,
    disabled=False,
)

check_on_startup("dfe-receiver", "1.2.0", config=cfg)
```

| Setting | Default | Env var | Purpose |
|---------|---------|---------|---------|
| `api_url` | `https://releases.hyperi.io/api/v1/check` | `VERSION_CHECK_URL` | Endpoint. Internal mirrors welcome. |
| `timeout` | `5.0` | — | HTTP timeout in seconds. Kept short so the daemon thread exits quickly even on bad networks. |
| `disabled` | `False` | `VERSION_CHECK_DISABLED` | Set to `true`, `1`, or `yes` to skip the check entirely. |

The check is auto-skipped when:

- `VERSION_CHECK_DISABLED` is truthy
- `product` or `version` is empty
- `httpx` is not installed (warning logged at DEBUG)

---

## Wire it into `ServiceApp`

```python
from scalo.cli import ServiceApp, VersionInfo
from scalo.version_check import check_on_startup

class MyService(ServiceApp):
    name = "my-service"
    env_prefix = "MY_SVC"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    def run_service(self, config):
        check_on_startup(self.name, "1.0.0", deployment="k8s")
        # ... start serving ...
```

Place the call early in `run_service` — after the logger is up so the
result shows, before the long-running work so the daemon thread has
network access while everything is still booting cleanly.

---

## Payload

POST body:

```json
{
  "product": "dfe-receiver",
  "current_version": "1.2.0",
  "os": "Linux",
  "arch": "x86_64",
  "instance_id": "4f9f9577-e391-5835-8236-3e88e902b11b"
}
```

The payload matches scalo-rs field for field. `deployment` is never
sent -- operators embed sensitive names in free-form deployment
strings; the config field remains accepted but stays local.
`instance_id` is included unless `version_check.send_instance_id:
false`, which yields a payload with no identifier at all.

Response:

```json
{
  "latest_version": "1.3.1",
  "update_available": true,
  "release_url": "https://releases.hyperi.io/dfe-receiver/1.3.1",
  "published_at": "2026-05-13T09:30:00Z",
  "message": "Security fixes — recommend prompt upgrade."
}
```

`message` (when present) is logged at INFO with the product name as a
prefix — used for one-off operator advisories.

---

## Instance ID

Derived from what the app is running on, so the same install reports as
the same install across restarts. Resolution order, first hit wins:

1. `version_check.instance_id` from the config, sent verbatim.
2. Kubernetes: UUIDv5 over the serviceaccount cluster CA cert plus the
   pod namespace — readable in-pod with no API permissions, unique per
   cluster, stable across every pod restart and reschedule.
3. `/etc/machine-id`, as an app-scoped UUIDv5 — the raw machine id never
   leaves the host. Skipped inside containers, where a machine-id baked
   into the image would make every install report as the same one.
4. A v4 UUID persisted at `~/.config/scalo/instance_id` (dev machines).
5. An ephemeral UUID for that run alone.

The derived forms are one-way UUIDv5 values: nothing about the host can
be recovered from them. scalo-rs shares the UUIDv5 namespace, so both
chassis derive the SAME id on the same platform. Disable entirely with
`version_check.send_instance_id: false`.

---

## Disabling in air-gapped environments

```bash
export VERSION_CHECK_DISABLED=true
```

Or set it in your container manifest / Helm chart values:

```yaml
env:
  - name: VERSION_CHECK_DISABLED
    value: "true"
```

Air-gapped sites typically also block the endpoint at the egress layer;
the env var saves on the connect timeout per restart.

---

## Failure handling

Anything that goes wrong inside `_run_check` — DNS failure, TCP timeout,
HTTP 5xx, malformed JSON — is caught and logged at WARN as
`version check failed (non-fatal): <reason>`. The thread exits cleanly.
Your service never sees the failure.

---

## Testing

```python
thread = check_on_startup("my-service", "1.0.0")
if thread is not None:
    thread.join(timeout=10)   # deterministic, no time.sleep races
```

For full offline tests, point the API at a local mock:

```python
from scalo.version_check.checker import VersionCheckConfig

cfg = VersionCheckConfig(api_url="http://localhost:8080/check", timeout=1.0)
check_on_startup("my-service", "1.0.0", config=cfg)
```

---

## Related

- [LICENSE.md](LICENSE.md)
- [CLI.md](CLI.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
- [HTTP-CLIENT.md](HTTP-CLIENT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../runtime/SERVICE-RUNTIME.md](../runtime/SERVICE-RUNTIME.md)
