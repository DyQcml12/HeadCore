from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.services.chat_service import ChatService


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "api-smoke"
DEFAULT_USER_INPUT = "\u6211 debug \u4e00\u665a\u4e0a\u4e86\uff0c\u771f\u7684\u70e6\u3002"


async def run_smoke(user_input: str, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "api-smoke-report.md"
    json_path = output_dir / "api-smoke-result.json"

    settings = load_settings()
    response = await ChatService(settings).reply(user_input)
    finished_at = dt.datetime.now()
    data = response.model_dump()

    json_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report = "\n".join(
        [
            "# API Smoke Report",
            "",
            f"- Started at: {started_at.isoformat(timespec='seconds')}",
            f"- Finished at: {finished_at.isoformat(timespec='seconds')}",
            f"- Provider: {settings.model_provider}",
            f"- Model: {settings.model_name}",
            f"- Used live API: {response.used_live_api}",
            f"- Fallback used: {response.fallback_used}",
            f"- Raw JSON: `{json_path}`",
            "",
            "## User Input",
            "",
            user_input,
            "",
            "## Reply",
            "",
            response.text,
            "",
            "## Error",
            "",
            redact_secrets(response.error or "none"),
            "",
        ]
    )
    report_path.write_text(redact_secrets(report), encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one live API smoke chat.")
    parser.add_argument(
        "--user-input",
        default=DEFAULT_USER_INPUT,
        help="User message for the smoke test.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path = asyncio.run(run_smoke(args.user_input))
    print(f"API smoke report: {report_path}")


if __name__ == "__main__":
    main()
