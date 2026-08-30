from __future__ import annotations

import subprocess
from dataclasses import asdict

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.control.config_schema import grouped_setting_specs
from app.control.config_store import EnvConfigStore
from app.control.health_checks import build_control_status
from app.control.log_reader import list_log_targets, read_log_tail
from app.control.service_manager import list_services, start_service, stop_service
from app.control.test_runner import list_control_tests, run_control_test
from app.control.access import (
    authorize_control_request,
    control_page_response,
    control_web_auth_enabled,
)
from app.core.config import PROJECT_ROOT
from app.core.config import load_settings
from app.database_control.mysql_adapter import build_mysql_database_control_adapter
from app.operations.aggregation import OperationsStatusService
from app.operations.observability import classify_error_lines
from app.operations.project_status import build_project_status_providers
from app.operations.reports import summarize_test_report
from app.operations.control_write import ControlWriteGuard
from app.storage.v2_relationship_service import parse_bootstrap_ids


router = APIRouter(tags=["control-center"])
STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "control"
_operations_settings = load_settings()
_operations_database_repository = build_mysql_database_control_adapter(_operations_settings)


def build_control_fallback_admins(settings) -> dict[str, set[str]]:  # type: ignore[no-untyped-def]
    if settings.database_v2_enabled:
        return {}
    return {
        "qq": set(parse_bootstrap_ids(settings.hutao_owner_qq_ids))
        | set(parse_bootstrap_ids(settings.owner_bootstrap_qq_ids)),
        "wechat": set(parse_bootstrap_ids(settings.owner_bootstrap_wechat_ids)),
    }


_control_write_guard = ControlWriteGuard(
    _operations_database_repository,
    fallback_admin_accounts=build_control_fallback_admins(_operations_settings),
)


async def require_control_admin(
    operation: str,
    platform: str | None,
    user_id: str | None,
    group_id: str | None,
):
    try:
        return await _control_write_guard.authorize(
            platform=platform,
            user_id=user_id,
            group_id=group_id,
            operation=operation,
        )
    except Exception as exc:
        raise HTTPException(status_code=403, detail={"code": "admin_required"}) from exc


async def audit_control_result(actor, operation: str, success: bool, reason_code: str) -> None:
    await _control_write_guard.record_result(
        actor=actor,
        operation=operation,
        success=success,
        reason_code=reason_code,
    )


def build_operations_status_service() -> OperationsStatusService:
    providers = build_project_status_providers(
        settings=_operations_settings,
        database_repository=_operations_database_repository,
        workspace_root=PROJECT_ROOT.parent,
    )
    return OperationsStatusService(providers, timeout_seconds=1.0)


class ConfigUpdateRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


@router.get("/control", include_in_schema=False)
async def control_page(request: Request):
    return await control_page_response(request, FileResponse(STATIC_ROOT / "index.html"))


@router.get("/control/app.js", include_in_schema=False)
async def control_app_js(request: Request):
    return await control_page_response(
        request, FileResponse(STATIC_ROOT / "app.js", media_type="application/javascript")
    )


@router.get("/control/style.css", include_in_schema=False)
async def control_style_css(request: Request):
    return await control_page_response(
        request, FileResponse(STATIC_ROOT / "style.css", media_type="text/css")
    )


@router.get("/control/assets/control-atmosphere.webp", include_in_schema=False)
async def control_atmosphere_asset(request: Request):
    return await control_page_response(
        request,
        FileResponse(
            STATIC_ROOT / "assets" / "control-atmosphere.webp",
            media_type="image/webp",
        ),
    )


@router.get("/api/control/access")
async def control_access(request: Request) -> dict[str, object]:
    actor = await authorize_control_request(
        request,
        operation="control_access_read",
        control_write_guard=_control_write_guard,
    )
    account = getattr(request.state, "control_web_admin_account", None)
    if account is not None:
        return {
            "authenticated": True,
            "authorized": True,
            "role": "owner_admin",
            "email": account.profile.email_normalized,
            "display_name": account.profile.display_name,
            "session_expires_at": account.session_expires_at.isoformat(),
            "mode": "web_session",
            "scope": "local_control_plane",
        }
    return {
        "authenticated": actor is not None,
        "authorized": actor is not None or not control_web_auth_enabled(),
        "role": "internal_actor" if actor is not None else "local_development",
        "mode": "internal_header" if actor is not None else "local_no_auth",
        "scope": "local_control_plane",
    }


@router.get("/api/control/status")
async def control_status(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="control_status_read", control_write_guard=_control_write_guard
    )
    return build_control_status()


@router.get("/api/control/operations/status")
async def control_operations_status(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="operations_status_read", control_write_guard=_control_write_guard
    )
    snapshot = await build_operations_status_service().snapshot()
    return jsonable_encoder(asdict(snapshot))


