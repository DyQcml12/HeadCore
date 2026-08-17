from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Header, HTTPException

from app.camera.contracts import CameraObservation, CameraSession, CameraSessionStartRequest
from app.camera.evidence_store import CameraEvidenceStore
from app.camera.normalization import camera_observation_to_world_observation
from app.camera.local_runtime import LocalCaptureController, LocalVisionAnalyzer
from app.camera.session_manager import CameraSessionManager
from app.camera.temporal_state import CameraTemporalState
from app.control import routes as control_routes
from app.core.config import Settings


@dataclass
class CameraControlRuntime:
    manager: CameraSessionManager
    capture: LocalCaptureController
    temporal_state: CameraTemporalState
    evidence_store: CameraEvidenceStore

    def start_consent_session(
        self,
        request: CameraSessionStartRequest,
        *,
        owner_key: str,
    ) -> CameraSession:
        return self.manager.start(request, owner_key=owner_key)

    def get_session(self, session_id: str, *, owner_key: str) -> CameraSession | None:
        return self.manager.get(session_id, owner_key=owner_key)

    def active_session(self, *, owner_key: str) -> CameraSession | None:
        for session_id in self.manager.owned_session_ids(owner_key=owner_key):
            session = self.manager.get(session_id, owner_key=owner_key)
            if session is not None and session.status == "active":
                return session
        return None

    def stop_session(self, session_id: str, *, owner_key: str) -> CameraSession | None:
        self.capture.stop(session_id)
        session = self.manager.stop(session_id, owner_key=owner_key)
        if session is not None:
            self.temporal_state.remove_session(session_id)
            self.evidence_store.remove_session(session_id)
        return session

    def stop_owner_sessions(self, *, owner_key: str) -> None:
        for session_id in self.manager.owned_session_ids(owner_key=owner_key):
            self.stop_session(session_id, owner_key=owner_key)


def build_camera_control_runtime(settings: Settings) -> CameraControlRuntime:
    manager = CameraSessionManager(
        perception_enabled=settings.camera_perception_enabled,
        local_capture_enabled=settings.camera_local_capture_enabled,
        max_session_seconds=settings.camera_session_max_seconds,
        raw_frame_retention_seconds=settings.camera_raw_frame_retention_seconds,
        face_identification_enabled=settings.camera_face_identification_enabled,
        cloud_upload_enabled=settings.camera_cloud_upload_enabled,
    )
    temporal_state = CameraTemporalState(
        confirmation_count=settings.camera_temporal_confirmation_count,
        window_seconds=settings.camera_temporal_window_seconds,
    )
    evidence_store = CameraEvidenceStore(
        max_age_seconds=settings.camera_observation_ttl_seconds,
    )
    def analyzer_factory() -> LocalVisionAnalyzer:
        return LocalVisionAnalyzer(
            yolo_model_path=settings.camera_yolo_model_path,
            enable_mediapipe=settings.camera_mediapipe_enabled,
        )

    def accept_capture_observation(observation: CameraObservation) -> None:
        manager.validate_capture_observation(observation)
        camera_observation_to_world_observation(
            observation, ttl_seconds=settings.camera_observation_ttl_seconds
        )
        temporal_update = temporal_state.observe(observation)
        if temporal_update is not None:
            evidence_store.record_update(temporal_update)

    # The callback only validates and normalizes transient data; it retains no frames or observations.
    capture = LocalCaptureController(
        analyzer_factory=analyzer_factory,
        minimum_interval_seconds=settings.camera_capture_interval_seconds,
        observation_callback=accept_capture_observation,
        session_active=manager.is_active_for_capture,
    )
    return CameraControlRuntime(
        manager=manager,
        capture=capture,
        temporal_state=temporal_state,
        evidence_store=evidence_store,
    )


