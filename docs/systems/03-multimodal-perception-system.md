# S3 多模态感知系统

## 目标

统一 ASR、语音情绪、OCR、VLM 和附件摘要的输出，让对话系统只消费带来源、置信度和质量状态的观察结果。

## 当前基础

- `app/audio/` 文件 ASR 已可用。
- QQ 视觉 provider、OCR 和 Ollama adapter 已存在。
- Ollama 当前没有注册模型。

## 独占写入范围

```text
app/perception/
tests/perception/
docs/systems/worklogs/s3/
```

## 公开契约

- `PerceptionInput`：模态、受控本地路径或安全元数据、来源。
- `PerceptionObservation`：text、objects、emotion、language、confidence、quality。
- `ProviderTrace`：provider、model、latency、fallback、error code。
- `MemoryEligibility`：allow/deny/review 与原因。

## 管线

```text
validate input -> select provider -> observe -> normalize -> quality gate
-> redact -> produce observation
```

## 规则

- 低置信度内容不能作为确定事实写入记忆。
- 用户文件不默认执行或解析主动内容。
- 远程 URL 必须经过大小、类型、超时和私网限制。
- provider 失败返回结构化原因，不能伪造观察。

## 记忆候选交接

S3 不直接写 S4 repository。感知完成后只产生不可变的 `PerceptionObservation` 和 `MemoryEligibility`；集成层将允许的观察映射为 S4 `MemoryCandidateInput`。

- `allow` 仅表示可以进入候选策略，不等于记忆已经批准或成为事实。
- `review` 只能进入人工/策略复核队列，不能直接出现在长期 prompt projection。
- `deny` 不创建长期候选；可以保留不含正文的失败指标和 trace 分类。
- handoff 必须携带 source event/attachment 引用、profile id、confidence、quality、观察时间和 provider trace 摘要。
- S4 独立执行身份、relationship、scope、冲突和审批规则；S3 provider 置信度不能覆盖这些规则。

## 测试

- string/object 两种 ASR 返回兼容；
- 空音频、超大图片、错误 MIME、模型不存在；
- OCR 与 VLM 冲突时的质量策略；
- provider 失败与 fallback trace；
- memory eligibility 矩阵。

## 完成标准

- ASR 和视觉至少各有一个 adapter 使用统一 observation。
- 单元测试不要求真实模型。
- 提供可选真实 smoke，缺模型时明确 SKIP/FAIL 原因。
- 不直接修改长期记忆或 ChatService。
- S3 -> S4 contract 测试证明 allow/review/deny 映射稳定，且原始媒体、临时 URL 和 provider 私密 details 不进入候选。

## 只读依赖

S2 `ChannelAttachment`、S6 provider health contract。

## 禁止修改

现有模型文件、Ollama 安装、`data/models`、QQ bot 和 `.env`。
