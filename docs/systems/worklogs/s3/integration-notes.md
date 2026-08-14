# S3 集成说明

## 公开入口

- `app.perception.PerceptionInput`
- `app.perception.PerceptionObservation`
- `app.perception.ProviderTrace`
- `app.perception.MemoryEligibility`
- `app.perception.PerceptionPipeline`

## 后续集成工作

1. S2 可通过 `perception_input_from_channel_event()` 将 `ChannelAttachment` 的安全元数据映射为 `PerceptionInput`。映射不会自动下载或读取附件正文。
2. S6 可通过 `routing_trace_to_perception()` 映射 provider attempt；敏感 `details` 不会跨边界进入感知 trace。
3. QQ 文件 ASR 已通过 `FunAsrProvider` 和 `QQAsrRouter` 接入；`normalize_asr_result()` 负责质量与记忆资格。流式 ASR 尚未迁移。
4. ChatService 只能消费 `PerceptionObservation`，并在使用前检查 `quality`；长期记忆层只能消费 `memory_eligibility.decision`，不能仅检查文本是否非空。
5. 远程附件下载器必须执行超时、流式大小上限、响应 MIME 校验，并在 DNS 解析和每次重定向后拒绝私网地址。S3 仅提供 URL 预检，不负责网络获取。

## 冻结文件记录

运行时集成已经由集成人员完成并记录在 README/AGENTS。S3 当前具备 typed contract、QQ 文件 ASR/视觉 adapter、质量/记忆门、fake 单测与可选 ASR smoke。
