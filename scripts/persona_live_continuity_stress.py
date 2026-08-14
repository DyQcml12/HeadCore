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

from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.persona.persona_state import PersonaMode, resolve_persona_state
from app.persona.profile_registry import resolve_persona_profile
from app.persona.scene_classifier import classify_scene
from app.schemas import ChatResponse
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.services.response_evaluator import ResponseEvaluator
from app.storage.chat_repository import JsonlChatRepository
from scripts.persona_continuity_eval import RESEARCH_BASIS as CONTINUITY_RESEARCH_BASIS
from scripts.persona_continuity_eval import evaluate_continuity_scenario


DEFAULT_SCENARIO_PATH = PROJECT_ROOT / "data" / "persona_live_continuity_scenarios.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "persona-live-continuity-stress"

RESEARCH_BASIS = [
    *CONTINUITY_RESEARCH_BASIS,
    {
        "name": "PersoBench",
        "source": "https://arxiv.org/abs/2406.07853",
        "engineering_use": "persona consistency should be tested across interaction turns, not only via isolated prompts.",
    },
    {
        "name": "Hello Again",
        "source": "https://arxiv.org/abs/2405.15153",
        "engineering_use": "multi-turn long-context dialogue exposes memory and personalization drift that short tests miss.",
    },
    {
        "name": "Common Ground is Necessary",
        "source": "https://arxiv.org/abs/2406.13654",
        "engineering_use": "agent replies should preserve shared context and avoid social misalignment after context changes.",
    },
]


class ReplyService(Protocol):
    async def reply(
        self,
        user_input: str,
        *,
        session_id: str,
        user_id: str,
        platform: str | None = None,
        platform_user_id: str | None = None,
    ) -> ChatResponse:
        pass


def load_live_continuity_scenarios(path: Path = DEFAULT_SCENARIO_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


async def run_live_continuity_stress(
    *,
    scenario_path: Path = DEFAULT_SCENARIO_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    service: ReplyService | None = None,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "persona-live-continuity-result.json"
    report_path = output_dir / "persona-live-continuity-report.md"

    settings = load_settings()
    scenarios = load_live_continuity_scenarios(scenario_path)
    profile_resolution = resolve_persona_profile(getattr(settings, "persona_profile", "hutao_v1"))
    live_service = service or ChatService(
        settings,
        audit_logger=ModelInvocationAuditLogger(output_dir / "audit.jsonl"),
        repository=JsonlChatRepository(output_dir / "storage"),
    )
    evaluator = ResponseEvaluator()
    scenario_results = []
    for scenario in scenarios:
        scenario_results.append(
            await run_live_scenario(
                service=live_service,
                evaluator=evaluator,
                scenario=scenario,
                timestamp=timestamp,
                persona_profile_id=profile_resolution.profile.id,
            )
        )

    covered_modes = sorted(
        {
            turn["persona_mode"]
            for scenario in scenario_results
            for turn in scenario["turns"]
        }
    )
    required_modes = sorted(mode.value for mode in PersonaMode)
    missing_modes = sorted(set(required_modes) - set(covered_modes))
    suite_reasons = []
    if profile_resolution.profile.id != "hutao_v1":
        suite_reasons.append("unexpected_persona_profile")
    if missing_modes:
        suite_reasons.append("missing_persona_mode_coverage")
    failed = [item for item in scenario_results if not item["passed"]]
    data = {
        "status": "PASS" if not failed and not suite_reasons else "FAIL",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
        "provider": settings.model_provider,
        "model": settings.model_name,
        "api_key_configured": bool(settings.deepseek_api_key),
        "scenario_count": len(scenario_results),
        "passed_count": len(scenario_results) - len(failed),
        "failed_count": len(failed),
        "turn_count": sum(len(item["turns"]) for item in scenario_results),
        "persona_profile_id": profile_resolution.profile.id,
        "persona_profile_version": profile_resolution.profile.version,
        "persona_profile_fallback_reason": profile_resolution.reason,
        "required_persona_modes": required_modes,
        "covered_persona_modes": covered_modes,
        "missing_persona_modes": missing_modes,
        "suite_reasons": suite_reasons,
        "research_basis": RESEARCH_BASIS,
        "scenarios": scenario_results,
    }
    result_path.write_text(redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)), encoding="utf-8")
    report_path.write_text(redact_secrets(build_report(data, result_path)), encoding="utf-8")
    return report_path


