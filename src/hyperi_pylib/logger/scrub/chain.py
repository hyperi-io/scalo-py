#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/chain.py
#  Purpose:   LayeredScrubber composition + NoOpScrubber test double
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Concrete Scrubber implementations.

:class:`LayeredScrubber` composes multiple per-layer scrubbers in
spec-mandated order. :class:`NoOpScrubber` passes input through
unchanged -- for tests and dependency-injection swaps.

Per spec §2.3, both are discrete objects with explicit per-instance
configuration. No global mutable state.
"""

from __future__ import annotations

import time
import warnings
from collections.abc import Sequence

from .config import ScrubConfig
from .metrics import ScrubMetrics
from .types import Scrubber


class NoOpScrubber:
    """Scrubber that returns input unchanged. For tests and DI.

    Use cases:

    - Test fixtures where scrubbing would obscure assertions
    - Code paths where scrubbing is explicitly disabled
    - Replacing the production scrubber in CI environments where
      the regex engine isn't built yet
    """

    def scrub(self, text: str) -> str:
        """Return ``text`` unchanged."""
        return text

    def __repr__(self) -> str:
        return "NoOpScrubber()"


class LayeredScrubber:
    """Compose multiple :class:`Scrubber` layers in spec-mandated order.

    Per spec §2.1, layers run in numeric order L1 -> L2 -> L3 -> L4. Each
    receives the output of the previous and may further redact.

    The order is enforced by the order of ``layers`` passed to the
    constructor -- callers MUST pass them in spec order. A future
    refactor may move ordering into the class itself once each layer
    has a stable type.

    Args:
        config: :class:`ScrubConfig` for layer-toggles and behaviour
            flags. Defaults to all-on canonical defaults.
        layers: sequence of :class:`Scrubber` instances to apply in
            order. Empty sequence means pass-through.

    Fail-safe contract (spec §5.1): if any layer raises, that layer
    is skipped for the current call (a one-time warning is emitted)
    and the chain continues with the remaining layers. The original
    text is returned if EVERY layer fails. The scrubber never raises
    to the caller -- broken scrubbing must not break logging itself.
    """

    def __init__(
        self,
        config: ScrubConfig | None = None,
        layers: Sequence[Scrubber] | None = None,
        metrics: ScrubMetrics | None = None,
    ) -> None:
        self._config = config if config is not None else ScrubConfig()
        self._layers: tuple[Scrubber, ...] = tuple(layers or ())
        self._metrics = metrics if metrics is not None else ScrubMetrics.noop()
        # Track which layers have raised at least once so we don't
        # warn repeatedly for the same bug.
        self._broken: set[int] = set()

    @property
    def config(self) -> ScrubConfig:
        """The scrubber's configuration. Read-only."""
        return self._config

    @property
    def layers(self) -> tuple[Scrubber, ...]:
        """The scrubber's layer chain. Read-only."""
        return self._layers

    def scrub(self, text: str) -> str:
        """Apply all layers in order; return the redacted text.

        Per spec §5.1, fails safe: a misbehaving layer is skipped
        with a one-time warning, not propagated to the caller.

        Per spec §5.5, ``observe_only`` mode does not skip layers --
        layers run normally and emit detection metrics, but the
        returned text equals the input. (Metrics not yet wired --
        see Step 9 of the implementation plan.)
        """
        if not self._config.enabled:
            return text

        result = text
        for i, layer in enumerate(self._layers):
            if i in self._broken:
                # Skip layers we've already learned are broken
                continue
            layer_name = type(layer).__name__
            start = time.perf_counter()
            try:
                result = layer.scrub(result)
            except Exception as e:
                self._broken.add(i)
                self._metrics.inc_error(layer_name, type(e).__name__)
                warnings.warn(
                    f"Scrub layer {layer_name} raised "
                    f"{type(e).__name__}: {e}. Skipping this layer for "
                    f"the rest of this process. Logging continues.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            else:
                self._metrics.observe_duration(layer_name, time.perf_counter() - start)

        # Observe-only mode: discard redactions, return input. Detection
        # metrics still fire (when metrics layer lands in Step 9).
        if self._config.observe_only:
            return text

        return result

    def __repr__(self) -> str:
        layer_names = [type(layer).__name__ for layer in self._layers]
        return (
            f"LayeredScrubber(layers={layer_names}, "
            f"enabled={self._config.enabled}, "
            f"observe_only={self._config.observe_only})"
        )
