from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import os
import platform as platform_module
import random
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings
from app.core.security import redact_secrets
from app.head.contracts import (
    CausalHypothesis,
    HeadEventContext,
    WorldEntity,
    WorldEvent,
    WorldRelation,
)
from app.head.state import build_head_state
from app.head.world_model import build_head_world_model, project_head_world_model
from app.head.world_model_store import (
    decode_head_world_model,
    encode_head_world_model,
    load_head_world_model,
    save_head_world_model,
)
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import build_self_state
from app.mind.social_state import build_social_state
from app.persona.relationship_context import DEFAULT_RELATIONSHIP_CONTEXT
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger, text_hash
from app.storage.chat_repository import JsonlChatRepository
from app.world.context import WorldContextProjection


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "world-model-stress"
STRESS_PROFILES: dict[str, dict[str, int]] = {
    "smoke": {
        "graph_iterations": 10,
        "decision_iterations": 40,
        "persistence_users": 8,
        "snapshots_per_user": 3,
        "persistence_concurrency": 4,
        "chat_requests": 20,
        "chat_concurrency": 4,
    },
    "high": {
        "graph_iterations": 3_000,
        "decision_iterations": 40_000,
        "persistence_users": 128,
        "snapshots_per_user": 8,
        "persistence_concurrency": 32,
        "chat_requests": 800,
        "chat_concurrency": 32,
    },
}


class OfflineTextClient:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        await asyncio.sleep(0)
        return "我会依据当前可验证的信息回答。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        self.calls += 1
        await asyncio.sleep(0)
        yield "我会依据当前可验证的信息回答。"


class MixedWorldContextProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection:
        self.calls += 1
        await asyncio.sleep(0)
        marker = user_input.split("|", 1)[0]
        if marker == "ready":
            return WorldContextProjection(
                status="ready",
                tool_intent="weather_current",
                rendered_text="Synthetic verified weather evidence for offline stress testing.",
                item_count=1,
                source_ids=("offline-stress",),
            )
        if marker in {"needs_location", "conflicted", "unavailable"}:
            return WorldContextProjection(
                status=marker,
                tool_intent="weather_current",
                conflict_count=1 if marker == "conflicted" else 0,
            )
        return WorldContextProjection(status="not_requested", tool_intent="none")


def _full_graph_inputs(now: dt.datetime) -> tuple[
    tuple[WorldEntity, ...],
    tuple[WorldRelation, ...],
    tuple[WorldEvent, ...],
    tuple[CausalHypothesis, ...],
]:
    entities = tuple(
        WorldEntity(f"entity-{index:02d}", "synthetic", f"Synthetic entity {index:02d}")
        for index in range(64)
    )
    relations = tuple(
        WorldRelation(
            relation_id=f"relation-{index:03d}",
            subject_id=f"entity-{index // 2:02d}",
            predicate=f"stress_edge_{index % 2}",
            object_id=f"entity-{(index + 1) % 64:02d}",
            source_id="offline-stress",
            valid_from=(now - dt.timedelta(hours=1)).isoformat(),
            valid_until=None,
            confidence=0.9,
        )
        for index in range(128)
    )
    events = tuple(
        WorldEvent(
            event_id=f"event-{index:03d}",
            event_type="synthetic_event",
            actor_ids=(f"entity-{index % 64:02d}",),
            occurred_at=(now - dt.timedelta(seconds=index)).isoformat(),
            source_id="offline-stress",
            summary=f"Synthetic bounded event {index:03d}",
            confidence=0.9,
        )
        for index in range(128)
    )
    hypotheses = tuple(
        CausalHypothesis(
            hypothesis_id=f"hypothesis-{index:02d}",
            cause_event_id=f"event-{index * 2:03d}",
            effect_event_id=f"event-{index * 2 + 1:03d}",
            rationale=f"Synthetic causal hypothesis {index:02d}",
            confidence=0.6,
            evidence_ids=(f"event-{index * 2:03d}",),
            confirmed=False,
        )
        for index in range(64)
    )
    return entities, relations, events, hypotheses


