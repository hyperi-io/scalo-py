#  Project:   scalo
#  File:      src/scalo/ddl/__init__.py
#  Purpose:   DDL module -- declare ClickHouse tables, apply them to any topology
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Apply a declared ClickHouse schema to whatever server you are pointed at.

Making your tables exist before you serve traffic is a startup concern, the same
shelf as health probes and the config cascade. What differs per deployment is
the storage engine, and you cannot read that off the DDL: a keeperless node
rejects the Replicated forms, a Replicated database wants them argumentless, an
Atomic database on a cluster needs ``ON CLUSTER``, and Cloud substitutes its own.

:class:`~scalo.ddl.engine.EngineResolver` senses the server and picks, so a
service declares the engine it needs and stays portable::

    from scalo.ddl import EngineResolver, parse_engine

    resolver = EngineResolver(client=ch, topology_setting=cfg.topology)
    resolved = resolver.resolve(parse_engine("ReplacingMergeTree(updated_at)"), "analytics")

    ch.command(
        f"CREATE TABLE IF NOT EXISTS analytics.events{resolved.on_cluster} "
        f"(id UInt64, updated_at DateTime) "
        f"ENGINE = {resolved.clause} ORDER BY id"
    )

Nothing here knows what your tables mean. Column definitions, type systems and
schema registries belong to the application; this module owns the mechanics of
getting them onto a server.
"""

from scalo.ddl.engine import (
    EngineResolver,
    EngineSpec,
    ResolvedEngine,
    Topology,
    parse_engine,
)

__all__ = [
    "EngineResolver",
    "EngineSpec",
    "ResolvedEngine",
    "Topology",
    "parse_engine",
]
