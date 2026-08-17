from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.persona.profile_registry import DEFAULT_PERSONA_PROFILE_ID, resolve_persona_profile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    storage_backend: str
    jsonl_storage_dir: str
    model_provider: str
    model_name: str
    model_base_url: str
    deepseek_api_key: str
    request_timeout_seconds: float
    temperature: float
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_user: str
    postgres_password: str
    database_v2_enabled: bool
    knowledge_candidate_intake_enabled: bool
    persona_management_persistence_enabled: bool
    persona_management_writes_enabled: bool
    asr_file_presets: str
    asr_repair_presets: str
    audio_emotion_enabled: bool
    audio_emotion_model: str
    hutao_owner_qq_ids: str
    owner_bootstrap_qq_ids: str
    owner_bootstrap_wechat_ids: str
    hutao_owner_name: str
    persona_profile: str
    persona_profile_requested: str
    persona_profile_fallback_reason: str
    persona_display_name: str
    persona_style: str
    hutao_voice_profile: str
    voice_chat_reply_timeout_seconds: float = 25.0
    semantic_memory_enabled: bool = False
    semantic_memory_qdrant_url: str = ""
    semantic_memory_qdrant_api_key: str = ""
    semantic_memory_qdrant_collection: str = "hutao_memories"
    semantic_memory_embedding_provider: str = "openai_compatible"
    semantic_memory_embedding_model_path: str = ""
    semantic_memory_embedding_device: str = "cpu"
    semantic_memory_embedding_max_length: int = 8192
    semantic_memory_embedding_base_url: str = ""
    semantic_memory_embedding_api_key: str = ""
    semantic_memory_embedding_model: str = ""
    semantic_memory_embedding_timeout_seconds: float = 15.0
    semantic_memory_retrieval_limit: int = 8
    semantic_memory_min_score: float = 0.35
    text_provider_order: str = "deepseek"
    text_stream_ttft_timeout_seconds: float = 20.0
    text_stream_total_budget_seconds: float = 90.0
    recent_context_max_messages: int = 8
    recent_context_max_chars: int = 80
    text_provider_retries: int = 0
    text_provider_circuit_failure_threshold: int = 3
    text_provider_circuit_recovery_seconds: float = 60.0
    asr_provider_timeout_seconds: float = 180.0
    asr_provider_circuit_failure_threshold: int = 3
    asr_provider_circuit_recovery_seconds: float = 60.0
    audio_warmup_enabled: bool = False
    world_awareness_enabled: bool = False
    world_fetch_timeout_seconds: float = 12.0
    world_fetch_max_bytes: int = 1_048_576
    world_cache_max_entries: int = 512
    world_max_cache_ttl_seconds: int = 2_592_000
    amap_web_service_api_key: str = ""
    amap_web_service_base_url: str = "https://restapi.amap.com"
    amap_allowed_hosts: str = "restapi.amap.com"
    amap_source_legal_approved: bool = False
    amap_ip_cache_ttl_seconds: int = 86_400
    amap_weather_cache_ttl_seconds: int = 900
    amap_district_cache_ttl_seconds: int = 2_592_000
    amap_place_cache_ttl_seconds: int = 86_400
    amap_route_cache_ttl_seconds: int = 300
    qweather_api_key: str = ""
    qweather_api_base_url: str = "https://devapi.qweather.com"
    qweather_allowed_hosts: str = "devapi.qweather.com"
    qweather_source_legal_approved: bool = False
    qweather_weather_cache_ttl_seconds: int = 900
    world_domestic_news_api_key: str = ""
    world_domestic_news_api_base_url: str = ""
    world_international_news_api_key: str = ""
    world_international_news_api_base_url: str = ""
    world_official_source_manifest: str = "./data/world/sources.json"
    world_source_enabled_ids: str = ""
    world_source_legal_approved_ids: str = ""
    camera_perception_enabled: bool = False
    camera_local_capture_enabled: bool = False
    camera_session_max_seconds: int = 300
    camera_observation_ttl_seconds: int = 15
    camera_raw_frame_retention_seconds: int = 0
    camera_face_identification_enabled: bool = False
    camera_cloud_upload_enabled: bool = False
    camera_capture_interval_seconds: float = 2.0
    camera_temporal_confirmation_count: int = 2
    camera_temporal_window_seconds: int = 8
    camera_yolo_model_path: str = ""
    camera_mediapipe_enabled: bool = True
    visual_workbench_enabled: bool = False
    visual_workbench_admin_secret: str = ""
    visual_workbench_session_lifetime_seconds: int = 1800
    public_web_auth_enabled: bool = False
    session_cookie_secure: bool = False
    public_web_session_lifetime_seconds: int = 604800
    email_delivery_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_starttls: bool = True
    public_web_tts_enabled: bool = False
    public_web_tts_provider: str = "gpt_sovits"
    public_web_tts_base_url: str = "http://127.0.0.1:9880"
    public_web_tts_output_dir: str = "data/generated_voice/web"
    public_web_tts_reply_ttl_seconds: int = 300
    public_web_tts_min_interval_seconds: int = 8
    public_web_tts_max_reply_chars: int = 800

    @property
    def chat_completions_url(self) -> str:
        return self.model_base_url.rstrip("/") + "/chat/completions"

    @property
    def hutao_persona_profile(self) -> str:
        return self.persona_profile

    @property
    def hutao_persona_display_name(self) -> str:
        return self.persona_display_name

    @property
    def hutao_persona_style(self) -> str:
        return self.persona_style


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in [
        WORKSPACE_ROOT / "HutaoPersonaLab" / ".env",
        PROJECT_ROOT / ".env",
    ]:
        values.update(read_env_file(path))
    return values


