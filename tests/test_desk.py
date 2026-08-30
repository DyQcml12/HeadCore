import asyncio
from pathlib import Path

import httpx

from app.main import app


def _get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def test_desk_static_routes_publish_the_sandbox() -> None:
    page = _get("/desk")
    script = _get("/desk/app.js")
    style = _get("/desk/style.css")
    worker = _get("/desk/service-worker.js")
    shared_theme = _get("/ui/liquid-theme.css")

    assert page.status_code == 200
    assert 'class="desk-shell"' in page.text
    assert 'class="conversation-stage"' in page.text
    assert 'id="personaSelect"' in page.text
    assert 'id="sandboxStatus"' in page.text
    assert 'id="sessionMode">未加载任何人格' in page.text
    assert 'id="accountAction"' in page.text
    assert 'id="historyTimestamp"' in page.text
    assert 'id="historyMenuButton"' in page.text
    assert 'id="newSessionAction"' in page.text
    assert 'id="newSessionSidebar"' in page.text
    assert 'id="attachmentAction"' in page.text
    assert 'id="voiceModeAction"' in page.text
    assert 'id="contextToggle"' in page.text
    assert 'id="mobileContextAction"' in page.text
    assert 'id="contextBackdrop"' in page.text
    assert 'id="scrollToLatest"' in page.text
    assert '<textarea id="chatInput"' in page.text
    assert "Sandbox Mode" in page.text
    assert "消息不会写入长期记忆" in page.text
    assert "Current Persona" in page.text
    assert 'placeholder="输入测试消息…"' in page.text
    assert 'id="charCount" aria-live="polite">0/4000' in page.text
    assert "Workspace" not in page.text
    assert "Personas" not in page.text
    assert "Models" not in page.text
    assert "保存人格到我的工坊" not in page.text
    assert 'id="roleSheet"' not in page.text
    assert '/ui/liquid-theme.css' in page.text
    assert 'class="layout-statusbar"' not in page.text
    assert 'class="composer liquid-glass glass-card"' in page.text
    assert 'id="voiceControlLink"' in page.text
    assert 'href="/control"' in page.text
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-store"
    assert '"/api/v1/chat/stream"' in script.text
    assert '"/api/v1/audio/chat/prepare/file"' in script.text
    assert "SANDBOX_PERSONA_API" in script.text
    assert "const params = new URLSearchParams(location.search)" in script.text
    assert 'params.get("prompt")' in script.text
    assert 'params.delete("prompt")' in script.text
    assert "location.assign(`/auth?return_to=" in script.text
    assert "function setHistoryMenuOpen" in script.text
    assert "function startNewSession" in script.text
    assert "localStorage.setItem(\"deskSessionId\", state.sessionId)" in script.text
    assert "function setContextCollapsed" in script.text
    assert "function resizeComposerInput" in script.text
    assert "function attachRetryControl" in script.text
    assert "DESK_DRAFT_KEY" in script.text
    assert 'window.addEventListener("offline"' in script.text
    assert "compactContextQuery" in script.text
    assert 'dots.className = "thinking-dots"' in script.text
    assert "/api/control/" not in script.text
    assert style.status_code == 200
    assert ".persona-toolbar" in style.text
    assert ".sandbox-status" in style.text
    assert ".history-menu" in style.text
    assert ".thinking-dots" in style.text
    assert ".context-toggle" in style.text
    assert ".mobile-context-action" in style.text
    assert ".scroll-to-latest" in style.text
    assert ".message-retry-action" in style.text
    assert ".new-session-action" in style.text
    assert ".new-session-sidebar" in style.text
    assert "grid-template-rows: minmax(0, 1fr)" in style.text
    assert "grid-template-rows: auto minmax(0, 1fr)" in style.text
    assert "min-height: 64px" in style.text
    assert "position: fixed" in style.text
    assert "main > section.conversation-stage" in style.text
    assert "content-visibility: visible" in style.text
    assert "oklch(65% 0.25 265)" in style.text
    assert "@media (max-width: 360px)" in style.text
    assert "cursor: url(" not in style.text
    assert shared_theme.status_code == 200
    assert "Instrument Serif" in shared_theme.text
    assert ".liquid-glass" in shared_theme.text
    assert ".sr-only" in shared_theme.text
    assert "--transition-slow: 1000ms" in shared_theme.text
    assert worker.status_code == 200
    assert "desk-shell-v20" in worker.text


def test_desk_keeps_chat_and_audio_flow_with_a_real_local_persona() -> None:
    studio_root = Path(__file__).resolve().parents[1] / "app" / "static" / "web" / "studio"
    page = (studio_root / "index.html").read_text(encoding="utf-8")
    script = (studio_root / "app.js").read_text(encoding="utf-8")
    style = (studio_root / "style.css").read_text(encoding="utf-8")

    assert 'data-composer-mode="text"' in page
    assert 'data-composer-mode="voice"' in page
    assert 'id="holdToTalk"' in page
    assert 'id="voiceReview"' in page
    assert 'id="voiceTranscript"' in page
    assert 'id="personaWarning"' in page
    assert 'id="authFrame"' not in page
    assert 'id="sandboxDetail"' in page
    assert "人格设定会影响表达方式" in script
    assert "function renderPersonaOptions" in script
    assert "function attachReplyVoiceControl" in script
    assert '"/api/v1/chat/history"' in script
    assert "function loadHistory" in script
    assert "function setVoiceReview" in script
    assert "button.dataset.replyVoice" in script
    assert '"/api/v1/audio/chat/file"' not in script
    assert "@media (max-width: 767px)" in style
    assert ".composer-leading" in style
    assert "prefers-reduced-motion" in style
    assert "width: min(calc(100% - 40px), 1040px)" in style
    assert "max-width: 100%" in style
    assert "setupMobileNavigation" not in script
    assert "prefers-reduced-motion" in _get("/ui/liquid-theme.css").text


