# Version check

Non-blocking startup probe that asks a configured releases endpoint
whether a newer version of your service is available, and logs the result.
Daemon thread, fire-and-forget — never blocks startup, never raises,
never affects exit code. Ships in the base package; needs `httpx` to
actually make the call (otherwise skipped with a DEBUG line).

The check is OPT-OUT: wiring it into an app is the opt-in, so `enabled`
defaults true — and it stays inert until an `api_url` is supplied, so
nothing is ever sent unless the app (or config) names an endpoint. An
explicit `version_check.enabled: false` in any config layer is the
opt-out and always wins. Don't want a check at all? Don't call it.

```python
from scalo.version_check import check_on_startup
```

---

## Quick start

```python
from scalo.version_check import check_on_startup
from scalo.version_check.checker import VersionCheckConfig

# On by default; the app supplies only its endpoint, and any config
# layer can still turn the check off.
check_on_startup(
    "dfe-receiver",
    "1.2.0",
    config=VersionCheckConfig.from_cascade_or(
        api_url="https://releases.example.com/api/v1/check",
    ),
)
# Returns immediately. The check runs in a background daemon thread.

# Without an endpoint the call is inert (returns None, one DEBUG line).
check_on_startup("dfe-receiver", "1.2.0")
```

If a newer version is found:

```
INFO  new version available: dfe-receiver (current: 1.2.0, latest: 1.3.1)
      [released 12 days ago] — https://releases.example.com/dfe-receiver/1.3.1
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
| `deployment` | Optional local context (`"k8s"`, `"docker"`, `"systemd"`). Never sent -- see Payload. |
| `config` | Optional `VersionCheckConfig` override. |

Returns the spawned `threading.Thread` if a check was kicked off, or
`None` when the check was skipped (disabled, product missing, version
missing). Production code can ignore the return value; tests use it to
`.join()` deterministically instead of `time.sleep`.

---

## Configuration

All settings live under the `version_check` key of the config cascade, so
any layer (file or env, via the app's cascade prefix) can set them:

```yaml
version_check:
  enabled: true
  api_url: "https://releases.example.com/api/v1/check"
  timeout: 5
  send_instance_id: true   # false = no identifier in the payload
  instance_id: ""          # explicit override of the derived id
```

| Setting | Library default | Purpose |
|---------|-----------------|---------|
| `enabled` | `True` | The kill switch. An explicit `false` wins over any app default. |
| `api_url` | `None` | Endpoint. No baked-in default -- the app supplies its own; without one the check is inert. |
| `timeout` | `5.0` | HTTP timeout in seconds, kept short so the daemon thread exits quickly. |
| `send_instance_id` | `True` | `false` strips the instance id from the payload. |
| `instance_id` | `""` | Explicit id, sent verbatim -- overrides the derived one. |

An app supplies its own defaults -- typically just the endpoint -- via
`from_cascade_or`; the cascade overlays them, so unset keys fall to the
app and set keys win:

```python
from scalo.version_check.checker import VersionCheckConfig

cfg = VersionCheckConfig.from_cascade_or(
    api_url="https://releases.example.com/api/v1/check",
)
check_on_startup("dfe-receiver", "1.2.0", config=cfg)
```

The check is auto-skipped when:

- `enabled` resolves false, or no `api_url` is set
- `product` or `version` is empty
- `httpx` is not installed (logged at DEBUG)

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
  "release_url": "https://releases.example.com/dfe-receiver/1.3.1",
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

Set `version_check.enabled: false` in any config layer -- a deployment
yaml, or the env form of the cascade key with the app's prefix:

```bash
export MY_SVC_VERSION_CHECK__ENABLED=false
```

The explicit `false` wins even when the app ships the check on by
default. Air-gapped sites typically also block the endpoint at the
egress layer; without the config opt-out that costs one WARN line and
one connect timeout per restart, nothing more.

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

- [CLI.md](CLI.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
- [HTTP-CLIENT.md](HTTP-CLIENT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../runtime/SERVICE-RUNTIME.md](../runtime/SERVICE-RUNTIME.md)
