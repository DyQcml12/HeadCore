from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.audio.funasr_engine import FunAsrFileEngine
from app.audio.pipeline import NamedFileAsrEngine, transcribe_with_repair_candidates
from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.services.chat_service import ChatService


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "audio-online-random-hutao"
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "asr_online_random"
EMPTY_TEXT = "\u65e0"

ONLINE_AUDIO_POOL = [
    {
        "id": "funasr-public-zh",
        "url": "https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav",
        "language": "zh",
        "source": "FunASR public tutorial sample",
        "license_note": "Public sample audio referenced by FunASR examples.",
        "expected_contains": ["\u6b22\u8fce", "\u4f53\u9a8c"],
    },
    {
        "id": "openspeech-mandarin-0072-8k",
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0072_8k.wav",
        "language": "zh",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable if source is identified as "Open Speech Repository".',
        "expected_contains": [],
    },
    {
        "id": "openspeech-mandarin-0073-8k",
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0073_8k.wav",
        "language": "zh",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable if source is identified as "Open Speech Repository".',
        "expected_contains": [],
    },
    {
        "id": "openspeech-mandarin-0074-8k",
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0074_8k.wav",
        "language": "zh",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable if source is identified as "Open Speech Repository".',
        "expected_contains": [],
    },
    {
        "id": "openspeech-mandarin-0075-8k",
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0075_8k.wav",
        "language": "zh",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable if source is identified as "Open Speech Repository".',
        "expected_contains": [],
    },
]


def pick_samples(count: int, seed: int | None) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    pool = list(ONLINE_AUDIO_POOL)
    rng.shuffle(pool)
    return pool[: min(max(count, 1), len(pool))]


def select_samples(count: int, seed: int | None, sample_id: str | None) -> list[dict[str, Any]]:
    if sample_id:
        matches = [sample for sample in ONLINE_AUDIO_POOL if sample["id"] == sample_id]
        if not matches:
            raise ValueError(f"Unknown online audio sample id: {sample_id}")
        return matches[:1]
    return pick_samples(count, seed)


def download_audio(sample: dict[str, Any], output_dir: Path) -> Path:
    suffix = Path(sample["url"]).suffix or ".wav"
    audio_path = output_dir / f"{sample['id']}{suffix}"
    headers = {
        "User-Agent": "Mozilla/5.0 HutaoChatCore-Audio-Test/1.0",
        "Accept": "*/*",
    }
    with httpx.stream(
        "GET",
        sample["url"],
        headers=headers,
        follow_redirects=True,
        timeout=120.0,
    ) as response:
        response.raise_for_status()
        with audio_path.open("wb") as file:
            for chunk in response.iter_bytes():
                if chunk:
                    file.write(chunk)
    return audio_path


