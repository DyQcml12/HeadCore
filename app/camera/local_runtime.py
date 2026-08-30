from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from typing import Any, Callable, Protocol

from app.camera.contracts import CameraObservation


LOCAL_VISION_MIN_CONFIDENCE = 0.55


@dataclass(frozen=True)
class CameraAnalysis:
    scene_label: str = ""
    objects: tuple[str, ...] = ()
    pose_labels: tuple[str, ...] = ()
    gesture_labels: tuple[str, ...] = ()
    facial_cues: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class LocalVisionCapability:
    """Non-sensitive local capability diagnostics for the workbench."""

    opencv_available: bool
    mediapipe_available: bool
    ultralytics_available: bool
    yolo_model_configured: bool
    yolo_model_exists: bool
    capture_ready: bool
    labeling_ready: bool
    reason_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "opencv_available": self.opencv_available,
            "mediapipe_available": self.mediapipe_available,
            "ultralytics_available": self.ultralytics_available,
            "yolo_model_configured": self.yolo_model_configured,
            "yolo_model_exists": self.yolo_model_exists,
            "capture_ready": self.capture_ready,
            "labeling_ready": self.labeling_ready,
            "reason_codes": list(self.reason_codes),
        }


def inspect_local_vision_capabilities(
    *,
    yolo_model_path: str = "",
    enable_mediapipe: bool = True,
) -> LocalVisionCapability:
    opencv_available = importlib.util.find_spec("cv2") is not None
    mediapipe_available = enable_mediapipe and importlib.util.find_spec("mediapipe") is not None
    ultralytics_available = importlib.util.find_spec("ultralytics") is not None
    yolo_model_configured = bool(yolo_model_path.strip())
    yolo_model_exists = yolo_model_configured and Path(yolo_model_path).is_file()
    capture_ready = opencv_available
    labeling_ready = bool(mediapipe_available or (ultralytics_available and yolo_model_exists))
    reasons: list[str] = []
    if not opencv_available:
        reasons.append("opencv_missing")
    if not labeling_ready:
        if enable_mediapipe and not mediapipe_available:
            reasons.append("mediapipe_missing")
        if not yolo_model_configured:
            reasons.append("yolo_model_not_configured")
        elif not yolo_model_exists:
            reasons.append("yolo_model_missing")
        elif not ultralytics_available:
            reasons.append("ultralytics_missing")
    return LocalVisionCapability(
        opencv_available=opencv_available,
        mediapipe_available=mediapipe_available,
        ultralytics_available=ultralytics_available,
        yolo_model_configured=yolo_model_configured,
        yolo_model_exists=yolo_model_exists,
        capture_ready=capture_ready,
        labeling_ready=labeling_ready,
        reason_codes=tuple(reasons),
    )


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

    # YOLO's COCO names are normalized to the small, explicit contract used by
    # the camera evidence store. Anything outside this map is ignored.
    _YOLO_LABEL_MAP = {
        "person": "person",
        "backpack": "backpack",
        "book": "book",
        "bottle": "bottle",
        "car": "car",
        "cat": "cat",
        "chair": "chair",
        "cup": "cup",
        "dining_table": "table",
        "dog": "dog",
        "keyboard": "keyboard",
        "laptop": "laptop",
        "mouse": "mouse",
        "cell_phone": "phone",
        "tv": "screen",
    }

    def __init__(
        self,
        *,
        yolo_model_path: str = "",
        enable_mediapipe: bool = True,
    ) -> None:
        self._yolo = self._load_yolo(yolo_model_path)
        self._pose = self._hands = None
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
        except (ImportError, AttributeError, RuntimeError):
            self._pose = self._hands = None

    def analyze(self, frame: Any) -> CameraAnalysis:
        objects, scores = self._detect_objects(frame)
        pose, gesture, facial = self._detect_landmarks(frame)
        # MediaPipe landmarks are direct evidence that a person is present;
        # this label is not inferred from identity, emotion, or intent.
        if (pose or gesture or facial) and "person" not in objects:
            objects = (*objects, "person")
        confidence = max(scores, default=0.0)
        if pose or gesture or facial:
            confidence = max(confidence, 0.86)
        return CameraAnalysis(
            scene_label=_infer_scene_label(objects),
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
            result = self._yolo.predict(frame, verbose=False, conf=0.55, max_det=12)[0]
            names = result.names
            labels: list[str] = []
            scores: list[float] = []
            for cls, score in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist()):
                raw_label = str(names[int(cls)]).strip().lower().replace(" ", "_")
                label = self._YOLO_LABEL_MAP.get(raw_label)
                if label and label not in labels:
                    labels.append(label)
                    scores.append(float(score))
            return tuple(labels), scores
        except (AttributeError, IndexError, RuntimeError, ValueError):
            return (), []

    def _detect_landmarks(self, frame: Any) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        if self._pose is None and self._hands is None:
            return (), (), ()
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_result = self._pose.process(rgb) if self._pose else None
            hands_result = self._hands.process(rgb) if self._hands else None
            pose_labels: list[str] = []
            gestures: list[str] = []
            facial: list[str] = []
            landmarks = getattr(pose_result, "pose_landmarks", None)
            points = getattr(landmarks, "landmark", ()) if landmarks else ()
            if len(points) > 28:
                nose = points[0]
                left_shoulder, right_shoulder = points[11], points[12]
                left_hip, right_hip = points[23], points[24]
                left_knee, right_knee = points[25], points[26]
                left_ankle, right_ankle = points[27], points[28]
                shoulder_y = None
                if _landmark_visible(left_shoulder) and _landmark_visible(right_shoulder):
                    shoulder_y = (float(left_shoulder.y) + float(right_shoulder.y)) / 2
                if shoulder_y is not None and _landmark_visible(nose) and float(nose.y) > shoulder_y - 0.03:
                    pose_labels.append("head_down")
                    facial.append("head_down_detected")

                if all(_landmark_visible(point) for point in (left_hip, right_hip, left_knee, right_knee)):
                    hip_y = (float(left_hip.y) + float(right_hip.y)) / 2
                    knee_y = (float(left_knee.y) + float(right_knee.y)) / 2
                    knee_delta = knee_y - hip_y
                    if knee_delta < 0.18:
                        pose_labels.append("sitting")
                    elif knee_delta > 0.22 and all(_landmark_visible(point) for point in (left_ankle, right_ankle)):
                        ankle_y = (float(left_ankle.y) + float(right_ankle.y)) / 2
                        if ankle_y > knee_y - 0.05:
                            pose_labels.append("standing")

            if hands_result and getattr(hands_result, "multi_hand_landmarks", None):
                shoulder_reference = 0.42
                if len(points) > 12 and _landmark_visible(points[11]) and _landmark_visible(points[12]):
                    shoulder_reference = min(float(points[11].y), float(points[12].y))
                for hand in hands_result.multi_hand_landmarks:
                    hand_points = getattr(hand, "landmark", ())
                    if len(hand_points) < 21:
                        continue
                    if _is_raised_hand(hand_points[0], shoulder_reference):
                        _append_unique(gestures, "raised_hand")
                    if _is_pointing_hand(hand_points):
                        _append_unique(gestures, "pointing")
            return tuple(pose_labels[:4]), tuple(gestures[:4]), tuple(facial[:4])
        except (AttributeError, IndexError, RuntimeError, TypeError, ValueError):
            return (), (), ()

    def close(self) -> None:
        for model in (self._pose, self._hands):
            if model is not None:
                model.close()


