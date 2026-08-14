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
from app.world.runtime import build_world_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an explicit cached multi-source news digest.")
    parser.add_argument("--sources", help="Comma-separated registered news source IDs.")
    parser.add_argument("--topic", default="")
    parser.add_argument("--per-source-limit", type=int, default=10)
    parser.add_argument("--max-items", type=int, default=20)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    runtime = build_world_runtime(load_settings())
    if not args.sources:
        print(json.dumps(asdict(runtime.status()), ensure_ascii=False, indent=2))
        return 0
    source_ids = tuple(value.strip() for value in args.sources.split(",") if value.strip())
    result = await runtime.news_digest(
        topic=args.topic,
        source_ids=source_ids,
        per_source_limit=args.per_source_limit,
        max_items=args.max_items,
    )
    print(
        json.dumps(
            {
                "ready": any(source.success for source in result.digest.sources),
                "cache_hit": result.cache_hit,
                "shared_request": result.shared_request,
                "cache_key": result.cache_key,
                "topic": result.digest.topic,
                "sources": [asdict(source) for source in result.digest.sources],
                "items": [asdict(item) for item in result.digest.items],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if any(source.success for source in result.digest.sources) else 2


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