def get_setting(name: str, env_values: dict[str, str], default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    return env_values.get(name) or default


def sanitize_persona_text(value: str, default: str = "") -> str:
    text = value.strip()
    mojibake_markers = ("�", "锟", "ï", "¿", "½", "Ã")
    has_private_use = any("\ue000" <= char <= "\uf8ff" for char in text)
    if has_private_use or any(marker in text for marker in mojibake_markers):
        return default
    return text or default


def load_settings() -> Settings:
    env_values = load_env_values()
    legacy_profile = get_setting("HUTAO_PERSONA_PROFILE", env_values, DEFAULT_PERSONA_PROFILE_ID)
    requested_profile = get_setting(
        "PERSONA_PROFILE",
        env_values,
        legacy_profile or DEFAULT_PERSONA_PROFILE_ID,
    )
    profile_resolution = resolve_persona_profile(requested_profile)
    return Settings(
        app_name=get_setting("APP_NAME", env_values, "HutaoChatCore"),
        environment=get_setting("ENVIRONMENT", env_values, "local"),
        storage_backend=get_setting("STORAGE_BACKEND", env_values, "jsonl"),
        jsonl_storage_dir=get_setting(
            "JSONL_STORAGE_DIR",
            env_values,
            str(PROJECT_ROOT / "logs" / "storage"),
        ),
        model_provider=get_setting("MODEL_PROVIDER", env_values, "deepseek"),
        model_name=get_setting("MODEL_NAME", env_values, "deepseek-v4-pro"),
        model_base_url=get_setting("MODEL_BASE_URL", env_values, "https://api.deepseek.com"),
        deepseek_api_key=get_setting("DEEPSEEK_API_KEY", env_values),
        request_timeout_seconds=float(get_setting("API_TIMEOUT_SECONDS", env_values, "90")),
        temperature=float(get_setting("API_TEMPERATURE", env_values, "0.8")),
        mysql_host=get_setting("MYSQL_HOST", env_values, "127.0.0.1"),
        mysql_port=int(get_setting("MYSQL_PORT", env_values, "3306")),
        mysql_database=get_setting("MYSQL_DATABASE", env_values),
        mysql_user=get_setting("MYSQL_USER", env_values),
        mysql_password=get_setting("MYSQL_PASSWORD", env_values),
        postgres_host=get_setting("POSTGRES_HOST", env_values, "127.0.0.1"),
        postgres_port=int(get_setting("POSTGRES_PORT", env_values, "5432")),
        postgres_database=get_setting("POSTGRES_DATABASE", env_values),
        postgres_user=get_setting("POSTGRES_USER", env_values),
        postgres_password=get_setting("POSTGRES_PASSWORD", env_values),
        database_v2_enabled=get_setting("DATABASE_V2_ENABLED", env_values, "false").lower()
        in {"1", "true", "yes", "on"},
        knowledge_candidate_intake_enabled=get_setting(
            "KNOWLEDGE_CANDIDATE_INTAKE_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        persona_management_persistence_enabled=get_setting(
            "PERSONA_MANAGEMENT_PERSISTENCE_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        persona_management_writes_enabled=get_setting(
            "PERSONA_MANAGEMENT_WRITES_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        asr_file_presets=get_setting("ASR_FILE_PRESETS", env_values, "sensevoice-small"),
        asr_repair_presets=get_setting("ASR_REPAIR_PRESETS", env_values, ""),
        audio_emotion_enabled=get_setting("AUDIO_EMOTION_ENABLED", env_values, "true").lower()
        in {"1", "true", "yes", "on"},
        audio_emotion_model=get_setting(
            "AUDIO_EMOTION_MODEL",
            env_values,
            "iic/emotion2vec_plus_large",
        ),
        hutao_owner_qq_ids=get_setting("HUTAO_OWNER_QQ_IDS", env_values, ""),
        owner_bootstrap_qq_ids=get_setting("OWNER_BOOTSTRAP_QQ_IDS", env_values, ""),
        owner_bootstrap_wechat_ids=get_setting("OWNER_BOOTSTRAP_WECHAT_IDS", env_values, ""),
        hutao_owner_name=get_setting("HUTAO_OWNER_NAME", env_values, "主人"),
        persona_profile=profile_resolution.profile.id,
        persona_profile_requested=requested_profile,
        persona_profile_fallback_reason=profile_resolution.reason,
        persona_display_name=profile_resolution.profile.identity_name,
        persona_style=profile_resolution.profile.default_style,
        hutao_voice_profile=get_setting("HUTAO_VOICE_PROFILE", env_values, "hutao_e15"),
        voice_chat_reply_timeout_seconds=float(
            get_setting("VOICE_CHAT_REPLY_TIMEOUT_SECONDS", env_values, "25")
        ),
        semantic_memory_enabled=get_setting(
            "SEMANTIC_MEMORY_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        semantic_memory_qdrant_url=get_setting("SEMANTIC_MEMORY_QDRANT_URL", env_values),
        semantic_memory_qdrant_api_key=get_setting(
            "SEMANTIC_MEMORY_QDRANT_API_KEY", env_values
        ),
        semantic_memory_qdrant_collection=get_setting(
            "SEMANTIC_MEMORY_QDRANT_COLLECTION", env_values, "hutao_memories"
        ),
        semantic_memory_embedding_provider=get_setting(
            "SEMANTIC_MEMORY_EMBEDDING_PROVIDER", env_values, "openai_compatible"
        ),
        semantic_memory_embedding_model_path=get_setting(
            "SEMANTIC_MEMORY_EMBEDDING_MODEL_PATH", env_values
        ),
        semantic_memory_embedding_device=get_setting(
            "SEMANTIC_MEMORY_EMBEDDING_DEVICE", env_values, "cpu"
        ),
        semantic_memory_embedding_max_length=int(
            get_setting("SEMANTIC_MEMORY_EMBEDDING_MAX_LENGTH", env_values, "8192")
        ),
        semantic_memory_embedding_base_url=get_setting(
            "SEMANTIC_MEMORY_EMBEDDING_BASE_URL", env_values
        ),
        semantic_memory_embedding_api_key=get_setting(
            "SEMANTIC_MEMORY_EMBEDDING_API_KEY", env_values
        ),
        semantic_memory_embedding_model=get_setting(
            "SEMANTIC_MEMORY_EMBEDDING_MODEL", env_values
        ),
        semantic_memory_embedding_timeout_seconds=float(
            get_setting("SEMANTIC_MEMORY_EMBEDDING_TIMEOUT_SECONDS", env_values, "15")
        ),
        semantic_memory_retrieval_limit=int(
            get_setting("SEMANTIC_MEMORY_RETRIEVAL_LIMIT", env_values, "8")
        ),
        semantic_memory_min_score=float(
            get_setting("SEMANTIC_MEMORY_MIN_SCORE", env_values, "0.35")
        ),
        text_provider_order=get_setting(
            "TEXT_PROVIDER_ORDER",
            env_values,
            get_setting("MODEL_PROVIDER", env_values, "deepseek"),
        ),
        text_provider_retries=int(get_setting("TEXT_PROVIDER_RETRIES", env_values, "0")),
        text_stream_ttft_timeout_seconds=float(
            get_setting("TEXT_STREAM_TTFT_TIMEOUT_SECONDS", env_values, "20")
        ),
        text_stream_total_budget_seconds=float(
            get_setting("TEXT_STREAM_TOTAL_BUDGET_SECONDS", env_values, "90")
        ),
        recent_context_max_messages=int(
            get_setting("RECENT_CONTEXT_MAX_MESSAGES", env_values, "8")
        ),
        recent_context_max_chars=int(
            get_setting("RECENT_CONTEXT_MAX_CHARS", env_values, "80")
        ),
        text_provider_circuit_failure_threshold=int(
            get_setting("TEXT_PROVIDER_CIRCUIT_FAILURE_THRESHOLD", env_values, "3")
        ),
        text_provider_circuit_recovery_seconds=float(
            get_setting("TEXT_PROVIDER_CIRCUIT_RECOVERY_SECONDS", env_values, "60")
        ),
        asr_provider_timeout_seconds=float(
            get_setting("ASR_PROVIDER_TIMEOUT_SECONDS", env_values, "180")
        ),
        asr_provider_circuit_failure_threshold=int(
            get_setting("ASR_PROVIDER_CIRCUIT_FAILURE_THRESHOLD", env_values, "3")
        ),
        asr_provider_circuit_recovery_seconds=float(
            get_setting("ASR_PROVIDER_CIRCUIT_RECOVERY_SECONDS", env_values, "60")
        ),
        audio_warmup_enabled=get_setting(
            "AUDIO_WARMUP_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        world_awareness_enabled=get_setting(
            "WORLD_AWARENESS_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        world_fetch_timeout_seconds=float(
            get_setting("WORLD_FETCH_TIMEOUT_SECONDS", env_values, "12")
        ),
        world_fetch_max_bytes=int(
            get_setting("WORLD_FETCH_MAX_BYTES", env_values, "1048576")
        ),
        world_cache_max_entries=int(
            get_setting("WORLD_CACHE_MAX_ENTRIES", env_values, "512")
        ),
        world_max_cache_ttl_seconds=int(
            get_setting("WORLD_MAX_CACHE_TTL_SECONDS", env_values, "2592000")
        ),
        amap_web_service_api_key=get_setting("AMAP_WEB_SERVICE_API_KEY", env_values),
        amap_web_service_base_url=get_setting(
            "AMAP_WEB_SERVICE_BASE_URL",
            env_values,
            "https://restapi.amap.com",
        ),
        amap_allowed_hosts=get_setting(
            "AMAP_ALLOWED_HOSTS", env_values, "restapi.amap.com"
        ),
        amap_source_legal_approved=get_setting(
            "AMAP_SOURCE_LEGAL_APPROVED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        amap_ip_cache_ttl_seconds=int(
            get_setting("AMAP_IP_CACHE_TTL_SECONDS", env_values, "86400")
        ),
        amap_weather_cache_ttl_seconds=int(
            get_setting("AMAP_WEATHER_CACHE_TTL_SECONDS", env_values, "900")
        ),
        amap_district_cache_ttl_seconds=int(
            get_setting("AMAP_DISTRICT_CACHE_TTL_SECONDS", env_values, "2592000")
        ),
        amap_place_cache_ttl_seconds=int(
            get_setting("AMAP_PLACE_CACHE_TTL_SECONDS", env_values, "86400")
        ),
        amap_route_cache_ttl_seconds=int(
            get_setting("AMAP_ROUTE_CACHE_TTL_SECONDS", env_values, "300")
        ),
        qweather_api_key=get_setting("QWEATHER_API_KEY", env_values),
        qweather_api_base_url=get_setting(
            "QWEATHER_API_BASE_URL", env_values, "https://devapi.qweather.com"
        ),
        qweather_allowed_hosts=get_setting(
            "QWEATHER_ALLOWED_HOSTS", env_values, "devapi.qweather.com"
        ),
        qweather_source_legal_approved=get_setting(
            "QWEATHER_SOURCE_LEGAL_APPROVED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        qweather_weather_cache_ttl_seconds=int(
            get_setting("QWEATHER_WEATHER_CACHE_TTL_SECONDS", env_values, "900")
        ),
        world_domestic_news_api_key=get_setting(
            "WORLD_DOMESTIC_NEWS_API_KEY", env_values
        ),
        world_domestic_news_api_base_url=get_setting(
            "WORLD_DOMESTIC_NEWS_API_BASE_URL", env_values
        ),
        world_international_news_api_key=get_setting(
            "WORLD_INTERNATIONAL_NEWS_API_KEY", env_values
        ),
        world_international_news_api_base_url=get_setting(
            "WORLD_INTERNATIONAL_NEWS_API_BASE_URL", env_values
        ),
        world_official_source_manifest=get_setting(
            "WORLD_OFFICIAL_SOURCE_MANIFEST",
            env_values,
            "./data/world/sources.json",
        ),
        world_source_enabled_ids=get_setting(
            "WORLD_SOURCE_ENABLED_IDS", env_values
        ),
        world_source_legal_approved_ids=get_setting(
            "WORLD_SOURCE_LEGAL_APPROVED_IDS", env_values
        ),
        camera_perception_enabled=get_setting(
            "CAMERA_PERCEPTION_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        camera_local_capture_enabled=get_setting(
            "CAMERA_LOCAL_CAPTURE_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        camera_session_max_seconds=int(
            get_setting("CAMERA_SESSION_MAX_SECONDS", env_values, "300")
        ),
        camera_observation_ttl_seconds=int(
            get_setting("CAMERA_OBSERVATION_TTL_SECONDS", env_values, "15")
        ),
        camera_raw_frame_retention_seconds=int(
            get_setting("CAMERA_RAW_FRAME_RETENTION_SECONDS", env_values, "0")
        ),
        camera_face_identification_enabled=get_setting(
            "CAMERA_FACE_IDENTIFICATION_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        camera_cloud_upload_enabled=get_setting(
            "CAMERA_CLOUD_UPLOAD_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        camera_capture_interval_seconds=float(
            get_setting("CAMERA_CAPTURE_INTERVAL_SECONDS", env_values, "2")
        ),
        camera_temporal_confirmation_count=int(
            get_setting("CAMERA_TEMPORAL_CONFIRMATION_COUNT", env_values, "2")
        ),
        camera_temporal_window_seconds=int(
            get_setting("CAMERA_TEMPORAL_WINDOW_SECONDS", env_values, "8")
        ),
        camera_yolo_model_path=get_setting("CAMERA_YOLO_MODEL_PATH", env_values),
        camera_mediapipe_enabled=get_setting(
            "CAMERA_MEDIAPIPE_ENABLED", env_values, "true"
        ).lower() in {"1", "true", "yes", "on"},
        visual_workbench_enabled=get_setting(
            "VISUAL_WORKBENCH_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        visual_workbench_admin_secret=get_setting("VISUAL_WORKBENCH_ADMIN_SECRET", env_values),
        visual_workbench_session_lifetime_seconds=int(
            get_setting("VISUAL_WORKBENCH_SESSION_LIFETIME_SECONDS", env_values, "1800")
        ),
        public_web_auth_enabled=get_setting(
            "PUBLIC_WEB_AUTH_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        session_cookie_secure=get_setting(
            "SESSION_COOKIE_SECURE", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        public_web_session_lifetime_seconds=int(
            get_setting("PUBLIC_WEB_SESSION_LIFETIME_SECONDS", env_values, "604800")
        ),
        email_delivery_enabled=get_setting(
            "EMAIL_DELIVERY_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        smtp_host=get_setting("SMTP_HOST", env_values),
        smtp_port=int(get_setting("SMTP_PORT", env_values, "587")),
        smtp_username=get_setting("SMTP_USERNAME", env_values),
        smtp_password=get_setting("SMTP_PASSWORD", env_values),
        smtp_from_address=get_setting("SMTP_FROM_ADDRESS", env_values),
        smtp_starttls=get_setting("SMTP_STARTTLS", env_values, "true").lower()
        in {"1", "true", "yes", "on"},
        public_web_tts_enabled=get_setting(
            "PUBLIC_WEB_TTS_ENABLED", env_values, "false"
        ).lower() in {"1", "true", "yes", "on"},
        public_web_tts_provider=get_setting("PUBLIC_WEB_TTS_PROVIDER", env_values, "gpt_sovits"),
        public_web_tts_base_url=get_setting(
            "PUBLIC_WEB_TTS_BASE_URL", env_values, "http://127.0.0.1:9880"
        ),
        public_web_tts_output_dir=get_setting(
            "PUBLIC_WEB_TTS_OUTPUT_DIR", env_values, "data/generated_voice/web"
        ),
        public_web_tts_reply_ttl_seconds=int(
            get_setting("PUBLIC_WEB_TTS_REPLY_TTL_SECONDS", env_values, "300")
        ),
        public_web_tts_min_interval_seconds=int(
            get_setting("PUBLIC_WEB_TTS_MIN_INTERVAL_SECONDS", env_values, "8")
        ),
        public_web_tts_max_reply_chars=int(
            get_setting("PUBLIC_WEB_TTS_MAX_REPLY_CHARS", env_values, "800")
        ),
    )