def _snapshot_model(user_index: int, version: int, now: dt.datetime):
    entities = (
        WorldEntity("subject", "synthetic_user", f"stress-user-{user_index}-v{version}"),
        WorldEntity("service", "synthetic_service", "offline-service"),
    )
    events = (
        WorldEvent(
            event_id="cause",
            event_type="synthetic_change",
            actor_ids=("subject",),
            occurred_at=(now - dt.timedelta(seconds=2)).isoformat(),
            source_id="offline-stress",
            summary=f"Synthetic input version {version}",
            confidence=0.9,
        ),
        WorldEvent(
            event_id="effect",
            event_type="synthetic_result",
            actor_ids=("service",),
            occurred_at=(now - dt.timedelta(seconds=1)).isoformat(),
            source_id="offline-stress",
            summary=f"Synthetic output version {version}",
            confidence=0.9,
        ),
    )
    return build_head_world_model(
        entities=entities,
        relations=(
            WorldRelation(
                relation_id="uses",
                subject_id="subject",
                predicate="uses_service",
                object_id="service",
                source_id="offline-stress",
                valid_from=(now - dt.timedelta(minutes=1)).isoformat(),
                valid_until=None,
                confidence=0.9,
            ),
        ),
        events=events,
        causal_hypotheses=(
            CausalHypothesis(
                "causal",
                "cause",
                "effect",
                f"Synthetic version {version} hypothesis",
                0.6,
                ("cause",),
                False,
            ),
        ),
        now=now,
    )


def _latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {key: 0.0 for key in ("min", "mean", "p50", "p95", "p99", "max")}
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        index = max(0, math.ceil(len(ordered) * fraction) - 1)
        return ordered[index]

    return {
        "min": round(ordered[0], 3),
        "mean": round(statistics.fmean(ordered), 3),
        "p50": round(percentile(0.50), 3),
        "p95": round(percentile(0.95), 3),
        "p99": round(percentile(0.99), 3),
        "max": round(ordered[-1], 3),
    }


def _base_phase(operations: int, duration: float, latencies: list[float]) -> dict[str, Any]:
    return {
        "operations": operations,
        "duration_seconds": round(duration, 3),
        "throughput_per_second": round(operations / duration, 2) if duration else 0.0,
        "latency_ms": _latency_summary(latencies),
        "errors": 0,
        "integrity_errors": 0,
        "semantic_errors": 0,
        "error_samples": [],
    }


def _add_error(phase: dict[str, Any], exc: BaseException | str, *, kind: str = "errors") -> None:
    phase[kind] += 1
    if len(phase["error_samples"]) < 8:
        message = str(exc) if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        phase["error_samples"].append(redact_secrets(message)[:300])


def _run_world_graph(iterations: int, now: dt.datetime) -> dict[str, Any]:
    inputs = _full_graph_inputs(now)
    latencies: list[float] = []
    started = time.perf_counter()
    phase = _base_phase(iterations, 0.0, latencies)
    encoded_bytes = 0
    projection_items = 0
    for _ in range(iterations):
        item_started = time.perf_counter()
        try:
            model = build_head_world_model(
                entities=inputs[0],
                relations=inputs[1],
                events=inputs[2],
                causal_hypotheses=inputs[3],
                now=now,
            )
            encoded = encode_head_world_model(model)
            restored = decode_head_world_model(encoded)
            projection = project_head_world_model(restored, now=now)
            encoded_bytes += len(encoded.encode("utf-8"))
            projection_items += len(projection)
            counts = (
                len(restored.entities),
                len(restored.relations),
                len(restored.events),
                len(restored.causal_hypotheses),
            )
            if counts != (64, 128, 128, 64) or encode_head_world_model(restored) != encoded:
                _add_error(phase, f"round-trip mismatch: counts={counts}", kind="integrity_errors")
        except Exception as exc:
            _add_error(phase, exc)
        latencies.append((time.perf_counter() - item_started) * 1000)
    duration = time.perf_counter() - started
    phase.update(_base_phase(iterations, duration, latencies) | {
        "errors": phase["errors"],
        "integrity_errors": phase["integrity_errors"],
        "semantic_errors": phase["semantic_errors"],
        "error_samples": phase["error_samples"],
    })
    phase["encoded_megabytes"] = round(encoded_bytes / 1024 / 1024, 2)
    phase["projection_items"] = projection_items
    phase["graph_capacity"] = {
        "entities": 64,
        "relations": 128,
        "events": 128,
        "causal_hypotheses": 64,
    }
    return phase


