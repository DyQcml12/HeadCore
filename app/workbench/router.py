from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, File, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.camera.contracts import (
    CameraDemoScenario,
    CameraSession,
    CameraSessionMode,
    CameraSessionStartRequest,
)
from app.camera.router import CameraControlRuntime
from app.camera.scene_state import derive_scene_state
from app.core.config import PROJECT_ROOT, Settings
from app.workbench.sessions import (
    WorkbenchAuthenticationError,
    WorkbenchCsrfError,
    WorkbenchRateLimitError,
    WorkbenchSessionStore,
    WorkbenchUnavailableError,
)


STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "workbench"
SESSION_COOKIE_NAME = "hutao_workbench_session"
CSRF_COOKIE_NAME = "hutao_workbench_csrf"


class WorkbenchLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1, max_length=512)


class CameraDemoStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: CameraDemoScenario = CameraDemoScenario.DESK_WORK


def create_visual_workbench_router(
    settings: Settings,
    camera_runtime: CameraControlRuntime,
) -> APIRouter:
    store = WorkbenchSessionStore(
        enabled=settings.visual_workbench_enabled,
        admin_secret=settings.visual_workbench_admin_secret,
        lifetime_seconds=settings.visual_workbench_session_lifetime_seconds,
    )
    router = APIRouter(tags=["visual-workbench"])

    def require_identity(
        session_token: str | None,
        csrf_token: str | None = None,
        *,
        require_csrf: bool = False,
    ):
        try:
            return store.require(
                session_token=session_token,
                csrf_token=csrf_token,
                require_csrf=require_csrf,
            )
        except WorkbenchUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workbench unavailable") from exc
        except WorkbenchCsrfError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed") from exc
        except WorkbenchAuthenticationError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required") from exc

    def real_readiness() -> tuple[bool, tuple[str, ...]]:
        capabilities = camera_runtime.capabilities
        blockers: list[str] = []
        if not settings.camera_perception_enabled:
            blockers.append("camera_perception_disabled")
        if not settings.camera_local_capture_enabled:
            blockers.append("camera_local_capture_disabled")
        if not capabilities.get("capture_ready"):
            blockers.extend(["capture_dependency_missing"])
        if not capabilities.get("labeling_ready"):
            blockers.append("labeling_dependency_missing")
            blockers.extend(str(code) for code in capabilities.get("reason_codes", ()))
        return not blockers, tuple(dict.fromkeys(blockers))

    @router.get("/workbench", include_in_schema=False)
    async def workbench_page() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @router.get("/workbench/app.js", include_in_schema=False)
    async def workbench_app_js() -> FileResponse:
        return FileResponse(
            STATIC_ROOT / "app.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/workbench/style.css", include_in_schema=False)
    async def workbench_style_css() -> FileResponse:
        return FileResponse(
            STATIC_ROOT / "style.css",
            media_type="text/css",
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/api/workbench/login", status_code=status.HTTP_204_NO_CONTENT)
    async def login(
        request: WorkbenchLoginRequest,
        response: Response,
        http_request: Request,
    ) -> Response:
        try:
            issued = store.login(
                supplied_secret=request.secret,
                subject=(http_request.client.host if http_request.client else "unknown")[:128],
            )
        except WorkbenchUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workbench unavailable") from exc
        except WorkbenchRateLimitError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="try again later") from exc
        except WorkbenchAuthenticationError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid administrator secret") from exc
        max_age = max(1, int((issued.identity.expires_at - datetime.now(UTC)).total_seconds()))
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=issued.session_token,
            max_age=max_age,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=issued.csrf_token,
            max_age=max_age,
            httponly=False,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.post("/api/workbench/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        response: Response,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> Response:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        store.logout(session_token=workbench_session)
        camera_runtime.stop_owner_sessions(owner_key=identity.owner_key)
        response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.get("/api/workbench/status")
    async def workbench_status(
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session)
        real_available = bool(
            settings.camera_perception_enabled and settings.camera_local_capture_enabled
        )
        demo_available = bool(settings.camera_demo_enabled)
        camera_available = real_available or demo_available
        capabilities = dict(camera_runtime.capabilities)
        real_ready, real_blockers = real_readiness()
        return {
            "session_expires_at": identity.expires_at,
            "camera": {
                "available": camera_available,
                "real_available": real_available,
                "real_ready": real_ready,
                "real_blockers": list(real_blockers),
                "demo_available": demo_available,
                "capture_ready": bool(real_available and capabilities.get("capture_ready")),
                "labeling_ready": bool(real_available and capabilities.get("labeling_ready")),
                "demo_scenarios": [scenario.value for scenario in CameraDemoScenario],
                "diagnostics": capabilities,
                "max_session_seconds": settings.camera_session_max_seconds,
                "raw_frame_retention_seconds": settings.camera_raw_frame_retention_seconds,
                "face_identification_enabled": settings.camera_face_identification_enabled,
                "cloud_upload_enabled": settings.camera_cloud_upload_enabled,
            },
        }

    @router.get("/api/v1/visual/context")
    async def visual_context(
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, object]:
        """Expose the latest confirmed labels to the local conversation UI.

        The workbench session remains the authorization boundary. No frame or
        unconfirmed observation is returned to the browser.
        """

        try:
            identity = require_identity(workbench_session)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                return {
                    "available": False,
                    "reason": "not_authenticated",
                    "workbench_url": "/workbench",
                }
            raise
        session = camera_runtime.active_session(owner_key=identity.owner_key)
        if session is None:
            return {
                "available": False,
                "reason": "no_active_session",
                "workbench_url": "/workbench",
            }
        snapshot = camera_runtime.evidence_store.latest_snapshot(session.session_id)
        mode = getattr(session.mode, "value", str(session.mode))
        demo_scenario = getattr(session.demo_scenario, "value", str(session.demo_scenario)) if session.demo_scenario else None
        return {
            **snapshot,
            "mode": mode,
            "demo_scenario": demo_scenario,
            "workbench_url": "/workbench",
        }

    @router.post("/api/workbench/camera/sessions", response_model=CameraSession)
    async def start_camera_session(
        request: CameraSessionStartRequest,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> CameraSession:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        if request.mode != CameraSessionMode.REAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "camera_demo_endpoint_required"},
            )
        if camera_runtime.active_session(owner_key=identity.owner_key) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "camera_session_already_active"},
            )
        real_ready, blockers = real_readiness()
        if not real_ready:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "camera_real_not_ready", "reason_codes": list(blockers)},
            )
        try:
            return camera_runtime.start_consent_session(request, owner_key=identity.owner_key)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "camera_disabled"}) from exc

    @router.post("/api/workbench/camera/demo/sessions", response_model=CameraSession)
    async def start_demo_session(
        request: CameraDemoStartRequest,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> CameraSession:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        if camera_runtime.active_session(owner_key=identity.owner_key) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "camera_session_already_active"},
            )
        try:
            return camera_runtime.start_consent_session(
                CameraSessionStartRequest(
                    consent_granted=True,
                    mode=CameraSessionMode.DEMO,
                    demo_scenario=request.scenario,
                ),
                owner_key=identity.owner_key,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "camera_demo_disabled"}) from exc

    @router.get("/api/workbench/camera/sessions/{session_id}", response_model=CameraSession)
    async def get_camera_session(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> CameraSession:
        identity = require_identity(workbench_session)
        session = camera_runtime.get_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        return session

    @router.post("/api/workbench/camera/sessions/{session_id}/stop", response_model=CameraSession)
    async def stop_camera_session(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> CameraSession:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        session = camera_runtime.stop_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        return session

    @router.post("/api/workbench/camera/sessions/{session_id}/capture/start")
    async def start_camera_capture(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        session = camera_runtime.get_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        if session.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "camera_session_not_active"})
        if session.mode == CameraSessionMode.DEMO:
            camera_runtime.start_capture(session)
            capture_status = camera_runtime.capture_status(session) or {}
        else:
            real_ready, blockers = real_readiness()
            if not real_ready:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "camera_real_not_ready", "reason_codes": list(blockers)},
                )
            camera_runtime.start_browser_capture(session)
            capture_status = camera_runtime.browser_capture_status(session) or {}
        return {
            "started": True,
            "session_id": session_id,
            **capture_status,
        }

    @router.post("/api/workbench/camera/sessions/{session_id}/frames")
    async def ingest_camera_frame(
        session_id: str,
        frame: UploadFile = File(...),
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        session = camera_runtime.get_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        if session.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "camera_session_not_active"})
        if session.mode != CameraSessionMode.REAL:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "camera_demo_has_no_frames"})
        if frame.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail={"code": "camera_frame_type_invalid"})
        payload = await frame.read(camera_runtime.browser.max_frame_bytes + 1)
        if len(payload) > camera_runtime.browser.max_frame_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"code": "camera_frame_too_large"})
        try:
            return await run_in_threadpool(camera_runtime.process_browser_frame, session, payload)
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(exc)}) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(exc)}) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": str(exc)}) from exc

    @router.post("/api/workbench/camera/sessions/{session_id}/capture/stop")
    async def stop_camera_capture(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        session = camera_runtime.get_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        job = (
            camera_runtime.stop_browser_capture(session)
            if session.mode != CameraSessionMode.DEMO
            else camera_runtime.stop_capture(session)
        )
        return {"stopped": True, "session_id": session_id, "was_running": bool(job)}

    @router.get("/api/workbench/camera/sessions/{session_id}/capture/status")
    async def camera_capture_status(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session)
        session = camera_runtime.get_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        if session.mode != CameraSessionMode.DEMO:
            return camera_runtime.browser_capture_status(session) or {"running": False, "reason_code": "not_started", "mode": "browser"}
        return camera_runtime.capture_status(session) or {"running": False, "reason_code": "not_started"}

    @router.get("/api/workbench/camera/sessions/{session_id}/perception/status")
    async def camera_perception_status(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session)
        session = camera_runtime.get_session(session_id, owner_key=identity.owner_key)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        update = camera_runtime.temporal_state.latest(session_id) if session.status == "active" else None
        if update is None:
            return {
                "available": False,
                "mode": session.mode,
                "demo_scenario": session.demo_scenario,
            }
        observation = update.observation
        scene_state = derive_scene_state(observation)
        return {
            "available": True,
            "mode": session.mode,
            "demo_scenario": session.demo_scenario,
            "scene_label": observation.scene_label,
            "objects": observation.objects,
            "pose_labels": observation.pose_labels,
            "gesture_labels": observation.gesture_labels,
            "facial_cues": observation.facial_cues,
            "changes": update.changes,
            "scene_state": scene_state.state_id,
            "scene_facts": scene_state.facts,
            "scene_confidence": scene_state.confidence,
            "observed_at": observation.observed_at,
        }

    return router