def create_camera_control_router(
    settings: Settings,
    *,
    runtime: CameraControlRuntime | None = None,
) -> APIRouter:
    runtime = runtime or build_camera_control_runtime(settings)
    manager = runtime.manager
    temporal_state = runtime.temporal_state
    capture = runtime.capture
    router = APIRouter(tags=["camera-control"])

    async def authorize(platform: str | None, user_id: str | None, group_id: str | None):
        return await control_routes.require_control_admin(
            "camera_session_control", platform, user_id, group_id
        )

    def owner_key(actor) -> str:
        return f"{actor.source_account.platform}:{actor.profile_id}"

    @router.post("/api/control/camera/sessions", response_model=CameraSession)
    async def start_camera_session(
        request: CameraSessionStartRequest,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> CameraSession:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        try:
            session = manager.start(request, owner_key=owner_key(actor))
        except PermissionError as exc:
            await control_routes.audit_control_result(actor, "camera_session_start", False, "camera_disabled")
            raise HTTPException(status_code=409, detail={"code": "camera_disabled"}) from exc
        await control_routes.audit_control_result(actor, "camera_session_start", True, "consent_session_created")
        return session

    @router.get("/api/control/camera/sessions/{session_id}", response_model=CameraSession)
    async def get_camera_session(
        session_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> CameraSession:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        session = manager.get(session_id, owner_key=owner_key(actor))
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"})
        return session

    @router.post("/api/control/camera/sessions/{session_id}/stop", response_model=CameraSession)
    async def stop_camera_session(
        session_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> CameraSession:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        session = runtime.stop_session(session_id, owner_key=owner_key(actor))
        if session is None:
            await control_routes.audit_control_result(actor, "camera_session_stop", False, "not_found")
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"})
        await control_routes.audit_control_result(actor, "camera_session_stop", True, "stopped")
        return session

    @router.post("/api/control/camera/sessions/{session_id}/observations")
    async def submit_camera_observation(
        session_id: str,
        observation: CameraObservation,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        if observation.session_id != session_id:
            raise HTTPException(status_code=400, detail={"code": "camera_session_mismatch"})
        try:
            manager.validate_observation(observation, owner_key=owner_key(actor))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"}) from exc
        except (PermissionError, ValueError) as exc:
            await control_routes.audit_control_result(actor, "camera_observation_submit", False, "rejected")
            raise HTTPException(status_code=409, detail={"code": "camera_observation_rejected"}) from exc
        world = camera_observation_to_world_observation(
            observation, ttl_seconds=settings.camera_observation_ttl_seconds
        )
        temporal_update = temporal_state.observe(observation)
        await control_routes.audit_control_result(actor, "camera_observation_submit", True, "accepted")
        return {
            "accepted": True,
            "observation_id": world.observation_id,
            "expires_at": world.expires_at,
            "confidence": world.confidence,
            "capability": world.capability,
            "sensitivity": world.sensitivity,
        }

    @router.post("/api/control/camera/sessions/{session_id}/capture/start")
    async def start_camera_capture(
        session_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        session = manager.get(session_id, owner_key=owner_key(actor))
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"})
        if session.status != "active":
            raise HTTPException(status_code=409, detail={"code": "camera_session_not_active"})
        job = capture.start(session_id=session_id, camera_slot=session.camera_slot)
        await control_routes.audit_control_result(actor, "camera_capture_start", True, "started")
        return {"started": True, "session_id": session_id, **(capture.status(job.session_id) or {})}

    @router.get("/api/control/camera/sessions/{session_id}/capture/status")
    async def camera_capture_status(
        session_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        if manager.get(session_id, owner_key=owner_key(actor)) is None:
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"})
        return capture.status(session_id) or {"running": False, "reason_code": "not_started"}

    @router.get("/api/control/camera/sessions/{session_id}/perception/status")
    async def camera_perception_status(
        session_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        session = manager.get(session_id, owner_key=owner_key(actor))
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"})
        update = temporal_state.latest(session_id) if session.status == "active" else None
        if update is None:
            return {"available": False}
        observation = update.observation
        return {
            "available": True,
            "scene_label": observation.scene_label,
            "objects": observation.objects,
            "pose_labels": observation.pose_labels,
            "gesture_labels": observation.gesture_labels,
            "facial_cues": observation.facial_cues,
            "changes": update.changes,
            "observed_at": observation.observed_at,
        }

    @router.post("/api/control/camera/sessions/{session_id}/capture/stop")
    async def stop_camera_capture(
        session_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        actor = await authorize(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
        if manager.get(session_id, owner_key=owner_key(actor)) is None:
            raise HTTPException(status_code=404, detail={"code": "camera_session_not_found"})
        job = capture.stop(session_id)
        await control_routes.audit_control_result(actor, "camera_capture_stop", True, "stopped")
        return {"stopped": True, "session_id": session_id, "was_running": bool(job)}

    return router
