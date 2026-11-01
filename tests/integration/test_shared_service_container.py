#  Project:   scalo
#  File:      tests/integration/test_shared_service_container.py
#  Purpose:   Pin the shared-service convention on a real container: name, labels, loopback, removal
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The shared-service owner's convention, asked of Docker rather than of the naming helpers.

The run's OpenBao is the cheapest of the shared containers, so it carries the
core check: its name, its labels and where its port is bound. The removal of
a container a test holds alone needs a second one, so it runs in full.
"""

import json
import time

import pytest

from scalo.deployment.test_support import services
from scalo.deployment.test_support.pytest_plugin import suite_for
from scalo.deployment.test_support.shared_service import (
    LABEL,
    bound_addresses,
    container_name,
    docker,
    host_id,
    run_id,
    run_owner_pid,
    shared_name,
    start_alone,
)

pytestmark = pytest.mark.integration


def _labels(name: str) -> dict[str, str]:
    out = docker("inspect", "--format", "{{json .Config.Labels}}", name)
    assert out.returncode == 0, f"docker inspect {name}: {out.stderr.strip()}"
    return json.loads(out.stdout)


def test_the_runs_container_is_named_labelled_and_bound_to_loopback(shared_openbao, pytestconfig):
    suite = suite_for(pytestconfig)
    name = shared_name(suite, "openbao")

    assert docker("inspect", "--format", "{{.Name}}", name).stdout.strip() == f"/{name}"
    assert docker("inspect", f"{name}-not-this-one").returncode != 0, "a wrong name must fail the inspect"
    labels = _labels(name)
    assert {key: labels.get(f"{LABEL}.{key}") for key in ("suite", "repo", "service", "run")} == {
        "suite": suite.label(),
        "repo": suite.repo,
        "service": "openbao",
        "run": run_id(),
    }
    assert labels[f"{LABEL}.owner-pid"] == str(run_owner_pid())
    assert labels[f"{LABEL}.owner-host"] == host_id()
    assert int(labels[f"{LABEL}.lease-until"]) > time.time()
    assert set(bound_addresses(name)) == {"127.0.0.1"}
    started = suite.log_path().read_text(encoding="utf-8").count(f"started openbao container {name} ")
    assert started == 1, "every worker joins the one container"


@pytest.mark.full
def test_a_container_held_alone_is_removed_when_its_holder_closes(pytestconfig, request):
    suite = suite_for(pytestconfig)
    name = container_name(suite, request.node.name, "openbao")

    with start_alone(suite, services.openbao_spec(), name) as held:
        assert held.container.name == name
        assert _labels(name)[f"{LABEL}.service"] == "openbao"
    deadline = time.monotonic() + 30
    while docker("inspect", name).returncode == 0:
        assert time.monotonic() < deadline, f"{name} outlived its holder"
        time.sleep(0.25)
