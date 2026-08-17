from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.control.service_watchdog import GptSovitsWatchPolicy, GptSovitsWatchdog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restart GPT-SoVITS when its API goes down.")
    parser.add_argument("--interval", type=float, default=20.0, help="Check interval seconds.")
    parser.add_argument("--fail-threshold", type=int, default=2, help="Consecutive failures before restart.")
    parser.add_argument("--max-restarts", type=int, default=5, help="Restart cap per hour.")
    parser.add_argument("--grace", type=float, default=120.0, help="Ignore checks this long after a restart.")
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy = GptSovitsWatchPolicy(
        check_interval_seconds=args.interval,
        fail_threshold=args.fail_threshold,
        max_restarts_per_hour=args.max_restarts,
        grace_after_restart_seconds=args.grace,
    )
    watchdog = GptSovitsWatchdog(policy=policy)
    if args.once:
        print(watchdog.check_once())
        return
    watchdog.run_forever()


if __name__ == "__main__":
    main()
