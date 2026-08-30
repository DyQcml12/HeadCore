from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from app.camera.contracts import CameraDemoScenario, CameraObservation


@dataclass(frozen=True)
class DemoObservationTemplate:
    scene_label: str
    objects: tuple[str, ...]
    pose_labels: tuple[str, ...] = ()
    gesture_labels: tuple[str, ...] = ()
    facial_cues: tuple[str, ...] = ()


@dataclass
class DemoCaptureJob:
    session_id: str
    scenario: CameraDemoScenario
    stop_event: threading.Event
    thread: threading.Thread
    started_at: datetime
    last_error: str = ""
    observations_emitted: int = 0


_SCENARIO_TEMPLATES: dict[CameraDemoScenario, tuple[DemoObservationTemplate, ...]] = {
    CameraDemoScenario.DESK_WORK: (
        DemoObservationTemplate(
            scene_label="desk",
            objects=("desk", "laptop", "keyboard", "book"),
            pose_labels=("sitting",),
            gesture_labels=("typing",),
        ),
        DemoObservationTemplate(
            scene_label="desk",
            objects=("desk", "laptop", "cup", "phone"),
            pose_labels=("sitting",),
        ),
    ),
    CameraDemoScenario.DESK_SETUP: (
        DemoObservationTemplate(
            scene_label="desk",
            objects=("desk", "laptop", "cup", "phone"),
            pose_labels=("sitting",),
        ),
        DemoObservationTemplate(
            scene_label="desk",
            objects=("desk", "laptop", "book"),
            pose_labels=("sitting",),
        ),
    ),
    CameraDemoScenario.STREET_VEHICLE: (
        DemoObservationTemplate(
            scene_label="street",
            objects=("car", "person"),
            pose_labels=("standing",),
        ),
        DemoObservationTemplate(
            scene_label="street",
            objects=("car",),
        ),
    ),
    CameraDemoScenario.PERSON_PRESENT: (
        DemoObservationTemplate(
            scene_label="indoor",
            objects=("person",),
            pose_labels=("standing",),
        ),
        DemoObservationTemplate(
            scene_label="indoor",
            objects=("person",),
            pose_labels=("walking",),
        ),
    ),
}


class DemoCaptureController:
    """Emit deterministic structured observations without opening a camera."""

    def __init__(self, *, observation_callback, interval_seconds: float = 1.0) -> None:
        if interval_seconds < 0.2:
            raise ValueError("camera demo interval must be at least 0.2 seconds")
        self._observation_callback = observation_callback
        self._interval = interval_seconds
        self._jobs: dict[str, DemoCaptureJob] = {}
        self._lock = threading.Lock()

    def start(self, *, session_id: str, scenario: CameraDemoScenario) -> DemoCaptureJob:
        with self._lock:
            existing = self._jobs.get(session_id)
            if existing is not None and existing.thread.is_alive():
                return existing
            stop_event = threading.Event()
            job = DemoCaptureJob(
                session_id=session_id,
                scenario=scenario,
                stop_event=stop_event,
                thread=threading.Thread(),
                started_at=datetime.now(UTC),
            )
            job.thread = threading.Thread(
                target=self._run,
                args=(job,),
                daemon=True,
                name=f"camera-demo-{session_id[-8:]}",
            )
            self._jobs[session_id] = job
            job.thread.start()
            return job

    def stop(self, session_id: str) -> DemoCaptureJob | None:
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
            "mode": "demo",
            "scenario": job.scenario,
            "running": running,
            "state": "failed" if job.last_error else ("running" if running else "stopped"),
            "reason_code": job.last_error or ("running" if running else "stopped"),
            "started_at": job.started_at,
            "observations_emitted": job.observations_emitted,
            "last_error": job.last_error,
        }

    def _run(self, job: DemoCaptureJob) -> None:
        templates = _SCENARIO_TEMPLATES[job.scenario]
        emission = 0
        try:
            while not job.stop_event.is_set():
                template = templates[(emission // 3) % len(templates)]
                self._observation_callback(
                    CameraObservation(
                        session_id=job.session_id,
                        scene_label=template.scene_label,
                        objects=template.objects,
                        pose_labels=template.pose_labels,
                        gesture_labels=template.gesture_labels,
                        facial_cues=template.facial_cues,
                        confidence=0.98,
                        observed_at=datetime.now(UTC),
                    )
                )
                emission += 1
                job.observations_emitted = emission
                job.stop_event.wait(self._interval)
        except Exception as exc:
            job.last_error = type(exc).__name__.lower()


def demo_scenarios() -> tuple[CameraDemoScenario, ...]:
    return tuple(_SCENARIO_TEMPLATES)
