# Project:   scalo
# File:      tests/unit/deployment/test_contract_schema.py
# Purpose:   scalo-py's contracts pass the contract JSON Schema scalo-rs derives
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""The contracts scalo-py emits pass the JSON Schema scalo-rs derives from its contract types.

``src/scalo/deployment/data/contract.schema.json`` is scalo-rs's
``charts/scalo-service/schema/deployment-contract.v4.schema.json``, copied
verbatim at the ref ``.hyperi-ci-vendor.lock`` records. A chart assembler
validates every contract against that schema, whichever scalo wrote it.
"""

import copy
import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, SecretStr, ValidationError

from scalo.deployment.contract import (
    DEFAULT_SCHEMA_VERSION,
    DeploymentContract,
    EnabledCondition,
    HealthContract,
    PortContract,
    ResourceList,
    ResourcesContract,
    SecretEnvContract,
    SecretGroupContract,
    SecurityContract,
    WritablePath,
)
from scalo.deployment.emit import DIAL_KEYWORD, config_schema_json, emit_config_artifacts
from scalo.deployment.keda import KedaContract

ROOT = Path(__file__).parents[3]
VENDORED = "src/scalo/deployment/data/contract.schema.json"
LOCK = ROOT / ".hyperi-ci-vendor.lock"
FIXTURE = ROOT / "tests" / "fixtures" / "contract-parity" / "deployment-contract.json"


def _schema() -> dict[str, Any]:
    text = (resources.files("scalo.deployment") / "data" / "contract.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


def _errors(document: Any) -> list[str]:
    validator = Draft202012Validator(_schema())
    return sorted(error.message for error in validator.iter_errors(document))


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _emitted(contract: DeploymentContract) -> dict[str, Any]:
    return json.loads(contract.to_json())


class _SourceConfig(BaseModel):
    """A config section with two dials and a secret, marked the way an app marks them."""

    batch_size: int = Field(default=500, ge=1, le=100_000, json_schema_extra={DIAL_KEYWORD: "big"})
    level: str | None = Field(default=None, json_schema_extra={DIAL_KEYWORD: "small"})
    password: SecretStr


def _full_contract() -> DeploymentContract:
    """A contract built in Python that sets every v4 field."""
    return DeploymentContract(
        app_name="schema-app",
        metrics_port=9090,
        health=HealthContract(startup_budget_seconds=90),
        env_prefix="SCHEMA_APP",
        metric_prefix="schema",
        config_mount_path="",
        image_registry="registry.example.com/team",
        extra_ports=[
            PortContract(name="http", port=8080, public=True),
            PortContract(name="grpc", port=6000, app_protocol="kubernetes.io/h2c"),
        ],
        secrets=[
            SecretGroupContract(
                group_name="source",
                env_vars=[
                    SecretEnvContract(env_var="SCHEMA_APP__SOURCE__PASSWORD", key_name="password", secret_key="pw")
                ],
                optional=True,
            )
        ],
        keda=KedaContract(),
        config_schema=config_schema_json(_SourceConfig),
        writable_paths=[
            WritablePath(
                name="spool", path="/var/lib/schema-app/spool", size_limit="2Gi", when=EnabledCondition(path="x.y")
            ),
            WritablePath(name="state", path="/var/lib/schema-app/state", persistent=True, size="5Gi"),
        ],
        termination_grace_seconds=90,
        resources=ResourcesContract(requests=ResourceList(cpu="250m"), limits=ResourceList(memory="1Gi")),
        security=SecurityContract(run_as_user=0, read_only_root_filesystem=False, capabilities_add=["NET_ADMIN"]),
    )


# ---- The vendored schema is scalo-rs's, for the version scalo-py writes ----------


def test_the_vendored_schema_matches_its_lock() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    record = lock["files"][VENDORED]
    assert record["source"] == "hyperi-io/scalo-rs"
    assert record["path"] == f"charts/scalo-service/schema/deployment-contract.v{DEFAULT_SCHEMA_VERSION}.schema.json"
    assert hashlib.sha256((ROOT / VENDORED).read_bytes()).hexdigest() == record["sha256"]


def test_the_vendored_schema_is_for_the_version_scalo_py_writes() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == DEFAULT_SCHEMA_VERSION
    assert schema["required"][0] == "schema_version"


# ---- What scalo-py emits passes ---------------------------------------------------


def test_the_scalo_rs_fixture_passes() -> None:
    assert _errors(_fixture()) == []


def test_scalo_py_re_emitting_the_scalo_rs_fixture_passes() -> None:
    assert _errors(_emitted(DeploymentContract.model_validate(_fixture()))) == []


def test_a_contract_built_with_the_defaults_passes() -> None:
    bare = DeploymentContract(
        app_name="bare", metrics_port=9090, env_prefix="BARE", metric_prefix="bare", image_registry="r.example.com"
    )
    assert _errors(_emitted(bare)) == []


def test_a_contract_setting_every_v4_field_passes() -> None:
    emitted = _emitted(_full_contract())
    assert _errors(emitted) == []
    properties = emitted["config_schema"]["properties"]
    assert properties["batch_size"][DIAL_KEYWORD] == "big"
    assert properties["batch_size"]["minimum"] == 1
    assert properties["level"][DIAL_KEYWORD] == "small"
    assert properties["password"]["x-scalo-secret"] is True


# ---- What the schema refuses --------------------------------------------------


def _with(document: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """A copy of ``document`` with ``value`` at the dotted ``path``; a numeric segment indexes a list."""
    doc = copy.deepcopy(document)
    node: Any = doc
    *parents, leaf = path.split(".")
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(leaf)] = value
    else:
        node[leaf] = value
    return doc


def _without(document: dict[str, Any], key: str) -> dict[str, Any]:
    doc = copy.deepcopy(document)
    del doc[key]
    return doc


DIAL = "config_schema.$defs.SourceSection.properties.batch_size.x-scalo-dial"


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param(_without(_fixture(), "app_name"), id="app_name missing"),
        pytest.param(_without(_fixture(), "schema_version"), id="schema_version missing"),
        pytest.param(_with(_fixture(), "schema_version", 3), id="schema_version 3"),
        pytest.param(_with(_fixture(), "metrics_port", 70000), id="metrics_port out of range"),
        pytest.param(_with(_fixture(), DIAL, "huge"), id="dial tier unknown"),
        pytest.param(_with(_fixture(), DIAL, True), id="dial tier not a string"),
        pytest.param(
            _with(_fixture(), "config_schema.$defs.SourceSection.properties.password.x-scalo-secret", "yes"),
            id="secret marker not a boolean",
        ),
        pytest.param(_with(_fixture(), "writable_paths.0.name", "Spool_Dir"), id="writable path name invalid"),
        pytest.param(_with(_fixture(), "writable_paths.0.path", "var/spool"), id="writable path not absolute"),
        pytest.param(_with(_fixture(), "health.startup_budget_seconds", 0), id="startup budget zero"),
        pytest.param(_with(_fixture(), "termination_grace_seconds", -1), id="grace negative"),
        pytest.param(_with(_fixture(), "security.run_as_user", "root"), id="uid not an integer"),
    ],
)
def test_the_schema_refuses_a_contract_breaking_one_rule(broken: dict[str, Any]) -> None:
    assert _errors(broken) != []


def test_a_dial_tier_outside_big_and_small_fails_the_contract_and_the_schema() -> None:
    class Bad(BaseModel):
        rows: int = Field(default=1, json_schema_extra={DIAL_KEYWORD: "huge"})

    schema = config_schema_json(Bad)
    with pytest.raises(ValidationError, match="x-scalo-dial is"):
        DeploymentContract(
            app_name="bad",
            metrics_port=9090,
            env_prefix="BAD",
            metric_prefix="bad",
            image_registry="r.example.com",
            config_schema=schema,
        )
    assert _errors(_with(_fixture(), "config_schema", schema)) != []


def test_emitting_a_config_schema_with_an_infinite_default_refuses(tmp_path: Path) -> None:
    contract = _full_contract().model_copy(
        update={"config_schema": {"properties": {"limit": {"type": "number", "default": float("inf")}}}}
    )
    with pytest.raises(ValueError, match="not JSON compliant"):
        emit_config_artifacts(contract, tmp_path)
