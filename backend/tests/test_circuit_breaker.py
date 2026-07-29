"""Unit tests for the integration-gateway circuit breaker (R3 TA1.2)."""

from __future__ import annotations

from app.integrations.circuit_breaker import CircuitBreaker


class _FakeClock:
    """A manually advanced monotonic clock."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_closed_by_default() -> None:
    breaker = CircuitBreaker(clock=_FakeClock())
    assert breaker.is_open() is False


def test_opens_after_threshold_failures_in_window() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(threshold=5, window=60.0, cooldown=60.0, clock=clock)
    for _ in range(4):
        breaker.record_failure()
    assert breaker.is_open() is False  # 4 < 5
    breaker.record_failure()  # 5th
    assert breaker.is_open() is True


def test_failures_outside_window_do_not_trip() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(threshold=5, window=60.0, clock=clock)
    for _ in range(4):
        breaker.record_failure()
    clock.advance(61.0)  # the 4 age out of the window
    breaker.record_failure()  # only 1 recent failure
    assert breaker.is_open() is False


def test_success_resets_breaker() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(threshold=3, window=60.0, clock=clock)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.is_open() is True
    breaker.record_success()
    assert breaker.is_open() is False


def test_half_open_after_cooldown() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(threshold=3, window=60.0, cooldown=60.0, clock=clock)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.is_open() is True
    clock.advance(30.0)
    assert breaker.is_open() is True  # still cooling down
    clock.advance(31.0)  # cooldown elapsed
    assert breaker.is_open() is False  # half-open probe allowed
