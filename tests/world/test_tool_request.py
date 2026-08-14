from __future__ import annotations

import pytest

from app.world.tool_request import (
    TOOL_CAPABILITIES,
    TOOL_DENIED_REPLY,
    parse_tool_request,
    render_tool_protocol_instruction,
)


def test_marker_full_match_parses() -> None:
    request = parse_tool_request("[USE_WORLD_TOOL:天气:上海]")

    assert request is not None
    assert request.capability == "weather"
    assert request.query == "上海"
    assert request.as_user_query() == "天气 上海"


def test_embedded_marker_is_not_a_tool_request() -> None:
    assert parse_tool_request("我帮你查 [USE_WORLD_TOOL:天气:上海] 吧") is None
    assert parse_tool_request("普通回复") is None
    assert parse_tool_request("") is None


def test_chinese_capability_alias_is_canonicalized() -> None:
    request = parse_tool_request("[USE_WORLD_TOOL:天气:上海]")
    assert request is not None
    assert request.capability == "weather"


def test_unknown_capability_or_bad_query_is_rejected() -> None:
    assert parse_tool_request("[USE_WORLD_TOOL:股票:茅台]") is None
    assert parse_tool_request("[USE_WORLD_TOOL:天气:]") is None
    assert parse_tool_request("[USE_WORLD_TOOL:天气:" + "长" * 200 + "]") is None


def test_news_and_policy_queries_map_to_intent_text() -> None:
    news = parse_tool_request("[USE_WORLD_TOOL:新闻:科技]")
    policy = parse_tool_request("[USE_WORLD_TOOL:政策:国务院]")

    assert news is not None and news.as_user_query() == "新闻 科技"
    assert policy is not None and policy.as_user_query() == "政策 国务院"


def test_instruction_mentions_strict_format_and_no_fabrication() -> None:
    instruction = render_tool_protocol_instruction()

    assert "USE_WORLD_TOOL" in instruction
    assert "不要编造" in instruction
    assert "天气" in instruction and "新闻" in instruction and "政策" in instruction


def test_denial_reply_never_contains_raw_marker() -> None:
    assert "USE_WORLD_TOOL" not in TOOL_DENIED_REPLY
    assert TOOL_CAPABILITIES == frozenset({"weather", "news", "policy"})
