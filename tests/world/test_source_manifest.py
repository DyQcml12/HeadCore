from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.world.source_manifest import load_source_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_world_source_manifest_is_valid_and_disabled() -> None:
    manifest = load_source_manifest(PROJECT_ROOT / "data" / "world" / "sources.json")

    assert manifest.version == 1
    assert len(manifest.sources) == 8
    assert all(not source.enabled for source in manifest.sources)
    assert all(not source.legal_approved for source in manifest.sources)
    assert {source.region for source in manifest.sources} == {
        "domestic",
        "global",
        "international",
    }
    assert next(
        source for source in manifest.sources if source.source_id == "pboc-releases"
    ).automation_policy == "robots_blocked"


def test_manifest_rejects_enabled_unapproved_source(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "source_id": "example",
                        "display_name": "Example",
                        "region": "global",
                        "kind": "api",
                        "capabilities": ["news"],
                        "entry_url": "https://example.com/news",
                        "allowed_hosts": ["example.com"],
                        "refresh_seconds": 900,
                        "enabled": True,
                        "legal_approved": False,
                        "requires_api_key": False,
                        "discovery_only": True,
                        "terms_url": "https://example.com/terms",
                        "robots_url": "",
                        "automation_policy": "api",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legally approved"):
        load_source_manifest(path)


def test_manifest_rejects_unallowlisted_or_credentialed_urls(tmp_path: Path) -> None:
    base = {
        "source_id": "example",
        "display_name": "Example",
        "region": "global",
        "kind": "api",
        "capabilities": ["news"],
        "entry_url": "https://other.example/news",
        "allowed_hosts": ["example.com"],
        "refresh_seconds": 900,
        "enabled": False,
        "legal_approved": False,
        "requires_api_key": False,
        "discovery_only": True,
        "terms_url": "",
        "robots_url": "",
        "automation_policy": "api",
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"version": 1, "sources": [base]}), encoding="utf-8")
    with pytest.raises(ValueError, match="allowlisted"):
        load_source_manifest(path)

    base["entry_url"] = "https://user:password@example.com/news"
    path.write_text(json.dumps({"version": 1, "sources": [base]}), encoding="utf-8")
    with pytest.raises(ValueError, match="credentials"):
        load_source_manifest(path)
