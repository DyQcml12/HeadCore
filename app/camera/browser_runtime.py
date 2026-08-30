from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from app.camera.contracts import CameraObservation
from app.camera.local_runtime import CameraAnalysis, LOCAL_VISION_MIN_CONFIDENCE


@dataclass
class BrowserFrameJob:
    session_id: str
    analyzer: object
    started_at: datetime
    lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = True
    last_frame_at: datetime | None = None
    last_error: str = ""
    frames_received: int = 0
    observations_emitted: int = 0


class BrowserFrameProcessor:
    """Analyze short-lived browser camera frames without retaining media.

    The browser owns the camera device. Each JPEG is decoded, analyzed, and
    released in the same request, which avoids the Windows camera-device race
    caused by opening the same camera from both browser and OpenCV workers.
    """

    def __init__(
        self,
        *,
        analyzer_factory: Callable[[], object],
        observation_callback: Callable[[CameraObservation], None],
        session_active: Callable[[str], bool],
        max_frame_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if max_frame_bytes < 64 * 1024:
            raise ValueError("browser frame limit is too small")
        self._analyzer_factory = analyzer_factory
        self._observation_callback = observation_callback
        self._session_active = session_active
        self._max_frame_bytes = max_frame_bytes
        self._jobs: dict[str, BrowserFrameJob] = {}
        self._lock = threading.Lock()

    @property
    def max_frame_bytes(self) -> int:
        return self._max_frame_bytes

    def start(self, *, session_id: str) -> BrowserFrameJob:
        with self._lock:
            existing = self._jobs.get(session_id)
            if existing is not None and existing.running:
                return existing
            job = BrowserFrameJob(
                session_id=session_id,
                analyzer=self._analyzer_factory(),
                started_at=datetime.now(UTC),
            )
            self._jobs[session_id] = job
            return job

    def stop(self, session_id: str) -> BrowserFrameJob | None:
        with self._lock:
            job = self._jobs.get(session_id)
        if job is None:
            return None
        with job.lock:
            if job.running:
                job.running = False
                close = getattr(job.analyzer, "close", None)
                if callable(close):
                    close()
        return job

    def status(self, session_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(session_id)
        if job is None:
            return None
        with job.lock:
            running = job.running
            return {
                "mode": "browser",
                "running": running,
                "state": "failed" if job.last_error else ("running" if running else "stopped"),
                "reason_code": job.last_error or ("running" if running else "stopped"),
                "started_at": job.started_at,
                "last_frame_at": job.last_frame_at,
                "frames_received": job.frames_received,
                "observations_emitted": job.observations_emitted,
                "last_error": job.last_error,
            }

    def process(self, *, session_id: str, payload: bytes) -> dict[str, object]:
        if not payload or len(payload) > self._max_frame_bytes:
            raise ValueError("camera_frame_size_invalid")
        with self._lock:
            job = self._jobs.get(session_id)
        if job is None or not job.running:
            raise LookupError("camera_capture_not_started")
        if not self._session_active(session_id):
            self.stop(session_id)
            raise PermissionError("camera_session_not_active")

        with job.lock:
            if not job.running:
                raise LookupError("camera_capture_not_started")
            frame = _decode_image(payload)
            analysis = job.analyzer.analyze(frame)
            del frame
            job.frames_received += 1
            job.last_frame_at = datetime.now(UTC)
            emitted = False
            if _has_confirmable_labels(analysis) and analysis.confidence >= LOCAL_VISION_MIN_CONFIDENCE:
                self._observation_callback(
                    CameraObservation(
                        session_id=session_id,
                        scene_label=analysis.scene_label,
                        objects=analysis.objects,
                        pose_labels=analysis.pose_labels,
                        gesture_labels=analysis.gesture_labels,
                        facial_cues=analysis.facial_cues,
                        confidence=analysis.confidence,
                        observed_at=job.last_frame_at,
                    )
                )
                job.observations_emitted += 1
                emitted = True
            return {
                "accepted": True,
                "observation_emitted": emitted,
                "frames_received": job.frames_received,
                "observations_emitted": job.observations_emitted,
            }


def _decode_image(payload: bytes):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("opencv_missing") from exc
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or getattr(image, "size", 0) == 0:
        raise ValueError("camera_frame_invalid")
    return image


def _has_confirmable_labels(analysis: CameraAnalysis) -> bool:
    return bool(
        analysis.objects
        or analysis.pose_labels
        or analysis.gesture_labels
        or analysis.facial_cues
    )