def _decision_cases() -> tuple[tuple[str, tuple[str, ...], str, str], ...]:
    return (
        ("你好", (), DEFAULT_RELATIONSHIP_CONTEXT.role, "direct_response"),
        (
            "查询实时世界信息",
            ("world_input_required:weather_current",),
            DEFAULT_RELATIONSHIP_CONTEXT.role,
            "world_requires_input",
        ),
        (
            "查询实时世界信息",
            ("world_evidence_unavailable:weather_current",),
            DEFAULT_RELATIONSHIP_CONTEXT.role,
            "world_evidence_unavailable",
        ),
        (
            "查询实时世界信息",
            ("world_evidence_uncertain:weather_current",),
            DEFAULT_RELATIONSHIP_CONTEXT.role,
            "world_evidence_uncertain",
        ),
        ("普通请求", (), "blocked", "relationship_blocked"),
    )


def _run_head_decision(iterations: int, now: dt.datetime, seed: int) -> dict[str, Any]:
    cases = list(_decision_cases())
    random.Random(seed).shuffle(cases)
    snapshot = _snapshot_model(0, 0, now)
    world_model = build_head_world_model(
        entities=snapshot.entities,
        relations=snapshot.relations,
        events=snapshot.events,
        now=now,
    )
    latencies: list[float] = []
    reasons: Counter[str] = Counter()
    started = time.perf_counter()
    phase = _base_phase(iterations, 0.0, latencies)
    for index in range(iterations):
        user_input, uncertainties, relationship_role, expected_reason = cases[index % len(cases)]
        item_started = time.perf_counter()
        try:
            conversation = build_conversation_state(user_input=user_input, recent_messages=[])
            state = build_head_state(
                subject_id=f"decision-user-{index % 128}",
                user_input=user_input,
                relationship_role=relationship_role,
                conversation=conversation,
                self_state=build_self_state(conversation),
                social_state=build_social_state(
                    relationship=DEFAULT_RELATIONSHIP_CONTEXT,
                    conversation=conversation,
                    recent_messages=[],
                    user_input=user_input,
                ),
                recent_messages=[],
                event_context=HeadEventContext(world_model=world_model),
                additional_uncertainties=uncertainties,
            )
            reasons[state.decision.reason] += 1
            selected = state.plan.candidates[state.plan.selected_index]
            if selected.reason != state.decision.reason or state.decision.reason != expected_reason:
                _add_error(
                    phase,
                    f"decision mismatch: expected={expected_reason}; observed={state.decision.reason}",
                    kind="semantic_errors",
                )
        except Exception as exc:
            _add_error(phase, exc)
        latencies.append((time.perf_counter() - item_started) * 1000)
    duration = time.perf_counter() - started
    counters = {key: phase[key] for key in ("errors", "integrity_errors", "semantic_errors")}
    samples = phase["error_samples"]
    phase.update(_base_phase(iterations, duration, latencies))
    phase.update(counters)
    phase["error_samples"] = samples
    phase["decision_reasons"] = dict(sorted(reasons.items()))
    return phase


