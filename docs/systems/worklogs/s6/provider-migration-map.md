# S6 现有 Provider 迁移映射

本文件只描述后续集成方式，不修改或包装现有实现。迁移应由集成人员在共享文件解冻后完成。

| 现有实现 | S6 ID | Capability | 建议适配方法 | 结果/错误映射 |
| --- | --- | --- | --- | --- |
| `app.services.model_client.DeepSeekClient` | `deepseek` | `text` | `generate_text(TextRequest)` 调用 `chat(system_prompt, user_prompt)` | 空响应 -> `invalid_response`；HTTP 429 -> `rate_limited`；超时 -> `timeout`；无 API key -> `not_configured`；401/403 -> `authentication_failed` |
| `integrations.qq_bot.vision_providers.OllamaVisionProvider` | `ollama-vision` | `vision` | 已由 `QQVisionProviderAdapter.analyze_image(VisionRequest)` 在线程中转交现有图片分析方法；QQ Bot 复用持久路由器 | 模型未安装 -> `model_missing`；服务不可达 -> `unavailable`；解析失败 -> `invalid_response`；Ollama 失败后 fallback 到 `qq-ocr` |
| `app.audio.funasr_engine.FunAsrFileEngine` / `FunAsrStreamingEngine` | `funasr-*` | `asr` | 文件模式已由 `FunAsrProvider.transcribe(AsrRequest)` 接入 QQ 与 Core 文件管线；流式接口仍单独保留 | 模型目录缺失 -> `model_missing`；未初始化 -> `unavailable`；超时 -> `timeout`；空转写 -> `invalid_response` |
| `app.voice_chat.bert_vits2_tts.synthesize_bert_vits2` | `ellie-bert-vits2` | `tts` | `synthesize(TtsRequest)` 复用当前 speaker/language/model 配置 | 本地服务未启动 -> `unavailable`；请求超时 -> `timeout`；音频无效 -> `invalid_response` |
| `app.voice_chat.volcengine_tts.synthesize_volcengine_tts` | `volcengine-tts` | `tts` | `synthesize(TtsRequest)` 使用当前受控 Settings 构造适配器 | 凭据缺失 -> `not_configured`；401/403 -> `authentication_failed`；429 -> `rate_limited`；超时 -> `timeout` |

## 边界

- 适配器声明的 `capabilities` 必须与接口一致，不能让 TTS、ASR、视觉或文本调用互相复用。
- 凭据只从现有 Settings 注入，禁止进入 `ProviderTrace.details`。
- provider 顺序、超时和重试由集成层把现有受控配置转换为 `RoutingPolicy`；S6 不读取 `.env`。
- S6 当前只提供非流式文本契约。DeepSeek 流式调用应在公开流式契约确定后再迁移，不能通过缓存完整结果模拟流式输出。
