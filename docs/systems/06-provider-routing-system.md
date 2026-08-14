# S6 模型与 Provider 路由系统

## 目标

统一不同 provider 的健康、超时、错误、fallback 和审计语义，同时保留文本、视觉、ASR、TTS 的强类型接口。

## 独占写入范围

```text
app/providers/
tests/providers/
docs/systems/worklogs/s6/
```

## 公开契约

- `ProviderId`、`ProviderCapability`、`ProviderHealth`。
- `ProviderErrorCode`：not_configured、unavailable、model_missing、timeout、invalid_response、rate_limited。
- `ProviderAttempt`、`ProviderTrace`、`RoutingDecision`。
- 模态接口：`TextProvider`、`VisionProvider`、`AsrProvider`、`TtsProvider`。

## 路由规则

- capability 不匹配时禁止调用。
- fallback 顺序由受控配置决定。
- timeout、重试和熔断有上限。
- 鉴权错误不自动重试到同一 provider。
- 所有失败保留非敏感 trace。

## Runtime 与状态边界

- 文本、streaming 文本、视觉、文件 ASR 和 TTS 的生产 adapter 必须通过同一 registry/router family 调用；WebSocket 流式 ASR若保留专用协议，也必须发布等价的健康与错误 contract。
- registry 生命周期至少覆盖一个应用进程，不能按单次请求重建而丢失熔断状态。
- timeout 表示停止等待，不等价于底层同步线程或 GPU 推理已经终止；adapter 必须另有硬超时和资源上限。
- runtime monitor 只记录 provider id、capability、健康、错误码、延迟桶和熔断状态，不记录 prompt、媒体、响应正文或凭据。
- S8 通过公开 provider runtime status 读取状态；不得导入 adapter 私有 client 或通过真实推理做健康检查。

## 测试

- provider 未配置、模型缺失、超时、限流；
- fallback 顺序和停止条件；
- 熔断恢复；
- 不同模态不可混用；
- trace 脱敏；
- fake clock 下的确定性测试。

## 完成标准

- 内存 registry 与 fake provider 可独立运行。
- 不改变现有 DeepSeek、Ollama、FunASR、Ellie、火山 adapter。
- 给每个现有 adapter 提供迁移映射文档。
- 不增加网络调用或安装模型。
- DeepSeek、Ollama/OCR、FunASR、Ellie/火山 TTS 的生产路径均有“确实经过 router”的集成测试。
- 应用级 registry 与 runtime monitor 在文本、视觉、ASR、TTS 间保持能力隔离，并可被 S8 聚合。

## 禁止修改

现有 provider 实现、`.env`、Settings、模型目录和 requirements。
