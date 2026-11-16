#  Project:   scalo
#  File:      tests/unit/deployment/test_images.py
#  Purpose:   Which test image references go through the mirror
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Docker Hub references go through the mirror, every other registry does not."""

import pytest

from scalo.deployment.test_support import services
from scalo.deployment.test_support.images import DEFAULT_IMAGE_MIRROR, image_mirror, mirrored

KAFKA = "apache/kafka:4.3.1@sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837"


@pytest.mark.parametrize(
    ("mirror", "reference", "expected"),
    [
        ("m", "alpine:3.24.2", "m/library/alpine:3.24.2"),
        ("m/", "docker.io/alpine:3.24.2", "m/library/alpine:3.24.2"),
        ("m", "docker.io/library/busybox:1", "m/library/busybox:1"),
        ("m", "index.docker.io/prom/prometheus:v3", "m/prom/prometheus:v3"),
        ("m", KAFKA, f"m/{KAFKA}"),
        ("m", "ghcr.io/kafbat/kafka-ui:v1.5.0", "ghcr.io/kafbat/kafka-ui:v1.5.0"),
        ("m", "localhost:5000/app:1", "localhost:5000/app:1"),
        ("m", "localhost/app:1", "localhost/app:1"),
        ("", "alpine:3.24.2", "alpine:3.24.2"),
        ("", "docker.io/alpine:3.24.2", "alpine:3.24.2"),
    ],
)
def test_mirrored(mirror: str, reference: str, expected: str) -> None:
    assert mirrored(mirror, reference) == expected


@pytest.mark.parametrize(("env", "expected"), [(None, DEFAULT_IMAGE_MIRROR), ("", ""), ("r/x", "r/x")])
def test_env_layer_without_config(monkeypatch: pytest.MonkeyPatch, env: str | None, expected: str) -> None:
    if env is None:
        monkeypatch.delenv("DEPLOYMENT__TEST_IMAGE_MIRROR", raising=False)
    else:
        monkeypatch.setenv("DEPLOYMENT__TEST_IMAGE_MIRROR", env)
    assert image_mirror() == expected


def test_shared_specs_pull_through_the_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT__TEST_IMAGE_MIRROR", "m")
    assert services.kafka_spec().image == f"m/{services.KAFKA_IMAGE}"
    assert services.clickhouse_spec().image == f"m/{services.CLICKHOUSE_IMAGE}"
    assert services.openbao_spec().image == f"m/{services.OPENBAO_IMAGE}"
