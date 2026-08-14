# S2 统一平台事件系统

## 目标

建立 QQ、Weixin 和 Core API 共用的消息事件与响应契约，使权限、人格、记忆和感知系统不依赖 OneBot 或 Hermes 私有字段。

## 非目标

- 不重写 NapCat、NoneBot 或 Hermes。
- 不发送真实消息。
- 不改变平台登录、pairing 或 token 管理。

## 独占写入范围

```text
app/channels/
tests/channels/
docs/systems/worklogs/s2/
```

## 公开契约

```text
ChannelIdentity
ChannelThread
ChannelMessage
ChannelAttachment
ChannelEvent
ChannelCapabilitySet
ChannelResponse
DeliveryResult
```

必需字段包括 platform、user id、group/thread id、message id、timestamp、文本、附件元数据、reply/recall 信息。附件默认只有安全元数据，不默认下载正文。

## 适配边界

- `OneBotEventAdapter`：OneBot event -> `ChannelEvent`。
- `HermesEventAdapter`：仅在取得项目内事件入口后实现。
- `CoreApiEventAdapter`：HTTP chat request -> `ChannelEvent`。
- adapter 不判断管理员、关系或人格。

### Hermes/Weixin 正式适配契约

`HermesEventAdapter` 必须位于项目拥有的 Hermes 事件入口之后、任何领域逻辑之前。它只接受经过 Hermes transport 验证的事件快照，并遵守以下规则：

- Hermes 用户、会话和消息 id 映射到独立的 Weixin namespace，不与 QQ/Core API id 复用。
- 文本、引用、撤回和附件只映射稳定字段；未知字段进入固定安全摘要，不透传原始 payload。
- 图片、文件和音频只携带类型、大小、受控引用等安全元数据；临时 URL、token 和 pairing 数据不得进入 contract。
- Hermes 不支持的能力必须在 capability matrix 中为 false，不能模拟 QQ native voice、recall 或 typing 成功。
- adapter 解析失败返回结构化适配错误；调用方可以降级或拒绝，但不得绕过 S2 直接把 Hermes DTO 交给 S3/S4/S5/S7。

### 输出适配边界

每个平台提供 `ChannelResponse -> DeliveryResult` adapter。adapter 必须先检查 `ChannelCapabilitySet`，记录降级原因，并用平台 message id 填充投递结果。部分成功、重复投递和不可重试失败需要可区分；幂等键由 `channel event id + response part id` 组成。

## Capability Matrix

每个平台显式声明 text、image、file、audio attachment、native voice、recall、typing、profile update、voice call 等能力。调用方必须先检查 capability，不能假设 QQ 与 Weixin 等价。

## 测试

- OneBot 私聊、群聊、引用、撤回、图片、语音、文件 fixtures；
- 未知 segment 不崩溃且保留安全摘要；
- 平台 ID 不串号；
- capability 降级结果稳定；
- contract JSON 序列化兼容测试。

## 完成标准

- contract 不导入 NoneBot/Hermes 类型。
- QQ fixtures 100% 映射。
- Weixin 缺失能力被明确表示而非模拟成功。
- 提供 QQ adapter 集成说明，不直接修改 `integrations/qq_bot/bot.py`。
- Hermes/Weixin fixture 覆盖私聊、引用、附件、未知事件和能力缺失。
- QQ、Weixin/Hermes、Core API 均不存在绕过 `ChannelEvent` 的生产领域入口。
- 三个平台至少各有一个 `ChannelResponse -> DeliveryResult` adapter，并验证幂等键与部分失败语义。

## 禁止修改

现有 QQ bot、HermesRuntime、ChatService、数据库和控制中心入口。
