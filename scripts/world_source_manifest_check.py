from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings
from app.world.source_manifest import load_source_manifest


def main() -> int:
    settings = load_settings()
    manifest_path = Path(settings.world_official_source_manifest)
    if not manifest_path.is_absolute():
        manifest_path = PROJECT_ROOT / manifest_path
    try:
        manifest = load_source_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ready": False, "error": type(exc).__name__}, indent=2))
        return 2

    by_kind = Counter(entry.kind.value for entry in manifest.sources)
    by_automation_policy = Counter(entry.automation_policy for entry in manifest.sources)
    print(
        json.dumps(
            {
                "ready": True,
                "version": manifest.version,
                "source_count": len(manifest.sources),
                "enabled_count": sum(entry.enabled for entry in manifest.sources),
                "legal_approved_count": sum(entry.legal_approved for entry in manifest.sources),
                "by_kind": dict(sorted(by_kind.items())),
                "by_automation_policy": dict(sorted(by_automation_policy.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
