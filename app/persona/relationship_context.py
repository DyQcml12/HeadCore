from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.persona.relationship_roles import canonical_relationship_role
from app.persona.tone_policy import build_tone_policy_instruction
from app.storage.chat_repository import ContactRecord
from app.storage.chat_repository import ChatRepository


@dataclass(frozen=True)
class RelationshipContext:
    contact: ContactRecord | None
    is_identity_bound: bool
    role: str
    authority_level: int
    affection_level: int
    trust_level: int
    prompt_instruction: str
    allow_long_term_profile: bool
    allow_memory_write: bool


DEFAULT_RELATIONSHIP_CONTEXT = RelationshipContext(
    contact=None,
    is_identity_bound=False,
    role="normal_friend",
    authority_level=10,
    affection_level=10,
    trust_level=10,
    prompt_instruction=(
        "关系对象：未绑定平台身份的普通朋友/相关联系人。自然、礼貌、短句接话，"
        "不发展亲密关系，不写入长期用户画像。"
    ),
    allow_long_term_profile=False,
    allow_memory_write=False,
)


async def resolve_relationship_context(
    repository: ChatRepository,
    settings: Settings,
    *,
    platform: str | None,
    platform_user_id: str | None,
    platform_group_id: str | None = None,
) -> RelationshipContext:
    if not platform or not platform_user_id:
        return DEFAULT_RELATIONSHIP_CONTEXT
    contact = await repository.resolve_contact(
        platform=platform,
        platform_user_id=platform_user_id,
        platform_group_id=platform_group_id,
        owner_platform_user_ids=parse_owner_platform_ids(settings.hutao_owner_qq_ids)
        if platform.strip().lower() == "qq"
        else set(),
    )
    return build_relationship_context(contact)


def parse_owner_platform_ids(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def build_relationship_context(contact: ContactRecord) -> RelationshipContext:
    raw_role = contact.relationship_role
    role = canonical_relationship_role(raw_role)
    if role == "admin_partner":
        return RelationshipContext(
            contact=contact,
            is_identity_bound=True,
            role=role,
            authority_level=contact.authority_level,
            affection_level=contact.affection_level,
            trust_level=contact.trust_level,
            prompt_instruction=(
                "当前对象是管理员/爱人。对方拥有最高权限、最高信任和最高情感权重。"
            "胡桃对这个人最偏心、最在意、最愿意陪伴；关系可以接近恋人式熟悉，"
                "但不要主动宣布关系、不要油腻、不要占有、不要恋爱脑。"
                "可以使用管理员/爱人的长期画像和长期记忆。"
                + build_tone_policy_instruction(role)
            ),
            allow_long_term_profile=True,
            allow_memory_write=True,
        )
    if role == "blocked":
        return RelationshipContext(
            contact=contact,
            is_identity_bound=True,
            role=role,
            authority_level=0,
            affection_level=0,
            trust_level=0,
            prompt_instruction="当前对象在黑名单中。不要继续展开聊天。" + build_tone_policy_instruction(role),
            allow_long_term_profile=False,
            allow_memory_write=False,
        )
    prompt = (
        "当前对象是普通朋友或相关联系人。可以自然友好地接话，"
        "但不要表现出管理员/爱人级别亲密，不使用管理员/爱人的长期画像，"
        "不替对方编身份，不因为聊得多就自动升级亲密关系。"
        "不要嘴臭、辱骂、羞辱或刺激对方；绝对不要让任何人去死、自杀或伤害自己。"
        + build_tone_policy_instruction(role)
    )
    return RelationshipContext(
        contact=contact,
        is_identity_bound=True,
        role=role,
        authority_level=contact.authority_level,
        affection_level=contact.affection_level,
        trust_level=contact.trust_level,
        prompt_instruction=prompt,
        allow_long_term_profile=False,
        allow_memory_write=False,
    )
