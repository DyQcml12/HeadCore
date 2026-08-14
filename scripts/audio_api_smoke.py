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
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "audio-api-smoke"


def api_result_passed(status_code: int | None, text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if status_code != 200:
        reasons.append(f"HTTP 状态不是 200: {status_code}")
    if not text.strip():
        reasons.append("接口返回文本为空")
    for term in ["欢迎", "体验"]:
        if term not in text:
            reasons.append(f"缺少关键词: {term}")
    return not reasons, reasons


def run_smoke(
    *,
    base_url: str = "http://127.0.0.1:8011",
    audio_path: Path = DEFAULT_AUDIO_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    timeout_seconds: float = 180.0,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audio-api-smoke-report.md"
    result_path = output_dir / "audio-api-smoke-result.json"

    try:
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        with audio_path.open("rb") as file:
            response = httpx.post(
                base_url.rstrip("/") + "/api/v1/audio/transcribe/file",
                files={"file": (audio_path.name, file, content_type)},
                timeout=timeout_seconds,
            )
        body = response.json()
        text = str(body.get("text", ""))
        passed, reasons = api_result_passed(response.status_code, text)
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
    text = response.get("text", "") if isinstance(response, dict) else ""
    reasons = data.get("reasons") or []
    reason_text = "无" if not reasons else "；".join(str(item) for item in reasons)
    lines = [
        "# 音频转写 API 真实接口测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- HTTP 状态: {data.get('status_code')}",
        f"- 音频: `{data['audio_path']}`",
        f"- 文本: {text or '无'}",
        f"- 失败原因: {reason_text}",
        f"- 错误: {data.get('error') or '无'}",
        f"- 原始 JSON: `{result_path}`",
        "",
    ]
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实音频转写 API smoke 测试。")
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
    result_path = report_path.parent / "audio-api-smoke-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"音频转写 API 真实接口测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
