from pathlib import Path

from app.perception.contracts import PerceptionInput, PerceptionObservation


def test_contract_defaults_fail_closed() -> None:
    value = PerceptionInput(modality="audio", source="qq", local_path=Path("sample.wav"))
    observation = PerceptionObservation(
        modality="audio",
        quality="failed",
        memory_eligibility={"decision": "deny", "reasons": ["no_observation"]},
    )

    assert value.source == "qq"
    assert observation.quality == "failed"
    assert observation.memory_eligibility.decision == "deny"
