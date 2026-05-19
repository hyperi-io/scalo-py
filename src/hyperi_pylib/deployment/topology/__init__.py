# Project:   hyperi-pylib
# File:      deployment/topology/__init__.py
# Purpose:   DeploymentTopology Pydantic schema (shared across Rust + Python)
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""DeploymentTopology schema.

Cross-language data type describing which apps + third-party charts compose
into a deployable HyperI stack. Consumed by ``hyperi-ci stitch`` to
generate umbrella Helm charts; mirrored in
``hyperi_rustlib::deployment::topology`` for Rust consumers.

This module is opt-in via the parent ``[deployment]`` extra; the gate
follows the same pattern as ``hyperi_pylib.deployment`` itself.

Symbols are resolved lazily via :pep:`562` ``__getattr__`` so the package
can be imported even while sibling modules are still being built up
incrementally during development. Each sibling module
(``errors``, ``model``, ``loader``) lands as a self-contained atomic
commit; the package init does not have to be amended to bring each one
online.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import pydantic

    TOPOLOGY_AVAILABLE = True
except ImportError:
    TOPOLOGY_AVAILABLE = False


__all__ = [
    "TOPOLOGY_AVAILABLE",
    "AppEntry",
    "ArgocdHints",
    "DeploymentTopology",
    "GlueEntry",
    "ThirdPartyEntry",
    "TopologyError",
    "TopologySpec",
    "TopologyValidationError",
    "UmbrellaMeta",
    "VersionResolutionError",
    "load_topology",
]


# Public symbol -> (submodule name, attribute name) for PEP 562 lazy lookup.
_LAZY_MAP: dict[str, tuple[str, str]] = {
    "TopologyError": ("errors", "TopologyError"),
    "TopologyValidationError": ("errors", "TopologyValidationError"),
    "VersionResolutionError": ("errors", "VersionResolutionError"),
    "AppEntry": ("model", "AppEntry"),
    "ArgocdHints": ("model", "ArgocdHints"),
    "DeploymentTopology": ("model", "DeploymentTopology"),
    "GlueEntry": ("model", "GlueEntry"),
    "ThirdPartyEntry": ("model", "ThirdPartyEntry"),
    "TopologySpec": ("model", "TopologySpec"),
    "UmbrellaMeta": ("model", "UmbrellaMeta"),
    "load_topology": ("loader", "load_topology"),
}


def __getattr__(name: str) -> Any:
    """Resolve a public symbol lazily from the appropriate sibling module."""
    if not TOPOLOGY_AVAILABLE:
        from hyperi_pylib.secrets.exceptions import ProviderNotAvailableError

        raise ProviderNotAvailableError(
            "deployment.topology",
            "pydantic",
            "pip install 'hyperi-pylib[deployment]'",
        )

    target = _LAZY_MAP.get(name)
    if target is None:
        raise AttributeError(f"module 'hyperi_pylib.deployment.topology' has no attribute {name!r}")

    submodule, attr = target
    from importlib import import_module

    mod = import_module(f"hyperi_pylib.deployment.topology.{submodule}")
    value = getattr(mod, attr)
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value


if TYPE_CHECKING:
    from hyperi_pylib.deployment.topology.errors import (
        TopologyError,
        TopologyValidationError,
        VersionResolutionError,
    )
    from hyperi_pylib.deployment.topology.loader import load_topology
    from hyperi_pylib.deployment.topology.model import (
        AppEntry,
        ArgocdHints,
        DeploymentTopology,
        GlueEntry,
        ThirdPartyEntry,
        TopologySpec,
        UmbrellaMeta,
    )
