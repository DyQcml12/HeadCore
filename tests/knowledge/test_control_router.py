from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.knowledge.control import KnowledgeControlService
from app.knowledge.models import KnowledgeActor, MemoryScope, PortraitPatch
from app.knowledge.router import create_knowledge_control_router
from app.knowledge.service import KnowledgeLifecycleService
from tests.database_control.fakes import actor
from tests.knowledge.test_runtime_intake import ActorRepository, RuntimeKnowledgeRepository


ADMIN_HEADERS = {
    "X-Hutao-Actor-Platform": "qq",
    "X-Hutao-Actor-User-Id": "10001",
}


def client_for(resolved_actor=...):  # type: ignore[no-untyped-def]
    repository = RuntimeKnowledgeRepository()
    resolved = actor() if resolved_actor is ... else resolved_actor
    service = KnowledgeControlService(repository, ActorRepository(resolved))  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(create_knowledge_control_router(service))
    return TestClient(app), repository


def seed_candidate(repository: RuntimeKnowledgeRepository) -> str:
    service = KnowledgeLifecycleService(repository)
    candidate = asyncio.run(
        service.submit(
            PortraitPatch(
                profile_id="profile-user", key="reply.style", value="short",
                scope=MemoryScope.SAFE_PREFERENCE, source_type="message",
                source_id="message-1", confidence=0.9,
            ),
            actor=KnowledgeActor(profile_id="profile-user"),
        )
    )
    return candidate.id


def test_unconfigured_router_fails_closed() -> None:
    app = FastAPI()
    app.include_router(create_knowledge_control_router(None))
    response = TestClient(app).get("/api/control/knowledge/status")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_not_ready"


def test_candidate_list_requires_database_admin() -> None:
    missing_client, _ = client_for(None)
    normal_client, _ = client_for(actor("normal_friend"))

    assert missing_client.get("/api/control/knowledge/candidates", headers=ADMIN_HEADERS).status_code == 401
    assert normal_client.get("/api/control/knowledge/candidates", headers=ADMIN_HEADERS).status_code == 403


def test_admin_can_list_and_approve_candidate_without_source_identifier() -> None:
    client, repository = client_for()
    candidate_id = seed_candidate(repository)

    listed = client.get("/api/control/knowledge/candidates", headers=ADMIN_HEADERS)
    approved = client.post(
        f"/api/control/knowledge/candidates/{candidate_id}/decision",
        headers=ADMIN_HEADERS,
        json={"kind": "approve", "reason": "reviewed", "supersede_conflicts": False},
    )

    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["id"] == candidate_id
    assert "source_id" not in item
    assert "idempotency_key" not in item
    assert approved.status_code == 200
    assert approved.json()["record_id"]


def test_repeat_decision_returns_conflict_and_missing_returns_not_found() -> None:
    client, repository = client_for()
    candidate_id = seed_candidate(repository)
    payload = {"kind": "approve", "reason": "reviewed"}

    assert client.post(
        f"/api/control/knowledge/candidates/{candidate_id}/decision",
        headers=ADMIN_HEADERS, json=payload,
    ).status_code == 200
    repeated = client.post(
        f"/api/control/knowledge/candidates/{candidate_id}/decision",
        headers=ADMIN_HEADERS, json=payload,
    )
    missing = client.post(
        "/api/control/knowledge/candidates/missing/decision",
        headers=ADMIN_HEADERS, json=payload,
    )

    assert repeated.status_code == 409
    assert missing.status_code == 404
