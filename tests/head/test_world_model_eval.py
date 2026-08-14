from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from scripts.evaluate_world_model import EVAL_DISCLAIMER, evaluate_cases


def test_world_model_evaluation_dataset_passes_all_cases():
    path = Path(__file__).resolve().parents[2] / "data" / "world_model_evaluation_cases.json"
    document = json.loads(path.read_text(encoding="utf-8"))

    result = evaluate_cases(document, now=dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC))

    assert result["status"] == "PASS", result
    assert result["failed"] == 0
    assert result["margin"] == 1.0
    assert "不构成对 AGI" in result["disclaimer"]


def test_evaluation_disclaimer_denies_agi_or_consciousness_claims():
    assert "AGI" in EVAL_DISCLAIMER
    assert "意识" in EVAL_DISCLAIMER
