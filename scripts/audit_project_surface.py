from __future__ import annotations

import ast
import datetime as dt
import subprocess
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (PROJECT_ROOT / "app", PROJECT_ROOT / "scripts")
ENTRYPOINTS = {"app.main", "app.loop_factory"}
TEMP_PATTERNS = ("tmp-",)
RETIRED_MARKERS = ("qq", "weixin", "wechat", "napcat", "onebot", "hermes", "ollama")


def module_name(path: Path) -> str:
    relative = path.relative_to(PROJECT_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def local_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module if node.level == 0 else _resolve_relative(path, node))
    return imports


def _resolve_relative(path: Path, node: ast.ImportFrom) -> str:
    current = module_name(path).split(".")
    if path.stem != "__init__":
        current.pop()
    base = current[: max(0, len(current) - node.level + 1)]
    return ".".join(base + [node.module or ""]).rstrip(".")


def find_unreferenced_app_modules() -> list[str]:
    files = [path for path in SCAN_ROOTS[0].rglob("*.py") if "__pycache__" not in path.parts]
    modules = {module_name(path) for path in files}
    incoming: dict[str, set[str]] = defaultdict(set)
    for path in files:
        source_module = module_name(path)
        for imported in local_imports(path):
            for candidate in modules:
                if imported == candidate or imported.startswith(candidate + "."):
                    incoming[candidate].add(source_module)
    candidates = []
    for module in sorted(modules):
        if module in ENTRYPOINTS or module.endswith(".__init__") or module in incoming:
            continue
        candidates.append(module)
    return candidates


def untracked_artifacts() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    artifacts: list[str] = []
    for line in result.stdout.splitlines():
        relative = line[3:].strip() if len(line) >= 3 else line.strip()
        name = Path(relative).name.lower()
        if name.endswith((".log", ".zip")) or any(name.startswith(pattern) for pattern in TEMP_PATTERNS):
            artifacts.append(relative)
    return artifacts


def retired_named_paths() -> list[str]:
    matches: list[str] = []
    for root in (PROJECT_ROOT / "app", PROJECT_ROOT / "scripts", PROJECT_ROOT / "frontend", PROJECT_ROOT / "miniprogram"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and any(marker in path.name.lower() for marker in RETIRED_MARKERS):
                matches.append(str(path.relative_to(PROJECT_ROOT)))
    return sorted(matches)


def build_report() -> str:
    candidates = find_unreferenced_app_modules()
    artifacts = untracked_artifacts()
    retired = retired_named_paths()
    lines = [
        "# HutaoChatCore 项目表面审计报告",
        "",
        f"> 审计时间：{dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        "> 口径：静态导入图、Git 工作区状态、路径标记；结果必须人工复核，不自动删除。",
        "",
        "## 结论",
        "",
        "- 当前运行入口是 `app.main`；`app/` 内未发现可以直接判定为无用的业务模块。",
        "- `app/storage/mysql_repository.py` 虽含 legacy 命名，但仍是多个存储/认证模块共享的 SQL 传输基类，必须保留。",
        "- QQ/微信 Bot、Ollama、旧 TTS 等已退役功能只应保留在 `docs/archive/` 或历史日志中，不应重新接入当前运行路径。",
        "- 本地模型、音频、贴图和视觉缓存不属于代码交付物；发布 code-only 仓库时应排除。",
        "",
        "## 静态导入候选",
        "",
        "以下模块没有被简单 AST 导入图捕获，**不是删除结论**；需要结合动态导入、FastAPI 路由注册、脚本入口和测试再决定：",
        "",
    ]
    lines.extend(f"- `{item}`" for item in candidates or ["无候选"])
    lines.extend(["", "## 工作区临时产物", ""])
    lines.extend(
        f"- `{item}`：建议在提交/打包前移出工作区或加入忽略清单；不影响运行时。"
        for item in artifacts or ["未发现匹配的未跟踪日志、压缩包或 tmp-* 文件"]
    )
    lines.extend(["", "## 退役标记路径", ""])
    lines.extend(
        f"- `{item}`：当前扫描到路径名标记，需确认是否仅为归档/历史说明。"
        for item in retired or ["当前运行目录未发现退役平台命名文件"]
    )
    lines.extend(
        [
            "",
            "## 处理建议",
            "",
            "1. 不删除抽象基类、迁移脚本、离线评估脚本和条件能力 Provider；它们虽不在默认路径执行，但属于可验证的项目能力。",
            "2. 提交前清理 `tmp-*.log`、临时脚本、导出 zip 和缓存目录；模型权重、训练素材、生成音频继续留在本机资产目录。",
            "3. 成果书只写当前 HTTP/Web Desk/小程序、HeadCore、文本/语音条件能力、视觉 L1/L2 规则汇总；不写退役 Bot、Ollama VLM、未完成公网部署或未验收硬件。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    output = PROJECT_ROOT / "docs" / "PROJECT_SURFACE_AUDIT_2026-08-23.md"
    output.write_text(build_report(), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
