# Project:   hyperi-pylib
# File:      deployment/topology/model.py
# Purpose:   Pydantic models for DeploymentTopology YAML schema
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Pydantic models for the DeploymentTopology schema.

Schema mirrors the spec at
``docs/superpowers/specs/2026-05-15-helm-composition-and-deployments-repo-spec.md``
section 3.3. Each top-level type maps 1:1 with a YAML stanza.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CHART_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,51}[a-z0-9]$")


class _StrictModel(BaseModel):
    """Strict base -- reject unknown fields so typos surface early."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class AppEntry(_StrictModel):
    """A per-app chart entry under ``spec.apps``."""

    name: str
    version: str = Field(..., min_length=1)
    enabled: bool = True
    condition: str | None = None
    alias: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _CHART_NAME_RE.match(v):
            raise ValueError(f"chart name must be lowercase RFC-1123-ish, got {v!r}")
        return v

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str | None) -> str | None:
        if v is not None and not _CHART_NAME_RE.match(v):
            raise ValueError(f"alias must be lowercase RFC-1123-ish, got {v!r}")
        return v

    @model_validator(mode="after")
    def _derive_condition(self) -> AppEntry:
        if self.condition is None:
            key = self.alias or self.name
            object.__setattr__(self, "condition", f"{key}.enabled")
        return self


class ThirdPartyEntry(_StrictModel):
    """A third-party chart entry under ``spec.thirdParty``."""

    name: str
    repository: str
    version: str = Field(..., min_length=1)
    enabled: bool = True
    condition: str | None = None
    alias: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _CHART_NAME_RE.match(v):
            raise ValueError(f"chart name must be lowercase RFC-1123-ish, got {v!r}")
        return v

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str | None) -> str | None:
        if v is not None and not _CHART_NAME_RE.match(v):
            raise ValueError(f"alias must be lowercase RFC-1123-ish, got {v!r}")
        return v

    @model_validator(mode="after")
    def _derive_condition(self) -> ThirdPartyEntry:
        if self.condition is None:
            key = self.alias or self.name
            object.__setattr__(self, "condition", f"{key}.enabled")
        return self


class GlueEntry(_StrictModel):
    """A glue-template entry under ``spec.glue``."""

    name: str
    file: str

    @field_validator("file")
    @classmethod
    def _validate_relative(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError(f"glue file path must be relative, got absolute {v!r}")
        if ".." in v.split("/"):
            raise ValueError(f"glue file path must not contain '..' segments, got {v!r}")
        return v


class UmbrellaMeta(_StrictModel):
    """Umbrella chart metadata -- becomes the top of stitched Chart.yaml."""

    name: str
    description: str
    appVersion: str = "1.0"  # noqa: N815 -- YAML schema requires camelCase

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _CHART_NAME_RE.match(v):
            raise ValueError(f"umbrella chart name must be lowercase RFC-1123-ish, got {v!r}")
        return v


class ArgocdHints(_StrictModel):
    """ArgoCD app-of-apps / ApplicationSet hints for this topology."""

    appOfApps: bool = False  # noqa: N815 -- YAML schema requires camelCase
    appProject: str = "default"  # noqa: N815
    syncWaves: dict[str, int] = Field(default_factory=dict)  # noqa: N815


class TopologySpec(_StrictModel):
    """The ``spec:`` body of a DeploymentTopology declaration."""

    umbrella: UmbrellaMeta
    apps: list[AppEntry] = Field(default_factory=list)
    thirdParty: list[ThirdPartyEntry] = Field(default_factory=list)  # noqa: N815
    glue: list[GlueEntry] = Field(default_factory=list)
    argocd: ArgocdHints = Field(default_factory=ArgocdHints)

    @model_validator(mode="after")
    def _validate_non_empty(self) -> TopologySpec:
        if not self.apps and not self.thirdParty:
            raise ValueError("topology must declare at least one apps[] or thirdParty[] entry")
        return self

    @model_validator(mode="after")
    def _validate_no_duplicate_names(self) -> TopologySpec:
        seen: set[str] = set()
        for app in self.apps:
            key = app.alias or app.name
            if key in seen:
                raise ValueError(f"duplicate app name/alias: {key}")
            seen.add(key)
        for tp in self.thirdParty:
            key = tp.alias or tp.name
            if key in seen:
                raise ValueError(f"duplicate chart name/alias: {key}")
            seen.add(key)
        return self


class DeploymentTopology(_StrictModel):
    """Root model for a ``topologies/<name>/topology.yaml`` file."""

    apiVersion: Literal["hyperi.io/v1"] = "hyperi.io/v1"  # noqa: N815 -- YAML schema requires camelCase
    kind: Literal["DeploymentTopology"] = "DeploymentTopology"
    metadata: dict[str, str] = Field(default_factory=dict)
    spec: TopologySpec

    @model_validator(mode="after")
    def _validate_metadata_name(self) -> DeploymentTopology:
        if "name" not in self.metadata or not self.metadata["name"]:
            raise ValueError("metadata.name is required")
        if not _CHART_NAME_RE.match(self.metadata["name"]):
            raise ValueError(f"metadata.name must be lowercase RFC-1123-ish, got {self.metadata['name']!r}")
        return self
