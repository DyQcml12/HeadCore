from __future__ import annotations

from dataclasses import dataclass

from app.storage.v2_command_executor import (
    V2CommandExecutionResult,
    execute_v2_admin_command,
)
from app.storage.v2_command_policy import V2CommandDecision, decide_v2_admin_command
from app.storage.v2_relationship_service import (
    DatabaseV2RelationshipService,
    PlatformIdentity,
    RelationshipResolution,
)
from app.storage.v2_repository import DatabaseV2Repository


@dataclass(frozen=True)
class V2PlatformCommandResult:
    resolution: RelationshipResolution
    decision: V2CommandDecision
    execution_result: V2CommandExecutionResult | None
    is_command: bool
    should_enter_chat_service: bool
    should_reply: bool
    reply_text: str | None
    reason_code: str

    def to_adapter_payload(self) -> dict[str, object]:
        return {
            "is_command": self.is_command,
            "should_enter_chat_service": self.should_enter_chat_service,
            "should_reply": self.should_reply,
            "reply_text": self.reply_text,
            "reason_code": self.reason_code,
            "relationship": self.resolution.to_model_context(),
            "command": (
                {
                    "name": self.decision.command.name,
                    "args": self.decision.command.args,
                }
                if self.decision.command is not None
                else None
            ),
            "execution": (
                {
                    "executed": self.execution_result.executed,
                    "status": self.execution_result.status,
                    "message": self.execution_result.message,
                    "data": self.execution_result.data,
                }
                if self.execution_result is not None
                else None
            ),
        }


class DatabaseV2PlatformCommandService:
    def __init__(
        self,
        *,
        relationship_service: DatabaseV2RelationshipService,
        repository: DatabaseV2Repository,
        command_prefixes: tuple[str, ...] = ("胡桃",),
    ) -> None:
        self.relationship_service = relationship_service
        self.repository = repository
        self.command_prefixes = command_prefixes

    async def handle_message(
        self,
        *,
        identity: PlatformIdentity,
        message_text: str,
        message_id: str | None = None,
    ) -> V2PlatformCommandResult:
        resolution = await self.relationship_service.resolve(identity)
        empty_decision = V2CommandDecision(
            is_command=False,
            authorized=False,
            command=None,
            reason_code=resolution.reason_code,
        )
        if not resolution.should_enter_chat_service:
            return V2PlatformCommandResult(
                resolution=resolution,
                decision=empty_decision,
                execution_result=None,
                is_command=False,
                should_enter_chat_service=False,
                should_reply=resolution.should_reply,
                reply_text=resolution.fixed_reply,
                reason_code=resolution.reason_code,
            )

        command_text = normalize_platform_command_text(
            message_text,
            command_prefixes=self.command_prefixes,
        )
        decision = decide_v2_admin_command(
            command_text=command_text,
            resolution=resolution,
        )
        if not decision.is_command:
            return V2PlatformCommandResult(
                resolution=resolution,
                decision=decision,
                execution_result=None,
                is_command=False,
                should_enter_chat_service=resolution.should_enter_chat_service,
                should_reply=resolution.should_reply,
                reply_text=resolution.fixed_reply,
                reason_code=resolution.reason_code,
            )

        if not decision.authorized or decision.command is None:
            await self._record_command_audit(
                identity=identity,
                message_id=message_id,
                actor_profile_id=resolution.context.profile.id,
                decision=decision,
                status="rejected",
                reason_code=decision.reason_code,
            )
            return V2PlatformCommandResult(
                resolution=resolution,
                decision=decision,
                execution_result=None,
                is_command=True,
                should_enter_chat_service=False,
                should_reply=True,
                reply_text=decision.error or "没有权限使用这个命令。",
                reason_code=decision.reason_code,
            )

        try:
            execution_result = await execute_v2_admin_command(
                decision=decision,
                repository=self.repository,
                actor_profile_id=resolution.context.profile.id,
            )
        except Exception as exc:  # pragma: no cover - defensive platform boundary
            execution_result = V2CommandExecutionResult(
                False,
                "execution_failed",
                "command execution failed",
                {"error_type": type(exc).__name__},
            )

        audit_status = "accepted" if execution_result.executed else "failed"
        await self._record_command_audit(
            identity=identity,
            message_id=message_id,
            actor_profile_id=resolution.context.profile.id,
            decision=decision,
            status=audit_status,
            reason_code=execution_result.status,
            details=execution_result.data,
        )
        return V2PlatformCommandResult(
            resolution=resolution,
            decision=decision,
            execution_result=execution_result,
            is_command=True,
            should_enter_chat_service=False,
            should_reply=True,
            reply_text=execution_result.message,
            reason_code=execution_result.status,
        )

    async def _record_command_audit(
        self,
        *,
        identity: PlatformIdentity,
        message_id: str | None,
        actor_profile_id: str | None,
        decision: V2CommandDecision,
        status: str,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        command_name = decision.command.name if decision.command is not None else "invalid"
        await self.repository.record_platform_command_event(
            message_id=message_id,
            actor_profile_id=actor_profile_id,
            command_name=command_name,
            platform=identity.platform,
            target_platform_user_id=target_platform_user_id(decision),
            status=status,
            reason_code=reason_code,
            details=details or {"error": decision.error} if decision.error else details,
        )


def normalize_platform_command_text(
    message_text: str,
    *,
    command_prefixes: tuple[str, ...] = ("胡桃",),
) -> str:
    text = message_text.strip()
    for prefix in command_prefixes:
        prefix = prefix.strip()
        if not prefix or not text.startswith(prefix):
            continue
        return text[len(prefix) :].lstrip(" ，,：:").strip()
    return text


def target_platform_user_id(decision: V2CommandDecision) -> str | None:
    if decision.command is None:
        return None
    args = decision.command.args
    if "platform_user_id" in args:
        return args["platform_user_id"]
    if "target_platform_user_id" in args:
        return args["target_platform_user_id"]
    if "source_platform_user_id" in args:
        return args["source_platform_user_id"]
    if "claim_id" in args:
        return args["claim_id"]
    return None
