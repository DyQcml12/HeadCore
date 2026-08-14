from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings


def main() -> int:
    settings = load_settings()
    checks = {
        "camera_perception_enabled": settings.camera_perception_enabled,
        "camera_local_capture_enabled": settings.camera_local_capture_enabled,
        "mediapipe_available": _available("mediapipe"),
        "opencv_available": _available("cv2"),
        "local_yolo_model_configured": bool(settings.camera_yolo_model_path),
        "local_yolo_model_exists": _model_exists(settings.camera_yolo_model_path),
    }
    for name, value in checks.items():
        print(f"{name}={str(value).lower()}")

    required = (
        checks["camera_perception_enabled"],
        checks["camera_local_capture_enabled"],
    )
    return 0 if all(required) else 1


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _model_exists(path: str) -> bool:
    return bool(path) and Path(path).is_file()


if __name__ == "__main__":
    sys.exit(main())
