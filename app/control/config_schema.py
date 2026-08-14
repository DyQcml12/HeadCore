from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingSpec:
    key: str
    group: str
    label: str
    kind: str = "text"
    secret: bool = False
    restart_required: bool = True
    options: tuple[str, ...] = ()
    help_text: str = ""


SETTING_GROUPS: tuple[tuple[str, str], ...] = (
    ("brain", "Core model"),
    ("persona", "Persona"),
    ("clients", "Client connection"),
    ("voice", "Voice output"),
    ("audio", "Audio input"),
    ("world", "World tools"),
    ("storage", "Storage"),
)


SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("MODEL_PROVIDER", "brain", "Model provider", "select", options=("deepseek",)),
    SettingSpec("MODEL_NAME", "brain", "Model name"),
    SettingSpec("MODEL_BASE_URL", "brain", "Model API URL"),
    SettingSpec("DEEPSEEK_API_KEY", "brain", "DeepSeek API key", secret=True),
    SettingSpec("API_TIMEOUT_SECONDS", "brain", "Request timeout", "number"),
    SettingSpec("API_TEMPERATURE", "brain", "Temperature", "number"),
    SettingSpec("HUTAO_OWNER_NAME", "persona", "Owner display name", secret=True),
    SettingSpec("HUTAO_CORE_BASE_URL", "clients", "Core API URL"),
    SettingSpec("PUBLIC_WEB_TTS_ENABLED", "voice", "Enable signed web TTS", "bool"),
    SettingSpec("PUBLIC_WEB_TTS_PROVIDER", "voice", "TTS provider", "select", options=("gpt_sovits",)),
    SettingSpec("PUBLIC_WEB_TTS_BASE_URL", "voice", "TTS service URL"),
    SettingSpec("ASR_FILE_PRESETS", "audio", "ASR presets"),
    SettingSpec("ASR_REPAIR_PRESETS", "audio", "ASR repair presets"),
    SettingSpec("AUDIO_EMOTION_ENABLED", "audio", "Enable audio cues", "bool"),
    SettingSpec("AUDIO_EMOTION_MODEL", "audio", "Audio cue model"),
    SettingSpec("WORLD_AWARENESS_ENABLED", "world", "Enable world tools", "bool"),
    SettingSpec("AMAP_WEB_SERVICE_API_KEY", "world", "Amap API key", secret=True),
    SettingSpec("AMAP_SOURCE_LEGAL_APPROVED", "world", "Amap terms approved", "bool"),
    SettingSpec("WORLD_OFFICIAL_SOURCE_MANIFEST", "world", "World source manifest"),
    SettingSpec("WORLD_SOURCE_ENABLED_IDS", "world", "Enabled source IDs"),
    SettingSpec("WORLD_SOURCE_LEGAL_APPROVED_IDS", "world", "Approved source IDs"),
    SettingSpec("STORAGE_BACKEND", "storage", "Storage backend", "select", options=("jsonl", "postgresql")),
    SettingSpec("JSONL_STORAGE_DIR", "storage", "JSONL directory"),
    SettingSpec("MYSQL_HOST", "storage", "MySQL host"),
    SettingSpec("MYSQL_PORT", "storage", "MySQL port", "number"),
    SettingSpec("MYSQL_DATABASE", "storage", "MySQL database"),
    SettingSpec("MYSQL_USER", "storage", "MySQL user"),
    SettingSpec("MYSQL_PASSWORD", "storage", "MySQL password", secret=True),
)


SETTING_BY_KEY = {spec.key: spec for spec in SETTING_SPECS}


def grouped_setting_specs() -> list[dict[str, object]]:
    return [
        {
            "id": group_id,
            "label": label,
            "settings": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "kind": spec.kind,
                    "secret": spec.secret,
                    "restart_required": spec.restart_required,
                    "options": list(spec.options),
                    "help_text": spec.help_text,
                }
                for spec in SETTING_SPECS
                if spec.group == group_id
            ],
        }
        for group_id, label in SETTING_GROUPS
    ]
