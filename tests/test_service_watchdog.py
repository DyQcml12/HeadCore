from __future__ import annotations

import pytest

from app.control.service_watchdog import GptSovitsWatchPolicy, GptSovitsWatchdog


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_watchdog(
    ready_results: list[bool],
    *,
    restarter=None,  # type: ignore[no-untyped-def]
    policy: GptSovitsWatchPolicy | None = None,
    clock: FakeClock | None = None,
):
    results = iter(ready_results)
    calls = {"restarts": 0}

    def ready_check() -> bool:
        return next(results, True)

    def default_restarter() -> bool:
        calls["restarts"] += 1
        return True

    watchdog = GptSovitsWatchdog(
        policy=policy
        or GptSovitsWatchPolicy(
            check_interval_seconds=20.0,
            fail_threshold=2,
            max_restarts_per_hour=5,
            grace_after_restart_seconds=120.0,
        ),
        ready_check=ready_check,
        restarter=restarter or default_restarter,
        clock=clock or FakeClock(),
    )
    return watchdog, calls


def test_watchdog_reports_healthy_and_resets_failures() -> None:
    watchdog, calls = make_watchdog([False, True, True])

    assert watchdog.check_once() == "down"
    assert watchdog.check_once() == "healthy"
    assert watchdog.check_once() == "healthy"
    assert calls["restarts"] == 0


def test_watchdog_restarts_after_fail_threshold() -> None:
    watchdog, calls = make_watchdog([False, False, True])

    assert watchdog.check_once() == "down"
    assert watchdog.check_once() == "restarted"
    assert watchdog.check_once() == "starting"  # inside grace window
    assert calls["restarts"] == 1


def test_watchdog_leaves_grace_and_heals() -> None:
    clock = FakeClock()
    watchdog, calls = make_watchdog([False, False, True, True], clock=clock)

    assert watchdog.check_once() == "down"
    assert watchdog.check_once() == "restarted"
    clock.advance(200.0)  # beyond grace
    assert watchdog.check_once() == "healthy"


def test_watchdog_caps_restarts_per_hour() -> None:
    clock = FakeClock()
    policy = GptSovitsWatchPolicy(
        check_interval_seconds=20.0,
        fail_threshold=1,
        max_restarts_per_hour=1,
        grace_after_restart_seconds=120.0,
    )
    watchdog, calls = make_watchdog([False, False, False], policy=policy, clock=clock)

    assert watchdog.check_once() == "restarted"
    assert watchdog.check_once() == "starting"  # inside grace window
    clock.advance(200.0)
    assert watchdog.check_once() == "restart-limited"
    assert calls["restarts"] == 1


def test_watchdog_reports_restarter_failure_without_grace() -> None:
    attempts: list[bool] = []

    def flaky_restarter() -> bool:
        attempts.append(True)
        return len(attempts) > 1  # first attempt fails, second succeeds

    watchdog, calls = make_watchdog([False, False, False, False], restarter=flaky_restarter)

    assert watchdog.check_once() == "down"
    assert watchdog.check_once() == "restart-failed"
    assert watchdog.check_once() == "down"  # needs another failure to retry
    assert watchdog.check_once() == "restarted"
    assert len(attempts) == 2


def test_watchdog_rejects_invalid_policy() -> None:
    with pytest.raises(ValueError, match="fail_threshold"):
        GptSovitsWatchdog(policy=GptSovitsWatchPolicy(fail_threshold=0))
    with pytest.raises(ValueError, match="max_restarts_per_hour"):
        GptSovitsWatchdog(policy=GptSovitsWatchPolicy(max_restarts_per_hour=0))
