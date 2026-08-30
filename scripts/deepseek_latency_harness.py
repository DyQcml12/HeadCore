from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.services.model_client import DeepSeekClient
from app.storage.repository_factory import create_chat_repository


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "deepseek-latency"
DEFAULT_PROMPT = "\u8bf7\u81ea\u7136\u5730\u56de\u590d\u6211\u4e00\u53e5\u8bdd\uff0c\u4e0d\u8981\u5199\u89e3\u91ca\u3002"


async def run_harness(*, count: int, prompt: str, output_root: Path) -> Path:
    started_at = dt.datetime.now(dt.timezone.utc)
    run_dir = output_root / started_at.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "result.json"
    report_path = run_dir / "report.md"
    settings = load_settings()
    if not settings.deepseek_api_key:
        result_path.write_text(
            json.dumps({"status": "SKIP", "reason": "DEEPSEEK_API_KEY is not configured"}, indent=2),
            encoding="utf-8",
        )
        report_path.write_text("# DeepSeek latency harness\n\nStatus: SKIP\n", encoding="utf-8")
        return report_path

    client = DeepSeekClient(settings)
    service = ChatService(
        settings,
        client=client,
        repository=create_chat_repository(settings),
        audit_logger=ModelInvocationAuditLogger(run_dir / "audit.jsonl"),
    )
    samples: list[dict[str, object]] = []
    try:
        for index in range(max(1, count)):
            started = time.perf_counter()
            first_token_at: float | None = None
            chunks: list[str] = []
            error: str | None = None
            try:
                async for chunk in service.stream_reply(
                    prompt,
                    session_id=f"latency-{started_at.strftime('%Y%m%d%H%M%S')}-{index}",
                    user_id="deepseek-latency-harness",
                ):
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    chunks.append(chunk)
            except Exception as exc:
                error = type(exc).__name__
            finished = time.perf_counter()
            samples.append(
                {
                    "sample": index + 1,
                    "status": "PASS" if chunks and error is None else "FAIL",
                    "ttft_ms": round((first_token_at - started) * 1000, 2)
                    if first_token_at is not None
                    else None,
                    "total_ms": round((finished - started) * 1000, 2),
                    "chunk_count": len(chunks),
                    "response_chars": len("".join(chunks)),
                    "error_type": error,
                }
            )
    finally:
        await client.aclose()

    passed = [sample for sample in samples if sample["status"] == "PASS"]
    data = {
        "status": "PASS" if len(passed) == len(samples) else "FAIL",
        "provider": settings.model_provider,
        "model": settings.model_name,
        "storage_backend": settings.storage_backend,
        "sample_count": len(samples),
        "samples": samples,
    }
    result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report_lines = [
        "# DeepSeek latency harness",
        "",
        f"- Status: {data['status']}",
        f"- Provider: {settings.model_provider}",
        f"- Model: {settings.model_name}",
        f"- Samples: {len(samples)}",
        "",
        "| Sample | TTFT (ms) | Total (ms) | Chunks | Response chars | Status |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for sample in samples:
        report_lines.append(
            f"| {sample['sample']} | {sample['ttft_ms'] or '-'} | {sample['total_ms']} | "
            f"{sample['chunk_count']} | {sample['response_chars']} | {sample['status']} |"
        )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure DeepSeek streaming latency without logging secrets.")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = asyncio.run(
        run_harness(
            count=max(1, args.count),
            prompt=args.prompt,
            output_root=Path(args.output_root),
        )
    )
    print(report)
    result = report.with_name("result.json")
    return 0 if json.loads(result.read_text(encoding="utf-8")).get("status") in {"PASS", "SKIP"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
