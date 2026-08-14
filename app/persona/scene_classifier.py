from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PersonaScene(StrEnum):
    DAILY_CHAT = "daily_chat"
    EMOTIONAL_SUPPORT = "emotional_support"
    DEBUG_FRUSTRATION = "debug_frustration"
    TASK_SUPPORT = "task_support"
    AFFECTION = "affection"
    LIFE_DEATH = "life_death"
    MEMORY_CORRECTION = "memory_correction"
    MEMORY_REVOKE = "memory_revoke"
    IDENTITY_CHALLENGE = "identity_challenge"


@dataclass(frozen=True)
class SceneClassification:
    scene: PersonaScene
    confidence: float
    matched_markers: list[str]


SCENE_MARKERS: tuple[tuple[PersonaScene, tuple[str, ...]], ...] = (
    (
        PersonaScene.MEMORY_REVOKE,
        ("不要记", "别记", "不准记", "忘掉", "撤销", "删掉", "forget"),
    ),
    (
        PersonaScene.MEMORY_CORRECTION,
        ("记错", "改了称呼", "改称呼", "纠正", "以后叫", "不是这个"),
    ),
    (
        PersonaScene.DEBUG_FRUSTRATION,
        (
            "debug",
            "bug",
            "报错",
            "异常",
            "typeerror",
            "valueerror",
            "attributeerror",
            "traceback",
            "崩了",
            "跑不起来",
            "一晚上",
        ),
    ),
    (
        PersonaScene.LIFE_DEATH,
        ("死亡", "死", "去世", "离开了", "葬礼", "告别", "往生"),
    ),
    (
        PersonaScene.IDENTITY_CHALLENGE,
        (
            "你是谁",
            "你现在是谁",
            "你叫什么",
            "自我介绍",
            "你是不是在演",
            "你在演吗",
            "你的设定",
            "你是ai",
            "你是 ai",
            "ai吗",
            "你是模型",
            "是真人吗",
            "有意识吗",
        ),
    ),
    (
        PersonaScene.AFFECTION,
        ("想你", "喜欢你", "陪我", "亲近", "抱抱", "爱你"),
    ),
    (
        PersonaScene.TASK_SUPPORT,
        ("代码", "项目", "计划", "后端", "前端", "数据库", "接口", "测试", "论文", "模型", "训练", "下一步"),
    ),
    (
        PersonaScene.EMOTIONAL_SUPPORT,
        ("累", "烦", "焦虑", "难受", "崩溃", "没动力", "内耗", "怕"),
    ),
)


def classify_scene(user_input: str) -> SceneClassification:
    text = user_input.lower()
    for scene, markers in SCENE_MARKERS:
        matched = [marker for marker in markers if marker.lower() in text]
        if matched:
            confidence = min(1.0, 0.65 + len(matched) * 0.1)
            return SceneClassification(scene=scene, confidence=confidence, matched_markers=matched)
    return SceneClassification(
        scene=PersonaScene.DAILY_CHAT,
        confidence=0.5,
        matched_markers=[],
    )
