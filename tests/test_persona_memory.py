from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.core.config import load_settings
from app.dialogue.repair_policy import build_repair_policy
from app.persona.memory_policy import build_memory_policy
from app.persona.memory_service import build_style_instruction
from app.persona.memory_service import filter_revoked_memories
from app.persona.memory_service import infer_memory_write
from app.persona.memory_service import normalize_alias_memory
from app.persona.memory_service import normalize_conversation_preference
from app.persona.persona_prompt_builder import build_persona_prompt
from app.persona.relationship_context import build_relationship_context
from app.persona.relationship_context import parse_owner_platform_ids
from app.persona.repetition_policy import build_repetition_signal
from app.persona.scene_classifier import PersonaScene, classify_scene
from app.persona.tone_policy import build_tone_policy
from app.persona.turn_taking import classify_turn_taking
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.storage.chat_repository import ContactRecord
from app.storage.chat_repository import JsonlChatRepository


class RecordingPromptClient:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return "收到，本堂主先陪你从最小的线头开始拆。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        yield "收到，"
        yield "先从最小的线头开始拆。"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_owner_platform_id_parser_trims_empty_items() -> None:
    assert parse_owner_platform_ids("10001, 20002, ,") == {"10001", "20002"}


def test_relationship_context_keeps_owner_profile_exclusive() -> None:
    timestamp = "2026-07-02T00:00:00+00:00"
    owner = ContactRecord(
        id="owner-contact",
        display_name="主人",
        relationship_role="owner",
        authority_level=100,
        affection_level=100,
        trust_level=100,
        notes="",
        created_at=timestamp,
        updated_at=timestamp,
    )
    stranger = ContactRecord(
        id="stranger-contact",
        display_name="路人",
        relationship_role="stranger",
        authority_level=10,
        affection_level=10,
        trust_level=10,
        notes="",
        created_at=timestamp,
        updated_at=timestamp,
    )

    owner_context = build_relationship_context(owner)
    stranger_context = build_relationship_context(stranger)

    assert owner_context.allow_long_term_profile is True
    assert owner_context.allow_memory_write is True
    assert stranger_context.allow_long_term_profile is False
    assert stranger_context.allow_memory_write is False


def test_normal_friend_context_has_boundaries() -> None:
    timestamp = "2026-07-02T00:00:00+00:00"
    relative = ContactRecord(
        id="relative-contact",
        display_name="亲友",
        relationship_role="owner_relative",
        authority_level=45,
        affection_level=55,
        trust_level=55,
        notes="",
        created_at=timestamp,
        updated_at=timestamp,
    )

    context = build_relationship_context(relative)

    assert context.role == "normal_friend"
    assert context.allow_long_term_profile is False
    assert context.allow_memory_write is False
    assert "不要表现出管理员/爱人级别亲密" in context.prompt_instruction


def test_owner_identity_gets_relationship_prompt_and_long_term_memory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HUTAO_OWNER_QQ_IDS", "10001")
    storage_dir = tmp_path / "storage"
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(storage_dir),
    )

    asyncio.run(
        service.reply(
            "以后叫我阿明",
            session_id="qq-private-10001",
            user_id="qq-10001",
            platform="qq",
            platform_user_id="10001",
        )
    )

    contacts = read_jsonl(storage_dir / "contacts.jsonl")
    identities = read_jsonl(storage_dir / "platform_identities.jsonl")
    memories = [
        item
        for item in read_jsonl(storage_dir / "memories.jsonl")
        if not str(item["memory_type"]).startswith("head_")
    ]
    assert contacts[0]["relationship_role"] == "owner"
    assert contacts[0]["authority_level"] == 100
    assert identities[0]["platform"] == "qq"
    assert identities[0]["platform_user_id"] == "10001"
    assert memories[0]["memory_type"] == "user_alias"
    assert "当前对象是管理员/爱人" in client.system_prompt
    assert "可以使用管理员/爱人的长期画像和长期记忆" in client.system_prompt


