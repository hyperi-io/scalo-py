# Testing

The general rules are hyperi-ai's testing standard (`standards/universal/testing.md` in hyperi-ai). This page covers what scalo-py does on top of them.

## Levels

| Level | Runs | Command |
|---|---|---|
| core | locally, every push and PR | `hyperi-ci run test`, or `uv run pytest` |
| full | nightly (`schedule` in `.github/workflows/ci.yml`) and before every release (`test.full.required_for_release: true`) | `hyperi-ci run test --tier full`, or `uv run pytest -m ""` |

Core is pytest's default selection: `addopts` deselects the `full` marker. Full runs everything, and fails on any skip whose reason `test.full.python.allow_skip` in `.hyperi-ci.yaml` does not name. Those reasons are settings no CI runner has: a live cloud account, the scalo-rs golden file, macOS, and one moto gap.

Core's container-backed tests, one per service:

- `test_kafka_integration.py::TestKafkaProducerConsumerIntegration::test_produce_and_consume_user_events`: JSON events produced and consumed back, with commits
- `test_secrets_openbao_tier1.py::TestOpenBaoTier1Roundtrip::test_create_get_metadata_update_delete_roundtrip`: one KV v2 secret through its whole life
- `test_ddl_engine_clickhouse.py`: engine selection sensed on a Replicated and an Atomic database, and the server accepting the CREATE it rendered
- `test_secrets_kubernetes_cluster.py::TestReadAndWrite::test_get_reads_a_key_at_the_secret_resource_version`: a Secret read through a Role-bound service account
- `test_shared_service_container.py::test_the_runs_container_is_named_labelled_and_bound_to_loopback`: the convention below, asked of Docker

Those run on four containers per run. Full adds the rest of the Kafka, OpenBao and Kubernetes tests, the Docker image builds, and a container one test holds alone.

## Services, one instance each per run

| Service | Image | Container port |
|---|---|---|
| ClickHouse | `clickhouse/clickhouse-server:26.3.42.3@sha256:21d572843e59539c7d100286b6f5a6053c341fe4b33c2d7b74b1ff7cb24c5399` | 8123 HTTP, 9000 native |
| Kafka | `apache/kafka:4.3.1@sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837` | 9092 PLAINTEXT |
| OpenBao | `openbao/openbao:2.7.1@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf` | 8200, dev mode |
| k3s | `rancher/k3s:v1.37.1-k3s1@sha256:ca7f37d993d82ef0dcdcfecb2e0e2618ea541dbaffc620c8cedebe01a82acd0d` | 6443, API server only |

The first three are pinned in `scalo.deployment.test_support.services`, k3s in `tests/common/kube_cluster.py`. ClickHouse runs embedded Keeper with a one-replica cluster `default`, so `ON CLUSTER` and `ENGINE = Replicated` work as on a replicated server. Kafka refuses topic auto-create. The ClickHouse password and the OpenBao root token are generated per run and never logged.

`scalo.deployment.test_support.pytest_plugin`, loaded from `tests/conftest.py`, gives every xdist worker the same container per service:

- The controller names the run before any worker starts. The first worker to ask for a service creates it, named `<prefix>-integration-<service>-r<run>`, under a lock in `.tmp/shared-services/<run>/`, and the rest join it. `<prefix>` is `HYPERI_TEST_CONTAINER_PREFIX`, else `scalo-py-test`.
- The controller removes the run's containers when the session ends. A watcher started with each container removes it if the controller dies first.
- Containers carry `io.hyperi.test.suite=scalo-py-integration`, `io.hyperi.test.run`, and the owner: `owner-host`, `owner-pidns`, `owner-pid`, `owner-start` and `lease-until`. Each create sweeps the suite's containers whose owner has gone on this host, and another host's only once their 4-hour lease has lapsed.
- Ports bind 127.0.0.1 on the daemon host. An `ssh://` daemon or docker context gets an `ssh -L` tunnel per port, and a remote `tcp://` daemon is refused unless `HYPERI_TEST_DOCKER_BIND` names a private address on it.
- Each start and removal goes to `.tmp/shared-services-<run>.log`, which hyperi-ci prints after the tests (`test.logs`).

Tests keep to their own databases, topics, consumer groups, secret paths and namespaces. `kafka_topics` and `clickhouse_database` make run-prefixed ones and drop them afterwards.

Without Docker a test that needs a service skips locally and fails in CI or under the full tier. To run against a remote daemon, set `DOCKER_CONTEXT` (or `DOCKER_HOST`) to it.

A core run on a developer's machine may use the always-present devex ClickHouse and Kafka instead of starting them. It reads `HYPERI_TEST_CLICKHOUSE_*` and `HYPERI_TEST_KAFKA_*` from the environment, then `.env`, then the file `HYPERI_TEST_ENV_FILE` names, which `hyperi-ai secrets devex-env` writes. A pet is used only when its settings are present and a 2-second probe answers, and never in CI or under the full tier. The run log says which rung each service took. A full-tier test can need what a pet refuses, such as a consumer group outside its prefix, so run one locally under `HYPERCI_TEST_TIER=full`, which takes the containers. Run databases and topics carry the run id and its start time, are dropped at the end, and a later run drops any whose run started more than 4 hours ago.

The Kubernetes tests can use an existing API server instead of k3s: set all of `SCALO_TEST_K8S_API`, `SCALO_TEST_K8S_TOKEN_FILE` and `SCALO_TEST_K8S_CA_FILE`.
