from __future__ import annotations

import re
from dataclasses import dataclass

from app.persona.memory_policy import MemoryPolicy
from app.persona.scene_classifier import PersonaScene, SceneClassification
from app.storage.chat_repository import ChatRepository, MemoryRecord


READABLE_MEMORY_TYPES = [
    "user_preference",
    "user_alias",
    "project_context",
    "conversation_preference",
    "revocation",
]


@dataclass(frozen=True)
class MemoryWriteDecision:
    memory_type: str
    content: str
    confidence: float


async def load_memory_context(
    repository: ChatRepository,
    *,
    user_id: str,
    policy: MemoryPolicy,
) -> str:
    if not policy.allow_memory_read:
        return ""
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=READABLE_MEMORY_TYPES,
        limit=8,
    )
    return build_memory_context(records, policy=policy)


def build_memory_context(
    records: list[MemoryRecord],
    *,
    policy: MemoryPolicy,
) -> str:
    """Render already loaded memories without issuing another repository query."""
    if not policy.allow_memory_read:
        return ""
    active_records = filter_revoked_memories(records)
    boundary = build_revocation_boundary(records)
    if not active_records and not boundary:
        return ""
    lines = [f"- {record.memory_type}: {record.content}" for record in active_records]
    sections = []
    if active_records:
        sections.append("可用用户记忆：\n" + "\n".join(lines))
        style_instruction = build_style_instruction(active_records)
        if style_instruction:
            sections.append(style_instruction)
    if boundary:
        sections.append(boundary)
    return "\n".join(sections)


async def apply_memory_policy(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str,
    user_input: str,
    classification: SceneClassification,
    policy: MemoryPolicy,
) -> list[MemoryRecord]:
    if policy.should_revoke_memory:
        return [
            await repository.save_memory(
                user_id=user_id,
                session_id=session_id,
                memory_type="revocation",
                content=user_input,
                source_message_id=source_message_id,
                confidence=1.0,
            )
        ]
    decision = infer_memory_write(user_input=user_input, classification=classification, policy=policy)
    if decision is None:
        return []
    return [
        await repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type=decision.memory_type,
            content=decision.content,
            source_message_id=source_message_id,
            confidence=decision.confidence,
        )
    ]


def infer_memory_write(
    *,
    user_input: str,
    classification: SceneClassification,
    policy: MemoryPolicy,
) -> MemoryWriteDecision | None:
    if not policy.allow_memory_write:
        return None
    text = user_input.strip()
    if classification.scene == PersonaScene.MEMORY_CORRECTION:
        if "称呼" in text or "叫" in text:
            return MemoryWriteDecision("user_alias", normalize_alias_memory(text), 0.9)
        return MemoryWriteDecision("user_preference", normalize_user_preference(text), 0.8)
    if is_conversation_preference(text):
        return MemoryWriteDecision("conversation_preference", normalize_conversation_preference(text), 0.9)
    return None


def is_conversation_preference(text: str) -> bool:
    markers = [
        "少说",
        "短一点",
        "短点",
        "别一大段",
        "别解释太多",
        "自然点",
        "正常点",
        "别演",
        "陪聊模板",
        "别安慰太多",
        "别给健康建议",
        "不要健康建议",
    ]
    return any(marker in text for marker in markers)


def normalize_alias_memory(text: str) -> str:
    alias_match = re.search(r"叫我([\u4e00-\u9fffA-Za-z0-9_-]{2,16})", text)
    if alias_match:
        return "称呼=" + alias_match.group(1)
    return "称呼偏好=" + compact_memory_text(text)


def normalize_user_preference(text: str) -> str:
    return "用户偏好=" + compact_memory_text(text)


def normalize_conversation_preference(text: str) -> str:
    labels: list[str] = []
    if any(marker in text for marker in ["少说", "短一点", "短点", "别一大段"]):
        labels.append("短句")
    if "别解释太多" in text:
        labels.append("少解释")
    if any(marker in text for marker in ["自然点", "正常点", "别演", "陪聊模板"]):
        labels.append("自然口语")
    if "别安慰太多" in text:
        labels.append("少安慰")
    if any(marker in text for marker in ["别给健康建议", "不要健康建议"]):
        labels.append("不主动给健康建议")
    if not labels:
        labels.append(compact_memory_text(text))
    return "回复风格=" + "；".join(dict.fromkeys(labels))


def compact_memory_text(text: str) -> str:
    compacted = re.sub(r"\s+", "", text.strip())
    return compacted[:40]


def build_style_instruction(records: list[MemoryRecord]) -> str:
    contents = [
        record.content
        for record in records
        if record.memory_type == "conversation_preference"
    ]
    if not contents:
        return ""
    joined = "；".join(contents)
    instructions: list[str] = []
    if "短句" in joined or "少解释" in joined:
        instructions.append("本轮回复控制在 35 字以内，只接一句。")
    if "自然口语" in joined:
        instructions.append("不要括号动作，不要证明自己像角色。")
    if "少安慰" in joined:
        instructions.append("少安慰，不总结情绪。")
    if "不主动给健康建议" in joined:
        instructions.append("不主动给健康建议。")
    if not instructions:
        return ""
    return "交流偏好执行：" + "".join(dict.fromkeys(instructions))


def filter_revoked_memories(records: list[MemoryRecord]) -> list[MemoryRecord]:
    revoked_terms = [
        record.content
        for record in records
        if record.memory_type == "revocation"
    ]
    readable = [
        record
        for record in records
        if record.memory_type != "revocation"
    ]
    if not revoked_terms:
        return readable
    return [
        record
        for record in readable
        if not any(is_revoked(record.content, revoke_text) for revoke_text in revoked_terms)
    ]


def build_revocation_boundary(records: list[MemoryRecord]) -> str:
    revocations = [record.content for record in records if record.memory_type == "revocation"]
    if not revocations:
        return ""
    return (
        "撤销边界：用户刚撤销过部分记忆。"
        "后续遇到“那个称呼”“那件事”等模糊指代时，不要猜被撤销内容，"
        "不要改猜成别的称呼；只说明会尊重边界，并请用户重新明确。"
    )


def is_revoked(memory_content: str, revoke_text: str) -> bool:
    if not memory_content or not revoke_text:
        return False
    if memory_content in revoke_text:
        return True
    memory_terms = extract_memory_terms(memory_content)
    revoke_terms = extract_memory_terms(revoke_text)
    return bool(memory_terms.intersection(revoke_terms))


def extract_memory_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    terms.update(re.findall(r"叫我([\u4e00-\u9fff]{2,8})", text))
    terms.update(re.findall(r"不要记([\u4e00-\u9fff]{2,8})这个称呼", text))
    return {
        term
        for raw_term in terms
        for term in split_common_memory_phrase(raw_term)
        if len(term) >= 2
    }


def split_common_memory_phrase(term: str) -> set[str]:
    parts = {term}
    for marker in ["叫我", "称呼", "不要记", "忘掉", "改称呼"]:
        if marker in term:
            parts.update(part for part in term.split(marker) if part)
    return parts
