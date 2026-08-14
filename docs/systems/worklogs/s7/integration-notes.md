# S7 集成说明

日期：2026-07-14

## 当前集成状态

- QQ 语音与 sticker 运行时已经接入 S2/S6/S7 contracts。
- Core API 普通、流式和 V2 预处理文本已经接入 S2/S7 contracts，公开 HTTP schema 保持不变。
- `build_qq_response_parts()` 公共兼容接口保留；发送循环仍消费既有 `text`、`record` 和 `image` part。
- Weixin 尚未直接接入 `ResponseBundle`；后续只能映射为 audio attachment，不能模拟 native voice。

## QQ adapter 接入顺序

1. 将现有 `VoiceDecision`、`StickerDecision` 和选中的 sticker asset id 传给 `request_from_dialogue_decisions()`。
2. adapter 把 QQ/OneBot 实际能力映射为 `PlatformCapabilities`，把 owner/group 信息映射为 `DeliveryContext`。
3. 调用 `ExpressionPlanner.plan()`；仅当 `bundle.voice.should_synthesize` 为真时调用现有 TTS。
4. TTS 完成后调用 `finalize_voice()`。只有 `VoiceStatus.READY` 时发送语音，并遵守 `suppress_display_text`，避免重复文本。
5. 语音未就绪或任何 fallback 出现时发送 `display_text`；sticker 仅在 `bundle.sticker.should_send` 为真时发送。
6. adapter 将 `FallbackReason` 写入已有非秘密审计元数据，不把 provider 异常、路径或凭据直接暴露给用户。

已提供的映射函数：

```python
from app.expression import (
    capabilities_from_channel,
    delivery_context_from_event,
    response_bundle_to_channel_response,
    with_provider_capability,
)
```

- `capabilities_from_channel()`：S2 capability 到 S7 capability。
- `delivery_context_from_event()`：S2 event 到 S7 group/private 上下文；`is_owner` 必须由权限层提供。
- `with_provider_capability()`：依据 S6 TTS capability 和 health 更新表达请求。
- `response_bundle_to_channel_response()`：S7 bundle 到 S2 response，并执行最终能力一致性检查。

## 依赖接入

- S2/S6 已完成，S7 公开桥接已经实现；共享运行时只需在冻结入口调用这些函数。
- 不应让 S7 直接导入 S2/S6 的 repository、adapter 或配置内部类型。

## 冻结共享文件待办

按照 `docs/systems/README.md`，本开发包未直接修改 `README.md`、`AGENTS.md`、QQ bot、`app/voice_chat` 或 provider 配置。集成人员合并时应在 `README.md` 和 `AGENTS.md` 记录：

- S7 平台无关 `ResponseBundle`、语音/表情计划和显式 fallback 原因码已经实现；
- S7 聚焦测试 24 项通过；S2/S6/S7 联合测试 57 项通过；
- QQ adapter 已完成语音/sticker 接线，Core API 已完成 text 接线；Weixin 仍待直接集成。
