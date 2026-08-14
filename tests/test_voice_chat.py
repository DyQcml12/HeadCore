from __future__ import annotations

import struct
import wave
from collections import defaultdict
from pathlib import Path

import pytest

from app.voice_chat.audio_utils import trim_wav_start
from app.voice_chat.planner import VoiceReference
from app.voice_chat.naturalness import constrain_reply_for_realtime_tts
from app.voice_chat.naturalness import normalize_text_for_tts
from app.voice_chat.tts_service import synthesize_voice_reply


def test_realtime_tts_text_keeps_more_than_first_short_sentence() -> None:
    text = "哟，开口就要烧夜宵？昨儿半夜倒听见外面有猫学人笑，探头一看，它嘴里叼着半张符，还冲我翻白眼。"

    constrained = constrain_reply_for_realtime_tts(text, max_chars=42)

    assert constrained.startswith("哟，开口就要烧夜宵？")
    assert "探头一看" in constrained
    assert len(constrained) <= 42


def test_tts_text_removes_performance_cues() -> None:
    text = "（轻笑）这种话我可不会轻易说出口，不过我在。"

    normalized = normalize_text_for_tts(text)

    assert normalized == "这种话我可不会轻易说出口，不过我在。"
    assert "轻笑" not in normalized


def test_tts_text_removes_leading_punctuation_after_cleanup() -> None:
    text = "（轻笑）。！？、，那么，今天就出发吧。"

    normalized = normalize_text_for_tts(text)

    assert normalized == "那么，今天就出发吧。"
    assert normalized[0] not in "。！？、，,.!?"


def test_trim_wav_start_removes_initial_artifact(tmp_path: Path) -> None:
    wav_path = tmp_path / "input.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(1000)
        artifact = [9000] * 120
        body = [1200] * 300
        frames = struct.pack("<" + "h" * len(artifact + body), *(artifact + body))
        wav.writeframes(frames)

    trim_wav_start(wav_path, trim_ms=120, fade_ms=0)

    with wave.open(str(wav_path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
    samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)

    assert len(samples) == 300
    assert samples[0] == 1200


def test_synthesize_voice_reply_uses_gpt_sovits_provider(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_synthesize_gpt_sovits(**kwargs) -> int:
        calls.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"RIFF" + b"x" * 64)
        return 68

    monkeypatch.setattr(
        "app.voice_chat.planner.load_reference_library",
        lambda: defaultdict(lambda: VoiceReference("neutral", "fake-ref", "", "")),
    )
    monkeypatch.setattr("app.voice_chat.tts_service.synthesize_gpt_sovits", fake_synthesize_gpt_sovits)
    monkeypatch.setattr("app.voice_chat.tts_service.convert_audio_for_delivery", lambda **kwargs: kwargs["output_path"].write_bytes(b"mp3"))
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    result = synthesize_voice_reply(
        user_input="用语音说一句", reply_text="欸，我在啦。", output_dir=tmp_path,
        base_url="http://127.0.0.1:9880", provider="gpt_sovits",
        gpt_sovits_ref_audio_path=str(reference), gpt_sovits_prompt_text="呀，是旅行者和派蒙啊。",
    )
    assert calls[0]["base_url"] == "http://127.0.0.1:9880"
    assert calls[0]["top_p"] == 0.85
    assert result.send_path.suffix == ".mp3"
