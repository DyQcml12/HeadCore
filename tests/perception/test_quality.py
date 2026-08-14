import pytest

from app.perception.quality import assess_memory


@pytest.mark.parametrize(
    ("quality", "confidence", "has_content", "decision"),
    [
        ("good", 0.9, True, "allow"),
        ("good", 0.4, True, "review"),
        ("degraded", 0.9, True, "review"),
        ("conflicted", 0.9, True, "review"),
        ("failed", 0.9, True, "deny"),
        ("good", 0.9, False, "deny"),
    ],
)
def test_memory_eligibility_matrix(quality, confidence, has_content, decision) -> None:
    result = assess_memory(quality=quality, confidence=confidence, has_content=has_content)

    assert result.decision == decision

