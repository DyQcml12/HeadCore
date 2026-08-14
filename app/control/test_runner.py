from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT


RUNTIME_PYTHON = Path(r"D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe")
TEST_LOG_DIR = PROJECT_ROOT / "logs" / "control-center" / "test-runs"


@dataclass(frozen=True)
class ControlTestSpec:
    id: str
    label: str
    command: tuple[str, ...]
    timeout_seconds: int = 120


TEST_SPECS: dict[str, ControlTestSpec] = {
    "control_center": ControlTestSpec(
        id="control_center",
        label="控制中心接口测试",
        command=(str(RUNTIME_PYTHON), "-m", "pytest", "tests/test_control_center.py", "-q"),
        timeout_seconds=90,
    ),
    "api_voice": ControlTestSpec(
        id="api_voice",
        label="API + 语音 focused 测试",
        command=(
            str(RUNTIME_PYTHON),
            "-m",
            "pytest",
            "tests/test_control_center.py",
            "tests/test_api.py",
            "tests/test_voice_chat.py",
            "-q",
        ),
        timeout_seconds=180,
    ),
    "full_pytest": ControlTestSpec(
        id="full_pytest",
        label="全项目 pytest",
        command=(str(RUNTIME_PYTHON), "-m", "pytest", "tests", "-q"),
        timeout_seconds=240,
    ),
}


def list_control_tests() -> list[dict[str, object]]:
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "command": " ".join(spec.command),
            "timeout_seconds": spec.timeout_seconds,
        }
        for spec in TEST_SPECS.values()
    ]


def run_control_test(test_id: str) -> dict[str, object]:
    if test_id not in TEST_SPECS:
        raise ValueError(f"Unsupported control test: {test_id}")
    spec = TEST_SPECS[test_id]
    started = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    result = subprocess.run(
        list(spec.command),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=spec.timeout_seconds,
        check=False,
    )
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    report_path = write_test_report(
        test_id=test_id,
        label=spec.label,
        command=" ".join(spec.command),
        returncode=result.returncode,
        output=output,
        started=started,
    )
    return {
        "id": test_id,
        "label": spec.label,
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "report_path": str(report_path),
        "output_tail": "\n".join(output.splitlines()[-80:]),
    }


def write_test_report(
    *,
    test_id: str,
    label: str,
    command: str,
    returncode: int,
    output: str,
    started: str,
) -> Path:
    report_dir = TEST_LOG_DIR / started
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{test_id}.md"
    report_path.write_text(
        "\n".join(
            [
                f"# {label}",
                "",
                f"Time: {started}",
                f"Command: `{command}`",
                f"Return code: `{returncode}`",
                "",
                "```text",
                output[-12000:],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report_path
