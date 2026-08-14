from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "final-acceptance"

RESEARCH_BASIS = [
    {
        "name": "Software regression testing practice",
        "source": "https://martinfowler.com/articles/practical-test-pyramid.html",
        "engineering_use": "final acceptance should combine fast broad automated tests with a smaller set of high-value end-to-end checks.",
    },
    {
        "name": "HELM",
        "source": "https://arxiv.org/abs/2211.09110",
        "engineering_use": "model behavior should be evaluated across multiple scenarios and metrics instead of a single score.",
    },
    {
        "name": "LoCoMo",
        "source": "https://arxiv.org/abs/2402.17753",
        "engineering_use": "long-context conversational systems need explicit memory and continuity checks.",
    },
    {
        "name": "PersoBench",
        "source": "https://arxiv.org/abs/2406.07853",
        "engineering_use": "persona consistency should be part of acceptance testing for character agents.",
    },
]


@dataclass(frozen=True)
class AcceptanceStep:
    id: str
    title: str
    command: list[str]
    required: bool = True
    live: bool = False
    timeout_seconds: int = 900


@dataclass(frozen=True)
class StepResult:
    id: str
    title: str
    command: list[str]
    required: bool
    live: bool
    returncode: int
    passed: bool
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class CommandExecution:
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


CommandRunner = Callable[[list[str], int], CommandExecution]


def build_acceptance_steps(*, include_live: bool) -> list[AcceptanceStep]:
    python = sys.executable
    steps = [
        AcceptanceStep(
            id="runtime_preflight",
            title="Verify Python native runtime imports",
            command=[python, "scripts/python_runtime_preflight.py"],
            timeout_seconds=120,
        ),
        AcceptanceStep(
            id="compileall",
            title="Compile Python project files",
            command=[python, "-m", "compileall", "app", "scripts", "tests", "-q"],
            timeout_seconds=300,
        ),
        AcceptanceStep(
            id="pytest",
            title="Run full pytest suite",
            command=[python, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
            timeout_seconds=900,
        ),
        AcceptanceStep(
            id="persona_continuity_eval",
            title="Run offline persona continuity evaluation",
            command=[python, "scripts/persona_continuity_eval.py"],
            timeout_seconds=300,
        ),
    ]
    if include_live:
        steps.extend(
            [
                AcceptanceStep(
                    id="persona_live_adversarial_smoke",
                    title="Run real-model persona adversarial smoke",
                    command=[python, "scripts/persona_live_adversarial_smoke.py"],
                    live=True,
                    timeout_seconds=900,
                ),
                AcceptanceStep(
                    id="persona_live_continuity_stress",
                    title="Run real-model persona live continuity stress",
                    command=[python, "scripts/persona_live_continuity_stress.py"],
                    live=True,
                    timeout_seconds=1800,
                ),
            ]
        )
    return steps


def run_acceptance(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    include_live: bool = False,
    runner: CommandRunner | None = None,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "final-project-acceptance-result.json"
    report_path = output_dir / "final-project-acceptance-report.md"

    settings = load_settings()
    command_runner = runner or run_command
    step_results = [
        run_step(step, command_runner=command_runner)
        for step in build_acceptance_steps(include_live=include_live)
    ]
    failed_required = [step for step in step_results if step.required and not step.passed]
    data = {
        "status": "PASS" if not failed_required else "FAIL",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
        "include_live": include_live,
        "provider": settings.model_provider,
        "model": settings.model_name,
        "api_key_configured": bool(settings.deepseek_api_key),
        "step_count": len(step_results),
        "passed_count": sum(1 for step in step_results if step.passed),
        "failed_count": sum(1 for step in step_results if not step.passed),
        "research_basis": RESEARCH_BASIS,
        "steps": [asdict(step) for step in step_results],
    }
    result_path.write_text(redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)), encoding="utf-8")
    report_path.write_text(redact_secrets(build_report(data, result_path)), encoding="utf-8")
    return report_path


def run_step(step: AcceptanceStep, *, command_runner: CommandRunner) -> StepResult:
    result = command_runner(step.command, step.timeout_seconds)
    return StepResult(
        id=step.id,
        title=step.title,
        command=step.command,
        required=step.required,
        live=step.live,
        returncode=result.returncode,
        passed=result.returncode == 0,
        duration_seconds=round(result.duration_seconds, 2),
        stdout_tail=tail(redact_secrets(result.stdout)),
        stderr_tail=tail(redact_secrets(result.stderr)),
    )


def run_command(command: list[str], timeout_seconds: int) -> CommandExecution:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return CommandExecution(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.perf_counter() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandExecution(
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nTimed out after {timeout_seconds} seconds.",
            duration_seconds=time.perf_counter() - started,
        )


def tail(text: str, *, max_chars: int = 4000) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[-max_chars:]


def build_report(data: dict[str, object], result_path: Path) -> str:
    lines = [
        "# Final Project Acceptance Report",
        "",
        f"- Result: {data['status']}",
        f"- Started at: {data['started_at']}",
        f"- Finished at: {data['finished_at']}",
        f"- Include live model checks: {data['include_live']}",
        f"- Provider: {data['provider']}",
        f"- Model: {data['model']}",
        f"- API key configured: {data['api_key_configured']}",
        f"- Steps: {data['step_count']}",
        f"- Passed: {data['passed_count']}",
        f"- Failed: {data['failed_count']}",
        f"- Raw JSON: `{result_path}`",
        "",
        "## Research Basis",
        "",
    ]
    for item in data["research_basis"]:
        assert isinstance(item, dict)
        lines.extend(
            [
                f"- {item['name']}: {item['engineering_use']}",
                f"  Source: {item['source']}",
            ]
        )
    lines.extend(["", "## Steps", ""])
    for item in data["steps"]:
        assert isinstance(item, dict)
        lines.extend(
            [
                f"### {item['id']} - {item['title']}",
                "",
                f"- Passed: {item['passed']}",
                f"- Required: {item['required']}",
                f"- Live: {item['live']}",
                f"- Return code: {item['returncode']}",
                f"- Duration seconds: {item['duration_seconds']}",
                f"- Command: `{' '.join(item['command'])}`",
                "",
            ]
        )
        if item["stdout_tail"]:
            lines.extend(["Stdout tail:", "", "```text", str(item["stdout_tail"]), "```", ""])
        if item["stderr_tail"]:
            lines.extend(["Stderr tail:", "", "```text", str(item["stderr_tail"]), "```", ""])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run final HutaoChatCore acceptance checks.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--include-live", action="store_true", help="Run real-model acceptance checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_acceptance(
        output_root=Path(args.output_root),
        include_live=args.include_live,
    )
    data = json.loads(report_path.with_name("final-project-acceptance-result.json").read_text(encoding="utf-8"))
    print(f"Final project acceptance report: {report_path}")
    return 0 if data.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
