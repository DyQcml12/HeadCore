# S7 表达计划系统研究与实现记录

日期：2026-07-14

## 研究来源

1. Microsoft Bot Framework REST Connector API Reference  
   https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-api-reference
   - 工程映射：以平台无关 Activity/attachment 数据表达待发送内容，具体渠道负责转换和投递。
2. NoneBot OneBot Adapter  
   https://github.com/nonebot/adapter-onebot
   - 工程映射：OneBot 消息类型属于 adapter 边界，不进入 S7 的 `ResponseBundle`。
3. OpenAI Agents SDK  
   https://github.com/openai/openai-agents-python
   - 工程映射：将模型/策略输出和工具执行分离。S7 只生成计划，TTS 与平台发送由外层执行。

以上来源在 2026-07-14 可访问。本实现没有增加网络调用或运行时依赖。

## 实现结构

- `app/expression/models.py`：平台无关 contracts、平台能力、语音状态和标准降级原因码。
- `app/expression/planner.py`：纯表达规划、现有 dialogue decision 映射、TTS 完成后的显式提交或回退。
- `app/expression/integration.py`：S2 channel capability/event、S6 TTS capability/health 与 S7 contract 的公开契约桥接。
- `app/expression/__init__.py`：S7 稳定公开接口。

## 关键决策

- `ResponseBundle` 不导入 NoneBot、OneBot 或 Hermes 类型。
- TTS 完成前语音状态为 `pending`，文本不会被隐藏。
- 只有 TTS 成功且输出位于受控绝对路径内，才进入 `ready` 并设置 `suppress_display_text=True`。
- owner、群聊、provider、平台能力、cooldown、附件和平台限制均产生稳定原因码。
- S7 不读取配置、不调用 provider、不发送平台消息，也不修改人格、关系、权限或记忆。

## S2/S6 契约集成

- S2 `native_voice` 或 `audio_attachment` 任一可用时，S7 可以规划语音；最终响应仍保留两种渠道类型的差异。
- QQ ready voice 转换为 `native_voice`，Weixin ready voice 转换为 `audio_attachment`，不模拟 Weixin 原生语音气泡。
- 群聊语音默认关闭，只有集成方明确传入 `voice_in_group=True` 才启用。
- owner 身份必须由外部权限系统显式传入，channel adapter 和 S7 都不自行推断。
- S6 provider 必须声明 `ProviderCapability.TTS`，且健康状态为 `healthy` 或 `degraded`；`unavailable` 和 `circuit_open` 会触发 S7 文本降级。
- `ResponseBundle` 到 `ChannelResponse` 的转换会再次检查 channel capability，避免能力状态变化时模拟成功。
