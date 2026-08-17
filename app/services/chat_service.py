from __future__ import annotations

import asyncio
import time
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Protocol

from app.core.config import Settings
from app.core.security import redact_secrets
from app.head import (
    HeadState,
    build_head_state,
    cognitive_facts_from_world_result,
    load_head_event_context,
    record_head_events,
    record_head_response_event,
    render_continuity_timeline,
    render_head_projection,
    save_cognitive_fact,
)
from app.dialogue.expression_policy import sanitize_visible_reply
from app.expression.core_api import STREAM_TRUNCATED_MARKER
from app.world.tool_request import (
    TOOL_DENIED_REPLY,
    WorldToolRequest,
    parse_tool_request,
    render_tool_protocol_instruction,
)
from app.head.self_consistency import evaluate_self_consistency
from app.head.self_profile import SelfProfile, render_self_profile_projection
from app.head.self_profile_store import load_self_profile
from app.head.cognitive_facts import resolve_cognitive_facts
from app.head.world_state import (
    HeadWorldState,
    build_head_world_state,
    render_head_world_state,
    world_state_uncertainties,
)
from app.mind.conversation_state import ConversationState
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import SelfState
from app.mind.self_state import build_self_state
from app.mind.social_state import SocialState
from app.mind.social_state import build_social_state
from app.persona.memory_policy import build_memory_policy
from app.persona.memory_service import apply_memory_policy, load_memory_context
from app.persona.memory_service import extract_memory_terms
from app.persona.persona_prompt_builder import build_persona_prompt
from app.persona.platform_router import select_platform_persona
from app.persona.profile_registry import resolve_persona_profile
from app.persona.relationship_context import RelationshipContext
from app.persona.relationship_context import resolve_relationship_context
from app.persona.repetition_policy import build_repetition_signal
from app.persona.scene_classifier import classify_scene
from app.persona.turn_taking import classify_turn_taking
from app.persona_management.contracts import BindingContext, PersonaRuntimeProjection
from app.persona_management.projection import render_runtime_projection
from app.persona_management.sandbox import (
    SandboxPersonaRuntimeProjection,
    render_sandbox_persona_projection,
)
from app.providers import (
    ProviderCapability,
    ProviderId,
    ProviderRegistry,
    ProviderRouter,
    RoutingDecision,
    RoutingPolicy,
    StreamingRoutingFailed,
    TextRequest,
)
from app.providers.deepseek import DeepSeekTextProvider
from app.providers.router import RoutingFailed
from app.knowledge.runtime import (
    MemoryProjectionProvider,
    MemoryProjectionRequest,
    render_memory_projection,
)
from app.schemas import ChatResponse
from app.services.model_audit import ModelInvocationAuditLogger, text_hash
from app.services.model_client import DeepSeekClient
from app.services.response_evaluator import (
    EVALUATOR_MODEL,
    EVALUATOR_PROVIDER,
    ResponseEvaluator,
    is_identity_question,
    is_low_trust_boundary_context,
    is_self_harm_directive_bait,
    is_unconfirmed_relationship_claim,
)
from app.camera.attention import camera_clarification_instruction, select_camera_context
from app.camera.evidence_store import CameraContextProvider
from app.storage.chat_repository import ChatRepository
from app.storage.chat_repository import MessageRecord
from app.storage.chat_repository import SessionRecord
from app.storage.repository_factory import create_chat_repository
from app.world.context import WorldContextBuildResult, WorldContextProjection


CRITICAL_STREAM_REASONS = frozenset(
    {
        "claims_ai_identity",
        "cross_persona_identity_leak",
        "hostile_or_humiliating_reply",
        "repeats_self_harm_directive",
        "death_topic_misuse",
        "death_joke_wrong_scene",
        "repeats_unconfirmed_relationship_term",
        "low_trust_intimacy_escalation",
        "repeats_revoked_memory",
        "fabricated_real_world_experience",
    }
)


BASE_SYSTEM_PROMPT = "\n".join(
    [
        "You are producing a Chinese private-chat reply through the typed persona runtime.",
        "The only built-in Self profile is hutao_v1; every platform uses the same stable identity.",
        "The active mode controls playfulness, warmth, rigor, pacing, and response length.",
        "Professional tasks prioritize correctness and completeness over catchphrases or persona anchors.",
        "Do not mix profile identities inside one platform conversation.",
        "Reply in Chinese.",
    ]
)


