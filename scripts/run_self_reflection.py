from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import load_settings
from app.head.reflection_loop import run_self_reflection
from app.storage.repository_factory import create_chat_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline self-profile reflection loop.")
    parser.add_argument("--user-id", required=True, help="Target local user id (never printed).")
    parser.add_argument("--force", action="store_true", help="Skip the feedback-evidence threshold.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    repository = create_chat_repository(settings)
    result: dict[str, Any] = asyncio.run(
        run_self_reflection(repository, user_id=args.user_id, force=args.force)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"UPDATED", "NO_CHANGE", "SKIPPED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
