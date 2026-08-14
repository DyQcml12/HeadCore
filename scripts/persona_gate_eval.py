from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, WORKSPACE_ROOT
from app.core.config import load_settings
from app.core.security import redact_secrets
from app.schemas import ChatResponse
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.services.response_evaluator import ResponseEvaluator
from app.storage.chat_repository import JsonlChatRepository


DEFAULT_EVAL_PATH = WORKSPACE_ROOT / "HutaoPersonaLab" / "data" / "eval_sets" / "real_chat_eval_v1.jsonl"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "persona-gate"


class PersonaEvalService(Protocol):
    async def reply(
        self,
        user_input: str,
        *,
        session_id: str,
        user_id: str,
        head_runtime_origin: str,
    ) -> ChatResponse:
        pass


PASSING_REPLIES = {
    "real-chat-001": "累就先别逞强。胡桃在这儿，先喝口水，把今天非做不可的一件小事挑出来。",
    "real-chat-002": "听见了，不走客服那套。胡桃就在这儿陪你说人话，你说一句，我接一句。",
    "real-chat-003": "先别跟它硬撞。把报错第一行给我，胡桃陪你把这团线从头拆开。",
    "real-chat-004": "哎呀，话都说到这份上了。胡桃收下，但油腻话免了，陪你一会儿倒是不难。",
    "real-chat-005": "会听你的更正。旧称呼就让它退场，胡桃记新的规矩，不把错的硬留着。",
    "real-chat-006": "好，少挂招牌，多做正事。胡桃把那些响亮词收一收，留下陪你说话的劲儿。",
    "real-chat-007": "不开玩笑。死亡是告别，也是规矩；人走到那一步时，最要紧的是体面和被好好送一程。",
    "real-chat-008": "怕做不完就先别盯着整座山。胡桃陪你先圈一块最小的地，今天只推进一小步。",
    "real-chat-009": "你可以怀疑。可这会儿跟你说话的是胡桃，不是冷冰冰的说明书。",
    "real-chat-010": "臭豆腐啊，记下这个小偏好。胡桃下次提起吃的，少不了拿它打趣你一句。",
    "real-chat-011": "当然听你的。你说不要记，那就让它退场，胡桃不把你不要的东西强留在册子上。",
    "real-chat-012": "代码可以写，但不能写成冷冰冰的柜台话。把目标给胡桃，我们先拆接口，再拆报错。",
}


def load_eval_cases(path: Path = DEFAULT_EVAL_PATH) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def evaluate_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluator = ResponseEvaluator()
    results: list[dict[str, Any]] = []
    for case in cases:
        reply = PASSING_REPLIES.get(case["id"], "")
        results.append(
            evaluate_single_reply(
                evaluator=evaluator,
                case=case,
                reply=reply,
                mode="controlled",
                provider="local",
                model="controlled-passing-replies",
                error=None,
            )
        )
    return results


