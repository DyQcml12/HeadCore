"""Test-suite environment isolation.

The developer's local ``.env`` may enable authentication, PostgreSQL storage,
world tools, or TTS. Tests must not inherit that machine-specific shape, so a
neutral default is pinned here before any test module imports ``app.main``.
Individual tests that need a different shape set it explicitly with
``monkeypatch.setenv`` or ``replace(load_settings(), ...)``.
"""
from __future__ import annotations

import os

_NEUTRAL_TEST_ENV = {
    "PUBLIC_WEB_AUTH_ENABLED": "false",
    "DATABASE_V2_ENABLED": "false",
    "STORAGE_BACKEND": "jsonl",
    "EMAIL_DELIVERY_ENABLED": "false",
    "PUBLIC_WEB_TTS_ENABLED": "false",
    "WORLD_AWARENESS_ENABLED": "false",
    "WEB_SEARCH_ENABLED": "false",
    "AUDIO_WARMUP_ENABLED": "false",
    "CONTROL_ADMIN_EMAILS": "",
    "CONTROL_LOCAL_ONLY": "true",
    "POSTGRES_DATABASE": "",
    "POSTGRES_USER": "",
    "POSTGRES_PASSWORD": "",
    "MYSQL_DATABASE": "",
    "MYSQL_USER": "",
    "MYSQL_PASSWORD": "",
}

for _key, _value in _NEUTRAL_TEST_ENV.items():
    os.environ[_key] = _value
