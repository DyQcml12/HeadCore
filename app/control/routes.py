from __future__ import annotations

import subprocess
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.control.config_schema import grouped_setting_specs
from app.control.config_store import EnvConfigStore
from app.control.health_checks import build_control_status
from app.control.log_reader import list_log_targets, read_log_tail
from app.control.service_manager import list_services, start_service, stop_service
from app.control.test_runner import list_control_tests, run_control_test
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
WORLD_MODEL_DOCUMENT = PROJECT_ROOT / "docs" / "WORLD_MODEL_AND_PROJECT_CAPABILITIES.md"
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
async def control_page() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@router.get("/control/app.js", include_in_schema=False)
async def control_app_js() -> FileResponse:
    return FileResponse(STATIC_ROOT / "app.js", media_type="application/javascript")


@router.get("/control/style.css", include_in_schema=False)
async def control_style_css() -> FileResponse:
    return FileResponse(STATIC_ROOT / "style.css", media_type="text/css")


@router.get("/control/docs/world-model", include_in_schema=False)
async def control_world_model_document() -> FileResponse:
    return FileResponse(WORLD_MODEL_DOCUMENT, media_type="text/markdown; charset=utf-8")


@router.get("/control/assets/control-atmosphere.webp", include_in_schema=False)
async def control_atmosphere_asset() -> FileResponse:
    return FileResponse(
        STATIC_ROOT / "assets" / "control-atmosphere.webp",
        media_type="image/webp",
    )


@router.get("/api/control/status")
async def control_status() -> dict[str, object]:
    return build_control_status()


@router.get("/api/control/operations/status")
async def control_operations_status() -> dict[str, object]:
    snapshot = await build_operations_status_service().snapshot()
    return jsonable_encoder(asdict(snapshot))


@router.get("/api/control/operations/test-reports")
async def control_operations_test_reports(limit: int = 10) -> dict[str, object]:
    report_root = PROJECT_ROOT / "logs" / "test-runs"
    paths = sorted(
        report_root.glob("**/*.md") if report_root.exists() else (),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[: max(1, min(limit, 50))]
    summaries = [summarize_test_report(path, root=PROJECT_ROOT) for path in paths]
    return {"reports": jsonable_encoder([asdict(summary) for summary in summaries])}


@router.get("/api/control/operations/errors")
async def control_operations_errors() -> dict[str, object]:
    return {"errors": jsonable_encoder([])}


@router.get("/api/control/operations/actor")
async def control_operations_actor(
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    configured = bool(x_hutao_actor_platform and x_hutao_actor_user_id)
    actor = await _control_write_guard.verify(
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
    )
    return {
        "configured": configured,
        "authorized": actor is not None,
        "reason_code": "authorized" if actor is not None else "admin_required",
    }


@router.get("/api/control/operations/audits")
async def control_operations_audits(
    limit: int = 20,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    actor = await _control_write_guard.verify(
        platform=x_hutao_actor_platform,
        user_id=x_hutao_actor_user_id,
        group_id=x_hutao_actor_group_id,
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
async def control_config() -> dict[str, object]:
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
    request: ConfigUpdateRequest,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "control_config_update"
    actor = await require_control_admin(operation, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
    try:
        backup = EnvConfigStore().update_values(request.values)
    except ValueError as exc:
        await audit_control_result(actor, operation, False, "invalid_request")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit_control_result(actor, operation, True, "completed")
    return {
        "saved": True,
        "backup_path": str(backup) if backup else "",
        "restart_required": bool(request.values),
    }


@router.get("/api/control/logs")
async def control_logs() -> dict[str, object]:
    return {"targets": list_log_targets()}


@router.get("/api/control/logs/{log_id}")
async def control_log_tail(log_id: str, max_lines: int = 120) -> dict[str, object]:
    try:
        return read_log_tail(log_id, max_lines=max_lines)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/control/services")
async def control_services() -> dict[str, object]:
    return {"services": list_services()}


@router.post("/api/control/services/{service_id}/start")
async def start_control_service(
    service_id: str,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "service_start"
    actor = await require_control_admin(operation, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
    try:
        result = start_service(service_id)
    except (ValueError, FileNotFoundError) as exc:
        await audit_control_result(actor, operation, False, "operation_failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit_control_result(actor, operation, True, "completed")
    return result


@router.post("/api/control/services/{service_id}/stop")
async def stop_control_service(
    service_id: str,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "service_stop"
    actor = await require_control_admin(operation, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
    try:
        result = stop_service(service_id)
    except ValueError as exc:
        await audit_control_result(actor, operation, False, "operation_failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit_control_result(actor, operation, True, "completed")
    return result


@router.get("/api/control/tests")
async def control_tests() -> dict[str, object]:
    return {"tests": list_control_tests()}


@router.post("/api/control/tests/{test_id}/run")
async def run_control_test_endpoint(
    test_id: str,
    x_hutao_actor_platform: str | None = Header(default=None),
    x_hutao_actor_user_id: str | None = Header(default=None),
    x_hutao_actor_group_id: str | None = Header(default=None),
) -> dict[str, object]:
    operation = "control_test_run"
    actor = await require_control_admin(operation, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
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
