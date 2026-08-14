from pathlib import Path

from app.perception.smoke import run_audio_smoke


def test_real_smoke_explicitly_skips_missing_input(tmp_path: Path) -> None:
    result = run_audio_smoke(tmp_path / "missing.wav", preset="sensevoice-small", device="cpu")

    assert result["status"] == "SKIP"
    assert result["reason"] == "audio_file_missing"
