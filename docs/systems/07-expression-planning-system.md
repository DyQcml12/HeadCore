# S7 表达计划系统

## 目标

统一文本、语音、表情包和平台降级选择，生成一个不包含平台私有类型的 `ResponseBundle`。

## 独占写入范围

```text
app/expression/
tests/expression/
docs/systems/worklogs/s7/
```

## 公开契约

- `ResponseBundle`：display text、voice plan、sticker plan、delivery hints。
- `VoicePlan`：provider capability、segments、format、owner restriction。
- `StickerPlan`：asset id、intent、cooldown decision。
- `DeliveryFallback`：voice to text、unsupported attachment、platform limit。

## 边界

- 人格系统决定语气意图，表达系统决定输出形式。
- 表达系统不修改事实、关系、权限或记忆。
- 平台 adapter 负责把 bundle 转成 OneBot/Hermes 调用。
- 训练目录不能直接成为运行时模型 adapter。

## 平台投递设计

S7 只生成 `ResponseBundle`，不调用平台 SDK。S2 delivery adapter 负责最终投递，并返回 `DeliveryResult`。

- Core API：仅声明 text 能力；bundle 含非文本 part 时必须产生明确 fallback，不能静默丢弃。
- QQ：可以映射 native voice 和 sticker，但只有媒体文件通过受控绝对路径校验后才能抑制 display text。
- Weixin/Hermes：语音按 audio attachment 建模；除非 Hermes 公开契约明确支持，不得模拟 QQ native voice、sticker 或 recall。
- 每个 part 具有稳定 id；delivery adapter 使用 S2 幂等键，避免重试时重复发送文本和媒体。
- 部分投递失败必须保留已成功 part，并为失败 part 返回结构化原因；是否重试由投递层策略决定，S7 不重新生成事实内容。

## 输入与版本边界

S7 接受已确定的文本、人格表达意图和平台 capability 快照。人格版本 id、provider trace 和 fallback reason 可以进入非敏感审计，但完整 prompt、私密记忆和生成正文不得进入普通状态日志。

## 测试

- owner-only voice；
- group chat 禁止或降级；
- TTS 失败回退文本；
- 不重复发送文本和语音；
- 表情 cooldown；
- 平台 capability 不支持时降级；
- 输出文件必须是绝对受控路径。

## 完成标准

- `ResponseBundle` 无 NoneBot/Hermes 类型。
- 现有 QQ 表达策略可映射且行为不回归。
- 所有降级有原因码。
- 提交 QQ adapter 集成说明。
- Core API、QQ、Weixin/Hermes 都通过同一 `ResponseBundle` 边界，并覆盖 capability 降级测试。
- delivery adapter 覆盖幂等重试、部分成功、媒体路径拒绝和文本不重复发送。

## 禁止修改

现有 `app/voice_chat`、QQ bot 和 provider 配置。
