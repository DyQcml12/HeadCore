# 听觉系统设计

## 目标

听觉系统负责把用户语音稳定转成中文文本，再交给现有聊天链路处理。

第一阶段必须使用真实高质量本地 ASR 模型，不做“假引擎占位版”作为功能交付。

目标：

- 本地运行，不把用户语音上传到外部 ASR 服务。
- 中文普通话优先，兼容少量中英混说。
- 支持流式或 2pass 准流式输出，前端能边说边看到文字。
- 最终文本质量优先于极限低延迟。
- ASR 模块与人格、记忆、数据库解耦，ASR 失败不能影响文字聊天。
- 默认不保存原始音频。

## 模型选型结论

### 候选优先级

当前优先级按“中文效果、本地化、是否适合对话、工程可落地”排序：

1. `FireRedASR2S`：重点验证。它是新的开源工业级全链路 ASR，覆盖中文普通话、20+ 方言/口音、英语、中英混说，并包含 ASR、VAD、LID、Punc 模块。适合追求中文准确率和中英混说效果。
2. `Fun-ASR-Nano`：重点验证。通义实验室较新的端到端 ASR 大模型，训练数据量更大，支持低延迟实时转写和多语言。适合作为旧阿里开放 ASR 模型的升级路线。
3. `FunASR + SenseVoiceSmall / Paraformer 2pass`：稳定工程路线。中文生态成熟，VAD、标点、2pass、WebSocket/runtime 更容易接入。
4. `sherpa-onnx`：轻量流式备选。适合端侧和 CPU-only，但不作为高质量第一选择。
5. `Whisper / faster-whisper / whisper.cpp`：离线文件转写备选，不作为实时中文对话主路线。

结论：不要只停留在以前用过的阿里云开放模型。下一步应同时实测 `FireRedASR2S`、`Fun-ASR-Nano`、`FunASR 2pass`，用同一批中文语音样本比较。

### 第一候选：FireRedASR2S

优先验证原因：

- 面向中文普通话、20+ 方言/口音、英语、中英混说。
- 包含 ASR、VAD、LID、Punc，全链路更接近产品需要。
- 官方宣称在公开普通话基准和中文方言口音基准上有很强表现。
- 适合本项目这种“用户随口说中文、偶尔夹英文技术词”的场景。

风险：

- 工程接入复杂度可能高于 FunASR。
- 需要实测流式能力、显存/内存占用和 Windows 环境可用性。
- 如果实时流式不够成熟，可以作为 final 二次校正模型，而不是 partial 模型。

推荐用法：

- 第一轮：跑本地 wav 文件准确率 smoke。
- 第二轮：测试分块准流式。
- 第三轮：如果延迟可接受，作为主 ASR；如果延迟偏高，作为 2pass final 修正。

### 第二候选：Fun-ASR-Nano

优先验证原因：

- 通义实验室较新的 ASR 大模型。
- 支持低延迟实时转写。
- 支持中文、英文、日文；中文覆盖多种方言和区域口音。
- 有 vLLM/WebSocket 实时服务和 GGUF/llama.cpp 端侧路线，工程形态更灵活。

风险：

- 800M 级模型对本地资源有要求。
- 新模型链路需要单独确认依赖、显存和 Windows 支持。

推荐用法：

- 作为旧阿里开放模型的升级路线重点测试。
- 如果本机 GPU 足够，优先测它的实时服务。
- 如果部署成本可控，它可能比 SenseVoiceSmall 更适合作为主模型。

### 第一选择：FunASR 高质量中文链路

如果 `FireRedASR2S` 或 `Fun-ASR-Nano` 在本机部署成本过高，第一阶段直接围绕 FunASR 经典链路做。

推荐组合：

- `SenseVoiceSmall`：中文、英文、粤语、日语、韩语等多语种识别，适合真实用户语音和中英混说。
- `Paraformer` streaming / 2pass：适合中文流式识别，在线先出 partial，离线二次修正 final。
- `fsmn-vad`：端点检测，切句。
- `ct-punc`：中文标点恢复。

开发优先级：

1. 先跑通 FunASR Python 本地推理。
2. 再跑通 FunASR streaming / 2pass WebSocket。
3. 再接入本项目 FastAPI WebSocket。

原因：

- 你要的是“好用的中文语音转文字”，不是轻量 demo。
- FunASR 中文生态、2pass、VAD、标点链路更适合中文对话。
- 即使首包延迟略高，也比错误识别和没有标点更可接受。

### 第二选择：sherpa-onnx

保留为轻量本地流式备选。

适用：

- FunASR 环境过重或机器性能不够。
- 需要更低部署复杂度。
- CPU-only 边缘设备。

但它不是当前第一阶段主路线。

### 第三选择：Whisper / faster-whisper / whisper.cpp

作为离线音频文件转写备用。

不作为实时听觉主路线，原因：

- 原生不是严格 streaming ASR。
- 分块流式容易出现重复文本、断句差、延迟高。
- 更适合上传音频、长录音转写、离线总结。

## 推荐运行架构

第一版采用独立 ASR Worker，而不是把 FunASR 直接塞进聊天 API 进程。

