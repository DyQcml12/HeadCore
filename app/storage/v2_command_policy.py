from __future__ import annotations

from dataclasses import dataclass

from app.storage.v2_models import PlatformName, RelationshipType
from app.storage.v2_relationship_service import RelationshipResolution


ADMIN_COMMAND_NAMES = {
    "set_relationship",
    "block",
    "unblock",
    "bind_accounts",
    "view_relationship",
    "recent_chats",
    "view_chat",
    "pending_claims",
    "approve_claim",
    "reject_claim",
}


@dataclass(frozen=True)
class V2AdminCommand:
    name: str
    args: dict[str, str]


@dataclass(frozen=True)
class V2CommandDecision:
    is_command: bool
    authorized: bool
    command: V2AdminCommand | None
    reason_code: str
    error: str | None = None


def decide_v2_admin_command(
    *,
    command_text: str,
    resolution: RelationshipResolution,
) -> V2CommandDecision:
    parsed = parse_v2_admin_command(command_text)
    if parsed is None:
        return V2CommandDecision(
            is_command=False,
            authorized=False,
            command=None,
            reason_code="not_command",
        )
    if isinstance(parsed, str):
        return V2CommandDecision(
            is_command=True,
            authorized=False,
            command=None,
            reason_code="invalid_command",
            error=parsed,
        )
    if resolution.context.effective_relationship_type != "admin_partner":
        return V2CommandDecision(
            is_command=True,
            authorized=False,
            command=parsed,
            reason_code="admin_required",
        )
    return V2CommandDecision(
        is_command=True,
        authorized=True,
        command=parsed,
        reason_code="authorized",
    )


def parse_v2_admin_command(command_text: str) -> V2AdminCommand | str | None:
    tokens = command_text.strip().split()
    if not tokens:
        return None
    first = tokens[0]
    if first == "设置关系":
        return parse_set_relationship(tokens)
    if first == "拉黑":
        return parse_platform_user_command("block", tokens)
    if first == "解除拉黑":
        return parse_platform_user_command("unblock", tokens)
    if first == "绑定账号":
        return parse_bind_accounts(tokens)
    if first == "查看关系":
        return parse_platform_user_command("view_relationship", tokens)
    if first == "最近聊天":
        return V2AdminCommand("recent_chats", {})
    if first == "查看聊天":
        return parse_platform_user_command("view_chat", tokens)
    if first == "待确认关系":
        return V2AdminCommand("pending_claims", {})
    if first == "确认关系":
        return parse_claim_command("approve_claim", tokens)
    if first == "拒绝关系":
        return parse_claim_command("reject_claim", tokens)
    return None


def parse_set_relationship(tokens: list[str]) -> V2AdminCommand | str:
    if len(tokens) < 4:
        return "设置关系 requires: 设置关系 <platform> <platform_user_id> <relationship_type> [display_name]"
    platform = parse_platform(tokens[1])
    if platform is None:
        return "unsupported platform"
    relationship_type = parse_relationship_type(tokens[3])
    if relationship_type is None:
        return "unsupported relationship_type"
    return V2AdminCommand(
        "set_relationship",
        {
            "platform": platform,
            "platform_user_id": tokens[2],
            "relationship_type": relationship_type,
            "display_name": " ".join(tokens[4:]),
        },
    )


def parse_platform_user_command(name: str, tokens: list[str]) -> V2AdminCommand | str:
    if len(tokens) != 3:
        return f"{tokens[0]} requires: {tokens[0]} <platform> <platform_user_id>"
    platform = parse_platform(tokens[1])
    if platform is None:
        return "unsupported platform"
    return V2AdminCommand(
        name,
        {
            "platform": platform,
            "platform_user_id": tokens[2],
        },
    )


def parse_bind_accounts(tokens: list[str]) -> V2AdminCommand | str:
    if len(tokens) != 5:
        return "绑定账号 requires: 绑定账号 <platform> <platform_user_id> <platform> <platform_user_id>"
    source_platform = parse_platform(tokens[1])
    target_platform = parse_platform(tokens[3])
    if source_platform is None or target_platform is None:
        return "unsupported platform"
    return V2AdminCommand(
        "bind_accounts",
        {
            "source_platform": source_platform,
            "source_platform_user_id": tokens[2],
            "target_platform": target_platform,
            "target_platform_user_id": tokens[4],
        },
    )


def parse_claim_command(name: str, tokens: list[str]) -> V2AdminCommand | str:
    if len(tokens) != 2:
        return f"{tokens[0]} requires: {tokens[0]} <claim_id>"
    return V2AdminCommand(name, {"claim_id": tokens[1]})


def parse_platform(value: str) -> PlatformName | None:
    if value in {"qq", "wechat"}:
        return value  # type: ignore[return-value]
    return None


def parse_relationship_type(value: str) -> RelationshipType | None:
    if value in {"admin_partner", "normal_friend", "blocked"}:
        return value  # type: ignore[return-value]
    return None

