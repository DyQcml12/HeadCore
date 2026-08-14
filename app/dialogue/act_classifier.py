from __future__ import annotations


TECHNICAL_MARKERS = [
    "代码",
    "报错",
    "bug",
    "debug",
    "配置",
    "路径",
    "训练",
    "模型",
    "脚本",
    "接口",
    "日志",
    "方案",
    "步骤",
    "数据库",
    "环境变量",
]

TASK_MARKERS = ["帮我", "写一个", "完整方案", "怎么做", "优化", "设计", "实现", "开发"]
VOICE_REQUEST_MARKERS = [
    "发语音",
    "发个语音",
    "发一段语音",
    "来段语音",
    "来个语音",
    "语音说",
    "念出来",
    "说一句",
    "用语音",
]
STICKER_REQUEST_MARKERS = ["表情包", "发个表情", "来个表情", "贴图"]

EMOTION_MARKERS = {
    "happy": ["哈哈", "开心", "好耶", "笑死", "嘿嘿", "太好了", "赢了", "成功"],
    "angry": ["生气", "气死", "烦死", "可恶", "离谱"],
    "tease": ["阴阳", "吐槽", "坏笑", "得意", "哼", "你不行"],
    "comfort": ["难过", "委屈", "累", "想哭", "抱抱", "陪我", "崩溃"],
    "surprised": ["啊？", "啊?", "真的假的", "不会吧", "震惊"],
}

AFFECTION_MARKERS = ["想你", "喜欢你", "陪我", "抱抱", "在吗", "干嘛呢", "可爱"]
CASUAL_MARKERS = ["哈哈", "笑死", "嘿嘿", "在吗", "干嘛", "好耶", "无语", "离谱", "想你", "陪我"]


def is_technical_context(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(marker.lower() in lowered for marker in TECHNICAL_MARKERS)


def infer_emotion(user_input: str, reply_text: str = "") -> str:
    text = user_input + " " + reply_text
    for emotion, markers in EMOTION_MARKERS.items():
        if any(marker in text for marker in markers):
            return emotion
    return "neutral"


def classify_dialogue_act(user_input: str) -> str:
    stripped = user_input.strip()
    if not stripped:
        return "empty"
    if any(marker in stripped for marker in VOICE_REQUEST_MARKERS):
        return "voice_request"
    if any(marker in stripped for marker in STICKER_REQUEST_MARKERS):
        return "sticker_request"
    if is_technical_context(stripped):
        return "technical_debug"
    if any(marker in stripped for marker in TASK_MARKERS):
        return "task_request"
    if any(marker in stripped for marker in AFFECTION_MARKERS):
        return "affection"
    emotion = infer_emotion(stripped)
    if emotion == "comfort":
        return "emotion_support"
    if emotion == "happy":
        return "celebration"
    if emotion == "tease":
        return "tease"
    if len(stripped) <= 18:
        return "casual_question"
    return "normal_chat"


def has_casual_marker(user_input: str, reply_text: str = "") -> bool:
    text = user_input + " " + reply_text
    return any(marker in text for marker in CASUAL_MARKERS)
