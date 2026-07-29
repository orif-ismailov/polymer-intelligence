"""Generic circuit breaker for integration-gateway provider calls (R3 — §12).

A dead external provider must not be hammered on every request nor allowed to
starve the pipeline. This breaker trips **open** after `threshold` failures within
`window` seconds; while open, callers should short-circuit (raise a typed
`ProviderUnavailable`) instead of making a network call. After `cooldown` seconds
the breaker goes **half-open** — the next call is allowed as a probe; its success
resets the breaker, a fresh failure re-arms it.

State is in-process (per worker/API process), matching the source-adapter registry
model. Time is injectable (`clock`) so tests drive open/half-open transitions
deterministically without sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class CircuitBreaker:
    """A failure-counting breaker with a cooldown-gated half-open probe."""

    def __init__(
        self,
        *,
        threshold: int = 5,
        window: float = 60.0,
        cooldown: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._window = window
        self._cooldown = cooldown
        self._clock = clock
        self._failures: list[float] = []
        self._opened_at: float | None = None

    def is_open(self) -> bool:
        """True if calls should be short-circuited right now (open, pre-cooldown)."""
        if self._opened_at is None:
            return False
        # Cooldown elapsed → half-open: allow a probe through.
        return (self._clock() - self._opened_at) < self._cooldown

    def record_success(self) -> None:
        """A successful call closes the breaker."""
        self._failures.clear()
        self._opened_at = None

    def record_failure(self) -> None:
        """A failed call; trips open once `threshold` failures fall inside `window`."""
        now = self._clock()
        self._failures.append(now)
        self._failures = [t for t in self._failures if (now - t) < self._window]
        if len(self._failures) >= self._threshold:
            self._opened_at = now
