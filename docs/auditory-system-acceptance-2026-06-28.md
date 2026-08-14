# 听觉系统真实验收记录 2026-06-28

本记录对应当前文件音频听觉闭环，不包含假 ASR 或 mock 验收。

## 已完成

- 真实样本收集：`scripts/download_asr_samples.py` 会收集 FunASR 公开中文样本、Open Speech Repository 普通话样本、SenseVoiceSmall 官方缓存示例。
- 极端样本生成：`scripts/build_asr_stress_samples.py` 会从真实音频派生低音量、白噪声、前后静音、尾部截断、轻微加速样本，并在 manifest 里标注为 `stress-derived`。
- 批量 ASR 压力测试：`scripts/asr_batch_stress.py` 真实调用 `iic/SenseVoiceSmall + fsmn-vad + ct-punc`。
- 听觉到大脑联动：`scripts/audio_brain_smoke.py` 会执行真实音频 -> 本地 ASR -> `ChatService.reply` -> DeepSeek live API。
- 接口级联动：`scripts/audio_chat_api_smoke.py` 会通过 `POST /api/v1/audio/chat/file` 验证真实 HTTP 上传音频、后端 ASR 和大脑回复。

## 最新真实测试报告

- ASR 批量真实/压力测试 PASS：`logs/asr-batch-stress/2026-06-28_193156/asr-batch-stress-report.md`
- 听觉到大脑服务级联动 PASS：`logs/audio-brain-smoke/2026-06-28_193302/audio-brain-smoke-report.md`
- 音频转写 API PASS：`logs/audio-api-smoke/2026-06-28_193704/audio-api-smoke-report.md`
- 音频到大脑 API PASS：`logs/audio-chat-api-smoke/2026-06-28_193742/audio-chat-api-smoke-report.md`
- 全量单元测试 PASS：`logs/test-runs/2026-06-28_193425/all/all.test-report.md`

## 当前结论

文件音频链路已经可用：真实音频文件可以转文字，也可以直接送入大脑生成回复。

当前主模型仍是 SenseVoiceSmall。它能支撑第一版文件音频闭环，但还不是最终模型选择。下一步应使用同一套 manifest 横评 FireRedASR2S、Fun-ASR-Nano、Paraformer 2pass。

真实流式 ASR worker 还没有完成：`WS /api/v1/audio/transcribe/stream` 仍是协议入口/预留能力，不应标记为真实流式可用。