async def _save_user_snapshots(
    repository: JsonlChatRepository,
    user_index: int,
    snapshots: int,
    now: dt.datetime,
) -> list[float]:
    latencies = []
    for version in range(snapshots):
        started = time.perf_counter()
        await save_head_world_model(
            repository,
            user_id=f"stress-user-{user_index}",
            session_id=f"stress-session-{user_index}",
            source_message_id=None,
            model=_snapshot_model(user_index, version, now),
            allow_write=True,
        )
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def _run_persistence(config: dict[str, int], runtime_root: Path, now: dt.datetime) -> dict[str, Any]:
    users = config["persistence_users"]
    snapshots = config["snapshots_per_user"]
    operations = users * snapshots
    repository = JsonlChatRepository(runtime_root / "persistence-storage")
    latencies: list[float] = []
    started = time.perf_counter()
    phase = _base_phase(operations, 0.0, latencies)
    with ThreadPoolExecutor(max_workers=config["persistence_concurrency"]) as executor:
        futures = {
            executor.submit(
                asyncio.run,
                _save_user_snapshots(repository, user_index, snapshots, now),
            ): user_index
            for user_index in range(users)
        }
        for future in as_completed(futures):
            try:
                latencies.extend(future.result())
            except Exception as exc:
                _add_error(phase, exc)

    parsed_records: list[dict[str, Any]] = []
    jsonl_line_count = 0
    invalid_jsonl_lines = 0
    nul_bytes = 0
    if repository.memories_path.exists():
        raw_bytes = repository.memories_path.read_bytes()
        nul_bytes = raw_bytes.count(b"\x00")
        lines = raw_bytes.decode("utf-8").splitlines()
        jsonl_line_count = len(lines)
        for line_number, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
                parsed_records.append(record)
                if record.get("content_hash") != text_hash(str(record.get("content", ""))):
                    _add_error(phase, f"content hash mismatch at line {line_number}", kind="integrity_errors")
            except (TypeError, json.JSONDecodeError) as exc:
                invalid_jsonl_lines += 1
                _add_error(phase, f"invalid JSONL at line {line_number}: {exc}", kind="integrity_errors")
    if len(parsed_records) != operations:
        _add_error(
            phase,
            f"snapshot count mismatch: expected={operations}; observed={len(parsed_records)}",
            kind="integrity_errors",
        )

    records_by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in parsed_records:
        records_by_user[str(record.get("user_id"))].append(record)
    users_verified = 0
    for user_index in range(users):
        user_id = f"stress-user-{user_index}"
        records = records_by_user.get(user_id, [])
        if len(records) != snapshots:
            _add_error(
                phase,
                f"user snapshot mismatch: user={user_id}; expected={snapshots}; observed={len(records)}",
                kind="integrity_errors",
            )
            continue
        try:
            restored = asyncio.run(load_head_world_model(repository, user_id=user_id))
            expected_name = f"stress-user-{user_index}-v{snapshots - 1}"
            names_by_id = {entity.entity_id: entity.name for entity in restored.entities}
            if names_by_id.get("subject") != expected_name:
                _add_error(
                    phase,
                    f"user isolation mismatch: user={user_id}; expected={expected_name}",
                    kind="integrity_errors",
                )
                continue
            users_verified += 1
        except Exception as exc:
            _add_error(phase, exc, kind="integrity_errors")

    duration = time.perf_counter() - started
    counters = {key: phase[key] for key in ("errors", "integrity_errors", "semantic_errors")}
    samples = phase["error_samples"]
    phase.update(_base_phase(operations, duration, latencies))
    phase.update(counters)
    phase["error_samples"] = samples
    phase["users_verified"] = users_verified
    phase["snapshots_per_user"] = snapshots
    phase["jsonl_bytes"] = repository.memories_path.stat().st_size if repository.memories_path.exists() else 0
    phase["jsonl_line_count"] = jsonl_line_count
    phase["invalid_jsonl_lines"] = invalid_jsonl_lines
    phase["nul_bytes"] = nul_bytes
    phase["missing_valid_records"] = max(0, operations - len(parsed_records))
    return phase


async def _corruption_recovery(repository: JsonlChatRepository, now: dt.datetime) -> tuple[bool, bool]:
    valid = _snapshot_model(999, 1, now)
    await save_head_world_model(
        repository,
        user_id="recovery-user",
        session_id="recovery-session",
        source_message_id=None,
        model=valid,
        allow_write=True,
    )
    await repository.save_memory(
        user_id="recovery-user",
        session_id="recovery-session",
        memory_type="head_world_model",
        content="{invalid-world-model",
        confidence=1.0,
    )
    restored = await load_head_world_model(repository, user_id="recovery-user")
    isolated = await load_head_world_model(repository, user_id="recovery-other-user")
    names_by_id = {entity.entity_id: entity.name for entity in restored.entities}
    recovered = names_by_id.get("subject") == "stress-user-999-v1"
    return recovered, not isolated.entities


