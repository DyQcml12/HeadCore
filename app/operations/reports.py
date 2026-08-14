from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.operations.contracts import ComponentState, TestReportSummary


_RESULT = re.compile(r"(?P<passed>\d+)\s+passed(?:\s*[,，]\s*(?P<failed>\d+)\s+failed)?", re.IGNORECASE)


def summarize_test_report(path: Path, *, root: Path | None = None) -> TestReportSummary:
    safe_path = _display_path(path, root)
    timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) if path.exists() else datetime.now(timezone.utc)
    if not path.exists():
        return TestReportSummary(
            suite=path.stem,
            passed=0,
            failed=0,
            report_path=safe_path,
            timestamp=timestamp,
            state=ComponentState.MISSING,
            detail="report is missing",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        text = ""
    match = _RESULT.search(text)
    if match is None:
        return TestReportSummary(
            suite=path.stem,
            passed=0,
            failed=0,
            report_path=safe_path,
            timestamp=timestamp,
            state=ComponentState.DEGRADED,
            detail="report is unreadable or has no test result",
        )
    failed = int(match.group("failed") or 0)
    return TestReportSummary(
        suite=path.stem,
        passed=int(match.group("passed")),
        failed=failed,
        report_path=safe_path,
        timestamp=timestamp,
        state=ComponentState.ONLINE if failed == 0 else ComponentState.DEGRADED,
    )


def _display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.name