def _landmark_visible(point: Any, threshold: float = 0.45) -> bool:
    """Return false for missing or low-confidence pose landmarks."""

    if point is None:
        return False
    try:
        return float(getattr(point, "visibility", 1.0)) >= threshold
    except (TypeError, ValueError):
        return False


def _append_unique(labels: list[str], label: str) -> None:
    if label not in labels:
        labels.append(label)


def _distance(first: Any, second: Any) -> float:
    try:
        return ((float(first.x) - float(second.x)) ** 2 + (float(first.y) - float(second.y)) ** 2) ** 0.5
    except (AttributeError, TypeError, ValueError):
        return 0.0


def _finger_extended(points: Any, tip_index: int, pip_index: int) -> bool:
    if len(points) <= max(tip_index, pip_index):
        return False
    wrist = points[0]
    return _distance(points[tip_index], wrist) > _distance(points[pip_index], wrist) * 1.12


def _is_raised_hand(wrist: Any, shoulder_y: float) -> bool:
    try:
        return float(wrist.y) < shoulder_y - 0.08
    except (AttributeError, TypeError, ValueError):
        return False


def _is_pointing_hand(points: Any) -> bool:
    index_extended = _finger_extended(points, 8, 6)
    other_extended = sum(
        _finger_extended(points, tip, pip)
        for tip, pip in ((12, 10), (16, 14), (20, 18))
    )
    return index_extended and other_extended == 0


def _infer_scene_label(objects: tuple[str, ...]) -> str:
    object_set = set(objects)
    if "car" in object_set:
        return "street"
    if object_set.intersection({"desk", "table", "laptop", "keyboard", "book", "phone", "cup"}):
        return "desk"
    return ""


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
        running = job.thread.is_alive()
        return {
            "running": running,
            "state": "failed" if job.last_error else ("running" if running else "stopped"),
            "reason_code": job.last_error or ("running" if running else "stopped"),
            "started_at": job.started_at,
            "observations_emitted": job.observations_emitted,
            "last_error": job.last_error,
        }

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
                if result.confidence >= LOCAL_VISION_MIN_CONFIDENCE and any((result.objects, result.pose_labels, result.gesture_labels, result.facial_cues)):
                    self._observation_callback(CameraObservation(session_id=job.session_id, scene_label=result.scene_label, objects=result.objects, pose_labels=result.pose_labels, gesture_labels=result.gesture_labels, facial_cues=result.facial_cues, confidence=result.confidence, observed_at=datetime.now(UTC)))
                    job.observations_emitted += 1
                del frame
                job.stop_event.wait(self._interval)
        except Exception as exc:
            job.last_error = _capture_error_code(exc)
        finally:
            if analyzer is not None:
                analyzer.close()
            if source is not None:
                source.release()


def _capture_error_code(error: Exception) -> str:
    """Map local capture failures to bounded, non-sensitive UI reason codes."""

    message = str(error).lower()
    if "camera device is unavailable" in message:
        return "camera_device_unavailable"
    if "opencv-python is not installed" in message:
        return "opencv_missing"
    return type(error).__name__.lower()