def _run_corruption_recovery(runtime_root: Path, now: dt.datetime) -> dict[str, Any]:
    repository = JsonlChatRepository(runtime_root / "corruption-storage")
    started = time.perf_counter()
    phase = _base_phase(4, 0.0, [])
    try:
        recovered, isolated = asyncio.run(_corruption_recovery(repository, now))
        if not recovered:
            _add_error(phase, "latest corrupt snapshot did not fall back", kind="integrity_errors")
        if not isolated:
            _add_error(phase, "corruption recovery leaked another user", kind="integrity_errors")
    except Exception as exc:
        _add_error(phase, exc)
    duration = time.perf_counter() - started
    counters = {key: phase[key] for key in ("errors", "integrity_errors", "semantic_errors")}
    samples = phase["error_samples"]
    phase.update(_base_phase(4, duration, []))
    phase.update(counters)
    phase["error_samples"] = samples
    phase["fallback_verified"] = not phase["integrity_errors"] and not phase["errors"]
    return phase


async def _run_chat_requests(
    service: ChatService,
    requests: int,
    concurrency: int,
) -> tuple[list[float], Counter[str], list[str]]:
    semaphore = asyncio.Semaphore(concurrency)
    statuses = ("ready", "needs_location", "conflicted", "unavailable", "ordinary")
    latencies: list[float] = []
    responses: Counter[str] = Counter()
    errors: list[str] = []

    async def run_one(index: int) -> None:
        marker = statuses[index % len(statuses)]
        started = time.perf_counter()
        try:
            async with semaphore:
                response = await service.reply(
                    f"{marker}|offline stress request {index}",
                    user_id=f"chat-user-{index}",
                    session_id=f"chat-session-{index}",
                )
            expected_guard = marker in {"needs_location", "conflicted", "unavailable"}
            observed_guard = response.model == "world-guard"
            if expected_guard != observed_guard:
                errors.append(
                    f"world guard mismatch: marker={marker}; model={response.model}"
                )
            responses["world_guard" if observed_guard else "provider"] += 1
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            latencies.append((time.perf_counter() - started) * 1000)

    await asyncio.gather(*(run_one(index) for index in range(requests)))
    return latencies, responses, errors


