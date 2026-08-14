from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings
from app.world.errors import WorldSourceError
from app.world.runtime import build_world_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an explicit official-policy smoke check.")
    parser.add_argument("--topic", default="")
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    runtime = build_world_runtime(load_settings())
    if not args.topic and args.limit == 10:
        print(json.dumps(asdict(runtime.status()), ensure_ascii=False, indent=2))
        return 0
    try:
        result = await runtime.policy_updates(topic=args.topic, limit=args.limit)
    except WorldSourceError as exc:
        print(
            json.dumps(
                {"ready": False, "error_code": exc.code.value, "retryable": exc.retryable},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    observation = result.batch.observations[0]
    print(
        json.dumps(
            {
                "ready": True,
                "source_id": result.batch.source_id,
                "cache_hit": result.cache_hit,
                "shared_request": result.shared_request,
                "item_count": len(observation.payload.get("items", [])),
                "items": observation.payload.get("items", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
