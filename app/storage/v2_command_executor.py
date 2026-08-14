from __future__ import annotations

from dataclasses import asdict, dataclass

from app.storage.v2_command_policy import V2AdminCommand, V2CommandDecision
from app.storage.v2_models import PlatformName, RelationshipType, V2RelationshipContext
from app.storage.v2_repository import DatabaseV2Repository


@dataclass(frozen=True)
class V2CommandExecutionResult:
    executed: bool
    status: str
    message: str
    data: dict[str, object]


async def execute_v2_admin_command(
    *,
    decision: V2CommandDecision,
    repository: DatabaseV2Repository,
    actor_profile_id: str,
) -> V2CommandExecutionResult:
    if not decision.is_command:
        return V2CommandExecutionResult(False, "ignored", "not a command", {})
    if not decision.authorized or decision.command is None:
        return V2CommandExecutionResult(
            False,
            decision.reason_code,
            decision.error or decision.reason_code,
            {},
        )

    command = decision.command
    if command.name == "set_relationship":
        context = await repository.set_relationship(
            platform=platform_arg(command, "platform"),
            platform_user_id=command.args["platform_user_id"],
            relationship_type=relationship_arg(command, "relationship_type"),
            display_name=command.args.get("display_name", ""),
            changed_by_profile_id=actor_profile_id,
            reason="admin command set_relationship",
        )
        return context_result("relationship_updated", context)

    if command.name == "block":
        context = await repository.set_relationship(
            platform=platform_arg(command, "platform"),
            platform_user_id=command.args["platform_user_id"],
            relationship_type="blocked",
            changed_by_profile_id=actor_profile_id,
            reason="admin command block",
        )
        return context_result("blocked", context)

    if command.name == "unblock":
        context = await repository.set_relationship(
            platform=platform_arg(command, "platform"),
            platform_user_id=command.args["platform_user_id"],
            relationship_type="normal_friend",
            changed_by_profile_id=actor_profile_id,
            reason="admin command unblock",
        )
        return context_result("unblocked", context)

    if command.name == "bind_accounts":
        profile_id = await repository.bind_accounts(
            source_platform=platform_arg(command, "source_platform"),
            source_platform_user_id=command.args["source_platform_user_id"],
            target_platform=platform_arg(command, "target_platform"),
            target_platform_user_id=command.args["target_platform_user_id"],
            changed_by_profile_id=actor_profile_id,
            reason="admin command bind_accounts",
        )
        return V2CommandExecutionResult(
            True,
            "accounts_bound",
            "accounts bound",
            {"profile_id": profile_id},
        )

    if command.name == "view_relationship":
        context = await repository.resolve_relationship_context(
            platform=platform_arg(command, "platform"),
            platform_user_id=command.args["platform_user_id"],
        )
        return context_result("relationship_loaded", context)

    if command.name == "recent_chats":
        chats = await repository.list_recent_chats(limit=10)
        return V2CommandExecutionResult(
            True,
            "recent_chats_loaded",
            "recent chats loaded",
            {"chats": [asdict(chat) for chat in chats]},
        )

    if command.name == "view_chat":
        messages = await repository.list_chat_history(
            platform=platform_arg(command, "platform"),
            platform_user_id=command.args["platform_user_id"],
            limit=30,
        )
        return V2CommandExecutionResult(
            True,
            "chat_history_loaded",
            "chat history loaded",
            {"messages": [asdict(message) for message in messages]},
        )

    if command.name == "pending_claims":
        claims = await repository.list_pending_relationship_claims(limit=20)
        return V2CommandExecutionResult(
            True,
            "pending_claims_loaded",
            "pending claims loaded",
            {"claims": [asdict(claim) for claim in claims]},
        )

    if command.name == "approve_claim":
        data = await repository.approve_relationship_claim(
            claim_id=command.args["claim_id"],
            reviewed_by_profile_id=actor_profile_id,
        )
        return V2CommandExecutionResult(
            True,
            str(data.get("status") or "approved"),
            "relationship claim approved",
            data,
        )

    if command.name == "reject_claim":
        data = await repository.reject_relationship_claim(
            claim_id=command.args["claim_id"],
            reviewed_by_profile_id=actor_profile_id,
        )
        return V2CommandExecutionResult(
            True,
            str(data.get("status") or "rejected"),
            "relationship claim rejected",
            data,
        )

    return V2CommandExecutionResult(
        False,
        "not_implemented",
        f"command execution is not implemented yet: {command.name}",
        {"command": command.name},
    )


def context_result(status: str, context: V2RelationshipContext) -> V2CommandExecutionResult:
    return V2CommandExecutionResult(
        True,
        status,
        status,
        {
            "profile_id": context.profile.id,
            "platform_account_id": context.platform_account.id,
            "relationship_type": context.profile.relationship_type,
            "effective_relationship_type": context.effective_relationship_type,
            "verified": context.profile.verified,
        },
    )


def platform_arg(command: V2AdminCommand, name: str) -> PlatformName:
    value = command.args[name]
    if value not in {"qq", "wechat"}:
        raise ValueError(f"Unsupported platform in command: {value}")
    return value  # type: ignore[return-value]


def relationship_arg(command: V2AdminCommand, name: str) -> RelationshipType:
    value = command.args[name]
    if value not in {"admin_partner", "normal_friend", "blocked"}:
        raise ValueError(f"Unsupported relationship in command: {value}")
    return value  # type: ignore[return-value]
