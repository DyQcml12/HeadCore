from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.persona.memory_policy import build_memory_policy
from app.persona.memory_service import load_memory_context
from app.persona.scene_classifier import classify_scene
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.storage.repository_factory import create_chat_repository


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "live-memory-smoke"


async def run_live_memory_smoke(output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "live-memory-smoke-report.md"
    result_path = output_dir / "live-memory-smoke-result.json"

    settings = load_settings()
    if not settings.deepseek_api_key:
        data = {
            "status": "SKIP",
            "reason": "缺少 DEEPSEEK_API_KEY，无法运行真实模型测试。",
        }
        write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
        return report_path

    session_id = "live-memory-smoke-" + timestamp
    user_id = "live-memory-smoke-user-" + timestamp
    repository = create_chat_repository(settings)
    service = ChatService(
        settings,
        audit_logger=ModelInvocationAuditLogger(output_dir / "audit.jsonl"),
        repository=repository,
    )

    turns = [
        "我以后改称呼了，叫我阿明。",
        "你还记得怎么叫我吗？",
        "不要记阿明这个称呼，忘掉。",
        "现在随便聊聊，你还会提那个称呼吗？",
    ]
    turn_results: list[dict[str, Any]] = []
    status = "PASS"
    error: str | None = None
    try:
        for user_input in turns:
            response = await service.reply(user_input, session_id=session_id, user_id=user_id)
            classification = classify_scene(user_input)
            memory_context = await load_memory_context(
                repository,
                user_id=user_id,
                policy=build_memory_policy(classification),
            )
            turn_results.append(
                {
                    "user_input": user_input,
                    "scene": classification.scene.value,
                    "response": response.model_dump(),
                    "memory_context_after_turn": memory_context,
                }
            )
        memory_records = await repository.list_memories(user_id=user_id, limit=20)
        memory_rows = [
            {
                "memory_type": record.memory_type,
                "content": record.content,
                "confidence": record.confidence,
            }
            for record in memory_records
        ]
        if len(memory_rows) < 2:
            status = "FAIL"
            error = "记忆闭环至少应写入 user_alias 和 revocation 两条记录。"
        if "阿明" not in turn_results[1]["memory_context_after_turn"]:
            status = "FAIL"
            error = "第二轮后没有读到称呼记忆。"
        if "阿明" in turn_results[-1]["memory_context_after_turn"]:
            status = "FAIL"
            error = "撤销后仍然注入了被撤销的称呼记忆。"
    except Exception as exc:
        status = "FAIL"
        error = redact_secrets(str(exc))
        memory_rows = []

    data = {
        "status": status,
        "provider": settings.model_provider,
        "model": settings.model_name,
        "storage_backend": settings.storage_backend,
        "session_id": session_id,
        "turns": turn_results,
        "memory_rows": memory_rows,
        "error": error,
    }
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
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    lines = [
        "# 真实模型记忆闭环测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- 模型供应商: {data.get('provider')}",
        f"- 模型名称: {data.get('model')}",
        f"- 存储后端: {data.get('storage_backend')}",
        f"- 原始 JSON: `{result_path}`",
        "",
        "## 对话结果",
        "",
    ]
    for index, turn in enumerate(data.get("turns", []), start=1):
        response = turn["response"]
        lines.extend(
            [
                f"### 第 {index} 轮",
                "",
                f"- 用户输入: {turn['user_input']}",
                f"- 识别场景: {turn['scene']}",
                f"- 真实调用模型: {response['used_live_api']}",
                f"- 使用兜底回复: {response['fallback_used']}",
                f"- 模型回复: {response['text']}",
                f"- 本轮后可注入记忆: {turn['memory_context_after_turn'] or '无'}",
                "",
            ]
        )
    lines.extend(["## 记忆表记录", ""])
    memory_rows = data.get("memory_rows", [])
    if memory_rows:
        for row in memory_rows:
            lines.append(f"- {row['memory_type']}: {row['content']} (confidence={row['confidence']})")
    else:
        lines.append("无")
    if data.get("error"):
        lines.extend(["", "## 错误", "", str(data["error"])])
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实 DeepSeek 记忆闭环测试。")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(run_live_memory_smoke(Path(args.output_root)))
    print(f"真实模型记忆闭环测试报告: {report_path}")
    status = "FAIL"
    result_path = report_path.parent / "live-memory-smoke-result.json"
    if result_path.exists():
        status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