```text
Browser / Desktop Mic
        |
        | 16 kHz mono PCM chunks
        v
HutaoChatCore FastAPI
WS /api/v1/audio/transcribe/stream
        |
        | PCM chunks
        v
FunASR Worker
  - VAD
  - Streaming ASR partial
  - Offline 2pass final
  - Punctuation
        |
        | partial/final text
        v
FastAPI WebSocket response
        |
        v
Existing ChatService
```

## WebSocket 协议

路径：

```text
WS /api/v1/audio/transcribe/stream
```

客户端先发送：

```json
{"type":"start","sample_rate":16000,"language":"zh","mode":"2pass"}
```

随后发送二进制 PCM 音频块。

服务端返回 partial：

```json
{"type":"partial","text":"我今天有点","is_final":false}
```

服务端返回 final：

```json
{"type":"final","text":"我今天有点累。","is_final":true}
```

错误：

```json
{"type":"error","message":"asr engine unavailable"}
```

## 后端模块

建议新增：

```text
app/audio/
  __init__.py
  schemas.py
  asr_engine.py
  funasr_engine.py
  funasr_worker_client.py
  stream_session.py
  websocket_routes.py
```

核心接口：

```python
class StreamingAsrEngine(Protocol):
    async def start(self, *, sample_rate: int, language: str, mode: str) -> None: ...
    async def accept_audio(self, pcm: bytes) -> list[AsrEvent]: ...
    async def finish(self) -> list[AsrEvent]: ...
```

事件：

```python
AsrEvent(
    type="partial" | "final" | "error",
    text="识别文本",
    is_final=False,
    start_ms=None,
    end_ms=None,
    confidence=None,
)
```

## 开发顺序

1. 准备统一 ASR 评测集：10 条中文短句、5 条中英混说、5 条停顿/重复/口语化、3 条噪声样本。
2. 写 `scripts/asr_file_smoke.py`：同一批 wav 分别跑 `FireRedASR2S`、`Fun-ASR-Nano`、`FunASR 2pass`。
3. 输出统一 Markdown 报告：字错率、是否有标点、是否保留英文技术词、耗时、峰值内存/显存。
4. 先选 wav 文件效果最好的模型做主路线。
5. 再测试分块准流式或真实 streaming。
6. 新增 `WS /api/v1/audio/transcribe/stream`。
7. 写 WebSocket 流式测试：把 wav 切成 20ms/40ms PCM 块发送。
8. 再接前端麦克风。
9. 最后接 `WS /api/v1/voice/chat/stream`，把 final text 送入 `ChatService.stream_reply`。

说明：

- 可以用 mock 引擎做单元测试，但不能把 mock 当作功能完成。
- 功能验收必须跑真实 FunASR 模型。
- 每次真实 ASR 测试必须写 Markdown 报告。

## 验收标准

第一版可用标准：

- 真实 FunASR 模型本地运行成功。
- 本地 wav 文件测试 PASS。
- WebSocket 能返回 partial 和 final。
- 10 条中文短句测试通过。
- 中英混说至少能保留英文关键词。
- final 文本有基本标点。
- 真实麦克风 smoke 测试生成 Markdown PASS 报告。
- 默认不保存原始音频。
- ASR 失败不影响文字聊天接口。

## 当前实现状态

已完成：

- `app/audio/asr_engine.py`：ASR 引擎协议。
- `app/audio/funasr_engine.py`：真实 FunASR 文件转写引擎，当前模型为 `iic/SenseVoiceSmall`，带 VAD 和标点。
- `app/audio/stream_session.py`：流式会话包装。
- `app/audio/websocket_routes.py`：预留 `WS /api/v1/audio/transcribe/stream` 协议入口。
- `scripts/download_asr_samples.py`：下载公开中文测试音频。
- `scripts/asr_file_smoke.py`：真实模型文件转写 smoke 测试，生成 Markdown 和 JSON 报告。

已验证：

- `iic/SenseVoiceSmall` + `fsmn-vad` + `ct-punc` 能在本机 CUDA 环境跑通。
- 公开中文样本识别结果为：`欢迎大家来体验达摩院推出的语音识别模型。`
- 本机没有 `ffmpeg`，FunASR 当前通过 `torchaudio` 加载音频，可继续运行。

待完成：

- 增加更多公开中文/中英混说/噪声测试音频。
- 增加 `FireRedASR2S` 和 `Fun-ASR-Nano` 横评。
- 接入真正 streaming / 2pass Worker。
- 将 WebSocket 从协议预留改成真实流式转写。

## 当前结论

直接上高质量中文 ASR，并且先做模型横评。

实施路线：

1. 第一批横评：`FireRedASR2S`、`Fun-ASR-Nano`、`FunASR SenseVoiceSmall / Paraformer 2pass`。
2. 如果 FireRedASR2S 准确率明显更好且延迟可接受，优先使用 FireRedASR2S。
3. 如果 Fun-ASR-Nano 兼顾准确率和实时性，优先使用 Fun-ASR-Nano。
4. 如果两者部署成本过高，使用 FunASR 经典 2pass 链路。
5. `fsmn-vad` + `ct-punc` 作为中文对话质量补强。
6. sherpa-onnx 只保留为轻量备选。
7. Whisper 系列只保留为离线文件转写备选。
