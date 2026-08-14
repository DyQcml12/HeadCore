from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT


DEFAULT_SOURCE = PROJECT_ROOT / "data" / "persona_training_seed.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "fine_tune"
SYSTEM_MESSAGE = (
    "你为《原神》角色胡桃生成中文短回复。保持机灵、轻巧、有分寸；"
    "不要客服化、不要恋爱脑、不要话痨；按用户语气纠正及时调整。"
)


def load_seed_examples(path: Path = DEFAULT_SOURCE) -> list[dict[str, Any]]:
    examples = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(examples, list):
        raise ValueError("training seed file must contain a list")
    for example in examples:
        validate_seed_example(example)
    return examples


def validate_seed_example(example: dict[str, Any]) -> None:
    for field in ["id", "scene", "messages"]:
        if field not in example:
            raise ValueError(f"missing field {field}")
    messages = example["messages"]
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError(f"{example['id']} must contain at least user and assistant messages")
    if messages[-1].get("role") != "assistant":
        raise ValueError(f"{example['id']} must end with assistant message")
    for message in messages:
        if message.get("role") not in {"user", "assistant"}:
            raise ValueError(f"{example['id']} has invalid role")
        if not str(message.get("content", "")).strip():
            raise ValueError(f"{example['id']} has empty content")


def to_finetune_record(example: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE},
            *[
                {"role": message["role"], "content": message["content"]}
                for message in example["messages"]
            ],
        ]
    }


def export_dataset(
    *,
    source_path: Path = DEFAULT_SOURCE,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    validation_ratio: float = 0.2,
) -> Path:
    examples = load_seed_examples(source_path)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_count = max(1, round(len(examples) * validation_ratio)) if len(examples) >= 5 else 0
    validation_ids = {
        example["id"]
        for index, example in enumerate(examples)
        if validation_count and index % max(1, len(examples) // validation_count) == 0
    }
    validation_ids = set(list(validation_ids)[:validation_count])

    train_examples = [example for example in examples if example["id"] not in validation_ids]
    validation_examples = [example for example in examples if example["id"] in validation_ids]
    write_jsonl(output_dir / "train.jsonl", [to_finetune_record(example) for example in train_examples])
    write_jsonl(
        output_dir / "validation.jsonl",
        [to_finetune_record(example) for example in validation_examples],
    )
    manifest = {
        "source": str(source_path),
        "train_count": len(train_examples),
        "validation_count": len(validation_examples),
        "system_message": SYSTEM_MESSAGE,
        "train_file": str(output_dir / "train.jsonl"),
        "validation_file": str(output_dir / "validation.jsonl"),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(output_dir / "dataset-report.md", manifest)
    return output_dir


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def write_report(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        "\n".join(
            [
                "# 人格微调数据集导出报告",
                "",
                f"- 训练样本数: {manifest['train_count']}",
                f"- 验证样本数: {manifest['validation_count']}",
                f"- 训练文件: `{manifest['train_file']}`",
                f"- 验证文件: `{manifest['validation_file']}`",
                "",
                "## 用途",
                "",
                "这是训练前候选数据，不代表已经可以直接开训。开训前必须人工抽检样本、跑人格回归测试，并确认数据来源许可。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出胡桃人格微调候选 JSONL 数据集。")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = export_dataset(
        source_path=Path(args.source),
        output_root=Path(args.output_root),
        validation_ratio=args.validation_ratio,
    )
    print(f"人格微调数据集目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
