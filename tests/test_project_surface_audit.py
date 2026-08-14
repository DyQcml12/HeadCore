from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

from app.core.config import PROJECT_ROOT


def read_project_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_current_user_facing_surfaces_use_headcore_and_hutao_identity() -> None:
    surfaces = [
        "app/static/control/index.html",
        "README.md",
        "docs/HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md",
    ]

    for relative_path in surfaces:
        text = read_project_text(relative_path)
        assert "HeadCore" in text or "HEADCORE" in text, relative_path
        assert "xiaohe-chatcore" not in text, relative_path


def test_control_surface_does_not_publish_retired_bot_navigation() -> None:
    control = read_project_text("app/static/control/index.html")

    assert "/control/qq" not in control
    assert "/control/weixin" not in control
    assert "/weixin" not in control


def test_retired_qq_and_weixin_bot_runtimes_are_not_importable() -> None:
    for module_name in (
        "integrations",
        "app.channels.adapters.onebot",
        "app.control.hermes_weixin",
    ):
        assert find_spec(module_name) is None
