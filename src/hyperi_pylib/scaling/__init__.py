#  Project:      hyperi-pylib
#  File:         src/hyperi_pylib/scaling/__init__.py
#  Purpose:      Scaling pressure module for KEDA autoscaling
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Scaling pressure calculator for KEDA autoscaling.

Calculates a composite 0-100 pressure score from weighted component
saturations, matching rustlib's ``src/scaling/pressure.rs`` gate logic.

Quick start::

    from hyperi_pylib.scaling import ScalingPressure, ScalingPressureConfig

    sp = ScalingPressure()
    sp.set_component("memory", 0.6)
    sp.set_component("queue", 0.8)
    sp.set_memory(used_bytes=512_000_000, limit_bytes=1_073_741_824)

    pressure = sp.calculate()  # 0-100 composite score
    snap = sp.snapshot()       # Frozen point-in-time state
"""

from .pressure import PressureSnapshot, ScalingPressure, ScalingPressureConfig

__all__ = [
    "PressureSnapshot",
    "ScalingPressure",
    "ScalingPressureConfig",
]