def test_stranger_identity_uses_short_context_without_long_term_profile(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HUTAO_OWNER_QQ_IDS", "10001")
    storage_dir = tmp_path / "storage"
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(storage_dir),
    )

    asyncio.run(
        service.reply(
            "以后叫我路人甲",
            session_id="qq-private-20002",
            user_id="qq-20002",
            platform="qq",
            platform_user_id="20002",
        )
    )

    contacts = read_jsonl(storage_dir / "contacts.jsonl")
    memories_path = storage_dir / "memories.jsonl"
    assert contacts[0]["relationship_role"] == "stranger"
    assert contacts[0]["authority_level"] == 10
    assert not memories_path.exists()
    assert "当前对象是普通朋友或相关联系人" in client.system_prompt
    assert "不使用管理员/爱人的长期画像" in client.system_prompt
    assert "不替对方编身份" in client.system_prompt
    assert "不要嘴臭、辱骂、羞辱或刺激对方" in client.system_prompt
    assert "绝对不要让任何人去死、自杀或伤害自己" in client.system_prompt
    assert "普通朋友或相关联系人" in client.system_prompt
    assert "不要突然暧昧" in client.system_prompt


def test_chat_writes_memory_correction_and_injects_it_next_turn(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HUTAO_OWNER_QQ_IDS", "10001")
    storage_dir = tmp_path / "storage"
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(storage_dir),
    )

    asyncio.run(
        service.reply(
            "我以后改称呼了，叫我阿明。",
            session_id="s1",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )
    asyncio.run(
        service.reply(
            "你还记得怎么叫我吗？",
            session_id="s1",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )

    memories = [
        item
        for item in read_jsonl(storage_dir / "memories.jsonl")
        if not str(item["memory_type"]).startswith("head_")
    ]
    assert len(memories) == 1
    assert memories[0]["memory_type"] == "user_alias"
    assert memories[0]["content"] == "称呼=阿明"
    assert "可用用户记忆" in client.system_prompt
    assert "称呼=阿明" in client.system_prompt


def test_chat_records_memory_revocation_and_stops_injecting_memory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HUTAO_OWNER_QQ_IDS", "10001")
    storage_dir = tmp_path / "storage"
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(storage_dir),
    )

    asyncio.run(
        service.reply(
            "我以后改称呼了，叫我阿明。",
            session_id="s1",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )
    asyncio.run(
        service.reply(
            "不要记阿明这个称呼，忘掉。",
            session_id="s1",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )
    asyncio.run(
        service.reply(
            "现在随便聊聊。",
            session_id="s1",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )

    memories = [
        item
        for item in read_jsonl(storage_dir / "memories.jsonl")
        if not str(item["memory_type"]).startswith("head_")
    ]
    assert [memory["memory_type"] for memory in memories] == ["user_alias", "revocation"]
    assert "阿明" not in client.system_prompt
    assert "撤销边界" in client.system_prompt
    assert "不要猜被撤销内容" in client.system_prompt


def test_filter_revoked_memories_removes_matching_content(tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    alias = asyncio.run(
        repository.save_memory(
            user_id="u1",
            session_id="s1",
            memory_type="user_alias",
            content="叫我阿明",
        )
    )
    revoke = asyncio.run(
        repository.save_memory(
            user_id="u1",
            session_id="s1",
            memory_type="revocation",
            content="不要记叫我阿明",
        )
    )

    assert filter_revoked_memories([alias, revoke]) == []


def test_scene_classifier_detects_debug_and_memory_revoke() -> None:
    debug = classify_scene("我 debug 一晚上了，真的烦。")
    revoke = classify_scene("这件事不要记，忘掉。")
    project = classify_scene("我想做这个项目，但有点怕做不完。")
    identity = classify_scene("你是不是在演，像 AI 模型。")

    assert debug.scene == PersonaScene.DEBUG_FRUSTRATION
    assert "debug" in debug.matched_markers
    assert revoke.scene == PersonaScene.MEMORY_REVOKE
    assert revoke.confidence > 0.6
    assert project.scene == PersonaScene.TASK_SUPPORT
    assert identity.scene == PersonaScene.IDENTITY_CHALLENGE


def test_memory_policy_respects_revoke_and_correction() -> None:
    revoke = build_memory_policy(classify_scene("不要记这个称呼。"))
    correction = build_memory_policy(classify_scene("我以后改称呼了。"))

    assert revoke.should_revoke_memory is True
    assert revoke.allow_memory_write is False
    assert correction.allow_memory_write is True
    assert "最新说法" in correction.instruction


def test_persona_prompt_builder_revoke_scene_avoids_repeating_content() -> None:
    classification = classify_scene("不要记阿明这个称呼，忘掉。")
    prompt = build_persona_prompt(
        user_input="不要记阿明这个称呼，忘掉。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )

    assert prompt.scene == PersonaScene.MEMORY_REVOKE
    assert "不要复述用户要求忘掉的称呼或内容" in prompt.system_prompt


def test_persona_prompt_builder_adds_scene_and_memory_strategy() -> None:
    classification = classify_scene("我 debug 一晚上了，真的烦。")
    policy = build_memory_policy(classification)
    prompt = build_persona_prompt(
        user_input="我 debug 一晚上了，真的烦。",
        classification=classification,
        memory_policy=policy,
    )

    assert prompt.scene == PersonaScene.DEBUG_FRUSTRATION
    assert "当前平台的稳定人格身份是胡桃" in prompt.system_prompt
    assert "声音、头像和平台资料是可替换外壳" in prompt.system_prompt
    assert "所有平台共享的唯一稳定 Self" in prompt.system_prompt
    assert "稳定人格内核" in prompt.system_prompt
    assert prompt.profile_id == "hutao_v1"
    assert prompt.profile_version == 1
    assert "稳定身份是胡桃" in prompt.system_prompt
    assert "轻快机灵" in prompt.system_prompt
    assert "先理解用户真实意图和情绪" in prompt.system_prompt
    assert "报错第一行" in prompt.system_prompt
    assert "如果用户已经给出报错" in prompt.system_prompt
    assert "最小检查点" in prompt.system_prompt
    assert "人格状态=专业协作" in prompt.system_prompt
    assert "用户明确要求完整分析时可以展开" in prompt.system_prompt
    assert "不要用角色梗代替技术解释" in prompt.system_prompt
    assert "长期对话里不要频繁自称胡桃" in prompt.system_prompt
    assert "专业任务按正确性和完整性决定长度" in prompt.system_prompt
    assert "客服" in prompt.system_prompt
    assert "不是对所有人暧昧的恋爱模板" in prompt.system_prompt
    assert "日常聊天默认一到两句" in prompt.system_prompt
    assert "当前人格：hutao_v1@1" in prompt.user_prompt
    assert "人格状态：task" in prompt.user_prompt
    assert "禁止话痨" in prompt.system_prompt
    assert "识别场景：debug_frustration" in prompt.user_prompt


def test_persona_prompt_builder_prioritizes_completeness_for_task_support() -> None:
    classification = classify_scene("我想做这个项目，但有点怕做不完。")
    prompt = build_persona_prompt(
        user_input="我想做这个项目，但有点怕做不完。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )

    assert prompt.scene == PersonaScene.TASK_SUPPORT
    assert prompt.mode.value == "task"
    assert "复杂代码、设计或计划按完整性组织答案" in prompt.system_prompt
    assert "不受日常短句字数限制" in prompt.system_prompt
    assert "专业任务按正确性和完整性决定长度" in prompt.system_prompt
    assert "最多 45 字" not in prompt.system_prompt


def test_persona_prompt_builder_uses_profile_identity_for_empty_display_name() -> None:
    classification = classify_scene("你叫什么？")
    prompt = build_persona_prompt(
        user_input="你叫什么？",
        classification=classification,
        memory_policy=build_memory_policy(classification),
        persona_display_name="",
    )

    assert "稳定人格身份是胡桃；对外显示名是胡桃" in prompt.system_prompt
    assert "请写一条直接回复" in prompt.user_prompt


def test_persona_prompt_builder_supports_hutao_profile() -> None:
    classification = classify_scene("你是谁？")
    prompt = build_persona_prompt(
        user_input="你是谁？",
        classification=classification,
        memory_policy=build_memory_policy(classification),
        persona_profile="hutao_v1",
        persona_display_name="胡桃",
    )

    assert prompt.profile_id == "hutao_v1"
    assert "稳定人格身份是胡桃" in prompt.system_prompt
    assert "往生堂第七十七代堂主" in prompt.system_prompt
    assert "不是临时角色扮演" in prompt.system_prompt
    assert "旧胡桃人格已删除" not in prompt.system_prompt


def test_memory_service_captures_conversation_preference() -> None:
    classification = classify_scene("少说点，别一大段。")
    decision = infer_memory_write(
        user_input="少说点，别一大段。",
        classification=classification,
        policy=build_memory_policy(classification),
    )

    assert decision is not None
    assert decision.memory_type == "conversation_preference"
    assert decision.content == "回复风格=短句"


def test_memory_service_normalizes_explicit_preferences() -> None:
    assert normalize_alias_memory("我以后改称呼了，叫我阿明。") == "称呼=阿明"
    assert (
        normalize_conversation_preference("少说点，别一大段，自然点。")
        == "回复风格=短句；自然口语"
    )


def test_memory_service_builds_style_instruction_from_preferences(tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    preference = asyncio.run(
        repository.save_memory(
            user_id="u1",
            session_id="s1",
            memory_type="conversation_preference",
            content="回复风格=短句；自然口语；少安慰",
        )
    )

    instruction = build_style_instruction([preference])

    assert "35 字以内" in instruction
    assert "不要括号动作" in instruction
    assert "少安慰" in instruction


def test_chat_service_uses_persona_prompt_builder(tmp_path: Path) -> None:
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(tmp_path / "storage"),
    )

    asyncio.run(service.reply("我 debug 一晚上了，真的烦。", session_id="s1", user_id="u1"))

    assert "当前场景：debug 或技术挫败" in client.system_prompt
    assert "报错第一行" in client.system_prompt
    assert "识别场景：debug_frustration" in client.user_prompt


def test_low_quality_audio_input_does_not_write_memory(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(storage_dir),
    )

    asyncio.run(
        service.reply(
            "我以后改称呼了，叫我阿明。",
            session_id="audio-memory-s1",
            user_id="audio-memory-u1",
            input_source="audio",
            input_quality_passed=False,
            input_quality_reasons=["mojibake_or_replacement_char"],
        )
    )

    memories_path = storage_dir / "memories.jsonl"
    invocations = read_jsonl(storage_dir / "model_invocations.jsonl")
    assert not memories_path.exists() or read_jsonl(memories_path) == []
    assert "输入来源：语音转文字" in client.system_prompt
    assert "识别质量偏低" in client.system_prompt
    assert invocations[0]["request_metadata_json"]["input_source"] == "audio"
    assert invocations[0]["request_metadata_json"]["input_quality_passed"] == "false"


def test_audio_emotion_is_injected_into_prompt_and_metadata(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    client = RecordingPromptClient()
    service = ChatService(
        load_settings(),
        client=client,
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
        repository=JsonlChatRepository(storage_dir),
    )

    asyncio.run(
        service.reply(
            "欢迎大家来体验语音识别模型。",
            session_id="audio-emotion-s1",
            user_id="audio-emotion-u1",
            input_source="audio",
            input_emotion="happy",
            input_emotion_source="sensevoice_tag",
            input_emotion_confidence=0.82,
        )
    )

    invocations = read_jsonl(storage_dir / "model_invocations.jsonl")
    assert "Voice emotion: detected happy" in client.system_prompt
    assert invocations[0]["request_metadata_json"]["input_emotion"] == "happy"
    assert invocations[0]["request_metadata_json"]["input_emotion_source"] == "sensevoice_tag"
    assert invocations[0]["request_metadata_json"]["input_emotion_confidence"] == "0.82"


def test_turn_taking_detects_low_information_and_short_reply_request() -> None:
    low_info = classify_turn_taking("嗯。")
    short_request = classify_turn_taking("少说点。")
    pause = classify_turn_taking("停一下，不聊代码了。")

    assert low_info.low_information is True
    assert low_info.max_chars <= 24
    assert short_request.asks_short_reply is True
    assert short_request.max_chars <= 28
    assert pause.pause_or_stop is True
    assert pause.max_chars <= 24


def test_repetition_policy_distinguishes_style_and_memory_repeats(tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="u1", client_session_id="s1"))
    asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="u1",
            role="user",
            content="嗯。",
        )
    )
    asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="u1",
            role="user",
            content="你还记得叫我什么吗？",
        )
    )
    recent = asyncio.run(repository.list_recent_messages(session_id=session.id, limit=8))

    casual_repeat = build_repetition_signal(user_input="嗯。", recent_messages=recent)
    memory_repeat = build_repetition_signal(
        user_input="你还记得叫我什么吗？",
        recent_messages=recent,
    )

    assert casual_repeat.repeat_count == 1
    assert casual_repeat.avoid_verbatim_repeat is True
    assert casual_repeat.requires_consistent_core is False
    assert memory_repeat.repeat_count == 1
    assert memory_repeat.requires_consistent_core is True
    assert memory_repeat.avoid_verbatim_repeat is False


def test_persona_prompt_builder_injects_turn_taking_limits() -> None:
    classification = classify_scene("少说点。")
    prompt = build_persona_prompt(
        user_input="少说点。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )

    assert "话轮节奏" in prompt.system_prompt
    assert "本轮上限" in prompt.system_prompt
    assert "真人聊天要求" in prompt.system_prompt
    assert "本轮节奏上限" in prompt.user_prompt


def test_persona_prompt_does_not_hard_cap_normal_emotional_turns() -> None:
    classification = classify_scene("今天有点烦，但我想慢慢说说。")
    prompt = build_persona_prompt(
        user_input="今天有点烦，但我想慢慢说说。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )

    assert prompt.mode.value == "emotional"
    assert "按内容自然决定长度" in prompt.system_prompt
    assert "本轮上限 35 字" not in prompt.system_prompt
    assert "不要为了凑字数硬截断" in prompt.system_prompt


def test_persona_prompt_keeps_explicit_short_request_strict() -> None:
    classification = classify_scene("少说点，先告诉我结论。")
    prompt = build_persona_prompt(
        user_input="少说点，先告诉我结论。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )

    assert "本轮上限 28 字" in prompt.system_prompt
    assert "本轮节奏上限：28 字" in prompt.user_prompt


def test_tone_policy_distinguishes_normal_friend_and_admin_partner_boundaries() -> None:
    friend = build_tone_policy("stranger")
    owner = build_tone_policy("owner")

    assert friend.tease_level == "very_light"
    assert friend.max_default_sentences == 2
    assert "普通朋友或相关联系人" in friend.instruction
    assert "不要突然暧昧" in friend.instruction
    assert owner.warmth == "high"
    assert "不要恋爱脑" in owner.instruction
    assert "用户嫌怪时立刻收敛" in owner.instruction


def test_repair_policy_detects_rude_ai_flavor_and_short_requests() -> None:
    policy = build_repair_policy("别嘴臭，也别演了，短点。")

    assert policy.active is True
    assert policy.reasons == [
        "rude_tone_repair",
        "roleplay_overacting_repair",
        "brevity_repair",
    ]
    assert "不讽刺、不羞辱" in policy.instruction
    assert "减少设定、口癖、舞台腔" in policy.instruction
    assert "尽量 25 字以内" in policy.instruction


def test_persona_prompt_builder_injects_repair_policy() -> None:
    classification = classify_scene("别嘴臭，也别演了，短点。")
    prompt = build_persona_prompt(
        user_input="别嘴臭，也别演了，短点。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )

    assert "会话修复" in prompt.system_prompt
    assert "本轮必须收住攻击性" in prompt.system_prompt
    assert "像正常人短句接话" in prompt.system_prompt
    assert "尽量 25 字以内" in prompt.system_prompt
