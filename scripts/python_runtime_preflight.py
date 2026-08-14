from __future__ import annotations

import importlib
import json
import platform
import sys
from pathlib import Path


REQUIRED_MODULES = ("pydantic_core", "pydantic", "fastapi", "pytest")


def classify_import_error(exc: BaseException) -> str:
    text = str(exc).lower()
    if "应用程序控制策略" in str(exc) or "code integrity" in text:
        return "code_integrity_blocked"
    if isinstance(exc, ModuleNotFoundError):
        return "module_missing"
    if "dll load failed" in text:
        return "native_extension_load_failed"
    return "import_failed"


def run_preflight() -> tuple[bool, dict[str, object]]:
    modules: dict[str, dict[str, str]] = {}
    ready = True
    for name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(name)
            modules[name] = {
                "status": "ready",
                "version": str(getattr(module, "__version__", "")),
            }
        except Exception as exc:
            ready = False
            modules[name] = {
                "status": classify_import_error(exc),
                "error_type": type(exc).__name__,
            }
            break
    return ready, {
        "ready": ready,
        "python": platform.python_version(),
        "executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "modules": modules,
    }


def main() -> int:
    ready, report = run_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
