from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from app.camera.contracts import CameraObservation


@dataclass(frozen=True)
class CameraAnalysis:
    scene_label: str = ""
    objects: tuple[str, ...] = ()
    pose_labels: tuple[str, ...] = ()
    gesture_labels: tuple[str, ...] = ()
    facial_cues: tuple[str, ...] = ()
    confidence: float = 0.0


class FrameSource(Protocol):
    def read(self) -> tuple[bool, Any]: ...

    def release(self) -> None: ...


class FrameAnalyzer(Protocol):
    def analyze(self, frame: Any) -> CameraAnalysis: ...

    def close(self) -> None: ...


class OpenCvFrameSource:
    def __init__(self, camera_slot: int) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("opencv-python is not installed") from exc
        self._capture = cv2.VideoCapture(camera_slot)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError("camera device is unavailable")

    def read(self) -> tuple[bool, Any]:
        ok, frame = self._capture.read()
        if not ok:
            self.last_error = "camera_frame_unavailable"
        return ok, frame

    def release(self) -> None:
        self._capture.release()


class LocalVisionAnalyzer:
    """Optional local MediaPipe and YOLO analyzers; never downloads a model."""

    def __init__(
        self,
        *,
        yolo_model_path: str = "",
        enable_mediapipe: bool = True,
    ) -> None:
        self._yolo = self._load_yolo(yolo_model_path)
        self._pose = self._hands = self._face = None
        if enable_mediapipe:
            self._load_mediapipe()

    def _load_yolo(self, model_path: str):
        if not model_path or not Path(model_path).is_file():
            return None
        try:
            from ultralytics import YOLO
            return YOLO(model_path)
        except (ImportError, OSError, RuntimeError):
            return None

    def _load_mediapipe(self) -> None:
        try:
            import mediapipe as mp
            self._pose = mp.solutions.pose.Pose(static_image_mode=False, model_complexity=0)
            self._hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=2)
            self._face = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1)
        except (ImportError, AttributeError, RuntimeError):
            self._pose = self._hands = self._face = None

    def analyze(self, frame: Any) -> CameraAnalysis:
        objects, scores = self._detect_objects(frame)
        pose, gesture, facial = self._detect_landmarks(frame)
        confidence = max(scores, default=0.0)
        if pose or gesture or facial:
            confidence = max(confidence, 0.86)
        return CameraAnalysis(
            objects=objects,
            pose_labels=pose,
            gesture_labels=gesture,
            facial_cues=facial,
            confidence=confidence,
        )

    def _detect_objects(self, frame: Any) -> tuple[tuple[str, ...], list[float]]:
        if self._yolo is None:
            return (), []
        try:
            result = self._yolo.predict(frame, verbose=False, conf=0.85, max_det=12)[0]
            names = result.names
            labels: list[str] = []
            scores: list[float] = []
            for cls, score in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist()):
                label = str(names[int(cls)]).lower().replace(" ", "_")
                if label in {"backpack", "book", "bottle", "car", "cat", "chair", "cup", "desk", "dog", "keyboard", "laptop", "mouse", "person", "phone", "screen", "table"} and label not in labels:
                    labels.append(label)
                    scores.append(float(score))
            return tuple(labels), scores
        except (AttributeError, IndexError, RuntimeError, ValueError):
            return (), []

    def _detect_landmarks(self, frame: Any) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        if self._pose is None:
            return (), (), ()
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_result = self._pose.process(rgb)
            hands_result = self._hands.process(rgb) if self._hands else None
            pose_labels: list[str] = []
            gestures: list[str] = []
            facial: list[str] = []
            landmarks = getattr(pose_result, "pose_landmarks", None)
            if landmarks:
                points = landmarks.landmark
                nose, left_shoulder, right_shoulder = points[0], points[11], points[12]
                shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
                if nose.y > shoulder_y:
                    pose_labels.append("head_down")
                    facial.append("head_down_detected")
                elif abs(left_shoulder.y - right_shoulder.y) < 0.12:
                    pose_labels.append("standing")
            if hands_result and getattr(hands_result, "multi_hand_landmarks", None):
                gestures.append("raised_hand")
            return tuple(pose_labels[:4]), tuple(gestures[:4]), tuple(facial[:4])
        except (AttributeError, RuntimeError, ValueError):
            return (), (), ()

    def close(self) -> None:
        for model in (self._pose, self._hands, self._face):
            if model is not None:
                model.close()


