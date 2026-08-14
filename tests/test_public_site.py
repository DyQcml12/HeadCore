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
    assert "metric" in script.text
    assert "500" in script.text


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
