from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets
from app.main import app


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "database-control-smoke"


async def run_database_control_smoke(
    *,
    actor_platform: str,
    actor_user_id: str,
    allow_write: bool = False,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    started_at = dt.datetime.now()
    output_dir = output_root / started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "database-control-smoke-report.md"
    headers = {
        "X-Hutao-Actor-Platform": actor_platform,
        "X-Hutao-Actor-User-Id": actor_user_id,
    }
    checks: list[dict[str, object]] = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
        for path in (
            "/api/control/database-v2/status",
            "/api/control/database-v2/admin",
            "/api/control/database-v2/profiles?limit=1",
        ):
            response = await client.get(path, headers=headers)
            checks.append(_response_check("GET", path, response))

        if allow_write and all(int(check["status_code"]) == 200 for check in checks):
            admin_response = await client.get(
                "/api/control/database-v2/admin", headers=headers
            )
            profile = admin_response.json()["profile"]
            path = f"/api/control/database-v2/profiles/{profile['id']}/relationship"
            response = await client.post(
                path,
                headers=headers,
                json={
                    "relationship_type": profile["relationship_type"],
                    "verified": profile["verified"],
                    "reason": "database control idempotent smoke",
                },
            )
            checks.append(_response_check("POST", path, response))

    status = "PASS" if checks and all(int(item["status_code"]) == 200 for item in checks) else "FAIL"
    data = {
        "status": status,
        "mode": "read-write" if allow_write else "read-only",
        "actor_platform": actor_platform,
        "actor_user_id": _redact_id(actor_user_id),
        "checks": checks,
    }
    safe_json = redact_secrets(json.dumps(data, ensure_ascii=False, indent=2))
    report_path.write_text(
        "\n".join(
            [
                "# Database Control Smoke Report",
                "",
                f"- Result: {status}",
                f"- Mode: {data['mode']}",
                f"- Started at: {started_at.isoformat(timespec='seconds')}",
                "",
                "```json",
                safe_json,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report_path


def _response_check(method: str, path: str, response: httpx.Response) -> dict[str, object]:
    payload = response.json()
    error_code = payload.get("error", {}).get("code") if isinstance(payload, dict) else None
    return {
        "method": method,
        "path": path.split("?", 1)[0],
        "status_code": response.status_code,
        "error_code": error_code,
    }


def _redact_id(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * min(8, len(value) - 4)}{value[-2:]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Database V2 control-plane smoke checks.")
    parser.add_argument("--actor-platform", choices=["qq", "wechat"], required=True)
    parser.add_argument("--actor-user-id", required=True)
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Run one idempotent admin relationship write after read checks pass.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(
        run_database_control_smoke(
            actor_platform=args.actor_platform,
            actor_user_id=args.actor_user_id,
            allow_write=args.allow_write,
        )
    )
    print(f"Database control smoke report: {report}")


if __name__ == "__main__":
    main()
