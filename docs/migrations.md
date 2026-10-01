# Migrations

Behaviour and API changes that need a consumer adjustment, indexed by the scalo release where each first ships. Moving over from `hyperi-pylib` has its own guide, [MIGRATING-FROM-HYPERI-PYLIB.md](MIGRATING-FROM-HYPERI-PYLIB.md).

---

## Unreleased

### Console logs: JSON off a TTY, fields in text, colour only on a TTY (BEHAVIOUR CHANGE)

`auto`, the default `LOG_FORMAT`, now does what [core-pillars/LOGGING.md](core-pillars/LOGGING.md#format-selection) always said: JSON when stderr is not a TTY, text when it is. It used to write coloured text everywhere, so a container's logs carried ANSI escapes and no keyword fields. Text now appends the fields as `key=value`, and colour is on only for a TTY unless `LOG_COLOR`, `NO_COLOR` or `logging.color` says otherwise.

`LOG_FORMAT=json` no longer dumps loguru's raw record (`{"text": ..., "record": {...}}`). Each line is one flat object, `timestamp`, `level`, `target`, `function`, `line_number`, `message` and `fields`, described in [core-pillars/LOGGING.md](core-pillars/LOGGING.md#json-records). `logfmt` was documented but never had a renderer; it is now reported as unrecognised and treated as `auto`.

**Consumer adjustment** -- a deployment that wants text in a container sets `LOG_FORMAT=text`. A parser that read `record.extra` or `text` from the old JSON reads `fields` and `message` instead.

### Stdlib logging goes through the scalo sinks (BEHAVIOUR CHANGE)

`setup()` now routes stdlib `logging` records into the scalo sinks, see [core-pillars/LOGGING.md](core-pillars/LOGGING.md#stdlib-logging). Before, a library logging through `logging` (uvicorn, clickhouse_connect, scalo's own secrets manager) wrote unformatted and unscrubbed lines, or nothing below WARNING. The root logger's existing handlers are replaced and its level follows the scalo level.

**Consumer adjustment** -- build any `uvicorn.Config` after `setup()` with `log_config=None`, or uvicorn's own handlers come back. An app that relies on its own root handler sets `logging.intercept_stdlib: false`.

### Internal Kafka group ids derive from the client's config (BEHAVIOUR CHANGE)

The consumer that `KafkaClient`, `AsyncKafkaClient` and `ReadOnlyKafkaClient` build for watermark and offset-for-time queries used fixed group ids of scalo's own: `scalo-offset-lookup-<n>`, `scalo-watermark-<n>`, `scalo-async-<n>`, `scalo-async-wm-<n>` and `scalo-readonly-<n>`, where `<n>` was the Python object id of the client. A broker granting groups by prefix refused all five, logging `GroupAuthorizationFailed`. They are now one id, `<group.id>-admin`, falling back to `<client.id>-admin` and then `scalo-admin`. See [transport/KAFKA.md](transport/KAFKA.md), "Internal consumer groups and broker ACLs".

None of those consumers ever joined its group or committed an offset, and `<n>` changed with every process, so no offsets are stranded under the old names.

**Consumer adjustment** -- none in code. A deployment that granted the old names is the only one affected, and since `<n>` changed with every process that grant was a prefix such as `scalo-`; it now needs to cover `<group.id>-admin`, which an app's own group prefix already does. A client given neither `group.id` nor `client.id` gets `scalo-admin`, so set one of them to land inside the app's prefix.
