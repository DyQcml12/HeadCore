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
from app.services.model_audit import ModelInvocationAuditLogger
from app.storage.repository_factory import create_chat_repository


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "live-stream-smoke"


async def run_live_stream_smoke(output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "live-stream-smoke-report.md"
    result_path = output_dir / "live-stream-smoke-result.json"

    settings = load_settings()
    if not settings.deepseek_api_key:
        data = {
            "status": "SKIP",
            "reason": "缺少 DEEPSEEK_API_KEY，无法运行真实流式测试。",
        }
        write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
        return report_path

    service = ChatService(
        settings,
        audit_logger=ModelInvocationAuditLogger(output_dir / "audit.jsonl"),
        repository=create_chat_repository(settings),
    )
    user_id = "live-stream-user-" + timestamp
    session_id = "live-stream-" + timestamp
    chunks: list[str] = []
    error: str | None = None
    try:
        async for chunk in service.stream_reply(
            "少说点，随便接我一句。",
            session_id=session_id,
            user_id=user_id,
        ):
            chunks.append(chunk)
    except Exception as exc:
        error = redact_secrets(str(exc))

    text = "".join(chunks)
    data = {
        "status": "PASS" if chunks and error is None else "FAIL",
        "provider": settings.model_provider,
        "model": settings.model_name,
        "storage_backend": settings.storage_backend,
        "chunk_count": len(chunks),
        "text": text,
        "error": error,
    }
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
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    lines = [
        "# 真实流式输出测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- 模型供应商: {data.get('provider')}",
        f"- 模型名称: {data.get('model')}",
        f"- 存储后端: {data.get('storage_backend')}",
        f"- 分片数量: {data.get('chunk_count')}",
        f"- 最终文本: {data.get('text')}",
        f"- 原始 JSON: `{result_path}`",
    ]
    if data.get("error"):
        lines.extend(["", "## 错误", "", str(data["error"])])
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实 DeepSeek 流式输出测试。")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(run_live_stream_smoke(Path(args.output_root)))
    print(f"真实流式输出测试报告: {report_path}")
    result_path = report_path.parent / "live-stream-smoke-result.json"
    status = "FAIL"
    if result_path.exists():
        status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
