from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "asr_samples"
DEFAULT_MANIFEST = DEFAULT_OUTPUT_DIR / "manifest.json"
SENSEVOICE_EXAMPLE_DIR = (
    Path.home()
    / ".cache"
    / "modelscope"
    / "hub"
    / "models"
    / "iic"
    / "SenseVoiceSmall"
    / "example"
)

DOWNLOAD_SAMPLES = [
    {
        "id": "funasr-zh-example-001",
        "language": "zh",
        "expected_contains": ["欢迎", "体验"],
        "expected_text": "欢迎大家来体验达摩院推出的语音识别模型。",
        "max_cer": 0.15,
        "url": "https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav",
        "source": "FunASR public example",
        "license_note": "Public sample audio referenced by FunASR examples.",
        "hard_assert": True,
    },
    {
        "id": "openspeech-mandarin-0072-8k",
        "language": "zh",
        "expected_contains": [],
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0072_8k.wav",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable with source identified as "Open Speech Repository".',
        "hard_assert": True,
    },
    {
        "id": "openspeech-mandarin-0073-8k",
        "language": "zh",
        "expected_contains": [],
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0073_8k.wav",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable with source identified as "Open Speech Repository".',
        "hard_assert": True,
    },
    {
        "id": "openspeech-mandarin-0074-8k",
        "language": "zh",
        "expected_contains": [],
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0074_8k.wav",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable with source identified as "Open Speech Repository".',
        "hard_assert": True,
    },
    {
        "id": "openspeech-mandarin-0075-8k",
        "language": "zh",
        "expected_contains": [],
        "url": "https://www.voiptroubleshooter.com/open_speech/chinese/OSR_cn_000_0075_8k.wav",
        "source": "Open Speech Repository",
        "license_note": 'Freely usable with source identified as "Open Speech Repository".',
        "hard_assert": True,
    },
]

LOCAL_SENSEVOICE_SAMPLES = [
    {
        "id": "sensevoice-official-zh",
        "language": "zh",
        "expected_contains": [],
        "source_file": SENSEVOICE_EXAMPLE_DIR / "zh.mp3",
        "source": "SenseVoiceSmall official cached example",
        "license_note": "Bundled example audio from the locally cached ModelScope SenseVoiceSmall model.",
        "hard_assert": True,
    },
    {
        "id": "sensevoice-official-yue",
        "language": "yue",
        "expected_contains": [],
        "source_file": SENSEVOICE_EXAMPLE_DIR / "yue.mp3",
        "source": "SenseVoiceSmall official cached example",
        "license_note": "Bundled example audio from the locally cached ModelScope SenseVoiceSmall model.",
        "hard_assert": False,
    },
    {
        "id": "sensevoice-official-en",
        "language": "en",
        "expected_contains": [],
        "source_file": SENSEVOICE_EXAMPLE_DIR / "en.mp3",
        "source": "SenseVoiceSmall official cached example",
        "license_note": "Bundled example audio from the locally cached ModelScope SenseVoiceSmall model.",
        "hard_assert": False,
    },
]


def download_file(url: str, destination: Path) -> None:
    headers = {
        "User-Agent": "Mozilla/5.0 HutaoChatCore-ASR-Test/1.0",
        "Accept": "*/*",
    }
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_bytes():
                if chunk:
                    file.write(chunk)


def collect_samples(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    for sample in DOWNLOAD_SAMPLES:
        suffix = Path(str(sample["url"])).suffix or ".wav"
        audio_path = output_dir / f"{sample['id']}{suffix}"
        if not audio_path.exists():
            download_file(str(sample["url"]), audio_path)
        manifest.append({**sample, "path": str(audio_path), "sample_type": "public-original"})

    official_dir = output_dir / "official"
    official_dir.mkdir(parents=True, exist_ok=True)
    for sample in LOCAL_SENSEVOICE_SAMPLES:
        source_file = Path(sample["source_file"])
        if not source_file.exists():
            continue
        audio_path = official_dir / source_file.name
        if not audio_path.exists():
            shutil.copy2(source_file, audio_path)
        item = {key: value for key, value in sample.items() if key != "source_file"}
        manifest.append({**item, "path": str(audio_path), "sample_type": "official-original"})

    DEFAULT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return DEFAULT_MANIFEST


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="收集公开/官方 ASR 真实测试音频并生成 manifest。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = collect_samples(Path(args.output_dir))
    print(f"ASR 样本 manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
