from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class CameraControlClient:
    base_url: str
    actor_platform: str
    actor_user_id: str
    actor_group_id: str = ""
    timeout_seconds: float = 10.0

    def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        headers = {
            "X-Hutao-Actor-Platform": self.actor_platform,
            "X-Hutao-Actor-User-Id": self.actor_user_id,
        }
        if self.actor_group_id:
            headers["X-Hutao-Actor-Group-Id"] = self.actor_group_id
        try:
            response = httpx.request(
                method,
                self.base_url.rstrip("/") + path,
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = _response_detail(exc.response)
            raise RuntimeError(f"control_request_rejected:{exc.response.status_code}:{detail}") from exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"control_core_unreachable:{self.base_url.rstrip('/')}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("control_request_unavailable") from exc
        if not isinstance(data, dict):
            raise RuntimeError("control_response_invalid")
        return data


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operate consent-gated local camera sessions through HutaoCore.")
    parser.add_argument("--core-url", default="http://127.0.0.1:8000")
    parser.add_argument("--actor-platform", default="core")
    parser.add_argument("--actor-user-id", required=True)
    parser.add_argument("--actor-group-id", default="")
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("session-start", help="Create a consented camera session.")
    start.add_argument("--camera-slot", type=int, default=0)
    for command in ("camera-capture-start", "capture-status", "capture-stop", "session-stop"):
        item = subcommands.add_parser(command)
        item.add_argument("--session-id", required=True)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, object]:
    client = CameraControlClient(
        base_url=args.core_url,
        actor_platform=args.actor_platform,
        actor_user_id=args.actor_user_id,
        actor_group_id=args.actor_group_id,
    )
    if args.command == "session-start":
        return client.request("POST", "/api/control/camera/sessions", {"consent_granted": True, "camera_slot": args.camera_slot})
    paths = {
        "camera-capture-start": ("POST", f"/api/control/camera/sessions/{args.session_id}/capture/start"),
        "capture-status": ("GET", f"/api/control/camera/sessions/{args.session_id}/capture/status"),
        "capture-stop": ("POST", f"/api/control/camera/sessions/{args.session_id}/capture/stop"),
        "session-stop": ("POST", f"/api/control/camera/sessions/{args.session_id}/stop"),
    }
    method, path = paths[args.command]
    payload = None
    return client.request(method, path, payload)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _response_detail(response: httpx.Response) -> str:
    try:
        data: Any = response.json()
        detail = data.get("detail") if isinstance(data, dict) else None
        if isinstance(detail, dict):
            return str(detail.get("code") or "request_rejected")
    except ValueError:
        pass
    return "request_rejected"


if __name__ == "__main__":
    raise SystemExit(main())
