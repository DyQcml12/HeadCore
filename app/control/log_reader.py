from __future__ import annotations

from pathlib import Path
import re

from app.core.config import PROJECT_ROOT


SERVICE_LOG_DIR = PROJECT_ROOT / "logs" / "control-center" / "services"
HIDDEN_TEXT = "[\u5df2\u9690\u85cf]"


LOG_TARGETS: dict[str, Path] = {
    # Keep reader targets aligned with the filenames used by service_manager.
    # A mismatch here makes a running service look as if it has no logs.
    "hutao_core": SERVICE_LOG_DIR / "core_api.log",
    "gpt_sovits": SERVICE_LOG_DIR / "gpt_sovits_api.log",
}


def list_log_targets() -> list[dict[str, str]]:
    return [
        {
            "id": log_id,
            "path": str(path),
            "exists": str(path.exists()).lower(),
        }
        for log_id, path in LOG_TARGETS.items()
    ]


def read_log_tail(log_id: str, *, max_lines: int = 120) -> dict[str, object]:
    if log_id not in LOG_TARGETS:
        raise ValueError(f"Unsupported log target: {log_id}")
    path = LOG_TARGETS[log_id]
    if not path.exists():
        return {"id": log_id, "path": str(path), "exists": False, "lines": []}
    line_limit = max(1, min(max_lines, 500))
    lines = read_recent_lines(path, max_lines=line_limit)
    return {
        "id": log_id,
        "path": str(path),
        "exists": True,
        "lines": lines,
    }


BOT_LOG_TARGETS: dict[str, tuple[str, ...]] = {}


def read_bot_log_summary(bot_id: str, *, max_lines: int = 80) -> dict[str, object]:
    if bot_id not in BOT_LOG_TARGETS:
        raise ValueError(f"Unsupported bot log target: {bot_id}")
    lines: list[str] = []
    for log_id in BOT_LOG_TARGETS[bot_id]:
        path = LOG_TARGETS[log_id]
        if not path.exists():
            lines.append(f"[{log_id}] \u65e5\u5fd7\u6587\u4ef6\u4e0d\u5b58\u5728\uff1a{path}")
            continue
        raw_lines = read_recent_lines(path, max_lines=300)
        for line in raw_lines[-300:]:
            clean = compact_log_line(line)
            if clean:
                lines.append(f"[{log_id}] {clean}")
    return {
        "id": bot_id,
        "lines": lines[-max(1, min(max_lines, 200)) :],
    }


def read_recent_lines(path: Path, *, max_lines: int, max_bytes: int = 1_048_576) -> list[str]:
    line_limit = max(1, max_lines)
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        chunks: list[bytes] = []
        newline_count = 0
        bytes_read = 0
        while position > 0 and newline_count <= line_limit and bytes_read < max_bytes:
            chunk_size = min(8192, position, max_bytes - bytes_read)
            position -= chunk_size
            stream.seek(position)
            chunk = stream.read(chunk_size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")
            bytes_read += len(chunk)
    text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    lines = text.splitlines()
    if position > 0 and lines:
        lines = lines[1:]
    return lines[-line_limit:]


def compact_log_line(line: str) -> str:
    text = repair_mojibake(strip_ansi(line).strip())
    if not text:
        return ""
    if is_noisy_log_line(text):
        return ""
    lower = text.lower()
    keep_markers = (
        "error",
        "warn",
        "exception",
        "ready",
        "login",
        "connected",
        "websocket",
        "message",
        "gateway",
        "model",
        "allow",
        "token",
        "asr",
        "tts",
        "\u767b\u5f55",
        "\u8fde\u63a5",
        "\u5fae\u4fe1",
        "\u6d88\u606f",
        "\u63a5\u6536",
        "\u53d1\u9001",
        "\u79c1\u4fe1",
        "\u4e34\u65f6\u6d88\u606f",
        "\u4e8c\u7ef4\u7801",
        "\u626b\u7801",
        "\u5931\u8d25",
        "\u9519\u8bef",
        "\u5f02\u5e38",
        "\u542f\u52a8",
        "\u505c\u6b62",
    )
    if not any(marker in lower or marker in text for marker in keep_markers):
        return ""
    text = re.sub(r"\s+", " ", text)
    text = redact_sensitive_log_text(text)
    return text[-180:]


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def is_noisy_log_line(text: str) -> bool:
    lower = text.lower()
    noisy_markers = (
        "consolelog",
        "fileloglevel",
        "packetbackend",
        "session storage:",
        "secret redaction:",
        "agent budget:",
        "kanban dispatcher:",
        "gateway housekeeping",
        "press ctrl+c",
    )
    return any(marker in lower for marker in noisy_markers)


def redact_sensitive_log_text(text: str) -> str:
    text = re.sub(r"(?i)(token[:=]\s*)[^\s&]+", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)([?&]token=)[^\s&]+", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)([?&]k=)[^\s&]+", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)(\b(?:from|user|chat)=)[^\s]+", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)(\baccount=)[^\s]+", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)(\bfor\s+)[0-9a-f]{8,}\b", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)(\bmsg=)(?:'[^']*'|\S+)", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"(?i)(\breply_to_text=)(?:'[^']*'|\S+)", rf"\1{HIDDEN_TEXT}", text)
    text = re.sub(r"[A-Za-z0-9_-]{8,}@im\.(?:wechat|bot)", HIDDEN_TEXT, text)
    text = re.sub(r"(?<![\d.])\d{7,}(?![\d.])", HIDDEN_TEXT, text)
    text = re.sub(r"(私聊\s*\([^)]*\)\s*).+$", rf"\1{HIDDEN_TEXT}", text)
    return text


def repair_mojibake(text: str) -> str:
    if not any(marker in text for marker in ("氓", "忙", "莽", "茫", "猫", "茅", "å", "æ", "ä")):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    if count_cjk(repaired) > count_cjk(text):
        return repaired
    return text


def count_cjk(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
