# Migrations

Behaviour and API changes that need a consumer adjustment, indexed by the scalo release where each first ships. Moving over from `hyperi-pylib` has its own guide, [MIGRATING-FROM-HYPERI-PYLIB.md](MIGRATING-FROM-HYPERI-PYLIB.md).

---

## Unreleased

### The secret schema marker is `x-scalo-secret` alone (BEHAVIOUR CHANGE)

`config_schema_json` no longer writes `x-dfe-secret`, and `json_schema_extra={"x-dfe-secret": True}` no longer opts a field in. A secret field now ends `"x-scalo-secret": true, "writeOnly": true`, as scalo-rs's `SensitiveString` emits.

**Consumer adjustment** -- a field marked with `x-dfe-secret` is marked with `x-scalo-secret` in the same change as the bump, or its schema stops calling it a secret. A reader that keyed on `x-dfe-secret` keys on `x-scalo-secret`. A committed `config-schema.*` loses the old marker on regeneration, so `check_config_artifact_drift` fails until it is regenerated.

### The contract carries every field scalo-rs writes (BEHAVIOUR CHANGE)

`DeploymentContract` parses a contract scalo-rs emitted, where it used to refuse it with `extra_forbidden`. New fields, each with scalo-rs's name, type and default: `unbound_listen_paths`, `PortContract.when` (`EnabledCondition`, `EqualsCondition` or `OneOfCondition`) and `bound_from`, `KedaContract.enabled` and `kafka_trigger` (`KafkaLagTrigger`), and `NativeDepsContract.distro` (`BaseDistro`), `unresolved_base_image` and `contradicted_base_image`. See [deployment/CONTRACT.md](deployment/CONTRACT.md).

- An emitted contract with a `keda` block gains `keda.enabled` and `keda.kafka_trigger`.
- One built through `for_scalo_extras` or `for_scalo_features` gains `native_deps.distro`.
- `KedaContract.from_config` copies `enabled`, where it dropped it, and `generate_chart` treats `enabled=False` as no KEDA.

**Consumer adjustment** -- an app that builds `KedaContract.from_config` from a `KedaConfig` with `enabled=False` now gets a chart with no `ScaledObject`. A committed `deployment-contract.json` changes on regeneration as above.

### Deployment contract schema 4 (BEHAVIOUR CHANGE)

`DEFAULT_SCHEMA_VERSION` and `MAX_SUPPORTED_SCHEMA_VERSION` are 4, matching scalo-rs. `DeploymentContract` gains `writable_paths` (`WritablePath`), `termination_grace_seconds` (45), `resources` (`ResourcesContract`, `ResourceList`), `security` (`SecurityContract`) and `singleton`. `HealthContract` gains `startup_budget_seconds` (150, at least 1), `PortContract` gains `public` and `app_protocol`, and `SecretGroupContract` gains `optional`. `config_mount_path` may be omitted or empty, meaning no config file. An app marks an operator dial with `json_schema_extra={DIAL_KEYWORD: "big"}` or `"small"`. The wheel ships scalo-rs's v4 contract JSON Schema. See [deployment/CONTRACT.md](deployment/CONTRACT.md).

**Consumer adjustment** -- an emitted contract now carries `schema_version: 4`, `termination_grace_seconds`, `security`, `singleton` and `health.startup_budget_seconds`, so a committed `deployment-contract.json` changes on regeneration. An app that passes `schema_version=3` passes nothing, or `DEFAULT_SCHEMA_VERSION`, because a v4 chart assembler refuses version 3. Construction now refuses a malformed writable path, a capability that is not an upper-case name, a singleton with KEDA on, and an `x-scalo-dial` other than `big` or `small`.

## 2.31.0

### Console logs: JSON off a TTY, fields in text, colour only on a TTY (BEHAVIOUR CHANGE)