async def run_live_scenario(
    *,
    service: ReplyService,
    evaluator: ResponseEvaluator,
    scenario: dict[str, Any],
    timestamp: str,
    persona_profile_id: str = "hutao_v1",
) -> dict[str, Any]:
    transcript_turns = []
    turn_results = []
    scenario_reasons: list[str] = []
    platform = scenario.get("platform")
    platform_user_id = scenario.get("platform_user_id")
    user_id = scenario.get("user_id") or "live-continuity-user-" + scenario["id"]
    session_id = "live-continuity-" + scenario["id"] + "-" + timestamp

    for user_input in scenario["turns"]:
        classification = classify_scene(str(user_input))
        persona_state = resolve_persona_state(classification, str(user_input))
        response = await service.reply(
            str(user_input),
            session_id=session_id,
            user_id=str(user_id),
            platform=str(platform) if platform else None,
            platform_user_id=str(platform_user_id) if platform_user_id else None,
        )
        evaluation = evaluator.evaluate(
            user_input=str(user_input),
            response_text=response.text,
            fallback_used=response.fallback_used,
            persona_profile=persona_profile_id,
        )
        turn_reasons = list(evaluation.reasons)
        if not response.used_live_api:
            turn_reasons.append("not_live_model_reply")
        if response.fallback_used:
            turn_reasons.append("guardrail_repaired_reply")
        scenario_reasons.extend(turn_reasons)
        transcript_turns.append({"user_input": str(user_input), "reply": response.text})
        turn_results.append(
            {
                "user_input": str(user_input),
                "reply": response.text,
                "used_live_api": response.used_live_api,
                "fallback_used": response.fallback_used,
                "provider": response.provider,
                "model": response.model,
                "error": response.error,
                "evaluation_passed": evaluation.passed,
                "evaluation_reasons": evaluation.reasons,
                "turn_reasons": sorted(set(turn_reasons)),
                "length": len(response.text),
                "persona_scene": classification.scene.value,
                "persona_mode": persona_state.mode.value,
            }
        )

    continuity_result = evaluate_continuity_scenario(
        {
            "id": scenario["id"],
            "title": scenario.get("title", ""),
            "focus": scenario.get("focus", ""),
            "turns": transcript_turns,
        }
    )
    scenario_reasons.extend(continuity_result["reasons"])
    return {
        "id": scenario["id"],
        "title": scenario.get("title", ""),
        "focus": scenario.get("focus", ""),
        "passed": not scenario_reasons,
        "reasons": sorted(set(scenario_reasons)),
        "continuity_reasons": continuity_result["reasons"],
        "turns": turn_results,
    }


def build_report(data: dict[str, Any], result_path: Path) -> str:
    lines = [
        "# Persona Live Continuity Stress Report",
        "",
        f"- Result: {data['status']}",
        f"- Started at: {data['started_at']}",
        f"- Finished at: {data['finished_at']}",
        f"- Provider: {data['provider']}",
        f"- Model: {data['model']}",
        f"- API key configured: {data['api_key_configured']}",
        f"- Scenarios: {data['scenario_count']}",
        f"- Turns: {data['turn_count']}",
        f"- Passed: {data['passed_count']}",
        f"- Failed: {data['failed_count']}",
        f"- Persona profile: {data['persona_profile_id']}@{data['persona_profile_version']}",
        f"- Profile fallback reason: {data['persona_profile_fallback_reason'] or 'none'}",
        f"- Covered persona modes: {', '.join(data['covered_persona_modes'])}",
        f"- Missing persona modes: {', '.join(data['missing_persona_modes']) if data['missing_persona_modes'] else 'none'}",
        f"- Suite reasons: {', '.join(data['suite_reasons']) if data['suite_reasons'] else 'none'}",
        f"- Raw JSON: `{result_path}`",
        "",
        "## Research Basis",
        "",
    ]
    for item in data["research_basis"]:
        lines.extend(
            [
                f"- {item['name']}: {item['engineering_use']}",
                f"  Source: {item['source']}",
            ]
        )
    lines.extend(["", "## Scenarios", ""])
    for scenario in data["scenarios"]:
        lines.extend(
            [
                f"### {scenario['id']} - {scenario['title']}",
                "",
                f"- Focus: {scenario['focus']}",
                f"- Passed: {scenario['passed']}",
                f"- Reasons: {', '.join(scenario['reasons']) if scenario['reasons'] else 'none'}",
                f"- Continuity reasons: {', '.join(scenario['continuity_reasons']) if scenario['continuity_reasons'] else 'none'}",
                "",
            ]
        )
        for index, turn in enumerate(scenario["turns"], start=1):
            lines.extend(
                [
                    f"#### Turn {index}",
                    "",
                    f"- User: {turn['user_input']}",
                    f"- Reply: {turn['reply']}",
                    f"- Used live API: {turn['used_live_api']}",
                    f"- Fallback used: {turn['fallback_used']}",
                    f"- Evaluation passed: {turn['evaluation_passed']}",
                    f"- Persona scene: {turn['persona_scene']}",
                    f"- Persona mode: {turn['persona_mode']}",
                    f"- Reasons: {', '.join(turn['turn_reasons']) if turn['turn_reasons'] else 'none'}",
                    "",
                ]
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live multi-turn persona continuity stress with the configured model.")
    parser.add_argument("--scenario-path", default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(
        run_live_continuity_stress(
            scenario_path=Path(args.scenario_path),
            output_root=Path(args.output_root),
        )
    )
    data = json.loads(report_path.with_name("persona-live-continuity-result.json").read_text(encoding="utf-8"))
    print(f"Persona live continuity stress report: {report_path}")
    return 0 if data.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