@router.get("/api/control/operations/test-reports")
async def control_operations_test_reports(request: Request, limit: int = 10) -> dict[str, object]:
    await authorize_control_request(
        request, operation="test_reports_read", control_write_guard=_control_write_guard
    )
    report_root = PROJECT_ROOT / "logs" / "test-runs"
    paths = sorted(
        report_root.glob("**/*.md") if report_root.exists() else (),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[: max(1, min(limit, 50))]
    summaries = [summarize_test_report(path, root=PROJECT_ROOT) for path in paths]
    return {"reports": jsonable_encoder([asdict(summary) for summary in summaries])}


@router.get("/api/control/operations/errors")
async def control_operations_errors(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="operations_errors_read", control_write_guard=_control_write_guard
    )
    return {"errors": jsonable_encoder([])}


@router.get("/api/control/operations/actor")
async def control_operations_actor(
    request: Request,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    actor = await authorize_control_request(
        request,
        operation="operations_actor_read",
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
        control_write_guard=_control_write_guard,
    )
    configured = bool(x_hutao_actor_platform and x_hutao_actor_user_id)
    return {
        "configured": configured,
        "authorized": actor is not None,
        "reason_code": "authorized" if actor is not None else "admin_required",
    }


@router.get("/api/control/operations/audits")
async def control_operations_audits(
    request: Request,
    limit: int = 20,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    actor = await authorize_control_request(
        request,
        operation="operations_audits_read",
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
        control_write_guard=_control_write_guard,
    )
    if actor is None:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    try:
        events = await _operations_database_repository.list_control_operations(
            limit=max(1, min(limit, 100))
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "audit_unavailable"}) from exc
    return {"audits": jsonable_encoder([event.model_dump() for event in events])}


@router.get("/api/control/config")
async def control_config(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="control_config_read", control_write_guard=_control_write_guard
    )
    store = EnvConfigStore()
    values = store.read_public_values()
    return {
        "groups": grouped_setting_specs(),
        "values": {
            key: {
                "value": item.value,
                "configured": item.configured,
                "secret": item.secret,
            }
            for key, item in values.items()
        },
    }


@router.post("/api/control/config")
async def update_control_config(
    request: Request,
    payload: ConfigUpdateRequest,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "control_config_update"
    actor = await authorize_control_request(
        request,
        operation=operation,
        write=True,
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
        control_write_guard=_control_write_guard,
    )
    if actor is None:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    try:
        backup = EnvConfigStore().update_values(payload.values)
    except ValueError as exc:
        await audit_control_result(actor, operation, False, "invalid_request")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit_control_result(actor, operation, True, "completed")
    return {
        "saved": True,
        "backup_path": str(backup) if backup else "",
        "restart_required": bool(payload.values),
    }


@router.get("/api/control/logs")
async def control_logs(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="logs_read", control_write_guard=_control_write_guard
    )
    return {"targets": list_log_targets()}


@router.get("/api/control/logs/{log_id}")
async def control_log_tail(request: Request, log_id: str, max_lines: int = 120) -> dict[str, object]:
    await authorize_control_request(
        request, operation="log_tail_read", control_write_guard=_control_write_guard
    )
    try:
        return read_log_tail(log_id, max_lines=max_lines)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/control/services")
async def control_services(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="services_read", control_write_guard=_control_write_guard
    )
    return {"services": list_services()}


@router.post("/api/control/services/{service_id}/start")
async def start_control_service(
    request: Request,
    service_id: str,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "service_start"
    actor = await authorize_control_request(
        request,
        operation=operation,
        write=True,
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
        control_write_guard=_control_write_guard,
    )
    if actor is None:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    try:
        result = start_service(service_id)
    except (ValueError, FileNotFoundError) as exc:
        await audit_control_result(actor, operation, False, "operation_failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit_control_result(actor, operation, True, "completed")
    return result


@router.post("/api/control/services/{service_id}/stop")
async def stop_control_service(
    request: Request,
    service_id: str,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "service_stop"
    actor = await authorize_control_request(
        request,
        operation=operation,
        write=True,
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
        control_write_guard=_control_write_guard,
    )
    if actor is None:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    try:
        result = stop_service(service_id)
    except ValueError as exc:
        await audit_control_result(actor, operation, False, "operation_failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit_control_result(actor, operation, True, "completed")
    return result


@router.get("/api/control/tests")
async def control_tests(request: Request) -> dict[str, object]:
    await authorize_control_request(
        request, operation="control_tests_read", control_write_guard=_control_write_guard
    )
    return {"tests": list_control_tests()}


@router.post("/api/control/tests/{test_id}/run")
async def run_control_test_endpoint(
    request: Request,
    test_id: str,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "control_test_run"
    actor = await authorize_control_request(
        request,
        operation=operation,
        write=True,
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
        control_write_guard=_control_write_guard,
    )
    if actor is None:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    try:
        result = run_control_test(test_id)
    except ValueError as exc:
        await audit_control_result(actor, operation, False, "invalid_request")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except subprocess.TimeoutExpired as exc:  # type: ignore[name-defined]
        await audit_control_result(actor, operation, False, "timeout")
        raise HTTPException(status_code=408, detail=f"Test timed out: {test_id}") from exc
    await audit_control_result(actor, operation, bool(result.get("passed")), "completed" if result.get("passed") else "test_failed")
    return result
