from __future__ import annotations

import argparse
import asyncio
import socket
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings
from app.knowledge.factory import build_semantic_memory_outbox_processor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize derived semantic-memory vectors from the MySQL outbox."
    )
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit.")
    parser.add_argument("--limit", type=int, default=32, help="Maximum events per batch (1-100).")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Delay between batches.")
    return parser.parse_args()


async def run_worker(args: argparse.Namespace) -> int:
    if not 1 <= args.limit <= 100:
        raise ValueError("--limit must be between 1 and 100")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    processor = build_semantic_memory_outbox_processor(
        load_settings(),
        worker_id=f"{socket.gethostname()}-semantic-memory",
    )
    if processor is None:
        raise RuntimeError("semantic memory worker is not configured")
    await processor.initialize_index()
    if args.once:
        completed = await processor.process_once(limit=args.limit)
        print(f"semantic_memory_sync completed={completed}")
        return 0
    while True:
        await processor.process_once(limit=args.limit)
        await asyncio.sleep(args.poll_seconds)


def main() -> int:
    try:
        return asyncio.run(run_worker(parse_args()))
    except (RuntimeError, ValueError) as exc:
        print(f"semantic_memory_sync error={type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