def reply_quality_ok(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    clean = text.strip()
    if not clean:
        reasons.append("\u80e1\u6843\u56de\u590d\u4e3a\u7a7a")
    if len(clean) > 140:
        reasons.append("\u80e1\u6843\u56de\u590d\u8fc7\u957f")
    cjk_count = sum(1 for char in clean if "\u4e00" <= char <= "\u9fff")
    if cjk_count < max(2, len(clean) // 5):
        reasons.append("\u80e1\u6843\u56de\u590d\u4e2d\u6587\u5360\u6bd4\u8fc7\u4f4e")
    return not reasons, reasons


async def run_smoke(
    *,
    sample_count: int = 3,
    seed: int | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    audio_root: Path = DEFAULT_AUDIO_DIR,
    device: str = "cuda:0",
    sample_id: str | None = None,
    repair_preset: str | None = None,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    audio_dir = audio_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audio-online-random-hutao-report.md"
    result_path = output_dir / "audio-online-random-hutao-result.json"
    manifest_path = audio_dir / "manifest.json"

    samples = select_samples(sample_count, seed, sample_id)
    settings = load_settings()
    engine = FunAsrFileEngine.from_preset("sensevoice-small", device=device)
    asr_engines = [
        NamedFileAsrEngine(
            id="sensevoice-small",
            preset="sensevoice-small",
            engine=engine,
        )
    ]
    repair_engines = (
        [
            NamedFileAsrEngine(
                id=repair_preset,
                preset=repair_preset,
                engine=FunAsrFileEngine.from_preset(repair_preset, device=device),
            )
        ]
        if repair_preset
        else []
    )
    chat_service = ChatService(settings)
    results: list[dict[str, Any]] = []

    for index, sample in enumerate(samples, start=1):
        reasons: list[str] = []
        error = None
        audio_path = None
        transcript = ""
        reply_text = ""
        used_live_api = False
        fallback_used = True
        asr_quality_passed = False
        asr_quality_score = 0.0
        asr_quality_reasons: list[str] = []
        asr_selected_candidate_id = ""
        asr_selection_reason = ""
        asr_repair_attempted = False
        asr_candidates: list[dict[str, Any]] = []
        download_latency_ms = 0.0
        asr_latency_ms = 0.0
        chat_latency_ms = 0.0
        try:
            download_started = time.perf_counter()
            audio_path = download_audio(sample, audio_dir)
            download_latency_ms = round((time.perf_counter() - download_started) * 1000, 2)

            asr_started = time.perf_counter()
            asr_response = transcribe_with_repair_candidates(
                audio_path=audio_path,
                primary_engines=asr_engines,
                repair_engines=repair_engines,
            )
            transcript = asr_response.text
            asr_quality_passed = asr_response.quality_passed
            asr_quality_score = asr_response.quality_score
            asr_quality_reasons = asr_response.quality_reasons
            asr_selected_candidate_id = asr_response.selected_candidate_id
            asr_selection_reason = asr_response.selection_reason
            asr_repair_attempted = asr_response.repair_attempted
            asr_candidates = [candidate.model_dump() for candidate in asr_response.candidates]
            asr_latency_ms = round((time.perf_counter() - asr_started) * 1000, 2)
            if not transcript.strip():
                reasons.append("\u8bed\u97f3\u8f6c\u6587\u5b57\u4e3a\u7a7a")
            if not asr_quality_passed:
                reasons.append("\u8bed\u97f3\u8f6c\u6587\u5b57\u8d28\u91cf\u95e8\u672a\u901a\u8fc7")
            for term in sample.get("expected_contains") or []:
                if term not in transcript:
                    reasons.append(f"\u8bed\u97f3\u8f6c\u6587\u5b57\u7f3a\u5c11\u5173\u952e\u8bcd: {term}")

            chat_started = time.perf_counter()
            response = await chat_service.reply(
                transcript,
                session_id=f"online-random-hutao-{timestamp}-{index}",
                user_id="online-random-hutao-user",
                input_source="audio",
                input_quality_passed=asr_quality_passed,
                input_quality_reasons=asr_quality_reasons,
            )
            chat_latency_ms = round((time.perf_counter() - chat_started) * 1000, 2)
            reply_text = response.text
            used_live_api = response.used_live_api
            fallback_used = response.fallback_used
            if not used_live_api:
                reasons.append("\u80e1\u6843\u6ca1\u6709\u4f7f\u7528\u771f\u5b9e API")
            if fallback_used:
                reasons.append("\u80e1\u6843\u89e6\u53d1 fallback")
            ok, quality_reasons = reply_quality_ok(reply_text)
            if not ok:
                reasons.extend(quality_reasons)
        except Exception as exc:
            error = redact_secrets(str(exc))
            reasons.append("\u6d41\u7a0b\u629b\u9519")

        results.append(
            {
                "index": index,
                "id": sample["id"],
                "source": sample["source"],
                "url": sample["url"],
                "license_note": sample["license_note"],
                "audio_path": str(audio_path) if audio_path else "",
                "passed": not reasons,
                "download_latency_ms": download_latency_ms,
                "asr_latency_ms": asr_latency_ms,
                "chat_latency_ms": chat_latency_ms,
                "asr_quality_passed": asr_quality_passed,
                "asr_quality_score": asr_quality_score,
                "asr_quality_reasons": asr_quality_reasons,
                "asr_selected_candidate_id": asr_selected_candidate_id,
                "asr_selection_reason": asr_selection_reason,
                "asr_repair_attempted": asr_repair_attempted,
                "asr_candidates": asr_candidates,
                "transcript_text": transcript,
                "reply_text": reply_text,
                "used_live_api": used_live_api,
                "fallback_used": fallback_used,
                "reasons": reasons,
                "error": error,
            }
        )

    manifest_path.write_text(
        json.dumps(samples, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failed = [item for item in results if not item["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "sample_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "seed": seed,
        "audio_dir": str(audio_dir),
        "manifest_path": str(manifest_path),
        "asr_model": engine.model,
        "asr_repair_preset": repair_preset,
        "device": device,
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
        "# \u7f51\u4e0a\u968f\u673a\u97f3\u9891\u5230\u80e1\u6843\u771f\u5b9e\u6d4b\u8bd5\u62a5\u544a",
        "",
        f"- \u7ed3\u679c: {data['status']}",
        f"- \u5f00\u59cb\u65f6\u95f4: {started_at.isoformat(timespec='seconds')}",
        f"- \u7ed3\u675f\u65f6\u95f4: {finished_at.isoformat(timespec='seconds')}",
        f"- ASR \u6a21\u578b: {data['asr_model']}",
        f"- ASR \u4fee\u590d\u5019\u9009: {data['asr_repair_preset'] or EMPTY_TEXT}",
        f"- \u8bbe\u5907: {data['device']}",
        f"- \u6837\u672c\u6570: {data['sample_count']}",
        f"- \u901a\u8fc7: {data['passed_count']}",
        f"- \u5931\u8d25: {data['failed_count']}",
        f"- \u4e0b\u8f7d\u97f3\u9891\u76ee\u5f55: `{data['audio_dir']}`",
        f"- \u539f\u59cb JSON: `{result_path}`",
        "",
    ]
    for result in data["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        reason_text = "\u65e0" if not result["reasons"] else "\uff1b".join(result["reasons"])
        asr_quality_reason_text = (
            EMPTY_TEXT
            if not result["asr_quality_reasons"]
            else "\uff1b".join(result["asr_quality_reasons"])
        )
        lines.extend(
            [
                f"## {result['index']}. {result['id']} - {status}",
                "",
                f"- \u6765\u6e90: {result['source']}",
                f"- URL: {result['url']}",
                f"- \u97f3\u9891: `{result['audio_path']}`",
                f"- \u4e0b\u8f7d\u8017\u65f6 ms: {result['download_latency_ms']}",
                f"- ASR \u8017\u65f6 ms: {result['asr_latency_ms']}",
                f"- \u80e1\u6843\u8017\u65f6 ms: {result['chat_latency_ms']}",
                f"- ASR \u8d28\u91cf\u901a\u8fc7: {result['asr_quality_passed']}",
                f"- ASR \u8d28\u91cf\u5206: {result['asr_quality_score']}",
                f"- ASR \u8d28\u91cf\u539f\u56e0: {asr_quality_reason_text}",
                f"- ASR \u9009\u4e2d\u5019\u9009: {result['asr_selected_candidate_id'] or EMPTY_TEXT}",
                f"- ASR \u9009\u62e9\u539f\u56e0: {result['asr_selection_reason'] or EMPTY_TEXT}",
                f"- ASR \u4fee\u590d\u5df2\u89e6\u53d1: {result['asr_repair_attempted']}",
                f"- \u8bed\u97f3\u8f6c\u6587\u5b57: {result['transcript_text'] or EMPTY_TEXT}",
                f"- \u80e1\u6843\u56de\u590d: {result['reply_text'] or EMPTY_TEXT}",
                f"- \u4f7f\u7528\u771f\u5b9e API: {result['used_live_api']}",
                f"- fallback: {result['fallback_used']}",
                f"- \u5931\u8d25\u539f\u56e0: {reason_text}",
                f"- \u9519\u8bef: {result['error'] or EMPTY_TEXT}",
                "",
            ]
        )
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "\u4e0b\u8f7d\u7f51\u4e0a\u968f\u673a\u97f3\u9891\uff0c"
            "\u8bed\u97f3\u8f6c\u6587\u5b57\u540e\u4ea4\u7ed9\u80e1\u6843\u56de\u7b54\u3002"
        )
    )
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--audio-root", default=str(DEFAULT_AUDIO_DIR))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--sample-id", default=None)
    parser.add_argument("--repair-preset", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(
        run_smoke(
            sample_count=args.sample_count,
            seed=args.seed,
            output_root=Path(args.output_root),
            audio_root=Path(args.audio_root),
            device=args.device,
            sample_id=args.sample_id,
            repair_preset=args.repair_preset,
        )
    )
    result_path = report_path.parent / "audio-online-random-hutao-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"\u7f51\u4e0a\u968f\u673a\u97f3\u9891\u5230\u80e1\u6843\u771f\u5b9e\u6d4b\u8bd5\u62a5\u544a: {report_path}")
    print(f"\u7ed3\u679c: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
