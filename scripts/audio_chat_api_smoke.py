from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import sys
from pathlib import Path

import httpx

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets


DEFAULT_AUDIO_PATH = PROJECT_ROOT / "data" / "asr_samples" / "funasr-zh-example-001.wav"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "audio-chat-api-smoke"


def response_passed(status_code: int | None, body: dict[str, object] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    body = body or {}
    transcript = str(body.get("transcript_text", ""))
    reply = str(body.get("reply_text", ""))
    chat = body.get("chat") if isinstance(body.get("chat"), dict) else {}
    if status_code != 200:
        reasons.append(f"HTTP 状态不是 200: {status_code}")
    if not transcript.strip():
        reasons.append("语音转文字为空")
    if not reply.strip():
        reasons.append("胡桃回复为空")
    if len(reply.strip()) > 120:
        reasons.append("胡桃回复过长")
    if isinstance(chat, dict) and chat.get("used_live_api") is not True:
        reasons.append("胡桃回复没有使用真实 API")
    if isinstance(chat, dict) and chat.get("fallback_used") is True:
        reasons.append("胡桃回复触发 fallback")
    for term in ["欢迎", "体验"]:
        if term not in transcript:
            reasons.append(f"语音转文字缺少关键词: {term}")
    cjk_count = sum(1 for char in reply if "\u4e00" <= char <= "\u9fff")
    if cjk_count < max(2, len(reply) // 5):
        reasons.append("胡桃回复中文占比过低")
    return not reasons, reasons


def run_smoke(
    *,
    base_url: str = "http://127.0.0.1:8011",
    audio_path: Path = DEFAULT_AUDIO_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    timeout_seconds: float = 240.0,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audio-chat-api-smoke-report.md"
    result_path = output_dir / "audio-chat-api-smoke-result.json"

    try:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        with audio_path.open("rb") as file:
            response = httpx.post(
                base_url.rstrip("/") + "/api/v1/audio/chat/file",
                data={
                    "session_id": f"audio-chat-api-smoke-{timestamp}",
                    "user_id": "audio-chat-api-smoke-user",
                },
                files={"file": (audio_path.name, file, content_type)},
                timeout=timeout_seconds,
            )
        body = response.json()
        passed, reasons = response_passed(response.status_code, body)
        data = {
            "status": "PASS" if passed else "FAIL",
            "status_code": response.status_code,
            "audio_path": str(audio_path),
            "response": body,
            "reasons": reasons,
            "error": None,
        }
    except Exception as exc:
        data = {
            "status": "FAIL",
            "status_code": None,
            "audio_path": str(audio_path),
            "response": None,
            "reasons": ["接口调用抛错"],
            "error": redact_secrets(str(exc)),
        }
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
    return report_path


def write_report(
    *,
    report_path: Path,
    result_path: Path,
    data: dict[str, object],
    started_at: dt.datetime,
) -> None:
    finished_at = dt.datetime.now()
    response = data.get("response") or {}
    transcript = response.get("transcript_text", "") if isinstance(response, dict) else ""
    reply = response.get("reply_text", "") if isinstance(response, dict) else ""
    chat = response.get("chat", {}) if isinstance(response, dict) else {}
    used_live_api = chat.get("used_live_api") if isinstance(chat, dict) else None
    fallback_used = chat.get("fallback_used") if isinstance(chat, dict) else None
    reasons = data.get("reasons") or []
    reason_text = "无" if not reasons else "；".join(str(item) for item in reasons)
    lines = [
        "# 音频到胡桃真实联动测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- HTTP 状态: {data.get('status_code')}",
        f"- 音频: `{data['audio_path']}`",
        f"- 语音转文字: {transcript or '无'}",
        f"- 胡桃回复: {reply or '无'}",
        f"- 使用真实 API: {used_live_api}",
        f"- fallback: {fallback_used}",
        f"- 失败原因: {reason_text}",
        f"- 错误: {data.get('error') or '无'}",
        f"- 原始 JSON: `{result_path}`",
        "",
    ]
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实音频到胡桃 API 联动 smoke 测试。")
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--audio-path", default=str(DEFAULT_AUDIO_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_smoke(
        base_url=args.base_url,
        audio_path=Path(args.audio_path),
        output_root=Path(args.output_root),
    )
    result_path = report_path.parent / "audio-chat-api-smoke-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"音频到胡桃真实联动测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