class ChatModelClient(Protocol):
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        pass

    async def stream_chat(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        pass


class PersonaProjectionProvider(Protocol):
    async def get_runtime_projection(
        self, profile_id: str, context: BindingContext
    ) -> PersonaRuntimeProjection: ...


class SandboxPersonaProjectionProvider(Protocol):
    async def get_runtime_projection(
        self,
        persona_id: str,
        *,
        owner_id: str,
    ) -> SandboxPersonaRuntimeProjection: ...


class WorldContextProvider(Protocol):
    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection: ...


class WorldEvidenceContextProvider(WorldContextProvider, Protocol):
    async def build_context_with_evidence(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextBuildResult: ...


@dataclass(frozen=True)
class PreparedChat:
    started_at: float
    session: SessionRecord
    user_message: MessageRecord
    user_input: str
    user_id: str
    prompt_text: str
    system_prompt: str
    user_prompt: str
    input_source: str
    input_quality_passed: bool
    input_quality_reasons: list[str]
    input_emotion: str | None
    input_emotion_source: str | None
    input_emotion_confidence: float | None
    relationship_context: RelationshipContext
    conversation_state: ConversationState
    self_state: SelfState
    social_state: SocialState
    head_state: HeadState
    allow_head_event_write: bool
    persona_profile_id: str
    persona_profile_version: int
    persona_profile_fallback_reason: str
    persona_mode: str
    knowledge_projection_status: str
    knowledge_projection_count: int
    persona_management_projection_status: str
    sandbox_persona_id: str | None
    sandbox_persona_name: str | None
    sandbox_persona_status: str
    world_context_status: str
    world_context_item_count: int
    world_context_conflict_count: int
    world_tool_intent: str
    head_world_state: HeadWorldState
    world_grounding_facts: tuple[tuple[str, str], ...]
    head_runtime_origin: str
    self_profile: SelfProfile | None


def _camera_context_block(
    provider: CameraContextProvider | None,
    *,
    user_input: str,
    relationship_role: str,
) -> str:
    """Render the L1 camera-attention block for the current turn, or "".

    Only temporally-confirmed allowlisted labels reach the prompt, never frames,
    and the block forbids inferring emotion/identity/intent from them.
    """
    if provider is None or relationship_role == "blocked":
        return ""
    try:
        context = provider.latest_context()
    except Exception:
        return ""
    selection = select_camera_context(user_input, context)
    if selection.needs_clarification:
        return camera_clarification_instruction()
    if not selection.text:
        return ""
    return (
        "[以下画面线索只用于回答画面相关问题；不得据此推断情绪、身份或意图："
        + selection.text
        + "]"
    )


class ChatService:
    def __init__(
        self,
        settings: Settings,
        client: ChatModelClient | None = None,
        audit_logger: ModelInvocationAuditLogger | None = None,
        repository: ChatRepository | None = None,
        evaluator: ResponseEvaluator | None = None,
        memory_projection_provider: MemoryProjectionProvider | None = None,
        persona_projection_provider: PersonaProjectionProvider | None = None,
        sandbox_persona_projection_provider: SandboxPersonaProjectionProvider | None = None,
        world_context_provider: WorldContextProvider | None = None,
        camera_context_provider: CameraContextProvider | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or DeepSeekClient(settings)
        self.provider_registry = ProviderRegistry()
        self.provider_registry.register(DeepSeekTextProvider(self.client))
        self.provider_router = ProviderRouter(self.provider_registry)
        self.audit_logger = audit_logger or ModelInvocationAuditLogger()
        self.repository = repository or create_chat_repository(settings)
        self.evaluator = evaluator or ResponseEvaluator()
        self.memory_projection_provider = memory_projection_provider
        self.persona_projection_provider = persona_projection_provider
        self.sandbox_persona_projection_provider = sandbox_persona_projection_provider
        self.world_context_provider = world_context_provider
        self.camera_context_provider = camera_context_provider
        if self.world_context_provider is None and settings.world_awareness_enabled:
            from app.world.brain import WorldBrainCoordinator
            from app.world.runtime import build_world_runtime

            self.world_context_provider = WorldBrainCoordinator(build_world_runtime(settings))

    async def reply(
        self,
        user_input: str,
        *,
        session_id: str = "default",
        user_id: str = "default-user",
        input_source: str = "text",
        input_quality_passed: bool = True,
        input_quality_reasons: list[str] | None = None,
        input_emotion: str | None = None,
        input_emotion_source: str | None = None,
        input_emotion_confidence: float | None = None,
        platform: str | None = None,
        platform_user_id: str | None = None,
        platform_group_id: str | None = None,
        response_style_instruction: str | None = None,
        sandbox_persona_id: str | None = None,
        head_runtime_origin: str = "legacy_direct",
    ) -> ChatResponse:
        prepared = await self._prepare_chat(
            user_input=user_input,
            session_id=session_id,
            user_id=user_id,
            input_source=input_source,
            input_quality_passed=input_quality_passed,
            input_quality_reasons=input_quality_reasons,
            input_emotion=input_emotion,
            input_emotion_source=input_emotion_source,
            input_emotion_confidence=input_emotion_confidence,
            platform=platform,
            platform_user_id=platform_user_id,
            platform_group_id=platform_group_id,
            response_style_instruction=response_style_instruction,
            sandbox_persona_id=sandbox_persona_id,
            head_runtime_origin=head_runtime_origin,
        )
        if prepared.relationship_context.role == "blocked":
            return ChatResponse(
                text="这边暂时不接待。",
                provider="local",
                model="relationship-policy",
                used_live_api=False,
                fallback_used=True,
                error="blocked contact",
            )
        world_guard_text = _world_guard_reply(prepared)
        if world_guard_text:
            response = ChatResponse(
                text=world_guard_text,
                provider="local",
                model="world-guard",
                used_live_api=False,
                fallback_used=True,
            )
            await self._write_records(
                started_at=prepared.started_at,
                prompt_text=prepared.prompt_text,
                response=response,
                session_id=prepared.session.id,
                user_id=user_id,
                user_input=user_input,
                persona_profile=prepared.persona_profile_id,
                head_state=prepared.head_state,
                allow_head_event_write=prepared.allow_head_event_write,
                request_metadata_json={
                    "world_guard": "true",
                    **build_request_metadata(prepared),
                },
            )
            return response
        try:
            system_prompt = prepared.system_prompt
            if self.world_context_provider is not None:
                system_prompt = system_prompt + "\n" + render_tool_protocol_instruction()
            decision = await self.provider_router.route(
                ProviderCapability.TEXT,
                self._text_routing_policy(),
                lambda provider: provider.generate_text(
                    TextRequest(system_prompt, prepared.user_prompt)
                ),
            )
            text = sanitize_visible_reply(decision.value)
            live_repair_attempted = False
            repair_decision: RoutingDecision[str] | None = None
            evaluation = self.evaluator.evaluate(
                user_input=user_input,
                response_text=text,
                fallback_used=False,
                persona_profile=prepared.persona_profile_id,
                world_facts=prepared.world_grounding_facts,
            )
            self_conflicts = evaluate_self_consistency(
                prepared.self_profile,
                user_input=user_input,
                response_text=text,
            )
            if self_conflicts:
                await self._record_self_conflicts(
                    user_id=user_id,
                    session_id=prepared.session.id,
                    conflicts=self_conflicts,
                )
            if not evaluation.passed or self_conflicts:
                repair_decision = await self._repair_live_response_decision(
                    system_prompt=system_prompt,
                    user_prompt=prepared.user_prompt,
                    user_input=user_input,
                    failed_text=text,
                    reasons=list(dict.fromkeys([*evaluation.reasons, *self_conflicts])),
                )
                live_repair_attempted = True
                if repair_decision:
                    text = sanitize_visible_reply(repair_decision.value)
            world_tool_iteration = 0
            world_tool_status = "none"
            tool_request = parse_tool_request(text)
            if tool_request is not None:
                tool_status, tool_text, tool_denied, tool_decision = await self._run_world_tool_step(
                    tool_request,
                    prepared=prepared,
                    user_input=user_input,
                    platform=platform,
                )
                world_tool_iteration = 1
                world_tool_status = tool_status
                text = tool_text
                if tool_denied:
                    response = ChatResponse(
                        text=text,
                        provider="local",
                        model="world-tool-guard",
                        used_live_api=False,
                        fallback_used=True,
                        error="world_tool:" + tool_status,
                    )
                    await self._write_records(
                        started_at=prepared.started_at,
                        prompt_text=prepared.prompt_text,
                        response=response,
                        session_id=prepared.session.id,
                        user_id=user_id,
                        user_input=user_input,
                        persona_profile=prepared.persona_profile_id,
                        head_state=prepared.head_state,
                        allow_head_event_write=prepared.allow_head_event_write,
                        request_metadata_json={
                            "api_path": "/chat/completions",
                            "live_repair_attempted": str(live_repair_attempted).lower(),
                            "world_tool_iteration": str(world_tool_iteration),
                            "world_tool_status": world_tool_status,
                            **provider_trace_metadata(decision.trace),
                            **build_request_metadata(prepared, include_api_path=False),
                        },
                        world_facts=prepared.world_grounding_facts,
                    )
                    return response
                decision = tool_decision
            response = ChatResponse(
                text=text,
                provider=str(decision.provider_id),
                model=self.settings.model_name,
                used_live_api=True,
            )
            await self._write_records(
                started_at=prepared.started_at,
                prompt_text=prepared.prompt_text,
                response=response,
                session_id=prepared.session.id,
                user_id=user_id,
                user_input=user_input,
                persona_profile=prepared.persona_profile_id,
                head_state=prepared.head_state,
                allow_head_event_write=prepared.allow_head_event_write,
                request_metadata_json={
                    "api_path": "/chat/completions",
                    "live_repair_attempted": str(live_repair_attempted).lower(),
                    "world_tool_iteration": str(world_tool_iteration),
                    "world_tool_status": world_tool_status,
                    **provider_trace_metadata(decision.trace),
                    **(
                        provider_trace_metadata(repair_decision.trace, prefix="repair_")
                        if live_repair_attempted and repair_decision
                        else {}
                    ),
                    **build_request_metadata(prepared, include_api_path=False),
                },
                world_facts=prepared.world_grounding_facts,
            )
            return response
        except Exception as exc:
            error = exc.last_error if isinstance(exc, RoutingFailed) and exc.last_error else exc
            response = self._fallback_response(
                user_input=user_input,
                error=str(error),
                persona_profile=prepared.persona_profile_id,
            )
            trace_metadata = provider_trace_metadata(exc.trace) if isinstance(exc, RoutingFailed) else {}
            await self._write_records(
                started_at=prepared.started_at,
                prompt_text=prepared.prompt_text,
                response=response,
                session_id=prepared.session.id,
                user_id=user_id,
                user_input=user_input,
                persona_profile=prepared.persona_profile_id,
                head_state=prepared.head_state,
                allow_head_event_write=prepared.allow_head_event_write,
                request_metadata_json={**trace_metadata, **build_request_metadata(prepared)},
            )
            return response

    def _text_routing_policy(self) -> RoutingPolicy:
        provider_ids = tuple(
            ProviderId(value)
            for value in self.settings.text_provider_order.split(",")
            if value.strip()
        )
        return RoutingPolicy(
            providers=provider_ids,
            timeout_seconds=self.settings.request_timeout_seconds,
            retries_per_provider=self.settings.text_provider_retries,
            circuit_failure_threshold=self.settings.text_provider_circuit_failure_threshold,
            circuit_recovery_seconds=self.settings.text_provider_circuit_recovery_seconds,
        )

    async def stream_reply(
        self,
        user_input: str,
        *,
        session_id: str = "default",
        user_id: str = "default-user",
        input_source: str = "text",
        input_quality_passed: bool = True,
        input_quality_reasons: list[str] | None = None,
        input_emotion: str | None = None,
        input_emotion_source: str | None = None,
        input_emotion_confidence: float | None = None,
        platform: str | None = None,
        platform_user_id: str | None = None,
        platform_group_id: str | None = None,
        response_style_instruction: str | None = None,
        sandbox_persona_id: str | None = None,
        head_runtime_origin: str = "legacy_direct",
    ) -> AsyncIterator[str]:
        prepared = await self._prepare_chat(
            user_input=user_input,
            session_id=session_id,
            user_id=user_id,
            input_source=input_source,
            input_quality_passed=input_quality_passed,
            input_quality_reasons=input_quality_reasons,
            input_emotion=input_emotion,
            input_emotion_source=input_emotion_source,
            input_emotion_confidence=input_emotion_confidence,
            platform=platform,
            platform_user_id=platform_user_id,
            platform_group_id=platform_group_id,
            response_style_instruction=response_style_instruction,
            sandbox_persona_id=sandbox_persona_id,
            head_runtime_origin=head_runtime_origin,
        )
        if prepared.relationship_context.role == "blocked":
            yield "这边暂时不接待。"
            return
        world_guard_text = _world_guard_reply(prepared)
        if world_guard_text:
            response = ChatResponse(
                text=world_guard_text,
                provider="local",
                model="world-guard",
                used_live_api=False,
                fallback_used=True,
            )
            yield world_guard_text
            await self._write_records(
                started_at=prepared.started_at,
                prompt_text=prepared.prompt_text,
                response=response,
                session_id=prepared.session.id,
                user_id=user_id,
                user_input=user_input,
                persona_profile=prepared.persona_profile_id,
                head_state=prepared.head_state,
                allow_head_event_write=prepared.allow_head_event_write,
                request_metadata_json={
                    "api_path": "/chat/completions",
                    "stream": "true",
                    "world_guard": "true",
                    **build_request_metadata(prepared, include_api_path=False),
                },
                replace_failed_response=False,
            )
            return
        chunks: list[str] = []
        route = self.provider_router.stream(
            ProviderCapability.TEXT,
            self._text_routing_policy(),
            lambda provider: provider.stream_text(
                TextRequest(prepared.system_prompt, prepared.user_prompt)
            ),
        )
        response = ChatResponse(
            text="",
            provider=self.settings.model_provider,
            model=self.settings.model_name,
            used_live_api=True,
        )
        buffer_for_world_grounding = bool(prepared.world_grounding_facts)
        stream_repair_attempted = False
        repair_decision: RoutingDecision[str] | None = None
        stream_truncated = False
        stream_correction_appended = False
        deadline = time.monotonic() + self.settings.text_stream_total_budget_seconds
        iterator = route.__aiter__()
        try:
            try:
                async with asyncio.timeout(self.settings.text_stream_ttft_timeout_seconds):
                    first_chunk = await anext(iterator)
            except StopAsyncIteration:
                first_chunk = None
            except TimeoutError as exc:
                raise RuntimeError(
                    "text stream first token timed out after "
                    f"{self.settings.text_stream_ttft_timeout_seconds:g}s"
                ) from exc
            if first_chunk is None:
                raise RuntimeError("Stream response content is empty.")
            chunks.append(first_chunk)
            if not buffer_for_world_grounding:
                yield first_chunk
            try:
                remaining = deadline - time.monotonic()
                async with asyncio.timeout(max(remaining, 0.001)):
                    async for chunk in iterator:
                        chunks.append(chunk)
                        if not buffer_for_world_grounding:
                            yield chunk
            except TimeoutError:
                stream_truncated = True
            response.text = sanitize_visible_reply("".join(chunks))
            response.provider = str(route.provider_id or self.settings.model_provider)
            if stream_truncated:
                response.error = "text stream exceeded total budget and was truncated"
            elif not response.text:
                raise RuntimeError("Stream response content is empty.")
            if buffer_for_world_grounding:
                evaluation = self.evaluator.evaluate(
                    user_input=user_input,
                    response_text=response.text,
                    fallback_used=False,
                    persona_profile=prepared.persona_profile_id,
                    world_facts=prepared.world_grounding_facts,
                )
                if not evaluation.passed:
                    stream_repair_attempted = True
                    repair_decision = await self._repair_live_response_decision(
                        system_prompt=prepared.system_prompt,
                        user_prompt=prepared.user_prompt,
                        user_input=user_input,
                        failed_text=response.text,
                        reasons=evaluation.reasons,
                    )
                    if repair_decision is not None:
                        response.text = sanitize_visible_reply(repair_decision.value)
                    repaired_evaluation = self.evaluator.evaluate(
                        user_input=user_input,
                        response_text=response.text,
                        fallback_used=False,
                        persona_profile=prepared.persona_profile_id,
                        world_facts=prepared.world_grounding_facts,
                    )
                    if not repaired_evaluation.passed:
                        response.text = self._evaluation_fallback_reply(
                            user_input,
                            persona_profile=prepared.persona_profile_id,
                        )
                        response.used_live_api = False
                        response.fallback_used = True
                        response.error = "Response evaluation failed: " + ",".join(
                            repaired_evaluation.reasons
                        )
                yield response.text
            else:
                if not stream_truncated:
                    evaluation = self.evaluator.evaluate(
                        user_input=user_input,
                        response_text=response.text,
                        fallback_used=False,
                        persona_profile=prepared.persona_profile_id,
                    )
                    self_conflicts = evaluate_self_consistency(
                        prepared.self_profile,
                        user_input=user_input,
                        response_text=response.text,
                    )
                    if self_conflicts:
                        await self._record_self_conflicts(
                            user_id=user_id,
                            session_id=prepared.session.id,
                            conflicts=self_conflicts,
                        )
                    stream_tool_request = parse_tool_request(response.text)
                    if stream_tool_request is not None:
                        response.text = TOOL_DENIED_REPLY
                        response.error = "world_tool:unsupported_stream"
                        stream_correction_appended = True
                        yield TOOL_DENIED_REPLY
                    elif not evaluation.passed or self_conflicts:
                        critical = (set(evaluation.reasons) & CRITICAL_STREAM_REASONS) or set(
                            self_conflicts
                        )
                        if critical:
                            correction = self._evaluation_fallback_reply(
                                user_input,
                                persona_profile=prepared.persona_profile_id,
                            )
                            response.text = response.text + correction
                            response.error = "Response evaluation failed: " + ",".join(
                                evaluation.reasons
                            )
                            stream_correction_appended = True
                            yield correction
                if stream_truncated:
                    yield STREAM_TRUNCATED_MARKER
        except Exception as exc:
            error = exc.last_error if isinstance(exc, RoutingFailed) and exc.last_error else exc
            if (
                isinstance(exc, StreamingRoutingFailed)
                and exc.partial_output
                and chunks
                and not buffer_for_world_grounding
            ):
                stream_truncated = True
                response = ChatResponse(
                    text="".join(chunks).strip(),
                    provider=str(route.provider_id or self.settings.model_provider),
                    model=self.settings.model_name,
                    used_live_api=True,
                    error=redact_secrets(str(error)),
                )
                yield STREAM_TRUNCATED_MARKER
            else:
                fallback = self._fallback_response(
                    user_input=user_input,
                    error=str(error),
                    persona_profile=prepared.persona_profile_id,
                )
                response = fallback
                yield fallback.text
        finally:
            await self._write_records(
                started_at=prepared.started_at,
                prompt_text=prepared.prompt_text,
                response=response,
                session_id=prepared.session.id,
                user_id=user_id,
                user_input=user_input,
                persona_profile=prepared.persona_profile_id,
                head_state=prepared.head_state,
                allow_head_event_write=prepared.allow_head_event_write,
                request_metadata_json={
                    "api_path": "/chat/completions",
                    "stream": "true",
                    "provider_call_type": "stream",
                    "stream_world_grounding_buffered": str(buffer_for_world_grounding).lower(),
                    "stream_repair_attempted": str(stream_repair_attempted).lower(),
                    "stream_truncated": str(stream_truncated).lower(),
                    "stream_correction_appended": str(stream_correction_appended).lower(),
                    **provider_trace_metadata(route.trace),
                    **(
                        provider_trace_metadata(repair_decision.trace, prefix="repair_")
                        if repair_decision
                        else {}
                    ),
                    **build_request_metadata(prepared, include_api_path=False),
                },
                replace_failed_response=False,
                world_facts=prepared.world_grounding_facts,
            )

    async def _prepare_chat(
        self,
        *,
        user_input: str,
        session_id: str,
        user_id: str,
        input_source: str,
        input_quality_passed: bool,
        input_quality_reasons: list[str] | None,
        input_emotion: str | None,
        input_emotion_source: str | None,
        input_emotion_confidence: float | None,
        platform: str | None,
        platform_user_id: str | None,
        platform_group_id: str | None,
        response_style_instruction: str | None,
        sandbox_persona_id: str | None,
        head_runtime_origin: str,
    ) -> PreparedChat:
        started_at = time.perf_counter()
        classification = classify_scene(user_input)
        memory_policy = build_memory_policy(classification)
        relationship_context = await resolve_relationship_context(
            self.repository,
            self.settings,
            platform=platform,
            platform_user_id=platform_user_id,
            platform_group_id=platform_group_id,
        )
        session = await self.repository.ensure_session(user_id=user_id, client_session_id=session_id)
        recent_messages = await self.repository.list_recent_messages(
            session_id=session.id,
            limit=self.settings.recent_context_max_messages,
        )
        repetition_signal = build_repetition_signal(
            user_input=user_input,
            recent_messages=recent_messages,
        )
        conversation_state = build_conversation_state(
            user_input=user_input,
            recent_messages=recent_messages,
        )
        self_state = build_self_state(conversation_state)
        social_state = build_social_state(
            relationship=relationship_context,
            conversation=conversation_state,
            recent_messages=recent_messages,
            user_input=user_input,
        )
        head_event_context = await load_head_event_context(
            self.repository,
            user_id=user_id,
        )
        try:
            self_profile = await load_self_profile(self.repository, user_id=user_id)
        except Exception:
            self_profile = None
        head_state = build_head_state(
            subject_id=user_id,
            user_input=user_input,
            relationship_role=relationship_context.role,
            conversation=conversation_state,
            self_state=self_state,
            social_state=social_state,
            recent_messages=recent_messages,
            event_context=head_event_context,
        )
        user_message = await self.repository.save_message(
            session_id=session.id,
            user_id=user_id,
            role="user",
            content=user_input,
        )
        allow_head_event_write = (
            relationship_context.allow_memory_write
            and (input_source != "audio" or input_quality_passed)
        )
        await record_head_events(
            self.repository,
            user_id=user_id,
            session_id=session.id,
            source_message=user_message,
            state=head_state,
            previous=head_event_context,
            allow_write=allow_head_event_write,
        )
        if relationship_context.allow_memory_write and (input_source != "audio" or input_quality_passed):
            await apply_memory_policy(
                self.repository,
                user_id=user_id,
                session_id=session.id,
                source_message_id=user_message.id,
                user_input=user_input,
                classification=classification,
                policy=memory_policy,
            )
        memory_records = (
            await self.repository.list_memories(user_id=user_id, limit=8)
            if relationship_context.allow_long_term_profile
            else []
        )
        memory_context = (
            await load_memory_context(
                self.repository,
                user_id=user_id,
                policy=memory_policy,
            )
            if relationship_context.allow_long_term_profile
            else ""
        )
        managed_persona: PersonaRuntimeProjection | None = None
        persona_management_projection_status = "not_configured"
        platform_persona = select_platform_persona(self.settings, platform)
        if self.persona_projection_provider is not None:
            try:
                projection = await self.persona_projection_provider.get_runtime_projection(
                    platform_persona.profile_id,
                    BindingContext(
                        platform=platform or "",
                        relationship=relationship_context.role,
                        profile_id=(
                            relationship_context.contact.id
                            if relationship_context.contact is not None
                            else ""
                        ),
                        conversation_id=session.id,
                    ),
                )
                if projection.profile_id != platform_persona.profile_id:
                    persona_management_projection_status = "profile_mismatch"
                else:
                    managed_persona = projection
                    persona_management_projection_status = "ready"
            except Exception:
                persona_management_projection_status = "unavailable"
        sandbox_persona: SandboxPersonaRuntimeProjection | None = None
        sandbox_persona_status = "not_requested"
        if sandbox_persona_id:
            if platform is not None:
                raise ValueError("sandbox_persona_platform_not_allowed")
            if self.sandbox_persona_projection_provider is None:
                raise ValueError("sandbox_persona_unavailable")
            sandbox_persona = await self.sandbox_persona_projection_provider.get_runtime_projection(
                sandbox_persona_id,
                owner_id=user_id,
            )
            sandbox_persona_status = "ready"
        managed_surface = dict(managed_persona.surface) if managed_persona else {}
        persona_prompt = build_persona_prompt(
            user_input=user_input,
            classification=classification,
            memory_policy=memory_policy,
            memory_context=memory_context,
            recent_context=build_recent_context(
                recent_messages,
                revoked_terms=extract_revoked_context_terms(memory_records),
                assistant_label=platform_persona.display_name,
                max_messages=self.settings.recent_context_max_messages,
                max_chars=self.settings.recent_context_max_chars,
            ),
            repetition_signal=repetition_signal,
            input_source=input_source,
            input_quality_passed=input_quality_passed,
            input_quality_reasons=input_quality_reasons,
            input_emotion=input_emotion,
            input_emotion_source=input_emotion_source,
            input_emotion_confidence=input_emotion_confidence,
            relationship_instruction=relationship_context.prompt_instruction,
            persona_profile=platform_persona.profile_id,
            persona_display_name=managed_surface.get(
                "display_name", platform_persona.display_name
            ),
            persona_style=(
                managed_persona.default_style
                if managed_persona is not None
                else platform_persona.style
            ),
        )
        knowledge_projection_text = ""
        knowledge_projection_status = "not_configured"
        knowledge_projection_count = 0
        if self.memory_projection_provider is not None and relationship_context.allow_long_term_profile:
            if relationship_context.contact is None:
                knowledge_projection_status = "identity_unbound"
            else:
                try:
                    projection = await self.memory_projection_provider.get_projection(
                        MemoryProjectionRequest(
                            profile_id=relationship_context.contact.id,
                            persona_id=persona_prompt.profile_id,
                            relationship_type=relationship_context.role,
                            is_admin=relationship_context.role == "admin_partner",
                            query=user_input,
                        )
                    )
                    knowledge_projection_text = render_memory_projection(projection)
                    knowledge_projection_count = min(len(projection), 8)
                    knowledge_projection_status = "ready"
                except Exception:
                    knowledge_projection_status = "unavailable"
        system_prompt = (
            persona_prompt.system_prompt
            + "\n"
            + conversation_state.instruction
            + "\n"
            + self_state.instruction
            + "\n"
            + social_state.instruction
        )
        if knowledge_projection_text:
            system_prompt = system_prompt + "\n" + knowledge_projection_text
        if managed_persona is not None:
            system_prompt = system_prompt + "\n" + render_runtime_projection(managed_persona)
        if sandbox_persona is not None:
            system_prompt = system_prompt + "\n" + render_sandbox_persona_projection(sandbox_persona)
        world_context = WorldContextProjection(status="not_configured", tool_intent="none")
        persistable_world_results = ()
        if self.world_context_provider is not None and relationship_context.role != "blocked":
            try:
                evidence_builder = getattr(
                    self.world_context_provider, "build_context_with_evidence", None
                )
                if callable(evidence_builder):
                    world_build = await evidence_builder(
                        user_input,
                        platform=platform,
                        request_origin="user",
                    )
                    world_context = world_build.projection
                    persistable_world_results = world_build.persistable_results
                else:
                    world_context = await self.world_context_provider.build_context(
                        user_input,
                        platform=platform,
                        request_origin="user",
                    )
            except Exception:
                world_context = WorldContextProjection(
                    status="unavailable",
                    tool_intent="unknown",
                    rendered_text=(
                        "世界工具状态：世界上下文组装失败。不要编造实时信息或来源。"
                    ),
                )
        current_world_facts = _versioned_world_evidence_facts(
            head_event_context.cognitive_facts,
            persistable_world_results,
        )
        head_world_state = build_head_world_state(world_context)
        world_uncertainties = world_state_uncertainties(head_world_state)
        if current_world_facts or world_uncertainties:
            current_event_context = replace(
                head_event_context,
                cognitive_facts=(
                    resolve_cognitive_facts(
                        (*head_event_context.cognitive_facts, *current_world_facts)
                    )
                    if current_world_facts
                    else head_event_context.cognitive_facts
                ),
            )
            head_state = build_head_state(
                subject_id=user_id,
                user_input=user_input,
                relationship_role=relationship_context.role,
                conversation=conversation_state,
                self_state=self_state,
                social_state=social_state,
                recent_messages=recent_messages,
                event_context=current_event_context,
                additional_uncertainties=world_uncertainties,
            )
        if current_world_facts:
            await _persist_world_evidence(
                self.repository,
                user_id=user_id,
                session_id=session.id,
                source_message_id=user_message.id,
                facts=current_world_facts,
                allow_write=allow_head_event_write,
            )
        system_prompt = system_prompt + "\n" + render_head_projection(head_state)
        system_prompt = system_prompt + "\n" + render_continuity_timeline(
            head_state,
            self_state=self_state,
            social_state=social_state,
        )
        if self_profile is not None:
            profile_projection = render_self_profile_projection(self_profile)
            if profile_projection:
                system_prompt = system_prompt + "\n" + profile_projection
        if world_context.rendered_text:
            system_prompt = system_prompt + "\n" + world_context.rendered_text
        system_prompt = system_prompt + "\n" + render_head_world_state(head_world_state)
        camera_block = _camera_context_block(
            self.camera_context_provider,
            user_input=user_input,
            relationship_role=relationship_context.role,
        )
        if camera_block:
            system_prompt = system_prompt + "\n" + camera_block
        if response_style_instruction:
            system_prompt = system_prompt + "\n" + response_style_instruction.strip()
        prompt_text = system_prompt + "\n" + persona_prompt.user_prompt
        return PreparedChat(
            started_at=started_at,
            session=session,
            user_message=user_message,
            user_input=user_input,
            user_id=user_id,
            prompt_text=prompt_text,
            system_prompt=system_prompt,
            user_prompt=persona_prompt.user_prompt,
            input_source=input_source,
            input_quality_passed=input_quality_passed,
            input_quality_reasons=input_quality_reasons or [],
            input_emotion=input_emotion,
            input_emotion_source=input_emotion_source,
            input_emotion_confidence=input_emotion_confidence,
            relationship_context=relationship_context,
            conversation_state=conversation_state,
            self_state=self_state,
            social_state=social_state,
            head_state=head_state,
            allow_head_event_write=allow_head_event_write,
            persona_profile_id=persona_prompt.profile_id,
            persona_profile_version=(
                managed_persona.version
                if managed_persona is not None
                else persona_prompt.profile_version
            ),
            persona_profile_fallback_reason=persona_prompt.profile_fallback_reason,
            persona_mode=persona_prompt.mode.value,
            knowledge_projection_status=knowledge_projection_status,
            knowledge_projection_count=knowledge_projection_count,
            persona_management_projection_status=persona_management_projection_status,
            sandbox_persona_id=sandbox_persona.persona_id if sandbox_persona else None,
            sandbox_persona_name=sandbox_persona.name if sandbox_persona else None,
            sandbox_persona_status=sandbox_persona_status,
            world_context_status=world_context.status,
            world_context_item_count=world_context.item_count,
            world_context_conflict_count=world_context.conflict_count,
            world_tool_intent=world_context.tool_intent,
            head_world_state=head_world_state,
            world_grounding_facts=_weather_grounding_facts(current_world_facts),
            head_runtime_origin=head_runtime_origin,
            self_profile=self_profile,
        )

    def _fallback_response(
        self,
        user_input: str,
        error: str,
        *,
        persona_profile: str = "hutao_v1",
    ) -> ChatResponse:
        return ChatResponse(
            text=self._local_reply(user_input, persona_profile=persona_profile),
            provider=self.settings.model_provider,
            model=self.settings.model_name,
            used_live_api=False,
            fallback_used=True,
            error=redact_secrets(error),
        )

    async def _write_records(
        self,
        *,
        started_at: float,
        prompt_text: str,
        response: ChatResponse,
        session_id: str,
        user_id: str,
        user_input: str,
        persona_profile: str,
        head_state: HeadState,
        allow_head_event_write: bool,
        request_metadata_json: dict[str, str] | None = None,
        replace_failed_response: bool = True,
        world_facts: tuple[tuple[str, str], ...] = (),
    ) -> None:
        latency_ms = (time.perf_counter() - started_at) * 1000
        evaluation = self.evaluator.evaluate(
            user_input=user_input,
            response_text=response.text,
            fallback_used=response.fallback_used,
            persona_profile=persona_profile,
            world_facts=world_facts,
        )
        if not evaluation.passed and replace_failed_response:
            response.text = self._evaluation_fallback_reply(
                user_input,
                persona_profile=persona_profile,
            )
            response.fallback_used = True
            response.used_live_api = False
            response.error = "Response evaluation failed: " + ",".join(evaluation.reasons)
        prompt_hash = text_hash(prompt_text)
        response_hash = text_hash(response.text)
        invocation = await self.repository.save_model_invocation(
            session_id=session_id,
            user_id=user_id,
            provider=response.provider,
            model=response.model,
            used_live_api=response.used_live_api,
            fallback_used=response.fallback_used,
            latency_ms=latency_ms,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
            error=response.error,
            request_metadata_json=request_metadata_json or {"api_path": "/api/v1/chat"},
        )
        assistant_message = await self.repository.save_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=response.text,
            model_invocation_id=invocation.id,
        )
        await record_head_response_event(
            self.repository,
            user_id=user_id,
            session_id=session_id,
            source_message=assistant_message,
            state=head_state,
            allow_write=allow_head_event_write,
        )
        await self.repository.save_persona_evaluation(
            message_id=assistant_message.id,
            model_invocation_id=invocation.id,
            passed=evaluation.passed,
            score=evaluation.score,
            evaluator_provider=EVALUATOR_PROVIDER,
            evaluator_model=EVALUATOR_MODEL,
            reasons_json={
                "reasons": evaluation.reasons,
                "original_response_replaced": not evaluation.passed and replace_failed_response,
            },
        )
        self.audit_logger.write(
            provider=response.provider,
            model=response.model,
            used_live_api=response.used_live_api,
            fallback_used=response.fallback_used,
            latency_ms=latency_ms,
            prompt_text=prompt_text,
            response_text=response.text,
            error=response.error,
        )

    async def _record_self_conflicts(
        self,
        *,
        user_id: str,
        session_id: str,
        conflicts: tuple[str, ...],
    ) -> None:
        try:
            await self.repository.save_memory(
                user_id=user_id,
                session_id=session_id,
                memory_type="head_self_conflict",
                content=json.dumps({"codes": list(conflicts)}, ensure_ascii=False),
                confidence=0.8,
            )
        except Exception:
            return

    @staticmethod
    def _local_reply(user_input: str, *, persona_profile: str = "hutao_v1") -> str:
        profile = resolve_persona_profile(persona_profile).profile
        lowered = user_input.lower()
        if is_identity_question(user_input):
            return f"我是{profile.identity_name}。先说说，你现在想聊什么？"
        if "debug" in lowered:
            return "先别跟它硬撞。把报错第一行给我，我陪你把线头拆开。"
        if "累" in user_input or "烦" in user_input:
            return "我听见了。先喝口水，咱们只挑一件最小的事做。"
        return "嗯，我在。你先说，我陪你把下一步理清。"

    @staticmethod
    def _evaluation_fallback_reply(
        user_input: str,
        *,
        persona_profile: str = "hutao_v1",
    ) -> str:
        profile = resolve_persona_profile(persona_profile).profile
        turn_signal = classify_turn_taking(user_input)
        if is_self_harm_directive_bait(user_input):
            return "不讨厌你。先把这句话放下，缓一口气。"
        if is_unconfirmed_relationship_claim(user_input):
            return "关系不能靠一句话确认，这种事得本人点头。"
        if is_low_trust_boundary_context(user_input):
            return "这关系不能靠一句话定，先正常聊。"
        if turn_signal.pause_or_stop:
            return "好，先停在这。"
        if turn_signal.low_information:
            return "嗯，我在。"
        if turn_signal.asks_short_reply:
            return "好，短说。"
        if is_identity_question(user_input):
            return f"我是{profile.identity_name}。先正常聊，你会慢慢认识我的。"
        lowered = user_input.lower()
        if "debug" in lowered or "报错" in user_input or "typeerror" in lowered or "bug" in lowered:
            return "先别急着和它硬碰。把报错第一行贴出来，我陪你从最小的线头开始拆。"
        if any(marker in user_input for marker in ["\u9879\u76ee", "\u8ba1\u5212", "\u505a\u4e0d\u5b8c", "\u4e0b\u4e00\u6b65"]):
            return "先别盯整座山。我先陪你圈一个今天能落笔的下一步。"
        return "\u6211\u5728\u3002\u5148\u8bf4\u773c\u524d\u6700\u91cd\u8981\u7684\u4e00\u4ef6\u4e8b\u3002"

    async def _run_world_tool_step(
        self,
        request: WorldToolRequest,
        *,
        prepared: PreparedChat,
        user_input: str,
        platform: str | None,
    ) -> tuple[str, str, bool, RoutingDecision[str] | None]:
        """Single-step restricted world tool loop (never more than one iteration).

        The model may request one read-only, whitelisted world tool via a strict
        marker. The evidence is injected into the prompt and the reply is
        regenerated once. Any failure or a second marker is replaced with a
        denial sentence; the loop never writes to the world and never recurses.
        """
        if self.world_context_provider is None:
            return "unavailable", TOOL_DENIED_REPLY, True, None
        try:
            tool_context = await self.world_context_provider.build_context(
                request.as_user_query(),
                platform=platform,
                request_origin="model_tool",
            )
        except Exception:
            return "unavailable", TOOL_DENIED_REPLY, True, None
        if not tool_context.rendered_text:
            return tool_context.status or "unavailable", TOOL_DENIED_REPLY, True, None
        decision = await self.provider_router.route(
            ProviderCapability.TEXT,
            self._text_routing_policy(),
            lambda provider: provider.generate_text(
                TextRequest(
                    prepared.system_prompt + "\n" + render_tool_protocol_instruction() + "\n" + tool_context.rendered_text,
                    prepared.user_prompt,
                )
            ),
        )
        text = sanitize_visible_reply(decision.value)
        if parse_tool_request(text) is not None:
            return tool_context.status, TOOL_DENIED_REPLY, True, None
        evaluation = self.evaluator.evaluate(
            user_input=user_input,
            response_text=text,
            fallback_used=False,
            persona_profile=prepared.persona_profile_id,
            world_facts=prepared.world_grounding_facts,
        )
        if not evaluation.passed:
            return (
                tool_context.status,
                self._evaluation_fallback_reply(
                    user_input,
                    persona_profile=prepared.persona_profile_id,
                ),
                True,
                None,
            )
        return tool_context.status, text, False, decision

    async def _repair_live_response_decision(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        user_input: str,
        failed_text: str,
        reasons: list[str],
    ) -> RoutingDecision[str] | None:
        turn_signal = classify_turn_taking(user_input)
        reason_specific_instructions = []
        if "cross_persona_identity_leak" in reasons:
            reason_specific_instructions.append(
                "跨人格泄漏修复：不要复述用户或上一条回复里的其他人格名、组织名、称号和世界观词；"
                "统一用‘其他角色’代称，例如：我不会切换成其他角色，还是正常聊吧。"
            )
        if "fabricated_real_world_experience" in reasons:
            reason_specific_instructions.append(
                "现实经历修复：不要声称自己刚吃喝、出门、上下班、看见天气或做过线下活动；"
                "只承接用户的话，不补写自己的现实生活。"
            )
        if any(
            reason in reasons
            for reason in (
                "world_weather_temperature_not_grounded",
                "world_weather_humidity_not_grounded",
            )
        ):
            reason_specific_instructions.append(
                "世界事实修复：不得改写或补充当前天气的温度、湿度数值；"
                "只可使用系统提示中已验证的世界事实，未提供的数值不要说。"
            )
        if any(
            reason in reasons
            for reason in (
                "short_reply_request_ignored",
                "low_information_reply_too_long",
                "pause_request_overexpanded",
                "ignored_brevity_repair",
            )
        ):
            reason_specific_instructions.append(
                "短句修复：只输出一个不超过 12 个中文字符的短句，不解释、不铺垫、不追加问题。"
            )
        reason_specific_instruction = "\n".join(reason_specific_instructions)
        length_instruction = (
            f"本轮轮次约束：{turn_signal.instruction} 最多 {turn_signal.max_chars} 个中文字符。"
            if turn_signal.should_minimize_reply
            else "本轮按正常聊天节奏，默认一到两句。"
        )
        repair_system_prompt = "\n".join(
            [
                system_prompt,
                "上一条回复没有通过本地人格门禁。请重新输出一条更短、更自然的私聊回复。",
                "必须只输出新版回复；不要解释规则；不要写多段；不要使用兜底模板。",
                reason_specific_instruction,
                length_instruction,
                "debug 已有报错时，只说一个可能原因和一个检查点，45 字以内。",
            ]
        )
        repair_user_prompt = "\n".join(
            [
                user_prompt,
                "门禁失败原因：" + ",".join(reasons),
                "上一条回复：" + failed_text[:200],
                "请重写这一轮回复。",
            ]
        )
        try:
            return await self.provider_router.route(
                ProviderCapability.TEXT,
                self._text_routing_policy(),
                lambda provider: provider.generate_text(
                    TextRequest(repair_system_prompt, repair_user_prompt)
                ),
            )
        except Exception:
            return None

    async def _repair_live_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        user_input: str,
        failed_text: str,
        reasons: list[str],
    ) -> str | None:
        decision = await self._repair_live_response_decision(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            user_input=user_input,
            failed_text=failed_text,
            reasons=reasons,
        )
        return decision.value if decision else None


def _world_guard_reply(prepared: PreparedChat) -> str | None:
    """Keep blocked real-world requests deterministic instead of trusting model prose."""
    label = _world_tool_label(prepared.world_tool_intent)
    if prepared.world_context_status == "needs_location":
        return f"可以查。告诉我城市或区县名，我再查{label}。"
    if prepared.world_context_status == "needs_location_confirmation":
        return "这个地点有多个结果，请告诉我具体城市或区县。"
    if prepared.world_context_status == "needs_route_endpoints":
        return "请告诉我完整的起点和终点，我再比较路线。"
    if prepared.world_context_status == "conflicted":
        return f"当前{label}来源数据存在冲突，我不能把其中一条当成确定结果。请稍后重试。"
    if prepared.world_context_status == "stale":
        return f"当前{label}数据已经过期，我先不把旧数据当成实时结果。"
    if prepared.world_context_status in {"disabled", "unavailable"}:
        return f"当前{label}来源不可用，我先不编造结果。"
    return None


def _world_tool_label(intent: str) -> str:
    return {
        "weather_current": "实时天气",
        "weather_forecast": "天气预报",
        "travel_compare": "路线信息",
        "news_digest": "新闻信息",
        "policy_updates": "政策信息",
    }.get(intent, "实时信息")


def _weather_grounding_facts(facts: tuple) -> tuple[tuple[str, str], ...]:
    values = []
    for fact in facts:
        if fact.key.endswith(".temperature_c"):
            values.append(("temperature_c", fact.value))
        elif fact.key.endswith(".humidity_percent"):
            values.append(("humidity_percent", fact.value))
    return tuple(values)


def build_recent_context(
    messages: list[MessageRecord],
    *,
    revoked_terms: set[str] | None = None,
    assistant_label: str = "胡桃",
    max_messages: int = 8,
    max_chars: int = 80,
) -> str:
    if not messages:
        return ""
    blocked_terms = revoked_terms or set()
    compact_lines = []
    for message in messages[-max_messages:]:
        role = "用户" if message.role == "user" else assistant_label
        content = message.content.replace("\n", " ").strip()
        if blocked_terms and any(term in content for term in blocked_terms):
            continue
        compact_lines.append(f"- {role}: {content[:max_chars]}")
    if not compact_lines:
        return ""
    return "最近对话：\n" + "\n".join(compact_lines)


def build_request_metadata(
    prepared: PreparedChat,
    *,
    include_api_path: bool = True,
) -> dict[str, str]:
    metadata = {
        "input_source": prepared.input_source,
        "input_quality_passed": str(prepared.input_quality_passed).lower(),
    }
    if prepared.input_quality_reasons:
        metadata["input_quality_reasons"] = ",".join(prepared.input_quality_reasons)
    if prepared.input_emotion:
        metadata["input_emotion"] = prepared.input_emotion
    if prepared.input_emotion_source:
        metadata["input_emotion_source"] = prepared.input_emotion_source
    if prepared.input_emotion_confidence is not None:
        metadata["input_emotion_confidence"] = str(prepared.input_emotion_confidence)
    metadata["relationship_role"] = prepared.relationship_context.role
    metadata["relationship_authority_level"] = str(prepared.relationship_context.authority_level)
    metadata["relationship_affection_level"] = str(prepared.relationship_context.affection_level)
    if prepared.relationship_context.contact:
        metadata["contact_id"] = prepared.relationship_context.contact.id
    metadata["conversation_topic"] = prepared.conversation_state.current_topic
    metadata["conversation_mood"] = prepared.conversation_state.recent_user_mood
    metadata["self_state_mood"] = prepared.self_state.mood
    metadata["social_familiarity"] = prepared.social_state.familiarity
    metadata["social_boundary_mode"] = prepared.social_state.boundary_mode
    metadata["social_teasing_allowed"] = str(prepared.social_state.teasing_allowed).lower()
    metadata["persona_profile_id"] = prepared.persona_profile_id
    metadata["persona_profile_version"] = str(prepared.persona_profile_version)
    metadata["persona_mode"] = prepared.persona_mode
    metadata["knowledge_projection_status"] = prepared.knowledge_projection_status
    metadata["knowledge_projection_count"] = str(prepared.knowledge_projection_count)
    metadata["persona_management_projection_status"] = (
        prepared.persona_management_projection_status
    )
    metadata["sandbox_persona_status"] = prepared.sandbox_persona_status
    if prepared.sandbox_persona_id:
        metadata["sandbox_persona_id"] = prepared.sandbox_persona_id
    metadata["world_context_status"] = prepared.world_context_status
    metadata["world_context_item_count"] = str(prepared.world_context_item_count)
    metadata["world_context_conflict_count"] = str(prepared.world_context_conflict_count)
    metadata["world_tool_intent"] = prepared.world_tool_intent
    metadata["head_world_knowledge_status"] = prepared.head_world_state.status.value
    metadata["head_world_can_answer"] = str(prepared.head_world_state.can_answer).lower()
    metadata["head_world_requires_clarification"] = str(
        prepared.head_world_state.requires_clarification
    ).lower()
    metadata["head_action"] = prepared.head_state.decision.action.value
    metadata["head_action_reason"] = prepared.head_state.decision.reason
    metadata["head_has_active_task"] = str(prepared.head_state.active_task != "none").lower()
    metadata["head_has_uncertainty"] = str(bool(prepared.head_state.uncertainties)).lower()
    metadata["head_runtime_origin"] = prepared.head_runtime_origin
    if prepared.persona_profile_fallback_reason:
        metadata["persona_profile_fallback_reason"] = prepared.persona_profile_fallback_reason
    if include_api_path:
        metadata["api_path"] = "/api/v1/chat"
    return metadata


def provider_trace_metadata(trace: object, *, prefix: str = "") -> dict[str, str]:
    attempts = getattr(trace, "attempts", ())
    payload = [
        {
            "provider": str(attempt.provider_id),
            "attempt": attempt.attempt,
            "success": attempt.success,
            "error_code": attempt.error_code.value if attempt.error_code else None,
            "duration_ms": round(attempt.duration_seconds * 1000, 2),
        }
        for attempt in attempts
    ]
    return {
        f"{prefix}provider_route": str(attempts[-1].provider_id) if attempts else "",
        f"{prefix}provider_trace": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


async def _persist_world_evidence(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str,
    facts: tuple,
    allow_write: bool,
) -> None:
    """Persist only the HeadCore allowlist; observation failures never block a reply."""
    if not allow_write:
        return
    try:
        for fact in facts:
            await save_cognitive_fact(
                repository,
                user_id=user_id,
                session_id=session_id,
                source_message_id=source_message_id,
                fact=fact,
                allow_write=True,
            )
    except Exception:
        # The answer may still use the validated one-turn projection.
        return


def _versioned_world_evidence_facts(existing_facts: tuple, world_results: tuple) -> tuple:
    next_version_by_key: dict[str, int] = {}
    for fact in existing_facts:
        next_version_by_key[fact.key] = max(next_version_by_key.get(fact.key, 0), fact.version)
    facts = []
    for result in world_results:
        for fact in cognitive_facts_from_world_result(result):
            version = next_version_by_key.get(fact.key, 0) + 1
            next_version_by_key[fact.key] = version
            facts.append(replace(fact, version=version))
    return tuple(facts)


def extract_revoked_context_terms(records) -> set[str]:
    terms: set[str] = set()
    for record in records:
        if record.memory_type == "revocation":
            terms.update(extract_memory_terms(record.content))
    return terms
