from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

from app.core.config import load_settings
from app.world.runtime import build_world_runtime


@dataclass(frozen=True)
class ControlHealthItem:
    id: str
    label: str
    status: str
    detail: str
    action: str = ""
    url: str = ""


def build_control_status() -> dict[str, object]:
    items = [
        ControlHealthItem(
            id="hutao_core",
            label="HeadCore API",
            status="online",
            detail="核心 API 正在承载控制中心与多客户端契约。",
            action="当前控制中心已运行",
            url="http://127.0.0.1:8000/health",
        ),
        check_world_awareness(),
        check_http(
            "gpt_sovits",
            "GPT-SoVITS",
            "http://127.0.0.1:9880/openapi.json",
            "本地语音表达服务",
        ),
    ]
    return {
        "items": [item.__dict__ for item in items],
        "quick_links": {"desk": "/desk", "health": "/health", "openapi": "/docs"},
        "guides": {
            "clients": {
                "web": "Web Desk /desk",
                "pwa": "PWA 清单和离线缓存由 /desk 发布。",
                "future": "桌面 App、移动 App 与微信小程序复用 HeadCore API 契约。",
            }
        },
    }


def check_http(id: str, label: str, url: str, detail: str) -> ControlHealthItem:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            ok = 200 <= response.status < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        ok = False
    return ControlHealthItem(
        id=id,
        label=label,
        status="online" if ok else "offline",
        detail=detail,
        action="可访问" if ok else "未检测到服务",
        url=url,
    )


def check_world_awareness() -> ControlHealthItem:
    status = build_world_runtime(load_settings()).status()
    if not status.enabled:
        return ControlHealthItem(
            "world_awareness",
            "世界工具运行时",
            "not_configured",
            "响应式世界工具已关闭；刷新控制台不会调用外部世界接口。",
            "按需在本机配置中启用",
        )
    configured = status.amap_key_configured and status.amap_legal_approved
    approved = status.amap_legal_approved
    state = "online" if configured and approved else "degraded"
    detail = (
        f"高德（天气/地点/路线）：{'已配置' if status.amap_key_configured else '未配置'} / "
        f"{'已批准' if status.amap_legal_approved else '未批准'}；"
        f"新闻源已启用 {status.news_enabled_count} 个。"
    )
    return ControlHealthItem(
        "world_awareness",
        "世界工具运行时",
        state,
        detail,
        "状态来自受控 Provider 配置",
    )
