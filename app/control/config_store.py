from __future__ import annotations

import datetime as dt
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.control.config_schema import SETTING_BY_KEY, SettingSpec
from app.core.config import PROJECT_ROOT


SECRET_MASK = "********"


@dataclass(frozen=True)
class EnvSettingValue:
    key: str
    value: str
    configured: bool
    secret: bool


class EnvConfigStore:
    def __init__(self, env_path: Path | None = None) -> None:
        self.env_path = env_path or PROJECT_ROOT / ".env"

    def read_public_values(self) -> dict[str, EnvSettingValue]:
        values = self._read_values()
        result: dict[str, EnvSettingValue] = {}
        for key, spec in SETTING_BY_KEY.items():
            raw_value = values.get(key, "")
            result[key] = EnvSettingValue(
                key=key,
                value=SECRET_MASK if spec.secret and raw_value else raw_value,
                configured=bool(raw_value),
                secret=spec.secret,
            )
        return result

    def update_values(self, updates: dict[str, str]) -> Path | None:
        normalized = self._validate_updates(updates)
        if not normalized:
            return None
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.env_path.exists():
            self.env_path.write_text("", encoding="utf-8")
        backup_path = self._backup()
        lines = self.env_path.read_text(encoding="utf-8-sig").splitlines()
        handled: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            key = parse_env_key(line)
            if key and key in normalized:
                value = normalized[key]
                spec = SETTING_BY_KEY[key]
                if spec.secret and value == SECRET_MASK:
                    new_lines.append(line)
                else:
                    new_lines.append(f"{key}={value}")
                handled.add(key)
            else:
                new_lines.append(line)
        for key, value in normalized.items():
            if key in handled:
                continue
            if SETTING_BY_KEY[key].secret and value == SECRET_MASK:
                continue
            new_lines.append(f"{key}={value}")
        self.env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
        return backup_path

    def _read_values(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in self.env_path.read_text(encoding="utf-8-sig").splitlines():
            key = parse_env_key(raw_line)
            if not key:
                continue
            _, value = raw_line.split("=", 1)
            values[key] = value.strip().strip('"').strip("'")
        return values

    def _validate_updates(self, updates: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in updates.items():
            if key not in SETTING_BY_KEY:
                raise ValueError(f"Unsupported control setting: {key}")
            spec = SETTING_BY_KEY[key]
            text = normalize_setting_value(value, spec)
            normalized[key] = text
        return normalized

    def _backup(self) -> Path:
        timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_path = self.env_path.with_name(f"{self.env_path.name}.backup.{timestamp}")
        shutil.copy2(self.env_path, backup_path)
        return backup_path


def parse_env_key(line: str) -> str:
    match = re.match(r"^\s*([^#][^=\s]+)\s*=", line)
    return match.group(1).strip() if match else ""


def normalize_setting_value(value: str, spec: SettingSpec) -> str:
    text = str(value).strip()
    if spec.kind == "bool":
        return "true" if text.lower() in {"1", "true", "yes", "on"} else "false"
    if spec.kind == "select" and spec.options and text and text not in spec.options:
        raise ValueError(f"Unsupported value for {spec.key}: {text}")
    return text
