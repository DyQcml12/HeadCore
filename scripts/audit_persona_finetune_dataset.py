from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "fine_tune"
FORBIDDEN_MARKERS = (
    "作为一个AI",
    "AI语言模型",
    "我是AI",
    "亲爱的",
    "宝贝",
    "抱抱",
    "我会一直陪着你",
    "用户您好",
    "客服",
    "本堂主本堂主",
)


def find_latest_dataset(root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"fine-tune output root not found: {root}")
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "train.jsonl").exists() and (path / "validation.jsonl").exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"no exported dataset found under: {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit_dataset(
    dataset_dir: Path,
    *,
    min_training_examples: int = 200,
    min_validation_examples: int = 20,
    max_assistant_chars: int = 70,
) -> dict[str, Any]:
    train_records = read_jsonl(dataset_dir / "train.jsonl")
    validation_records = read_jsonl(dataset_dir / "validation.jsonl")
    records = train_records + validation_records

    assistant_texts = [extract_final_assistant(record) for record in records]
    assistant_texts = [text for text in assistant_texts if text is not None]
    lengths = [len(text) for text in assistant_texts]
    forbidden_hits = find_forbidden_hits(assistant_texts)
    overlong = [
        {"index": index, "length": len(text), "text": text}
        for index, text in enumerate(assistant_texts)
        if len(text) > max_assistant_chars
    ]
    repeated_prefixes = find_repeated_prefixes(assistant_texts)
    structure_errors = validate_record_structure(records)

    reasons: list[str] = []
    if len(train_records) < min_training_examples:
        reasons.append("insufficient_training_examples")
    if len(validation_records) < min_validation_examples:
        reasons.append("insufficient_validation_examples")
    if forbidden_hits:
        reasons.append("forbidden_persona_markers")
    if overlong:
        reasons.append("assistant_replies_too_long")
    if structure_errors:
        reasons.append("invalid_chat_record_structure")
    if repeated_prefixes:
        reasons.append("possible_template_repetition")

    hard_quality_failures = {
        "forbidden_persona_markers",
        "assistant_replies_too_long",
        "invalid_chat_record_structure",
    }
    recommended_to_train = not reasons
    data_quality_status = "PASS"
    if hard_quality_failures.intersection(reasons):
        data_quality_status = "FAIL"
    elif reasons:
        data_quality_status = "NOT_READY"

    return {
        "dataset_dir": str(dataset_dir),
        "train_count": len(train_records),
        "validation_count": len(validation_records),
        "total_count": len(records),
        "assistant_reply_count": len(assistant_texts),
        "assistant_length_avg": round(statistics.mean(lengths), 2) if lengths else 0,
        "assistant_length_max": max(lengths) if lengths else 0,
        "max_assistant_chars": max_assistant_chars,
        "overlong_count": len(overlong),
        "forbidden_hit_count": len(forbidden_hits),
        "repeated_prefixes": repeated_prefixes,
        "structure_error_count": len(structure_errors),
        "reasons": reasons,
        "recommended_to_train": recommended_to_train,
        "data_quality_status": data_quality_status,
        "samples_to_add_before_training": max(0, min_training_examples - len(train_records)),
        "validation_samples_to_add_before_training": max(
            0, min_validation_examples - len(validation_records)
        ),
        "forbidden_hits_preview": forbidden_hits[:10],
        "overlong_preview": overlong[:10],
        "structure_errors_preview": structure_errors[:10],
    }


def extract_final_assistant(record: dict[str, Any]) -> str | None:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if message.get("role") == "assistant":
            content = message.get("content")
            return content.strip() if isinstance(content, str) else None
    return None


def validate_record_structure(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        messages = record.get("messages")
        if not isinstance(messages, list) or len(messages) < 3:
            errors.append({"index": index, "reason": "messages_missing_or_too_short"})
            continue
        if messages[0].get("role") != "system":
            errors.append({"index": index, "reason": "first_message_not_system"})
        if messages[-1].get("role") != "assistant":
            errors.append({"index": index, "reason": "last_message_not_assistant"})
        for message_index, message in enumerate(messages):
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                errors.append({"index": index, "message_index": message_index, "reason": "invalid_role"})
            if not isinstance(content, str) or not content.strip():
                errors.append({"index": index, "message_index": message_index, "reason": "empty_content"})
    return errors


def find_forbidden_hits(texts: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in text.lower():
                hits.append({"index": index, "marker": marker, "text": text})
    return hits


def find_repeated_prefixes(texts: list[str]) -> dict[str, int]:
    prefixes = [normalize_prefix(text) for text in texts if normalize_prefix(text)]
    counter = Counter(prefixes)
    threshold = max(4, round(len(texts) * 0.2))
    return {prefix: count for prefix, count in sorted(counter.items()) if count >= threshold}


def normalize_prefix(text: str) -> str:
    stripped = text.strip()
    if len(stripped) < 4:
        return ""
    return stripped[:4]


def write_audit_report(dataset_dir: Path, result: dict[str, Any]) -> Path:
    report_path = dataset_dir / "dataset-audit-report.md"
    result_path = dataset_dir / "dataset-audit-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_markdown_report(result), encoding="utf-8")
    return report_path


def build_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# 人格微调数据集审计报告",
        "",
        f"- 结果: {result['data_quality_status']}",
        f"- 建议直接训练: {'是' if result['recommended_to_train'] else '否'}",
        f"- 训练样本数: {result['train_count']}",
        f"- 验证样本数: {result['validation_count']}",
        f"- 助手回复平均长度: {result['assistant_length_avg']}",
        f"- 助手回复最长长度: {result['assistant_length_max']}",
        f"- 超长回复数: {result['overlong_count']}",
        f"- 禁用话术命中数: {result['forbidden_hit_count']}",
        f"- 结构错误数: {result['structure_error_count']}",
        "",
        "## 不能直接训练的原因",
        "",
    ]
    if result["reasons"]:
        lines.extend(f"- {reason}" for reason in result["reasons"])
    else:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "继续收集人工认可样本，先把短回复、自然纠错、记忆撤销、长对话节奏做成回归集，再考虑微调。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计胡桃人格微调数据集是否达到开训条件")
    parser.add_argument("--dataset-dir", default="")
    parser.add_argument("--min-training-examples", type=int, default=200)
    parser.add_argument("--min-validation-examples", type=int, default=20)
    parser.add_argument("--max-assistant-chars", type=int, default=70)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_dir = Path(args.dataset_dir) if args.dataset_dir else find_latest_dataset()
    result = audit_dataset(
        dataset_dir,
        min_training_examples=args.min_training_examples,
        min_validation_examples=args.min_validation_examples,
        max_assistant_chars=args.max_assistant_chars,
    )
    report_path = write_audit_report(dataset_dir, result)
    print(f"人格微调数据集审计报告: {report_path}")
    print(f"结果: {result['data_quality_status']}")
    return 0 if result["data_quality_status"] in {"PASS", "NOT_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
