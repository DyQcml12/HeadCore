from __future__ import annotations

import unicodedata


def normalize_transcript(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(char for char in normalized if char.isalnum())


def character_error_rate(reference: str, hypothesis: str) -> float:
    expected = normalize_transcript(reference)
    actual = normalize_transcript(hypothesis)
    if not expected:
        raise ValueError("ASR reference transcript is empty")
    previous = list(range(len(actual) + 1))
    for row_index, expected_char in enumerate(expected, start=1):
        current = [row_index]
        for column_index, actual_char in enumerate(actual, start=1):
            substitution = previous[column_index - 1] + (
                0 if expected_char == actual_char else 1
            )
            current.append(
                min(
                    previous[column_index] + 1,
                    current[column_index - 1] + 1,
                    substitution,
                )
            )
        previous = current
    return previous[-1] / len(expected)
