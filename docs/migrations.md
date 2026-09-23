# Migrations

Behaviour and API changes that need a consumer adjustment, indexed by the scalo release where each first ships. Moving over from `hyperi-pylib` has its own guide, [MIGRATING-FROM-HYPERI-PYLIB.md](MIGRATING-FROM-HYPERI-PYLIB.md).

---

## Unreleased

### Internal Kafka group ids derive from the client's config (BEHAVIOUR CHANGE)

The consumer that `KafkaClient`, `AsyncKafkaClient` and `ReadOnlyKafkaClient` build for watermark and offset-for-time queries used fixed group ids of scalo's own: `scalo-offset-lookup-<n>`, `scalo-watermark-<n>`, `scalo-async-<n>`, `scalo-async-wm-<n>` and `scalo-readonly-<n>`, where `<n>` was the Python object id of the client. A broker granting groups by prefix refused all five, logging `GroupAuthorizationFailed`. They are now one id, `<group.id>-admin`, falling back to `<client.id>-admin` and then `scalo-admin`. See [transport/KAFKA.md](transport/KAFKA.md), "Internal consumer groups and broker ACLs".

None of those consumers ever joined its group or committed an offset, and `<n>` changed with every process, so no offsets are stranded under the old names.

**Consumer adjustment** -- none in code. A deployment that granted the old names is the only one affected, and since `<n>` changed with every process that grant was a prefix such as `scalo-`; it now needs to cover `<group.id>-admin`, which an app's own group prefix already does. A client given neither `group.id` nor `client.id` gets `scalo-admin`, so set one of them to land inside the app's prefix.
