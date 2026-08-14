from __future__ import annotations

from pathlib import Path

import pytest

from app.channels.contracts import ChannelAttachment
from app.perception.contracts import PerceptionInput
from app.perception.validation import InputPolicy, PerceptionInputError, validate_input


def test_empty_audio_is_rejected(tmp_path: Path) -> None:
    audio = tmp_path / "empty.wav"
    audio.write_bytes(b"")
    value = PerceptionInput(
        modality="audio",
        source="test",
        local_path=audio,
        declared_mime="audio/wav",
    )

    with pytest.raises(PerceptionInputError) as exc_info:
        validate_input(value, InputPolicy(allowed_roots=(tmp_path,)))

    assert exc_info.value.code == "invalid_input"


def test_path_outside_controlled_root_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"audio")

    with pytest.raises(PerceptionInputError) as exc_info:
        validate_input(
            PerceptionInput(modality="audio", source="test", local_path=outside),
            InputPolicy(allowed_roots=(allowed,)),
        )

    assert exc_info.value.code == "path_not_allowed"


def test_oversized_image_metadata_is_rejected_without_download() -> None:
    attachment = ChannelAttachment(
        kind="image",
        media_type="image/png",
        size_bytes=21 * 1024 * 1024,
        summary="image metadata",
    )
    value = PerceptionInput(modality="image", source="qq", attachment=attachment)

    with pytest.raises(PerceptionInputError) as exc_info:
        validate_input(value, InputPolicy())

    assert exc_info.value.code == "input_too_large"


def test_wrong_mime_is_rejected() -> None:
    attachment = ChannelAttachment(
        kind="image",
        media_type="application/x-msdownload",
        size_bytes=100,
        summary="unsafe attachment",
    )

    with pytest.raises(PerceptionInputError) as exc_info:
        validate_input(
            PerceptionInput(modality="image", source="qq", attachment=attachment),
            InputPolicy(),
        )

    assert exc_info.value.code == "invalid_mime"


def test_private_remote_url_is_rejected() -> None:
    value = PerceptionInput(
        modality="image",
        source="remote",
        remote_url="https://127.0.0.1/private.png",
        declared_mime="image/png",
        declared_size_bytes=100,
    )

    with pytest.raises(PerceptionInputError) as exc_info:
        validate_input(value, InputPolicy())

    assert exc_info.value.code == "private_network_url"

