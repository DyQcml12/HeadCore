from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_ROOT = PROJECT_ROOT / "logs" / "test-runs"
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9]{20,}")


MODULES = {
    "all": ["tests"],
    "api": ["tests/test_app.py"],
}


def redact(text: str) -> str:
    return SECRET_PATTERN.sub("<REDACTED_API_KEY>", text)


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行测试并保存中文 Markdown 报告。")
    parser.add_argument("--module", choices=sorted(MODULES), default="all")
    parser.add_argument("--log-root", default=str(DEFAULT_LOG_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    run_dir = Path(args.log_root).resolve() / timestamp / args.module
    stdout_path = run_dir / "pytest.stdout.log"
    env_path = run_dir / "environment.txt"
    report_path = run_dir / f"{args.module}.test-report.md"

    command = [sys.executable, "-m", "pytest", *MODULES[args.module]]
    result = run_command(command)
    finished_at = dt.datetime.now()
    status = "PASS" if result.returncode == 0 else "FAIL"

    write_text(stdout_path, result.stdout)
    freeze = run_command([sys.executable, "-m", "pip", "freeze"])
    write_text(
        env_path,
        "\n".join(
            [
                f"python={sys.executable}",
                f"platform={platform.platform()}",
                f"environment={os.environ.get('ENVIRONMENT', '')}",
                "pip_freeze:",
                freeze.stdout,
            ]
        ),
    )
    report = "\n".join(
        [
            f"# 测试报告 - {args.module}",
            "",
            f"- 结果: {status}",
            f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
            f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
            f"- 耗时秒数: {(finished_at - started_at).total_seconds():.2f}",
            f"- Python 解释器: {sys.executable}",
            f"- 运行平台: {platform.platform()}",
            f"- 执行命令: `{' '.join(command)}`",
            f"- 原始输出日志: `{stdout_path.relative_to(PROJECT_ROOT)}`",
            f"- 环境依赖快照: `{env_path.relative_to(PROJECT_ROOT)}`",
            "",
            "## 输出末尾",
            "",
            "```text",
            "\n".join(redact(result.stdout).splitlines()[-80:]),
            "```",
            "",
        ]
    )
    write_text(report_path, report)
    print(f"Markdown 测试报告: {report_path}")
    print(f"结果: {status}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
