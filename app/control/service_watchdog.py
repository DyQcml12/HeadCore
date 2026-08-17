from __future__ import annotations

import time
from dataclasses import dataclass

from app.control.service_manager import start_service
from app.voice_chat.gpt_sovits_tts import check_gpt_sovits_ready


@dataclass(frozen=True)
class GptSovitsWatchPolicy:
    base_url: str = "http://127.0.0.1:9880"
    check_interval_seconds: float = 20.0
    fail_threshold: int = 2
    max_restarts_per_hour: int = 5
    ready_timeout_seconds: float = 5.0
    grace_after_restart_seconds: float = 120.0


class GptSovitsWatchdog:
    """Restart GPT-SoVITS after consecutive health failures, with hourly caps.

    Readiness is probed via the api_v2 OpenAPI schema (same check the app
    itself uses). Restarts go through the control-center service manager so
    logs and process bookkeeping stay consistent.
    """

    def __init__(
        self,
        *,
        policy: GptSovitsWatchPolicy | None = None,
        ready_check=None,  # type: ignore[no-untyped-def]
        restarter=None,  # type: ignore[no-untyped-def]
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self._policy = policy or GptSovitsWatchPolicy()
        if not 1 <= self._policy.fail_threshold <= 10:
            raise ValueError("watchdog fail_threshold must be between 1 and 10")
        if not 1 <= self._policy.max_restarts_per_hour <= 60:
            raise ValueError("watchdog max_restarts_per_hour must be between 1 and 60")
        if not 5.0 <= self._policy.check_interval_seconds <= 3600:
            raise ValueError("watchdog check_interval_seconds must be between 5 and 3600")
        if not 10.0 <= self._policy.grace_after_restart_seconds <= 1800:
            raise ValueError("watchdog grace_after_restart_seconds must be between 10 and 1800")
        self._ready_check = ready_check or (
            lambda: check_gpt_sovits_ready(
                self._policy.base_url, self._policy.ready_timeout_seconds
            )
        )
        self._restarter = restarter or self._default_restarter
        self._clock = clock
        self._sleeper = sleeper
        self._consecutive_failures = 0
        self._restart_times: list[float] = []
        self._grace_until: float = 0.0

    def _default_restarter(self) -> bool:
        try:
            result = start_service("gpt_sovits")
            return bool(result.get("running"))
        except Exception:
            return False

    def check_once(self) -> str:
        """Run one check. Returns healthy/down/starting/restarted/restart-failed/restart-limited."""
        now = self._clock()
        if now < self._grace_until:
            return "starting"
        self._restart_times = [t for t in self._restart_times if now - t < 3600]
        if self._ready_check():
            self._consecutive_failures = 0
            return "healthy"
        self._consecutive_failures += 1
        if self._consecutive_failures < self._policy.fail_threshold:
            return "down"
        if len(self._restart_times) >= self._policy.max_restarts_per_hour:
            return "restart-limited"
        restarted = self._restarter()
        self._consecutive_failures = 0
        self._restart_times.append(now)
        if restarted:
            self._grace_until = now + self._policy.grace_after_restart_seconds
            return "restarted"
        return "restart-failed"

    def run_forever(self) -> None:
        while True:
            result = self.check_once()
            if result != "healthy":
                print(f"[gpt-sovits watchdog] {result}")
            self._sleeper(self._policy.check_interval_seconds)
