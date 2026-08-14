from __future__ import annotations

from app.perception.memory import evaluate_memory_eligibility


def test_memory_eligibility_matrix() -> None:
    assert evaluate_memory_eligibility(confidence=0.9, quality="good", has_text=True).decision == "allow"
    assert evaluate_memory_eligibility(confidence=0.7, quality="uncertain", has_text=True).decision == "review"
    assert evaluate_memory_eligibility(confidence=0.4, quality="uncertain", has_text=True).decision == "deny"
    assert evaluate_memory_eligibility(confidence=0.9, quality="failed", has_text=False).decision == "deny"
    assert evaluate_memory_eligibility(
        confidence=0.9, quality="uncertain", has_text=True, conflict=True
    ).reasons == ("provider_conflict",)
