from __future__ import annotations

from pathlib import Path

from app.perception.adapters import AdapterResult
from app.perception.contracts import PerceptionInput, ProviderOutput, ProviderTrace
from app.perception.pipeline import PerceptionPipeline
from app.perception.validation import InputPolicy


def test_provider_failure_uses_fallback_and_preserves_trace(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"not-decoded-by-unit-test")
    value = PerceptionInput(
        modality="image",
        source="test",
        local_path=image,
        declared_mime="image/png",
    )
    fallback_flags: list[bool] = []

    def failed(_: PerceptionInput, fallback: bool) -> AdapterResult:
        fallback_flags.append(fallback)
        return AdapterResult(
            None,
            ProviderTrace(
                provider="missing-vlm",
                model="not-installed",
                success=False,
                fallback=fallback,
                error_code="model_missing",
            ),
        )

    def successful(_: PerceptionInput, fallback: bool) -> AdapterResult:
        fallback_flags.append(fallback)
        return AdapterResult(
            ProviderOutput(text="OCR text", confidence=0.75),
            ProviderTrace(provider="fake-ocr", success=True, fallback=fallback),
        )

    result = PerceptionPipeline(input_policy=InputPolicy(allowed_roots=(tmp_path,))).run(
        value, (failed, successful)
    )

    assert fallback_flags == [False, True]
    assert result.text == "OCR text"
    assert result.quality == "uncertain"
    assert result.memory_eligibility.decision == "review"
    assert [trace.success for trace in result.traces] == [False, True]
    assert result.traces[0].error_code == "model_missing"


def test_all_provider_failures_do_not_fabricate_observation(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    value = PerceptionInput(modality="image", source="test", local_path=image)

    def unavailable(_: PerceptionInput, fallback: bool) -> AdapterResult:
        return AdapterResult(
            None,
            ProviderTrace(
                provider="offline",
                success=False,
                fallback=fallback,
                error_code="provider_unavailable",
            ),
        )

    result = PerceptionPipeline(input_policy=InputPolicy(allowed_roots=(tmp_path,))).run(
        value, (unavailable,)
    )

    assert result.text == ""
    assert result.objects == ()
    assert result.quality == "failed"
    assert result.quality_reasons == ("provider_unavailable",)
    assert result.memory_eligibility.decision == "deny"


def test_input_failure_stops_before_provider(tmp_path: Path) -> None:
    called = False

    def observer(_: PerceptionInput, fallback: bool) -> AdapterResult:
        nonlocal called
        called = True
        raise AssertionError("observer must not be called")

    result = PerceptionPipeline(input_policy=InputPolicy(allowed_roots=(tmp_path,))).run(
        PerceptionInput(
            modality="image",
            source="test",
            local_path=tmp_path / "missing.png",
        ),
        (observer,),
    )

    assert called is False
    assert result.quality == "failed"
    assert result.quality_reasons == ("invalid_input",)


def test_success_redacts_urls_and_secret_assignments(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    def observer(_: PerceptionInput, fallback: bool) -> AdapterResult:
        return AdapterResult(
            ProviderOutput(
                text="see https://example.invalid/private access_token=secret",
                confidence=0.9,
            ),
            ProviderTrace(provider="fake", success=True, fallback=fallback),
        )

    result = PerceptionPipeline(input_policy=InputPolicy(allowed_roots=(tmp_path,))).run(
        PerceptionInput(modality="image", source="test", local_path=image),
        (observer,),
    )

    assert "https://" not in result.text
    assert "secret" not in result.text
    assert result.memory_eligibility.decision == "allow"

