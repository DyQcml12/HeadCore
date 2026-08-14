from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.camera.contracts import CameraSession, CameraSessionStartRequest
from app.camera.router import CameraControlRuntime
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
        return {
            "session_expires_at": identity.expires_at,
            "camera": {
                "available": bool(
                    settings.camera_perception_enabled and settings.camera_local_capture_enabled
                ),
                "max_session_seconds": settings.camera_session_max_seconds,
                "raw_frame_retention_seconds": settings.camera_raw_frame_retention_seconds,
                "face_identification_enabled": settings.camera_face_identification_enabled,
                "cloud_upload_enabled": settings.camera_cloud_upload_enabled,
            },
        }

    @router.post("/api/workbench/camera/sessions", response_model=CameraSession)
    async def start_camera_session(
        request: CameraSessionStartRequest,
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
            return camera_runtime.start_consent_session(request, owner_key=identity.owner_key)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "camera_disabled"}) from exc

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
        camera_runtime.capture.start(session_id=session_id, camera_slot=session.camera_slot)
        return {
            "started": True,
            "session_id": session_id,
            **(camera_runtime.capture.status(session_id) or {}),
        }

    @router.post("/api/workbench/camera/sessions/{session_id}/capture/stop")
    async def stop_camera_capture(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session, csrf_token, require_csrf=True)
        if camera_runtime.get_session(session_id, owner_key=identity.owner_key) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        job = camera_runtime.capture.stop(session_id)
        return {"stopped": True, "session_id": session_id, "was_running": bool(job)}

    @router.get("/api/workbench/camera/sessions/{session_id}/capture/status")
    async def camera_capture_status(
        session_id: str,
        workbench_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, object]:
        identity = require_identity(workbench_session)
        if camera_runtime.get_session(session_id, owner_key=identity.owner_key) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "camera_session_not_found"})
        return camera_runtime.capture.status(session_id) or {"running": False, "reason_code": "not_started"}

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

    return router