`auto`, the default `LOG_FORMAT`, now does what [core-pillars/LOGGING.md](core-pillars/LOGGING.md#format-selection) always said: JSON when stderr is not a TTY, text when it is. It used to write coloured text everywhere, so a container's logs carried ANSI escapes and no keyword fields. Text now appends the fields as `key=value`, and colour is on only for a TTY unless `LOG_COLOR`, `NO_COLOR` or `logging.color` says otherwise.

`LOG_FORMAT=json` no longer dumps loguru's raw record (`{"text": ..., "record": {...}}`). Each line is one flat object, `timestamp`, `level`, `target`, `function`, `line_number`, `message` and `fields`, described in [core-pillars/LOGGING.md](core-pillars/LOGGING.md#json-records). `logfmt` was documented but never had a renderer; it is now reported as unrecognised and treated as `auto`.

**Consumer adjustment** -- a deployment that wants text in a container sets `LOG_FORMAT=text`. A parser that read `record.extra` or `text` from the old JSON reads `fields` and `message` instead.

### Stdlib logging goes through the scalo sinks (BEHAVIOUR CHANGE)

`setup()` now routes stdlib `logging` records into the scalo sinks, see [core-pillars/LOGGING.md](core-pillars/LOGGING.md#stdlib-logging). Before, a library logging through `logging` (uvicorn, clickhouse_connect, scalo's own secrets manager) wrote unformatted and unscrubbed lines, or nothing below WARNING. The root logger's existing handlers are replaced and its level follows the scalo level.

**Consumer adjustment** -- build any `uvicorn.Config` after `setup()` with `log_config=None`, or uvicorn's own handlers come back. An app that relies on its own root handler sets `logging.intercept_stdlib: false`.

### Scrubbed tracebacks, bounded fields, httpx capped (BEHAVIOUR CHANGE)

Tracebacks are now formatted the way the stdlib formats them and scrubbed before any sink writes them, in every format; loguru's extended frames above the `except` are gone. Keys and strings inside a field's containers are scrubbed up to 64 per record, and the rest of a larger list or dict is elided with a count, see [core-pillars/LOGGING.md](core-pillars/LOGGING.md#fields). `httpx` and `httpcore` join the loggers capped at WARNING, because their INFO request lines carry whole URLs.

**Consumer adjustment** -- a sink added with `logger.add()` after `setup()` sees `record["extra"]` as the scrubbed fields in plain JSON data, not the objects passed in. An app that wants httpx's request lines sets `logging.getLogger("httpx").setLevel(logging.INFO)` after `setup()`, knowing a signed URL goes out whole.

### Contract names and defaults carry no organisation or product name

The names `scalo.deployment` writes into artefacts, and the defaults it falls back on, named one organisation and one product. They are now scalo's own or the app's, and an app that relied on the old value sets it explicitly. Once it does, every artefact is byte-for-byte what it was with three exceptions: `deployment-contract.json` gains the two new `oci_labels` fields, a secret field's schema gains `x-scalo-secret` and ends with the three marker keys, and `Chart.yaml` names only the app. scalo-rs's section of the same name is the same change.

| Old | New | To keep the old value |
| --- | --- | --- |
| Secret schema marker `x-dfe-secret` | `x-scalo-secret`, with `x-dfe-secret` still emitted beside it. Either one in `json_schema_extra` opts a field in. A secret field now ends `"x-scalo-secret": true, "x-dfe-secret": true, "writeOnly": true`, the order scalo-rs's `SensitiveString` emits | Nothing: both are emitted. Move every reader to `x-scalo-secret` |
| Label keys `io.hyperi.profile`, `io.hyperi.app`, `io.hyperi.metrics_port`, `io.hyperi.contract.*` | `io.scalo.*`, under the new `OciLabels.label_namespace` | `OciLabels(label_namespace="io.hyperi")` |
| `KEY_PREFIX` (`io.hyperi.contract`) | `KEY_SEGMENT` (`contract`), under the label namespace, and `DEFAULT_LABEL_NAMESPACE` (`io.scalo`) | -- |
| `ContractIdentity.as_dockerfile_labels()`, `as_yaml_annotations(indent=0)` | take the namespace: `as_dockerfile_labels(namespace)`, `as_yaml_annotations(namespace, indent=0)`. New `as_labels(namespace)` returns the keys as a dict | pass `"io.hyperi"` |
| `DEFAULT_VENDOR` (`HYPERI PTY LIMITED`), the `OciLabels.vendor` default | removed. `vendor` is empty by default, and an empty vendor writes no label | `OciLabels(vendor="HYPERI PTY LIMITED")` |
| `DEFAULT_LICENSE` (`Apache-2.0`), the `OciLabels.licenses` default | removed. `licenses` is empty by default, and an empty licence writes no `org.opencontainers.image.licenses` label and no `# License:` line | `OciLabels(licenses="Apache-2.0")`, or the app's own licence |
| `generate_dockerfile` header `# License:   Apache-2.0` and `# Copyright: (c) 2026 HYPERI PTY LIMITED`, written whatever the contract named | `# License:` follows `OciLabels.licenses` and `# Copyright:` the new `OciLabels.copyright`, each only when set. With neither set the header drops both lines and the `#` after them | `OciLabels(licenses="Apache-2.0", copyright="(c) 2026 HYPERI PTY LIMITED")` writes the header exactly as before. An app that set another licence now gets it in the header too |
| `DeploymentContract.image_registry` default `localhost:5000`, and `DEFAULT_IMAGE_REGISTRY` | required, with no default. A missing or blank registry raises `ValidationError` when the contract is built. `DEFAULT_IMAGE_REGISTRY` is removed | `image_registry="localhost:5000"`, or the registry the app pushes to |
| `image_registry_from_cascade() -> str`, falling back to `localhost:5000` | `-> str \| None`, `None` when unset | `image_registry_from_cascade() or "localhost:5000"` |
| `argocd_repo_url_from_cascade(app_name) -> str`, falling back to `https://github.com/your-org/<app>` | `argocd_repo_url_from_cascade() -> str \| None`. `generate-artefacts` writes no `argocd-application.yaml` without it, and warns on stderr | `deployment.argocd.repo_url` in a config file the cascade reads |
| `ArgocdConfig().dest_namespace` `dfe` | empty, which deploys into a namespace named after `app_name`. New cascade key `deployment.argocd.dest_namespace`, read by `argocd_dest_namespace_from_cascade()` | `ArgocdConfig(dest_namespace="dfe")`, or `deployment.argocd.dest_namespace: dfe` for `generate-artefacts` |
| `generate_chart`'s `Chart.yaml` keywords `hyperi` and `dfe`, and maintainer `HyperI` at `https://github.com/hyperi-io` | one keyword, `app_name`, and no `maintainers` block | no setting: an app that wants its own keywords or maintainers edits the generated `Chart.yaml` |

scalo-rs's rows for `KafkaSource` consumer groups, the DLQ paths and topic, and the spool and file-output paths have no counterpart here. scalo-py derives no consumer group (every consumer takes an explicit `group_id`) and has no DLQ, spool or file-output module.

**Consumer adjustment** -- set each value the app relied on, in code or config, before the bump. The ones that break something when missed:

- A contract built without `image_registry` raises `ValidationError`, and so does `DeploymentContract.from_json` on JSON without the key.
- A call to `argocd_repo_url_from_cascade(app_name)` raises `TypeError`. Call it with no argument and handle `None`.
- A script that edits the generated `Chart.yaml` by anchoring on the old `keywords:` block finds no anchor.
- Committed artefacts that `generate_dockerfile`, `generate_runtime_stage`, `generate_container_manifest`, `generate_chart` or `config_schema_json` produced change on regeneration, so regenerate them in the same change as the bump. `check_config_artifact_drift` fails until they are. A committed `argocd-application.yaml` stops regenerating unless `deployment.argocd.repo_url` is set.

## 2.30.2

### Internal Kafka group ids derive from the client's config (BEHAVIOUR CHANGE)

The consumer that `KafkaClient`, `AsyncKafkaClient` and `ReadOnlyKafkaClient` build for watermark and offset-for-time queries used fixed group ids of scalo's own: `scalo-offset-lookup-<n>`, `scalo-watermark-<n>`, `scalo-async-<n>`, `scalo-async-wm-<n>` and `scalo-readonly-<n>`, where `<n>` was the Python object id of the client. A broker granting groups by prefix refused all five, logging `GroupAuthorizationFailed`. They are now one id, `<group.id>-admin`, falling back to `<client.id>-admin` and then `scalo-admin`. See [transport/KAFKA.md](transport/KAFKA.md), "Internal consumer groups and broker ACLs".

None of those consumers ever joined its group or committed an offset, and `<n>` changed with every process, so no offsets are stranded under the old names.

**Consumer adjustment** -- none in code. A deployment that granted the old names is the only one affected, and since `<n>` changed with every process that grant was a prefix such as `scalo-`; it now needs to cover `<group.id>-admin`, which an app's own group prefix already does. A client given neither `group.id` nor `client.id` gets `scalo-admin`, so set one of them to land inside the app's prefix.
