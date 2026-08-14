from __future__ import annotations

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.database_control.actor import build_actor_identity
from app.database_control.errors import (
    DatabaseControlError,
    DatabaseNotReadyError,
    ResourceConflictError,
    translate_database_exception,
)
from app.knowledge.control import KnowledgeControlService
from app.knowledge.models import InvalidStateTransitionError, MemoryDecisionKind, MemoryState


class CandidateDecisionRequest(BaseModel):
    kind: MemoryDecisionKind
    reason: str = Field(min_length=1, max_length=255)
    supersede_conflicts: bool = False


class RevokeMemoryRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


def create_knowledge_control_router(service: KnowledgeControlService | None) -> APIRouter:
    router = APIRouter(prefix="/api/control/knowledge", tags=["knowledge-control"])

    async def call(operation):  # type: ignore[no-untyped-def]
        try:
            if service is None:
                raise DatabaseNotReadyError("knowledge lifecycle storage is not configured")
            return await operation()
        except DatabaseControlError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.response())
        except InvalidStateTransitionError as exc:
            error = ResourceConflictError(str(exc))
            return JSONResponse(status_code=error.status_code, content=error.response())
        except Exception as exc:
            translated = translate_database_exception(exc)
            if translated is None:
                raise
            return JSONResponse(status_code=translated.status_code, content=translated.response())

    async def actor(write: bool, platform, user_id, group_id):  # type: ignore[no-untyped-def]
        assert service is not None
        identity = build_actor_identity(
            platform=platform, platform_user_id=user_id, platform_group_id=group_id
        )
        return await service.resolve_actor(identity, write=write)

    def summary(item):  # type: ignore[no-untyped-def]
        return {
            "id": item.id, "profile_id": item.profile_id, "key": item.key,
            "value": item.value, "scope": item.scope.value, "confidence": item.confidence,
            "state": item.state.value, "source_type": item.source_type,
            "created_at": item.created_at.isoformat(),
        }

    @router.get("/status")
    async def status(x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            resolved = await actor(False, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            value = await service.status(resolved)  # type: ignore[union-attr]
            return {"durable": value.durable, "write_ready": value.write_ready, "reason": value.reason, "required_tables": value.required_tables}
        return await call(operation)

    @router.get("/candidates")
    async def candidates(profile_id: str | None = Query(default=None, max_length=64), state: MemoryState | None = Query(default=MemoryState.CANDIDATE), limit: int = Query(default=50, ge=1, le=100), x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            resolved = await actor(False, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            items = await service.list_candidates(resolved, profile_id=profile_id, state=state, limit=limit)  # type: ignore[union-attr]
            return {"items": [summary(item) for item in items]}
        return await call(operation)

    @router.post("/candidates/{candidate_id}/decision")
    async def decide(candidate_id: str, payload: CandidateDecisionRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            resolved = await actor(True, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            record = await service.decide(resolved, candidate_id, kind=payload.kind, reason=payload.reason, supersede_conflicts=payload.supersede_conflicts)  # type: ignore[union-attr]
            return {"candidate_id": candidate_id, "status": payload.kind.value, "record_id": record.id if record else None}
        return await call(operation)

    @router.post("/records/{record_id}/revoke")
    async def revoke(record_id: str, payload: RevokeMemoryRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            resolved = await actor(True, x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            record = await service.revoke(resolved, record_id, reason=payload.reason)  # type: ignore[union-attr]
            return {"record_id": record.id, "state": record.state.value}
        return await call(operation)

    return router
