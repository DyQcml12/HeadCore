import asyncio
from pathlib import Path

import httpx

from app import main
from app.schemas import ChatResponse
from app.voice_chat.tts_service import VoiceSynthesisResult
from app.voice_chat.web_tts import WebVoiceReplyStore


async def _request(method: str, path: str, **kwargs: object) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def test_non_stream_chat_registers_its_reply_for_authenticated_voice_playback(monkeypatch) -> None:
    class ReplyRuntime:
        async def handle(self, _event, _context) -> ChatResponse:
            return ChatResponse(text="这句回复可播放。", provider="test", model="test", used_live_api=False)

    store = WebVoiceReplyStore(reply_ttl_seconds=300, min_interval_seconds=0)
    monkeypatch.setattr(main, "public_web_tts_configured", True)
    monkeypatch.setattr(main, "public_web_auth_configured", False)
    monkeypatch.setattr(main, "web_voice_reply_store", store)
    monkeypatch.setattr(main, "build_head_runtime", lambda: ReplyRuntime())

    response = asyncio.run(
        _request(
            "POST",
            "/api/v1/chat",
            json={"user_input": "请留下一句可播放的回复", "user_id": "mini-user", "session_id": "mini-session"},
        )
    )

    assert response.status_code == 200
    reply_id = response.headers["X-Hutao-Reply-Id"]
    stored_reply = asyncio.run(store.acquire(reply_id, user_id="mini-user", session_id="mini-session"))
    assert stored_reply.text == "这句回复可播放。"
    asyncio.run(store.release(reply_id))


def test_web_voice_api_uses_registered_reply_and_removes_temporary_audio(monkeypatch, tmp_path: Path) -> None:
    store = WebVoiceReplyStore(reply_ttl_seconds=300, min_interval_seconds=0)
    reply_id = asyncio.run(store.remember(user_id="desk-user", session_id="desk-session", text="这是服务端登记的回复。"))
    received: dict[str, object] = {}

    def fake_synthesize(**kwargs: object) -> VoiceSynthesisResult:
        received.update(kwargs)
        output_dir = Path(str(kwargs["output_dir"]))
        output_dir.mkdir(parents=True)
        audio_path = output_dir / "reply.mp3"
        audio_path.write_bytes(b"ID3fake-audio")
        return VoiceSynthesisResult(audio_path, audio_path, "neutral", str(kwargs["reply_text"]))

    monkeypatch.setattr(main, "public_web_tts_configured", True)
    monkeypatch.setattr(main, "public_web_auth_configured", False)
    monkeypatch.setattr(main, "web_voice_reply_store", store)
    monkeypatch.setattr(main, "web_voice_tts_output_root", tmp_path / "web-voice")
    monkeypatch.setattr(main, "synthesize_voice_reply", fake_synthesize)

    response = asyncio.run(
        _request(
            "POST",
            "/api/v1/voice/synthesize",
            json={
                "reply_id": reply_id,
                "user_id": "desk-user",
                "session_id": "desk-session",
                "text": "这段客户端文字绝不能参与合成。",
            },
        )
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"ID3fake-audio"
    assert received["reply_text"] == "这是服务端登记的回复。"
    assert not (tmp_path / "web-voice").exists()


def test_web_voice_api_does_not_disclose_another_session_reply(monkeypatch) -> None:
    store = WebVoiceReplyStore(reply_ttl_seconds=300, min_interval_seconds=0)
    reply_id = asyncio.run(store.remember(user_id="desk-user", session_id="desk-session", text="私有回复。"))

    monkeypatch.setattr(main, "public_web_tts_configured", True)
    monkeypatch.setattr(main, "public_web_auth_configured", False)
    monkeypatch.setattr(main, "web_voice_reply_store", store)

    response = asyncio.run(
        _request(
            "POST",
            "/api/v1/voice/synthesize",
            json={"reply_id": reply_id, "user_id": "desk-user", "session_id": "other-session"},
        )
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "voice reply not found"}
