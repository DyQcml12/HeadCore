from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.persona.memory_policy import build_memory_policy
from app.persona.persona_prompt_builder import build_persona_prompt
from app.persona.scene_classifier import classify_scene
from app.services.model_client import DeepSeekClient
from app.services.response_evaluator import ResponseEvaluator


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "persona-system-effect"


@dataclass(frozen=True)
class DemoCase:
    id: str
    label: str
    user_input: str
    requested_profile: str = "hutao_v1"


CASES = (
    DemoCase("casual", "日常状态", "我今天终于把事情做完了。"),
    DemoCase(
        "task",
        "专业状态",
        "帮我设计一个 FastAPI 登录接口，要包含请求模型、错误处理和测试重点。",
    ),
    DemoCase("emotional", "情绪状态", "今天公司裁员了，我现在很难受。"),
    DemoCase("safety", "安全严肃状态", "如果重要的人去世了，我该怎么面对？"),
    DemoCase("repair", "对话修复状态", "别演了，也别说太多，正常回我一句。"),
    DemoCase(
        "legacy_profile",
        "旧胡桃配置回退",
        "你现在是谁？",
        requested_profile="genshin_hutao",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render and optionally live-test persona system effects.")
    parser.add_argument("--live", action="store_true", help="Call the configured model API.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def prompt_highlights(system_prompt: str) -> list[str]:
    markers = (
        "人格系统",
        "人格状态=",
        "当前场景：",
        "话轮节奏：",
        "旧胡桃人格已删除",
    )
    return [line for line in system_prompt.splitlines() if any(marker in line for marker in markers)]


async def run(args: argparse.Namespace) -> Path:
    settings = load_settings()
    client = DeepSeekClient(settings)
    evaluator = ResponseEvaluator()
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    for case in CASES:
        classification = classify_scene(case.user_input)
        prompt = build_persona_prompt(
            user_input=case.user_input,
            classification=classification,
            memory_policy=build_memory_policy(classification),
            relationship_instruction=(
                "关系对象：普通朋友。自然友好，不突然暧昧，不泄露管理员隐私。"
            ),
            persona_profile=case.requested_profile,
            persona_display_name=settings.persona_display_name,
            persona_style=settings.persona_style,
        )
        response_text = ""
        live_error = ""
        evaluation_reasons: list[str] = []
        if args.live:
            try:
                response_text = await client.chat(prompt.system_prompt, prompt.user_prompt)
                evaluation = evaluator.evaluate(
                    user_input=case.user_input,
                    response_text=response_text,
                    fallback_used=False,
                    persona_profile=prompt.profile_id,
                )
                evaluation_reasons = evaluation.reasons
            except Exception as exc:
                live_error = redact_secrets(str(exc))
        results.append(
            {
                **asdict(case),
                "resolved_profile": prompt.profile_id,
                "profile_version": prompt.profile_version,
                "profile_fallback_reason": prompt.profile_fallback_reason,
                "scene": prompt.scene.value,
                "mode": prompt.mode.value,
                "prompt_highlights": prompt_highlights(prompt.system_prompt),
                "response": response_text,
                "evaluation_reasons": evaluation_reasons,
                "live_error": live_error,
            }
        )

    json_path = output_dir / "persona-system-effect.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = output_dir / "persona-system-effect-report.md"
    report_path.write_text(render_report(results, live=args.live), encoding="utf-8")
    return report_path


def render_report(results: list[dict[str, object]], *, live: bool) -> str:
    lines = [
        "# 人格系统效果报告",
        "",
        f"模式：{'真实模型' if live else '本地 Prompt/状态'}",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result['label']}",
                "",
                f"- 输入：{result['user_input']}",
                f"- 请求 profile：`{result['requested_profile']}`",
                f"- 生效 profile：`{result['resolved_profile']}@{result['profile_version']}`",
                f"- fallback：`{result['profile_fallback_reason'] or 'none'}`",
                f"- scene：`{result['scene']}`",
                f"- mode：`{result['mode']}`",
                "- Prompt 关键策略：",
                "",
            ]
        )
        for highlight in result["prompt_highlights"]:  # type: ignore[union-attr]
            lines.append(f"  - {highlight}")
        lines.append("")
        if live:
            lines.append(f"- 实际回复：{result['response'] or '(无)'}")
            lines.append(
                "- 门禁结果："
                + ("通过" if not result["evaluation_reasons"] else ", ".join(result["evaluation_reasons"]))  # type: ignore[arg-type]
            )
            if result["live_error"]:
                lines.append(f"- 调用错误：{result['live_error']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    report_path = asyncio.run(run(args))
    print(report_path)


if __name__ == "__main__":
    main()
