from __future__ import annotations

import asyncio
import re

import httpx

from app.main import app


def _get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def _vite_asset_paths(page: str) -> tuple[str, str]:
    script_match = re.search(r'<script type="module"[^>]+src="(?P<path>/site/assets/[^"]+\.js)"', page)
    style_match = re.search(r'<link rel="stylesheet"[^>]+href="(?P<path>/site/assets/[^"]+\.css)"', page)
    assert script_match is not None
    assert style_match is not None
    return script_match.group("path"), style_match.group("path")


def test_public_site_and_credits_have_dedicated_static_entries() -> None:
    home = _get("/")
    credits = _get("/credits")
    credits_style = _get("/credits/style.css")
    credits_script = _get("/credits/app.js")

    assert home.status_code == 200
    assert 'id="root"' in home.text
    assert "site/assets" in home.text
    assert credits.status_code == 200
    assert "credits-shell" in credits.text
    assert "registry-statbar" in credits.text
    assert "license-table" not in credits.text
    assert credits_style.status_code == 200
    assert "registry-card" in credits_style.text
    assert "content-visibility: auto" in credits_style.text
    assert credits_script.status_code == 200
    assert "status-confirmed" in credits_script.text
    assert "status-restricted" in credits_script.text
    assert "status-review" in credits_script.text


def test_public_site_build_preserves_the_hutao_experience_contract() -> None:
    home = _get("/")
    script_path, style_path = _vite_asset_paths(home.text)
    script = _get(script_path)
    style = _get(style_path)

    assert script.status_code == 200
    assert style.status_code == 200
    assert "HutaoChatCore" in script.text
    assert 'href:"/desk"' in script.text
    assert 'href:"/auth"' in script.text
    assert 'href:"/credits"' in script.text
    assert "particle-field" in script.text
    assert "feature-card" in script.text
    assert "feature-icon-halo" in script.text
    assert "closing-scope" in script.text
    assert "本机演示范围" in script.text


def test_public_site_build_keeps_responsive_accessibility_contracts() -> None:
    home = _get("/")
    _, style_path = _vite_asset_paths(home.text)
    style = _get(style_path)
    compact_style = re.sub(r"\s+", "", style.text)

    assert style.status_code == 200
    assert "oklch(" in style.text
    assert "content-visibility:auto" in compact_style
    assert "minmax(0,1.5fr)" in compact_style
    assert ":focus-visible" in style.text
    assert "prefers-reduced-motion" in style.text


def test_public_site_build_preserves_scroll_progress_and_back_to_top_contract() -> None:
    home = _get("/")
    script_path, style_path = _vite_asset_paths(home.text)
    script = _get(script_path)
    style = _get(style_path)

    assert script.status_code == 200
    assert style.status_code == 200
    # 滚动进度条与返回顶部控件：类名契约同时存在于 JS 与 CSS 产物中。
    assert "page-progress" in script.text
    assert "page-progress" in style.text
    assert "back-to-top" in script.text
    assert "back-to-top" in style.text
    # 返回顶部控件必须保留可访问名称。
    assert "返回顶部" in script.text


def test_public_site_build_preserves_cognitive_step_expansion_contract() -> None:
    home = _get("/")
    script_path, style_path = _vite_asset_paths(home.text)
    script = _get(script_path)
    style = _get(style_path)

    assert script.status_code == 200
    assert style.status_code == 200
    # 认知步骤按钮：展开态与详情区域契约（aria-expanded + cognitive-detail）。
    assert "cognitive-step" in script.text
    assert "cognitive-step" in style.text
    assert "aria-expanded" in script.text
    assert "cognitive-detail" in script.text


def test_public_site_build_preserves_aria_controls_wiring() -> None:
    home = _get("/")
    script_path, _ = _vite_asset_paths(home.text)
    script = _get(script_path)

    assert script.status_code == 200
    # 菜单按钮与认知步骤都通过 aria-controls 声明受控区域，产物必须保留该接线。
    assert "aria-controls" in script.text
    assert "mobileNavigation" in script.text
    assert "cognitive-detail" in script.text


def test_public_site_build_preserves_reduced_motion_adaptation_contract() -> None:
    home = _get("/")
    script_path, style_path = _vite_asset_paths(home.text)
    script = _get(script_path)
    style = _get(style_path)
    compact_style = re.sub(r"\s+", "", style.text)

    assert script.status_code == 200
    assert style.status_code == 200
    # 减少动态适配：JS 产物保留 reduced-motion 探测钩子，CSS 产物保留对应媒体查询。
    assert "reducedMotion" in script.text
    assert "prefers-reduced-motion" in script.text
    assert "prefers-reduced-motion:reduce" in compact_style