def test_auth_entry_is_modal_compatible_and_keeps_real_forms() -> None:
    page = _get("/auth")
    script = _get("/auth/app.js")
    style = _get("/auth/style.css")

    assert page.status_code == 200
    assert "auth-shell" in page.text
    assert "account-panel" in page.text
    assert "account-panel liquid-glass glass-card" in page.text
    assert '/ui/liquid-theme.css' in page.text
    assert 'id="authLoading"' in page.text
    assert 'id="localMode"' in page.text
    assert 'id="loginForm"' in page.text
    assert 'id="registerForm"' in page.text
    assert 'id="resetRequestForm"' in page.text
    assert 'id="resetConfirmForm"' in page.text
    assert 'id="themeToggle"' in page.text
    assert '<svg class="theme-toggle-icon"' in page.text
    assert 'class="auth-scope-note"' in page.text
    assert "早期体验者" not in page.text
    assert 'id="rememberEmail"' in page.text
    assert 'id="registerPasswordStrength"' in page.text
    assert 'id="registerPasswordConfirm"' in page.text
    assert script.status_code == 200
    assert "/api/v1/auth/status" in script.text
    assert "isEmbedded" in script.text
    assert "personacore-auth-complete" in script.text
    assert "sessionStorage" in script.text
    assert "localStorage" not in script.text
    assert "function updatePasswordStrength" in script.text
    assert "function resolveSafeReturnTo" in script.text
    assert "function shakeForm" in script.text
    assert style.status_code == 200
    assert "auth-embedded" in style.text
    assert "auth-panel-in" in style.text
    assert "::-ms-reveal" in style.text
    assert "auth-form-shake" in style.text
    assert 'data-theme="light"' in style.text


def test_workshop_uses_local_persona_service_without_claiming_cloud_deployment() -> None:
    page = _get("/me")
    script = _get("/me/app.js")
    style = _get("/me/style.css")

    assert page.status_code == 200
    assert "workshop-shell" in page.text
    assert 'class="layout-statusbar"' in page.text
    assert '/ui/liquid-theme.css' in page.text
    assert 'class="resource-sidebar liquid-glass"' in page.text
    assert 'data-workshop-view="persona"' in page.text
    assert 'data-workshop-view="models"' in page.text
    assert 'data-workshop-view="memory"' in page.text
    assert "本地草稿箱" in page.text
    assert "加载草稿后测试" in page.text
    assert "云端发布" in page.text
    assert 'id="personaForm"' in page.text
    assert 'id="modelFile"' in page.text
    assert 'id="modelDraftCard"' in page.text
    assert 'id="memoryArchive"' in page.text
    assert 'id="authDialog"' in page.text
    assert 'data-workshop-view="configuration"' in page.text
    assert 'data-workshop-view="profile"' in page.text
    assert 'data-workshop-view="security"' in page.text
    assert 'data-workshop-view="billing"' in page.text
    assert 'data-workshop-view="notifications"' in page.text
    assert 'id="agentAvatarInput"' in page.text
    assert 'id="systemPrompt"' in page.text
    assert 'id="temperature"' in page.text
    assert 'id="topP"' in page.text
    assert 'id="maxTokens"' in page.text
    assert 'id="toolWebSearch"' in page.text
    assert "/control" not in page.text
    assert script.status_code == 200
    assert "SANDBOX_PERSONA_API" in script.text
    assert "MODEL_DRAFT_KEY" in script.text
    assert "/api/v1/auth/me" in script.text
    assert "/api/v1/memories" in script.text
    assert "文件没有上传或部署" in script.text
    assert "AGENT_CONFIG_KEY" in script.text
    assert "scheduleAgentConfigSave" in script.text
    assert "setTimeout(saveAgentConfig, 2000)" in script.text
    assert 'new Set(["image/png", "image/jpeg", "image/webp"])' in script.text
    assert "personaSaveBusy" in script.text
    assert "function duplicatePersona" in script.text
    assert "function deletePersona" in script.text
    assert "data-persona-delete" in script.text
    assert "availableViews" in script.text
    assert "if (document.querySelector('[data-view=\"memory\"].active')) await loadMemories();" in script.text
    assert 'saveButton.setAttribute("aria-busy", "true")' in script.text
    assert "if (state.authEnabled && !state.account)" in script.text
    assert "请先登录账户，再保存可在沙盒加载的人格草稿。" in script.text
    assert style.status_code == 200
    assert ".workflow-stack" in style.text
    assert ".repository-panel" in style.text
    assert ".memory-item::before" in style.text
    assert "@media (max-width: 640px)" in style.text
    assert ".resource-sidebar { position: fixed" in style.text
    assert ".agent-config-form" in style.text
    assert ".tool-switches" in style.text
    assert ".sidebar-profile" in style.text


def test_retired_fixed_character_avatar_path_returns_not_found() -> None:
    assert _get("/desk/assets/hutao-avatar.png").status_code == 404


def test_public_auth_status_reports_disabled_services_without_exposing_configuration() -> None:
    response = _get("/api/v1/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "authentication_enabled": False,
        "registration_enabled": False,
        "password_reset_enabled": False,
    }
