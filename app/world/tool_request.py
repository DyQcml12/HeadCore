from __future__ import annotations

import re
from dataclasses import dataclass


TOOL_CAPABILITY_WEATHER = "weather"
TOOL_CAPABILITY_NEWS = "news"
TOOL_CAPABILITY_POLICY = "policy"
TOOL_CAPABILITIES = frozenset({TOOL_CAPABILITY_WEATHER, TOOL_CAPABILITY_NEWS, TOOL_CAPABILITY_POLICY})

_CAPABILITY_ALIASES = {
    "天气": TOOL_CAPABILITY_WEATHER,
    "weather": TOOL_CAPABILITY_WEATHER,
    "新闻": TOOL_CAPABILITY_NEWS,
    "news": TOOL_CAPABILITY_NEWS,
    "政策": TOOL_CAPABILITY_POLICY,
    "policy": TOOL_CAPABILITY_POLICY,
}
_MARKER_PATTERN = re.compile(
    r"\[USE_WORLD_TOOL:(天气|新闻|政策|weather|news|policy):([^\]]{1,120})\]"
)

TOOL_DENIED_REPLY = "世界工具现在没有可用证据，我先按已有信息回答，不编造实时数据。"


@dataclass(frozen=True)
class WorldToolRequest:
    capability: str
    query: str

    def __post_init__(self) -> None:
        canonical = _CAPABILITY_ALIASES.get(self.capability)
        if canonical is None:
            raise ValueError(f"unsupported world tool capability: {self.capability}")
        object.__setattr__(self, "capability", canonical)
        normalized = self.query.strip()
        if not normalized or len(normalized) > 120:
            raise ValueError("world tool query must be 1-120 characters")
        if any(char in normalized for char in "\r\n\x00"):
            raise ValueError("world tool query must be one bounded line")
        object.__setattr__(self, "query", normalized)

    def as_user_query(self) -> str:
        if self.capability == TOOL_CAPABILITY_WEATHER:
            return f"天气 {self.query}"
        if self.capability == TOOL_CAPABILITY_NEWS:
            return f"新闻 {self.query}"
        return f"政策 {self.query}"


def parse_tool_request(text: str) -> WorldToolRequest | None:
    """Parse a strict tool marker.

    Only a response that is EXACTLY one marker (no surrounding prose) is
    treated as a tool request, so markers inside normal replies never
    trigger a tool call and are never shown to the user raw.
    """
    stripped = text.strip()
    match = _MARKER_PATTERN.fullmatch(stripped)
    if match is None:
        return None
    try:
        return WorldToolRequest(capability=match.group(1), query=match.group(2))
    except ValueError:
        return None


def render_tool_protocol_instruction() -> str:
    """System prompt instruction enabling the single-step tool loop."""
    return (
        "[工具协议] 若回答需要实时天气、新闻或政策信息，而系统上下文没有对应证据："
        "只输出一个工具标记并停止，格式严格为 "
        "[USE_WORLD_TOOL:天气:<城市或区划>] 或 [USE_WORLD_TOOL:新闻:<主题>] "
        "或 [USE_WORLD_TOOL:政策:<主题>]；不要编造数值。工具结果会作为证据追加后重新生成。"
    )
