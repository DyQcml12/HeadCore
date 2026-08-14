from __future__ import annotations

from collections.abc import Callable, Sequence

from app.perception.adapters import AdapterResult
from app.perception.adapters import AsrObservationAdapter
from app.perception.contracts import (
    MemoryDecision,
    MemoryEligibility,
    PerceptionInput,
    PerceptionObservation,
    PerceptionQuality,
    ProviderOutput,
    ProviderTrace,
)
from app.perception.memory import evaluate_memory_eligibility
from app.perception.normalization import redact_text
from app.perception.validation import InputPolicy, PerceptionInputError, validate_input


Observer = Callable[[PerceptionInput, bool], AdapterResult]


class PerceptionPipeline:
    def __init__(self, *, input_policy: InputPolicy | None = None) -> None:
        self.input_policy = input_policy or InputPolicy()

    def observe_asr(self, value: PerceptionInput, engines: Sequence[object]) -> PerceptionObservation:
        policy = self.input_policy
        if value.local_path is not None and not policy.allowed_roots:
            policy = InputPolicy(
                allowed_roots=(value.local_path.resolve().parent,),
                remote_timeout_seconds=policy.remote_timeout_seconds,
            )
        pipeline = self if policy is self.input_policy else PerceptionPipeline(input_policy=policy)

        def observer_for(engine: object) -> Observer:
            adapter = AsrObservationAdapter(engine)
            return lambda request, fallback: adapter.observe(request.local_path, fallback=fallback)  # type: ignore[arg-type]

        return pipeline.run(value, tuple(observer_for(engine) for engine in engines))

    def run(self, value: PerceptionInput, observers: Sequence[Observer]) -> PerceptionObservation:
        try:
            validate_input(value, self.input_policy)
        except PerceptionInputError as exc:
            return self._failure(value, (), exc.code)

        traces: list[ProviderTrace] = []
        for index, observer in enumerate(observers):
            result = observer(value, index > 0)
            traces.append(result.trace)
            if result.output is not None:
                return self._success(value, result.output, tuple(traces))
        reason = traces[-1].error_code if traces else "provider_unavailable"
        return self._failure(value, tuple(traces), reason or "provider_unavailable")

    def _success(
        self, value: PerceptionInput, output: ProviderOutput, traces: tuple[ProviderTrace, ...]
    ) -> PerceptionObservation:
        text = redact_text(output.text)
        confidence = output.confidence if output.confidence is not None else (0.8 if text else 0.0)
        reasons = tuple(dict.fromkeys(output.quality_reasons))
        quality = PerceptionQuality.GOOD
        if reasons or confidence < 0.8:
            quality = PerceptionQuality.UNCERTAIN
        memory = evaluate_memory_eligibility(
            confidence=confidence,
            quality=quality,
            has_text=bool(text or output.objects),
            conflict="ocr_vlm_conflict" in reasons,
        )
        return PerceptionObservation(
            modality=value.modality,
            source=value.source,
            text=text,
            objects=output.objects,
            emotion=output.emotion,
            language=output.language,
            confidence=confidence,
            quality=quality,
            quality_reasons=reasons,
            traces=traces,
            memory_eligibility=memory,
        )

    def _failure(
        self, value: PerceptionInput, traces: tuple[ProviderTrace, ...], reason: str
    ) -> PerceptionObservation:
        return PerceptionObservation(
            modality=value.modality,
            source=value.source,
            quality=PerceptionQuality.FAILED,
            quality_reasons=(reason,),
            traces=traces,
            memory_eligibility=MemoryEligibility(
                decision=MemoryDecision.DENY,
                reasons=("no_reliable_observation",),
            ),
        )
