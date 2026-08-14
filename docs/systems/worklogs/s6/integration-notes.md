# S6 集成说明

## 已实现

- `app/providers/contracts.py`：Provider ID、能力、健康、错误、trace、routing decision 和四类模态协议。
- `app/providers/registry.py`：独立内存 registry、重复注册保护、能力校验和显式健康状态。
- `app/providers/router.py`：受控 fallback、每 provider 有限重试、调用超时、熔断与脱敏 trace。
- `app/providers/fakes.py`：fake clock、fake text provider 和通用 fake provider。

## 集成人员待办

DeepSeek 文本链路已完成集成：Settings 提供有序列表和策略参数，`ChatService.reply()`、`stream_reply()` 和人格 live repair 通过 `ProviderRouter` 调用，成功和失败 trace 写入请求审计元数据。

后续待办：

1. DeepSeek、Ollama Vision、FunASR 文件模式、Ellie 和火山 TTS 均已完成对应运行路径接入；FunASR 流式模式仍保持原独立接口。
2. S8 已同时提供配置 readiness 和运行中 Provider 汇总状态。

流式语义已经锁定：首个有效 chunk 前允许 retry/fallback；空流视为 `invalid_response`；每个 chunk 都受超时限制；一旦有内容发给调用方，后续失败立即终止且禁止切换 provider，避免重复输出。人格修复作为第二条 routing decision，以 `repair_provider_trace` 独立记录。

QQ TTS 使用 `QQ_VOICE_PROVIDER_ORDER` 控制顺序，真实 bot 调用异步入口并在线程中复用现有同步合成函数。同步 `build_qq_response_parts()` 保留用于兼容现有工具和测试。

Core 文件 ASR 的每个候选引擎也通过独立 Router 执行，候选质量选优与低质量 repair 仍由原音频管线控制。全局运行 monitor 只保存 Provider ID、能力、健康、失败计数、熔断标记和错误码。

## 语义说明

- `authentication_failed` 是为“鉴权错误不重试同一 provider”补充的明确错误码。
- 未注册 provider 记录 `not_configured`；能力不匹配记录 `invalid_response`，并保证不调用 provider。
- 只有 `unavailable`、`timeout`、`invalid_response`、`rate_limited` 计入熔断。配置缺失、模型缺失和鉴权失败不会污染运行健康状态。
- 熔断恢复采用首次探测即闭合/重新计数的简单状态机，fake clock 下完全确定。
- 策略硬上限：超时 300 秒、单 provider 重试 5 次、失败阈值 100、恢复窗口 3600 秒。