@dataclass
class CaptureJob:
    session_id: str
    stop_event: threading.Event
    thread: threading.Thread
    started_at: datetime
    last_error: str = ""
    observations_emitted: int = 0


class LocalCaptureController:
    def __init__(
        self,
        *,
        analyzer_factory: Callable[[], FrameAnalyzer],
        source_factory: Callable[[int], FrameSource] = OpenCvFrameSource,
        observation_callback: Callable[[CameraObservation], None],
        session_active: Callable[[str], bool] | None = None,
        minimum_interval_seconds: float = 1.0,
    ) -> None:
        if minimum_interval_seconds < 0.2:
            raise ValueError("camera capture interval must be at least 0.2 seconds")
        self._analyzer_factory = analyzer_factory
        self._source_factory = source_factory
        self._observation_callback = observation_callback
        self._session_active = session_active
        self._interval = minimum_interval_seconds
        self._jobs: dict[str, CaptureJob] = {}
        self._lock = threading.Lock()

    def start(
        self,
        *,
        session_id: str,
        camera_slot: int,
        source_factory: Callable[[int], FrameSource] | None = None,
    ) -> CaptureJob:
        with self._lock:
            if session_id in self._jobs and self._jobs[session_id].thread.is_alive():
                return self._jobs[session_id]
            stop_event = threading.Event()
            job = CaptureJob(session_id, stop_event, threading.Thread(), datetime.now(UTC))
            thread = threading.Thread(target=self._run, args=(job, camera_slot, source_factory or self._source_factory), daemon=True, name=f"camera-{session_id[-8:]}")
            job.thread = thread
            self._jobs[session_id] = job
            thread.start()
            return job

    def stop(self, session_id: str) -> CaptureJob | None:
        with self._lock:
            job = self._jobs.get(session_id)
        if job is None:
            return None
        job.stop_event.set()
        job.thread.join(timeout=3)
        return job

    def status(self, session_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(session_id)
        if job is None:
            return None
        return {"running": job.thread.is_alive(), "started_at": job.started_at, "observations_emitted": job.observations_emitted, "last_error": job.last_error}

    def _run(self, job: CaptureJob, camera_slot: int, source_factory: Callable[[int], FrameSource]) -> None:
        source = analyzer = None
        try:
            source = source_factory(camera_slot)
            analyzer = self._analyzer_factory()
            while not job.stop_event.is_set():
                if self._session_active is not None and not self._session_active(job.session_id):
                    job.last_error = "camera_session_not_active"
                    break
                ok, frame = source.read()
                if not ok:
                    job.last_error = str(getattr(source, "last_error", "") or "camera_frame_unavailable")[:80]
                    break
                result = analyzer.analyze(frame)
                if result.confidence >= 0.85 and any((result.objects, result.pose_labels, result.gesture_labels, result.facial_cues)):
                    self._observation_callback(CameraObservation(session_id=job.session_id, scene_label=result.scene_label, objects=result.objects, pose_labels=result.pose_labels, gesture_labels=result.gesture_labels, facial_cues=result.facial_cues, confidence=result.confidence, observed_at=datetime.now(UTC)))
                    job.observations_emitted += 1
                del frame
                job.stop_event.wait(self._interval)
        except Exception as exc:
            job.last_error = type(exc).__name__.lower()
        finally:
            if analyzer is not None:
                analyzer.close()
            if source is not None:
                source.release()
