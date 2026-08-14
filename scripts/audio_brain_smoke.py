from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.audio.funasr_engine import FunAsrFileEngine
from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.services.chat_service import ChatService


DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "asr_samples" / "manifest.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "audio-brain-smoke"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"ASR manifest 不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ASR manifest 必须是 list")
    return data


def choose_samples(manifest_path: Path, limit: int) -> list[dict[str, Any]]:
    samples = [
        item
        for item in load_manifest(manifest_path)
        if item.get("language") in {"zh", "yue"} and Path(str(item.get("path", ""))).exists()
    ]
    return samples[:limit]


def reply_quality_ok(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    clean = text.strip()
    if not clean:
        reasons.append("大脑回复为空")
    if len(clean) > 120:
        reasons.append("大脑回复过长")
    cjk_count = sum(1 for char in clean if "\u4e00" <= char <= "\u9fff")
    if cjk_count < max(2, len(clean) // 5):
        reasons.append("大脑回复中文占比过低")
    return not reasons, reasons


async def run_smoke(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    model: str = "iic/SenseVoiceSmall",
    device: str = "cuda:0",
    limit: int = 3,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audio-brain-smoke-report.md"
    result_path = output_dir / "audio-brain-smoke-result.json"

    settings = load_settings()
    engine = FunAsrFileEngine(model=model, device=device)
    chat_service = ChatService(settings)
    samples = choose_samples(manifest_path, limit)
    results: list[dict[str, Any]] = []
    if not samples:
        results.append(
            {
                "id": "no-sample",
                "passed": False,
                "audio_path": "",
                "asr_text": "",
                "asr_latency_ms": 0,
                "reply_text": "",
                "used_live_api": False,
                "fallback_used": True,
                "reasons": ["没有可用中文真实音频样本"],
                "error": None,
            }
        )
    for index, sample in enumerate(samples, start=1):
        audio_path = Path(str(sample["path"]))
        asr_text = ""
        reply_text = ""
        used_live_api = False
        fallback_used = True
        reasons: list[str] = []
        error = None
        asr_started = time.perf_counter()
        try:
            asr_text = engine.transcribe_file(audio_path)
            asr_latency_ms = round((time.perf_counter() - asr_started) * 1000, 2)
            if not asr_text.strip():
                reasons.append("ASR 文本为空")
            response = await chat_service.reply(
                asr_text,
                session_id=f"audio-brain-smoke-{timestamp}-{index}",
                user_id="audio-brain-smoke-user",
            )
            reply_text = response.text
            used_live_api = response.used_live_api
            fallback_used = response.fallback_used
            if not used_live_api:
                reasons.append("大脑没有使用真实 DeepSeek API")
            if fallback_used:
                reasons.append("大脑触发了 fallback")
            quality_ok, quality_reasons = reply_quality_ok(reply_text)
            if not quality_ok:
                reasons.extend(quality_reasons)
        except Exception as exc:
            asr_latency_ms = round((time.perf_counter() - asr_started) * 1000, 2)
            error = redact_secrets(str(exc))
            reasons.append("联动流程抛错")
        results.append(
            {
                "id": sample.get("id", audio_path.stem),
                "passed": not reasons,
                "audio_path": str(audio_path),
                "asr_text": asr_text,
                "asr_latency_ms": asr_latency_ms,
                "reply_text": reply_text,
                "used_live_api": used_live_api,
                "fallback_used": fallback_used,
                "reasons": reasons,
                "error": error,
            }
        )

    failed = [item for item in results if not item["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "asr_provider": "funasr",
        "asr_model": model,
        "asr_device": device,
        "brain_provider": settings.model_provider,
        "brain_model": settings.model_name,
        "sample_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "results": results,
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
    data: dict[str, Any],
    started_at: dt.datetime,
) -> None:
    finished_at = dt.datetime.now()
    lines = [
        "# 听觉到大脑真实联动测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- ASR: {data['asr_provider']} / {data['asr_model']} / {data['asr_device']}",
        f"- 大脑: {data['brain_provider']} / {data['brain_model']}",
        f"- 样本数: {data['sample_count']}",
        f"- 通过: {data['passed_count']}",
        f"- 失败: {data['failed_count']}",
        f"- 原始 JSON: `{result_path}`",
        "",
    ]
    for index, result in enumerate(data["results"], start=1):
        status = "PASS" if result["passed"] else "FAIL"
        reason_text = "无" if not result["reasons"] else "；".join(result["reasons"])
        lines.extend(
            [
                f"## {index}. {result['id']} - {status}",
                "",
                f"- 音频: `{result['audio_path']}`",
                f"- ASR 耗时 ms: {result['asr_latency_ms']}",
                f"- ASR 文本: {result['asr_text'] or '无'}",
                f"- 大脑回复: {result['reply_text'] or '无'}",
                f"- 使用真实 API: {result['used_live_api']}",
                f"- fallback: {result['fallback_used']}",
                f"- 失败原因: {reason_text}",
                f"- 错误: {result['error'] or '无'}",
                "",
            ]
        )
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="真实音频 -> 本地 ASR -> DeepSeek 大脑联动测试。")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--model", default="iic/SenseVoiceSmall")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(
        run_smoke(
            manifest_path=Path(args.manifest),
            output_root=Path(args.output_root),
            model=args.model,
            device=args.device,
            limit=max(args.limit, 1),
        )
    )
    result_path = report_path.parent / "audio-brain-smoke-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"听觉到大脑真实联动测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
