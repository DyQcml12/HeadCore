from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.desktop.config_store import (
    CONFIG_PATH,
    LOCAL_APP_ROOT,
    load_config,
    merge_config,
    public_config,
    save_config,
    secret_for,
)
from app.core.config import PROJECT_ROOT, Settings


STATIC_ROOT = Path(__file__).resolve().parents[1] / "static" / "desktop"


class DesktopConfigRequest(BaseModel):
    text: dict[str, Any] = Field(default_factory=dict)
    vision: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    persona: dict[str, Any] = Field(default_factory=dict)
    computer_control: dict[str, Any] = Field(default_factory=dict)


class VisionRouteRequest(BaseModel):
    has_image: bool = False


def create_desktop_router(settings: Settings) -> APIRouter:
    router = APIRouter(tags=["desktop-app"])

    @router.get("/app", include_in_schema=False)
    async def desktop_page() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @router.get("/app/app.js", include_in_schema=False)
    async def desktop_script() -> FileResponse:
        return FileResponse(STATIC_ROOT / "app.js", media_type="application/javascript")

    @router.get("/app/style.css", include_in_schema=False)
    async def desktop_style() -> FileResponse:
        return FileResponse(STATIC_ROOT / "style.css", media_type="text/css")

    @router.get("/api/v1/desktop/config")
    async def get_desktop_config() -> dict[str, Any]:
        config = load_config()
        visible_config = public_config(config)
        text = visible_config.get("text", {})
        if isinstance(text, dict) and settings.deepseek_api_key:
            text["api_key_configured"] = True
        return {
            "config": visible_config,
            "paths": {
                "data_root": str(LOCAL_APP_ROOT),
                "config_file": str(CONFIG_PATH),
            },
            "requires_restart": True,
        }

    @router.put("/api/v1/desktop/config")
    async def put_desktop_config(request: DesktopConfigRequest) -> dict[str, Any]:
        config = save_config(request.model_dump(exclude_unset=True))
        return {
            "config": public_config(config),
            "saved": True,
            "requires_restart": True,
            "message": "配置已保存。文本模型配置将在重启本地服务后生效。",
        }

    @router.post("/api/v1/desktop/config/test")
    async def test_desktop_config(request: DesktopConfigRequest) -> dict[str, Any]:
        incoming = request.model_dump(exclude_unset=True)
        candidate_api_key = str(incoming.get("text", {}).get("api_key") or "").strip()
        merged = merge_config(incoming, persist_secrets=False)
        text = merged.get("text", {})
        if not isinstance(text, dict):
            raise HTTPException(status_code=400, detail="文本模型配置无效")
        base_url = str(text.get("base_url") or "").strip().rstrip("/")
        api_key = candidate_api_key or secret_for(merged, "text", settings.deepseek_api_key)
        if not base_url:
            raise HTTPException(status_code=400, detail="请填写文本模型 Base URL")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="模型服务连接失败，请检查地址、密钥和网络") from exc
        return {
            "ok": True,
            "status_code": response.status_code,
            "provider": text.get("provider", "openai-compatible"),
            "model": text.get("model", ""),
        }

    @router.get("/api/v1/desktop/status")
    async def desktop_status() -> dict[str, Any]:
        config = load_config()
        text = config.get("text", {})
        vision = config.get("vision", {})
        return {
            "platform": sys.platform,
            "supported_windows": sys.platform == "win32",
            "service": "ready",
            "current_model": settings.model_name,
            "current_provider": settings.model_provider,
            "text_api_configured": bool(settings.deepseek_api_key or secret_for(config, "text")),
            "vision_configured": bool(isinstance(vision, dict) and vision.get("model") and vision.get("base_url")),
            "memory_backend": config.get("memory", {}).get("backend", "qdrant"),
            "config_file": str(CONFIG_PATH),
            "requires_restart": True,
            "text_capability": text.get("capability", "text-only") if isinstance(text, dict) else "text-only",
        }

    @router.post("/api/v1/desktop/vision/route")
    async def vision_route(request: VisionRouteRequest) -> dict[str, Any]:
        config = load_config()
        text = config.get("text", {})
        vision = config.get("vision", {})
        multimodal = isinstance(text, dict) and text.get("capability") == "multimodal"
        if not request.has_image:
            return {"route": "text-only", "label": "纯文本请求不调用视觉模型"}
        if multimodal:
            return {"route": "text-model-multimodal", "label": "当前文本模型支持多模态，直接处理图片"}
        if isinstance(vision, dict) and vision.get("enabled") and vision.get("model"):
            return {"route": "separate-vision-model", "label": "当前文本模型无视觉能力，转交视觉模型"}
        return {"route": "unavailable", "label": "未配置可用的视觉模型"}

    @router.post("/api/v1/desktop/vision/describe")
    async def describe_image(
        image: UploadFile = File(...),
        prompt: str = Form(default="请描述这张图片中的主要内容。"),
    ) -> dict[str, Any]:
        config = load_config()
        text = config.get("text", {})
        vision = config.get("vision", {})
        text_is_multimodal = isinstance(text, dict) and text.get("capability") == "multimodal"
        if text_is_multimodal:
            selected_section = text
            selected_key = secret_for(config, "text", settings.deepseek_api_key)
            route = "text-model-multimodal"
        elif isinstance(vision, dict) and vision.get("enabled"):
            selected_section = vision
            selected_key = secret_for(config, "vision")
            route = "separate-vision-model"
        else:
            raise HTTPException(status_code=409, detail="视觉模型未启用")
        if image.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise HTTPException(status_code=415, detail="只支持 JPG、PNG、WebP 或 GIF 图片")
        content = await image.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="图片不能超过 8 MB")
        try:
            text = await _call_compatible_model(
                section=selected_section,
                api_key=selected_key,
                prompt=prompt,
                image_bytes=content,
                mime_type=image.content_type,
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="视觉模型调用失败，请检查视觉模型服务") from exc
        return {"route": route, "description": text}

    @router.post("/api/v1/desktop/uninstall")
    async def launch_uninstaller() -> dict[str, Any]:
        install_root = Path(os.environ.get("HUTAO_INSTALL_ROOT") or str(PROJECT_ROOT)).resolve()
        for candidate in (install_root / "unins000.exe", install_root / "uninstall.exe"):
            if candidate.is_file():
                if sys.platform == "win32":
                    subprocess.Popen([str(candidate)], cwd=str(install_root))
                return {"launched": True, "path": str(candidate)}
        return {
            "launched": False,
            "message": "未找到卸载程序，请通过 Windows“设置 → 应用”卸载 HuTao Assistant。",
        }

    @router.get("/api/v1/desktop/voice/status")
    async def desktop_voice_status() -> dict[str, Any]:
        base_url = (settings.public_web_tts_base_url or "http://127.0.0.1:9880").rstrip("/")
        reachable = False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.get(f"{base_url}/")
                reachable = True
        except httpx.HTTPError:
            reachable = False
        return {
            "tts_enabled": settings.public_web_tts_enabled,
            "provider": settings.public_web_tts_provider,
            "base_url": base_url,
            "voice_profile": settings.hutao_voice_profile,
            "reachable": reachable,
        }

    return router


async def _call_compatible_model(
    *,
    section: dict[str, Any],
    api_key: str,
    prompt: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    base_url = str(section.get("base_url") or "").strip().rstrip("/")
    model = str(section.get("model") or "").strip()
    if not base_url or not model:
        raise ValueError("vision base_url and model are required")
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt.strip() or "请描述这张图片。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "temperature": 0.2,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("vision model returned an invalid response") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("vision model returned empty content")
    return content.strip()