def _validate_jsonl_directory(root: Path) -> list[str]:
    errors = []
    for path in root.rglob("*.jsonl"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSONL: {path.name}:{line_number}: {exc}")
    return errors


def _run_chat_service(config: dict[str, int], runtime_root: Path) -> dict[str, Any]:
    requests = config["chat_requests"]
    storage_root = runtime_root / "chat-storage"
    audit_path = storage_root / "audit.jsonl"
    client = OfflineTextClient()
    world_provider = MixedWorldContextProvider()
    settings = replace(
        load_settings(),
        storage_backend="jsonl",
        jsonl_storage_dir=str(storage_root),
        text_provider_order="deepseek",
        text_provider_retries=0,
        world_awareness_enabled=False,
    )
    service = ChatService(
        settings,
        client=client,
        repository=JsonlChatRepository(storage_root),
        audit_logger=ModelInvocationAuditLogger(audit_path),
        world_context_provider=world_provider,
    )
    started = time.perf_counter()
    latencies, responses, semantic_messages = asyncio.run(
        _run_chat_requests(service, requests, config["chat_concurrency"])
    )
    duration = time.perf_counter() - started
    phase = _base_phase(requests, duration, latencies)
    for message in semantic_messages:
        _add_error(phase, message, kind="semantic_errors")
    for message in _validate_jsonl_directory(storage_root):
        _add_error(phase, message, kind="integrity_errors")
    phase["provider_calls"] = client.calls
    phase["world_provider_calls"] = world_provider.calls
    phase["world_guard_responses"] = responses["world_guard"]
    phase["provider_responses"] = responses["provider"]
    return phase


def _build_report(result: dict[str, Any], result_path: Path) -> str:
    lines = [
        "# HeadCore World Model Stress Report",
        "",
        f"- Status: **{result['status']}**",
        f"- Profile: `{result['profile']}`",
        f"- Seed: `{result['seed']}`",
        f"- Duration: `{result['duration_seconds']:.3f}s`",
        f"- Peak traced Python memory: `{result['totals']['peak_python_memory_mib']:.2f} MiB`",
        "- No real network, model, database, camera, or user-data call was made.",
        "- Timing is observational; machine-dependent latency does not decide PASS/FAIL.",
        "",
        "## Phase Results",
        "",
        "| Phase | Operations | Throughput/s | P50 ms | P95 ms | P99 ms | Errors | Integrity | Semantic |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, phase in result["phases"].items():
        latency = phase["latency_ms"]
        lines.append(
            f"| {name} | {phase['operations']} | {phase['throughput_per_second']:.2f} | "
            f"{latency['p50']:.3f} | {latency['p95']:.3f} | {latency['p99']:.3f} | "
            f"{phase['errors']} | {phase['integrity_errors']} | {phase['semantic_errors']} |"
        )
    lines.extend(
        [
            "",
            "## Integrity Summary",
            "",
            f"- Full-capacity graph cycles: `{result['phases']['world_graph']['operations']}`.",
            f"- Isolated users verified: `{result['phases']['persistence']['users_verified']}`.",
            f"- Snapshots per user: `{result['phases']['persistence']['snapshots_per_user']}`.",
            f"- Corrupt-snapshot fallback verified: `{str(result['phases']['corruption_recovery']['fallback_verified']).lower()}`.",
            f"- Chat world-guard responses: `{result['phases']['chat_service']['world_guard_responses']}`.",
            f"- Offline text-provider calls: `{result['phases']['chat_service']['provider_calls']}`.",
            "",
            "## Error Samples",
            "",
        ]
    )
    samples = [
        f"- `{name}`: {sample}"
        for name, phase in result["phases"].items()
        for sample in phase["error_samples"]
    ]
    lines.extend(samples or ["- None."])
    lines.extend(["", f"Raw result: `{result_path.name}`", ""])
    return "\n".join(lines)


def run_stress(
    *,
    profile: str = "high",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    seed: int = 20260729,
) -> Path:
    if profile not in STRESS_PROFILES:
        raise ValueError(f"unknown stress profile: {profile}")
    config = dict(STRESS_PROFILES[profile])
    started_at = dt.datetime.now(dt.UTC)
    run_id = started_at.astimezone().strftime("%Y-%m-%d_%H%M%S_%f")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    tracemalloc.start()
    overall_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="hutao-world-model-stress-") as temp_dir:
        runtime_root = Path(temp_dir)
        phases = {
            "world_graph": _run_world_graph(config["graph_iterations"], started_at),
            "head_decision": _run_head_decision(
                config["decision_iterations"], started_at, seed
            ),
            "persistence": _run_persistence(config, runtime_root, started_at),
            "corruption_recovery": _run_corruption_recovery(runtime_root, started_at),
            "chat_service": _run_chat_service(config, runtime_root),
        }
    duration = time.perf_counter() - overall_started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    totals = {
        "operations": sum(phase["operations"] for phase in phases.values()),
        "errors": sum(phase["errors"] for phase in phases.values()),
        "integrity_errors": sum(phase["integrity_errors"] for phase in phases.values()),
        "semantic_errors": sum(phase["semantic_errors"] for phase in phases.values()),
        "peak_python_memory_mib": round(peak_bytes / 1024 / 1024, 2),
    }
    status = (
        "PASS"
        if not totals["errors"]
        and not totals["integrity_errors"]
        and not totals["semantic_errors"]
        else "FAIL"
    )
    result: dict[str, Any] = {
        "status": status,
        "profile": profile,
        "seed": seed,
        "started_at": started_at.isoformat(),
        "duration_seconds": round(duration, 3),
        "config": config,
        "environment": {
            "python": platform_module.python_version(),
            "platform": platform_module.platform(),
            "cpu_count": os.cpu_count(),
        },
        "external_calls": 0,
        "totals": totals,
        "phases": phases,
    }
    result_path = output_dir / "world-model-stress-result.json"
    report_path = output_dir / "world-model-stress-report.md"
    result_path.write_text(
        redact_secrets(json.dumps(result, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report_path.write_text(
        redact_secrets(_build_report(result, result_path)),
        encoding="utf-8",
    )
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded offline stress tests against the HeadCore world model."
    )
    parser.add_argument("--profile", choices=tuple(STRESS_PROFILES), default="high")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--seed", type=int, default=20260729)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_stress(profile=args.profile, output_root=args.output_root, seed=args.seed)
    result = json.loads(
        report_path.with_name("world-model-stress-result.json").read_text(encoding="utf-8")
    )
    print(f"World-model stress report: {report_path}")
    print(
        f"Status: {result['status']}; operations: {result['totals']['operations']}; "
        f"errors: {result['totals']['errors']}; integrity: {result['totals']['integrity_errors']}; "
        f"semantic: {result['totals']['semantic_errors']}"
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
