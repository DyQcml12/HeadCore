from __future__ import annotations

import json
from pathlib import Path

from app.voice_chat.gpt_sovits_tts import synthesize_gpt_sovits


class _Response:
    def __init__(self, body: bytes, content_type: str = "audio/wav") -> None:
        self._body = body
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_gpt_sovits_posts_audio_request(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"ref")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(b"RIFF" + b"x" * 64)

    monkeypatch.setattr("app.voice_chat.gpt_sovits_tts.urllib.request.urlopen", fake_urlopen)
    output = tmp_path / "reply.wav"
    synthesize_gpt_sovits(base_url="http://127.0.0.1:9880", text="你好", output_path=output,
                          ref_audio_path=str(reference), prompt_text="你好呀")
    assert captured["url"] == "http://127.0.0.1:9880/tts"
    assert captured["payload"]["top_p"] == 0.85
    assert output.read_bytes().startswith(b"RIFF")