async def evaluate_live_cases(
    cases: list[dict[str, Any]],
    *,
    service: PersonaEvalService | None = None,
    run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    settings = load_settings()
    evaluator = ResponseEvaluator()
    if service is None:
        if run_dir is None:
            raise ValueError("run_dir is required when a live evaluation service is not injected")
        service = ChatService(
            settings,
            audit_logger=ModelInvocationAuditLogger(run_dir / "model-audit.jsonl"),
            repository=JsonlChatRepository(run_dir / "chat-storage"),
        )
    results: list[dict[str, Any]] = []
    for case in cases:
        reply = ""
        error: str | None = None
        used_live_api = False
        fallback_used = False
        provider = settings.model_provider
        model = settings.model_name
        try:
            response = await service.reply(
                case["user_input"],
                session_id="persona-gate-live",
                user_id="persona-gate-evaluator",
                head_runtime_origin="persona-gate-eval",
            )
            reply = response.text
            used_live_api = response.used_live_api
            fallback_used = response.fallback_used
            provider = response.provider
            model = response.model
            error = response.error
        except Exception as exc:
            error = str(exc)
        results.append(
            evaluate_single_reply(
                evaluator=evaluator,
                case=case,
                reply=reply,
                mode="live",
                provider=provider,
                model=model,
                error=redact_secrets(error) if error else None,
                used_live_api=used_live_api,
                fallback_used=fallback_used,
            )
        )
    return results


def evaluate_single_reply(
    *,
    evaluator: ResponseEvaluator,
    case: dict[str, Any],
    reply: str,
    mode: str,
    provider: str,
    model: str,
    error: str | None,
    used_live_api: bool = True,
    fallback_used: bool = False,
) -> dict[str, Any]:
    evaluation = evaluator.evaluate(
        user_input=case["user_input"],
        response_text=reply,
        fallback_used=fallback_used,
    )
    reasons = list(evaluation.reasons)
    if mode == "live" and not used_live_api:
        reasons.append("not_live_model_reply")
    if fallback_used:
        reasons.append("fallback_response")
    if error:
        reasons.append("generation_error")
    return {
        "id": case["id"],
        "scene": case["scene"],
        "mode": mode,
        "provider": provider,
        "model": model,
        "user_input": case["user_input"],
        "reply": reply,
        "passed": evaluation.passed and used_live_api and not fallback_used and error is None,
        "score": evaluation.score if error is None else 0.0,
        "reasons": reasons,
        "error": error,
        "used_live_api": used_live_api,
        "fallback_used": fallback_used,
        "expected_behavior": case.get("expected_behavior", []),
        "failure_modes": case.get("failure_modes", []),
    }


def create_output_dir(output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_report(
    results: list[dict[str, Any]],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    output_dir: Path | None = None,
) -> Path:
    output_dir = output_dir or create_output_dir(output_root)
    jsonl_path = output_dir / "persona-gate-results.jsonl"
    report_path = output_dir / "persona-gate-report.md"
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    status = "PASS" if failed == 0 else "FAIL"
    modes = sorted({str(result.get("mode", "unknown")) for result in results})
    providers = sorted({str(result.get("provider", "unknown")) for result in results})
    models = sorted({str(result.get("model", "unknown")) for result in results})

    jsonl_path.write_text(
        "\n".join(redact_secrets(json.dumps(result, ensure_ascii=False)) for result in results) + "\n",
        encoding="utf-8",
    )
    failure_lines = [
        f"- {result['id']}: {', '.join(result['reasons'])}"
        for result in results
        if not result["passed"]
    ]
    report = "\n".join(
        [
            "# 人格门禁评测报告",
            "",
            f"- 结果: {status}",
            f"- 用例总数: {len(results)}",
            f"- 通过数量: {passed}",
            f"- 失败数量: {failed}",
            f"- 生成模式: {', '.join(modes)}",
            f"- 模型供应商: {', '.join(providers)}",
            f"- 模型名称: {', '.join(models)}",
            f"- 逐条结果 JSONL: `{jsonl_path}`",
            "",
            "## 失败项",
            "",
            *(failure_lines or ["无"]),
            "",
        ]
    )
    report_path.write_text(redact_secrets(report), encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行胡桃人格门禁评测集。")
    parser.add_argument("--eval-path", default=str(DEFAULT_EVAL_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--live",
        action="store_true",
        help="调用当前配置的 DeepSeek 模型，评测真实回复。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_eval_cases(Path(args.eval_path))
    output_dir = create_output_dir(Path(args.output_root))
    results = (
        asyncio.run(evaluate_live_cases(cases, run_dir=output_dir))
        if args.live
        else evaluate_cases(cases)
    )
    report_path = write_report(results, output_dir=output_dir)
    failed = sum(1 for result in results if not result["passed"])
    print(f"人格门禁评测报告: {report_path}")
    print("结果: " + ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
