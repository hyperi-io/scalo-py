#  Project:   scalo
#  File:      tests/unit/deployment/test_shared_service.py
#  Purpose:   The shared-service owner's pure decisions: daemons, bindings, sweeps, names and the lookup
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""What the shared-service owner decides without a Docker daemon.

The container itself is pinned by tests/integration/test_shared_service_container.py.
"""

import os
import re
from pathlib import Path

import pytest

from scalo.deployment.test_support import pytest_plugin
from scalo.deployment.test_support.shared_service import (
    LEASE_SECONDS,
    Labelled,
    LocalDaemon,
    SharedServiceError,
    SshDaemon,
    Suite,
    TcpDaemon,
    binding,
    container_name,
    lookup,
    parse_daemon,
    parse_listing,
    pets_allowed,
    process_start,
    run_id,
    run_owner_pid,
    shared_name,
    sweep_removes,
)

_DOCKER_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")


@pytest.fixture
def suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Suite:
    for key in ("HYPERI_TEST_CONTAINER_PREFIX", "HYPERI_TEST_DOCKER_BIND", "HYPERI_TEST_ENV_FILE"):
        monkeypatch.delenv(key, raising=False)
    return Suite(repo="r", project_dir=tmp_path, run_dir=tmp_path / "run", log_dir=tmp_path / "log")


LOCAL = ("127.0.0.1", "127.0.0.1")


@pytest.mark.parametrize(
    ("endpoint", "daemon", "bound"),
    [
        pytest.param("unix:///var/run/docker.sock", LocalDaemon(), LOCAL, id="unix-socket"),
        pytest.param("", LocalDaemon(), LOCAL, id="empty"),
        pytest.param("tcp://127.0.0.1:2375", LocalDaemon(), LOCAL, id="tcp-loopback"),
        pytest.param("tcp://localhost:2375", LocalDaemon(), LOCAL, id="tcp-localhost"),
        pytest.param("tcp://[::1]:2375", LocalDaemon(), LOCAL, id="tcp-ipv6-loopback"),
        pytest.param("ssh://derek@build.example:2222", SshDaemon("derek@build.example", 2222), LOCAL, id="ssh-port"),
        pytest.param("ssh://build.example", SshDaemon("build.example", None), LOCAL, id="ssh-bare"),
        pytest.param("tcp://10.0.0.5:2376", TcpDaemon("10.0.0.5"), None, id="tcp-remote-refused"),
    ],
)
def test_daemons_and_where_their_ports_bind(suite, endpoint, daemon, bound):
    assert parse_daemon(endpoint) == daemon
    if bound is None:
        with pytest.raises(SharedServiceError, match="HYPERI_TEST_DOCKER_BIND"):
            binding(daemon, suite)
    else:
        assert binding(daemon, suite) == bound


@pytest.mark.parametrize(
    ("bind", "refused"),
    [
        pytest.param("10.0.0.5", False, id="private-address"),
        pytest.param("0.0.0.0", True, id="ipv4-wildcard"),
        pytest.param("::", True, id="ipv6-wildcard"),
    ],
)
def test_a_remote_tcp_daemon_binds_only_one_named_address(suite, monkeypatch, bind, refused):
    monkeypatch.setenv("HYPERI_TEST_DOCKER_BIND", bind)
    if refused:
        with pytest.raises(SharedServiceError, match="one address"):
            binding(TcpDaemon("10.0.0.5"), suite)
    else:
        assert binding(TcpDaemon("10.0.0.5"), suite) == (bind, bind)


def _container(host: str, ns: str, pid: int | None, start: str, lease: int | None) -> Labelled:
    return Labelled(name="c", host=host, pid_ns=ns, pid=pid, start=start, lease_until=lease)


@pytest.mark.parametrize(
    ("container", "removed"),
    [
        pytest.param(_container("h1/m1", "pid:[1]", 10, "500", 2_000), False, id="ours-owner-alive"),
        pytest.param(_container("h1/m1", "pid:[1]", 11, "500", 2_000), True, id="ours-owner-gone"),
        pytest.param(_container("h1/m1", "pid:[1]", 10, "400", 2_000), True, id="ours-pid-reused"),
        pytest.param(_container("h2/m2", "pid:[1]", 11, "1", 2_000), False, id="another-host-lease-live"),
        pytest.param(_container("h2/m2", "pid:[1]", 11, "1", 900), True, id="another-host-lease-lapsed"),
        pytest.param(_container("h1/m1", "pid:[9]", 11, "1", 2_000), False, id="another-namespace-lease-live"),
        pytest.param(_container("h1/m1", "pid:[1]", None, "", None), False, id="ours-no-owner-pid"),
        pytest.param(Labelled(name="old"), False, id="no-owner-labels"),
    ],
)
def test_a_sweep_takes_only_containers_whose_owner_is_gone(container, removed):
    # Process 10, started at 500, is the only one alive here.
    def start_of(pid: int) -> str | None:
        return "500" if pid == 10 else None

    assert sweep_removes(container, "h1/m1", "pid:[1]", 1_000, start_of) is removed


def test_a_listing_reads_back_into_owner_labels():
    got = parse_listing("a\th\tns\t42\t900\t1234\nb\t\t\t\t\t\n\n")
    assert got == [
        Labelled(name="a", host="h", pid_ns="ns", pid=42, start="900", lease_until=1234),
        Labelled(name="b"),
    ]


def test_container_names_are_legal_per_test_and_carry_the_run(suite, monkeypatch):
    monkeypatch.setenv("HYPERI_TEST_RUN_ID", "ab12cd34")
    pid = os.getpid()
    names = {
        container_name(suite, "test_rbac[tenant-a:read]", "ClickHouse"): (
            f"r-test-integration-test-rbac-tenant-a-read--clickhouse-p{pid}"
        ),
        container_name(suite, None, "kafka"): f"r-test-integration-kafka-p{pid}",
        shared_name(suite, "openbao"): "r-test-integration-openbao-rab12cd34",
    }
    for name, want in names.items():
        assert name == want
        assert _DOCKER_NAME.fullmatch(name), f"{name} is not a legal Docker container name"
    assert container_name(suite, "first", "kafka") != container_name(suite, "second", "kafka")


@pytest.mark.parametrize(
    ("raw_id", "raw_owner", "want_id", "want_owner"),
    [
        pytest.param("ab12cd34ef", "4242", "ab12cd34", 4242, id="named-run"),
        pytest.param("a-b_1!", "", "ab1", None, id="punctuation-dropped-owner-unset"),
        pytest.param("", "not-a-pid", None, None, id="unset-falls-back-to-this-process"),
    ],
)
def test_the_run_is_named_by_its_controller(monkeypatch, raw_id, raw_owner, want_id, want_owner):
    monkeypatch.setenv("HYPERI_TEST_RUN_ID", raw_id)
    monkeypatch.setenv("HYPERI_TEST_RUN_OWNER", raw_owner)
    assert run_id() == (want_id or f"p{os.getpid()}")
    assert run_owner_pid() == (want_owner or os.getpid())


def test_the_lookup_ladder(suite, monkeypatch, tmp_path):
    key = "HYPERI_TEST_CONTAINER_PREFIX"
    user_file = tmp_path / "user.env"
    user_file.write_text(f"{key}=from-user-file\nHYPERI_TEST_CLICKHOUSE_HOST=pet.example\n", encoding="utf-8")
    project_env = tmp_path / ".env"

    assert suite.prefix() == "r-test"
    monkeypatch.setenv("HYPERI_TEST_ENV_FILE", str(user_file))
    assert suite.prefix() == "from-user-file"
    project_env.write_text(f'{key}="from-project"\n', encoding="utf-8")
    assert suite.prefix() == "from-project"
    monkeypatch.setenv(key, "from-env")
    assert suite.prefix() == "from-env"
    monkeypatch.setenv(key, "")
    assert suite.prefix() == "from-project", "an empty value counts as unset"

    monkeypatch.delenv("HYPERI_TEST_ENV_FILE")
    project_env.write_text(f"HYPERI_TEST_ENV_FILE={user_file}\n", encoding="utf-8")
    assert lookup(suite, "HYPERI_TEST_CLICKHOUSE_HOST") == "pet.example", "the project .env may name the user file"
    assert lookup(suite, "HYPERI_TEST_NOT_SET") is None


@pytest.mark.parametrize(
    ("ci", "tier", "allowed"),
    [
        pytest.param(None, None, True, id="local-core"),
        pytest.param(None, "FULL", False, id="local-full"),
        pytest.param("true", None, False, id="ci-core"),
    ],
)
def test_pets_only_off_ci_and_outside_the_full_tier(monkeypatch, ci, tier, allowed):
    for name, value in (("CI", ci), ("HYPERCI_TEST_TIER", tier)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert pets_allowed() is allowed


def test_process_start_tells_a_live_process_from_a_gone_one():
    # One past pid_max is a pid the kernel never hands out.
    never = int(Path("/proc/sys/kernel/pid_max").read_text(encoding="utf-8")) + 1
    assert process_start(os.getpid())
    assert process_start(never) is None


@pytest.mark.parametrize(
    ("name", "stale"),
    [
        pytest.param("test_zz99yy88_{old}_db_abc123", True, id="another-run-past-the-lease"),
        pytest.param("test_zz99yy88_{now}_db_abc123", False, id="another-run-inside-the-lease"),
        pytest.param("test_{run}_{old}_db_abc123", False, id="this-run"),
        pytest.param("test_hand_made", False, id="not-a-run-object"),
        pytest.param("prod_zz99yy88_{old}_db", False, id="another-prefix"),
    ],
)
def test_the_pet_sweep_drops_only_objects_of_ended_runs(monkeypatch, name, stale):
    monkeypatch.setenv("HYPERI_TEST_RUN_ID", "ab12cd34")
    now = 2_000_000_000
    filled = name.format(run="ab12cd34", old=now - LEASE_SECONDS - 1, now=now)
    assert pytest_plugin._stale(filled, "test_", "_", now) is stale


def test_pet_object_names_carry_the_run_and_start(monkeypatch):
    monkeypatch.setenv("HYPERI_TEST_RUN_ID", "ab12cd34")
    monkeypatch.setenv("HYPERI_TEST_RUN_STARTED", "1793500000")
    first = pytest_plugin._object_name("test_", "test_rbac[tenant-a:read]", "_")
    second = pytest_plugin._object_name("test_", "test_rbac[tenant-a:read]", "_")
    assert first.startswith("test_ab12cd34_1793500000_test_rbac_tenant_a_read_")
    assert first != second
    assert re.fullmatch(r"[a-z0-9_]+", first)
