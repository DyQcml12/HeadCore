# HutaoChatCore

> 以 **HeadCore** 为唯一认知主体的胡桃人格聊天后端。当前产品主线是 FastAPI Core HTTP 服务、Web Desk/PWA、OpenAI-Compatible 文本接口、文件语音识别，以及一组默认关闭的可选能力（公开账号、网页 TTS、本地视觉工作台、Database V2、语义记忆、世界证据工具）。原生微信小程序（`miniprogram/`）是当前客户端工程，与已退役的微信 Bot 无关。

> 本 README 是面向代码仓库的概览。架构、验收、操作与部署细节以根目录 `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`（唯一编辑源）为准；本文件不与它冲突，也不复制它的完整验收清单。

---

## 1. 项目定位

HutaoChatCore 不是“把用户消息转发给大语言模型”的简单壳。它在模型调用前后加入身份、关系、会话、自我状态、记忆、世界证据、表达规划和回复质量门禁：

- 所有客户端（网页、PWA、未来 App、微信小程序）连接同一个 HeadCore，不复制人格、关系、记忆或决策系统。
- 运行时唯一内置人格是 `hutao_v1`。模型、ASR、TTS、视觉或世界工具都只能作为能力提供者，不能创建第二套 Self 或直接写入长期记忆。
- 文本模型负责理解和生成候选表达；HeadCore 负责身份、关系边界、上下文、事实边界、决策与最终输出规范。
- 普通用户界面、个人中心和管理控制中心严格分离。

## 2. 当前状态与边界

当前阶段是“本地 Web 主线可运行”，**不是可直接开放注册的生产系统**。

- **本地可运行**：`/desk` 文字与“按住说话”流式聊天、对话脉络、记忆读取/删除、登录注册与个人中心页面（服务开关关闭时页面降级为预览）、本地控制中心、PWA 壳、OpenAI 兼容接口、文件语音转写、跨会话自我档案与自我一致性门禁（内部机制，档案不存在时不改变任何行为）。
- **条件可用（默认关闭）**：公开账号与 SMTP 邮件验证（2026-08-17 已切换真实 QQ 邮箱（smtp.qq.com:587 STARTTLS）并直连发信验收；本地调试 SMTP `scripts/dev_smtp_sink.py` 保留，仅当 SMTP_HOST=127.0.0.1 时由启动器拉起）、网页 TTS（2026-08-15 已用本机 GPT-SoVITS（胡桃权重，CUDA）真实联调通过：聊天回复经 planner 按情绪选参考分段合成，`/api/v1/voice/synthesize` 返回 mp3；使用前提是 GPT-SoVITS API 在 9880 运行 + `PUBLIC_WEB_TTS_ENABLED=true`；`scripts/watch_gpt_sovits.py` 守护进程在 TTS 开启时由启动器自动拉起，自动重启退出的服务）、本地视觉工作台（2026-08-17 视觉 L1 已接线：摄像头时序确认后的白名单标签经 `app/camera/evidence_store.py` 注入对话证据链，仅显式画面问题才回答，禁止推断情绪/身份/意图）、Database V2（MySQL）、语义记忆（Qdrant + 嵌入模型）、世界证据工具（高德地图与高德天气、受控新闻/政策来源（和风天气适配器保留为备选）；自动摄取覆盖天气/新闻/政策/路线四类，只写白名单字段；世界模型带时间衰减与信念强度，旧证据自动降权；非流式对话支持受限单步工具循环，模型可请求一次实时证据后再作答）。ASR 冷启动由 `AUDIO_WARMUP_ENABLED=true` 后台预热（SenseVoice+emotion2vec，首次转写秒级）。
- **尚未完成**：域名与 HTTPS、反向代理白名单、共享限流、图形验证码与邮件发送上限（公网开放前必做）、备份与恢复演练、真实语音与视觉设备验收。
- **已退役**：见“12. 已退役模块”。

状态用语统一为：已实现 / 条件可用 / 部分实现 / 规划中 / 已退役。自动化测试通过**不等于**真实 DeepSeek、MySQL、SMTP、语音模型、视觉设备或世界数据源已经线上验收；只有手册中明确写“真实联调通过”的记录才可作为真实验收证据。

## 3. 架构概览

### 3.1 请求主链路

```text
客户端输入（文本 / 录音文件 / 受控视觉）
  -> S2 统一 ChannelEvent
  -> 身份解析与权限（S1）
  -> 附件感知（S3，经 S6 Provider 路由）
  -> 记忆候选与只读投影（S4）
  -> 人格运行时投影（S5，hutao_v1）
  -> ChatService / 模型调用（S6）
  -> 表达规划与输出规范化（S7）
  -> 客户端投递（S2）
  -> 状态、trace 与审计投影（S8）
```

### 3.2 HeadCore 唯一认知主体

HeadCore（`app/head/`）维护当前认知状态、世界状态、决策、长期计划、反馈与校准，并把渠道事件、用户主体、会话和 ChatService 组合成统一运行入口。模型不可直接：

- 决定当前用户是谁；
- 修改其他用户资料；
- 把外部网页全文写入长期记忆；
- 自动启用摄像头、定位、新闻抓取或高成本工具；
- 返回或记录 API Key、密码、Cookie、CSRF Token 和数据库凭据。

### 3.3 S1-S8 系统划分

| 编号 | 系统 | 职责 |
| --- | --- | --- |
| S1 | Database V2 控制面 | 身份、权限和持久化 readiness 的权威来源 |
| S2 | 统一平台事件 | 把客户端原始输入规范为 `ChannelEvent` |
| S3 | 多模态感知 | 音频/视觉附件感知，经 Provider 路由执行 |
| S4 | 记忆与画像生命周期 | 记忆候选、只读投影、审核与撤销 |
| S5 | 人格管理控制面 | `hutao_v1` 运行时投影、发布与回滚 |
| S6 | Provider 路由 | 文本/ASR/TTS/视觉 Provider 注册、超时、重试与熔断 |
| S7 | 表达计划 | 把候选回复规范为可投递的表达束 |
| S8 | 控制面与可观察性 | 状态聚合、测试报告、错误分类与审计 |

设计与并行开发规则见 `docs/systems/README.md`。

## 4. 目录结构

| 路径 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 装配、页面路由、聊天/音频/记忆 API、认证开关接入 |
| `app/head/` | HeadCore：状态、决策、规划、反馈、世界状态与证据 |
| `app/services/` | 对话主服务、模型调用、记忆与世界上下文接入 |
| `app/persona/`、`app/mind/` | `hutao_v1` 人格、关系、语气；对话/自我/社会状态 |
| `app/dialogue/`、`app/expression/` | 对话策略与修复；输出规划与文本规范化 |
| `app/providers/` | 文本/ASR/TTS Provider 注册、路由、熔断与脱敏 trace |
| `app/storage/` | JSONL 默认后端与 Database V2 仓库 |
| `app/knowledge/` | 记忆候选、生命周期、投影权限、语义记忆 |
| `app/auth/` | 公开账号、会话、CSRF、审计、限流、SMTP（默认关闭） |
| `app/audio/`、`app/voice_chat/` | 文件转写、音频质量与情绪线索；TTS 适配与规划 |
| `app/camera/`、`app/workbench/` | 短时本地视觉感知与受保护视觉工作台（默认关闭） |
| `app/world/` | 地图/天气/新闻/政策证据、缓存、许可与冲突处理（默认关闭） |
| `app/control/`、`app/operations/` | 本地控制中心；状态聚合、审计、探针与报告 |
| `app/static/web/studio/` | `/desk` Web Desk 与 PWA（manifest、service-worker） |
| `app/static/auth/`、`profile/`、`control/`、`workbench/` | 对应页面静态资源 |
| `app/static/web/site/` | 官网落地页构建产物；源码在 `frontend/site/`（Vite/React） |
| `app/static/shared/` | 共享主题、氛围动画与指针资源 |
| `miniprogram/` | 原生微信小程序客户端（对话、登录注册、个人中心） |
| `migrations/v2/` | MySQL V2 迁移（按编号顺序执行） |
| `deploy/` | Docker Compose 部署模板 |
| `docs/` | 手册、技术报告、设计与归档文档 |
| `tests/`、`scripts/` | 自动化测试；运维与 smoke 脚本 |

## 5. 快速开始

### 5.1 环境要求

- Python 3.11（以 `Dockerfile` 与依赖为准）。
- 文本能力需要可用的模型 Provider Key（默认 DeepSeek）。
- 本地语音识别需要下载第 6 节的模型；纯文字 Core 不要求本地模型权重。

### 5.2 安装依赖

```powershell
pip install -r requirements.txt
# 仅当启用本地视觉能力时（可选）：
pip install -r requirements-vision.txt
```

### 5.3 配置

```powershell
Copy-Item .env.example .env
```

最小文字 Core 配置（其余保持默认即可）：

```env
MODEL_PROVIDER=deepseek
MODEL_NAME=deepseek-v4-pro
MODEL_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=<在这里填写你的 Key>
PERSONA_PROFILE=hutao_v1
STORAGE_BACKEND=jsonl
```

私密值只放 `.env`，不写入代码、README、AGENTS 或日志；`.env.example` 不含任何秘密。

### 5.4 启动

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows 也可用一键脚本（启动 Core 并打开控制中心，`--check-only` 只做启动预检）：

```powershell
.\启动控制中心.bat
.\启动控制中心.bat --check-only
```

### 5.5 常用地址

- `http://127.0.0.1:8000/health` — 健康检查
- `http://127.0.0.1:8000/docs` — OpenAPI 文档（仅开发环境）
- `http://127.0.0.1:8000/desk` — Web Desk（普通用户对话入口）
- `http://127.0.0.1:8000/auth` — 登录注册（开关关闭时仅预览）
- `http://127.0.0.1:8000/me` — 个人中心
- `http://127.0.0.1:8000/control` — 本地控制中心（不得公网开放）
- `http://127.0.0.1:8000/` — 官网落地页

## 6. 本地模型清单

模型不随源码上传。GitHub 仓库只保存框架、代码、配置模板和文档；下列权重都下载到本机对应目录。

| 用途 | 模型 ID | 本地目录 | 是否必需 |
| --- | --- | --- | --- |
| 默认语音识别 | `iic/SenseVoiceSmall` | `data/models/modelscope/iic/SenseVoiceSmall` | 启用文件/Desk 语音输入时必需 |
| 语音活动检测 | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | `data/models/modelscope/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | 默认 ASR 预设必需 |
| 中英文标点恢复 | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | `data/models/modelscope/iic/punc_ct-transformer_cn-en-common-vocab471067-large` | 默认 ASR 预设必需 |
| 音频情绪线索 | `iic/emotion2vec_plus_large` | `data/models/modelscope/iic/emotion2vec_plus_large` | `AUDIO_EMOTION_ENABLED=true` 时必需 |
| 备用高质量 ASR | `FunAudioLLM/Fun-ASR-Nano-2512` | `data/models/modelscope/FunAudioLLM/Fun-ASR-Nano-2512` | 仅 `fun-asr-nano` 预设需要 |
| 语义记忆嵌入 | `BAAI/bge-m3` | 任意本机目录，经 `SEMANTIC_MEMORY_EMBEDDING_MODEL_PATH` 指定 | 可选；默认关闭，更换模型须重建向量索引 |
| 本地视觉检测 | YOLO11n/YOLOv8n ONNX | `data/models/vision/yolo/yolo11n.onnx`，经 `CAMERA_YOLO_MODEL_PATH` 指定 | 可选；仅启用本地视觉工作台时 |
| 姿态/手势/面部线索 | MediaPipe 官方 task 资产 | `data/models/vision/mediapipe/` | 可选，规划中的固定资产 |
| OCR | RapidOCR ONNX 资产 | `data/models/vision/ocr/rapidocr/` | 可选 |
| 语音生成音色 | 本地 GPT-SoVITS 音色权重与参考音频 | `external/GPT-SoVITS-v2pro-20250604/`（不入库） | 可选；仅启用网页 TTS 且完成音色验收时 |

ModelScope 模型下载示例（`app/audio/model_paths.py` 会优先解析这些本地目录；目录不存在时可能按模型 ID 联网解析，离线部署必须先下载完成）：

```python
from modelscope import snapshot_download

models = {
    "iic/SenseVoiceSmall": r"data\models\modelscope\iic\SenseVoiceSmall",
    "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch": r"data\models\modelscope\iic\speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "iic/punc_ct-transformer_cn-en-common-vocab471067-large": r"data\models\modelscope\iic\punc_ct-transformer_cn-en-common-vocab471067-large",
    "iic/emotion2vec_plus_large": r"data\models\modelscope\iic\emotion2vec_plus_large",
}
for model_id, target_dir in models.items():
    snapshot_download(model_id, local_dir=target_dir)
```

TTS 说明：网页语音播放默认关闭。GPT-SoVITS 程序、经授权验收的胡桃音色权重和参考音频都在 `external/`，不入库；相关配置项是 `PUBLIC_WEB_TTS_ENABLED=false`、`PUBLIC_WEB_TTS_PROVIDER=gpt_sovits`、`PUBLIC_WEB_TTS_BASE_URL`、`PUBLIC_WEB_TTS_OUTPUT_DIR` 及回复时限/频率/字数限制键。没有真实音色验收时保持关闭，Desk 只显示文字。

更完整的目录规划见 `docs/deployment/LOCAL_MODEL_LAYOUT.md` 与 `docs/LOCAL_MODEL_INSTALLATION_MAP.md`。

## 7. 配置要点

`.env.example` 是无秘密模板，可按组阅读；`.env` 不提交 Git。关键分组：

| 分组 | 关键键 | 说明 |
| --- | --- | --- |
| 核心模型 | `MODEL_PROVIDER`、`MODEL_NAME`、`MODEL_BASE_URL`、`DEEPSEEK_API_KEY`、`API_TEMPERATURE`、`API_TIMEOUT_SECONDS` | 文本 Provider；Key 只放 `.env` |
| 上下文窗口 | `RECENT_CONTEXT_MAX_MESSAGES`、`RECENT_CONTEXT_MAX_CHARS` | 最近对话注入窗口（默认 8 条 / 每条约 80 字） |
| Provider 路由 | `TEXT_PROVIDER_ORDER`、`TEXT_PROVIDER_RETRIES`、`TEXT_PROVIDER_CIRCUIT_*`、`TEXT_STREAM_TTFT_TIMEOUT_SECONDS`、`TEXT_STREAM_TOTAL_BUDGET_SECONDS`、`ASR_PROVIDER_*` | 有序回退、重试、熔断与流式延迟预算参数 |
| 存储与数据库 | `STORAGE_BACKEND`、`JSONL_STORAGE_DIR`、`MYSQL_*`、`DATABASE_V2_ENABLED`、`POSTGRES_*` | JSONL 为默认；V2 默认关闭 |
| 人格 | `PERSONA_PROFILE=hutao_v1` | 唯一内置人格；旧人格名回退到 `hutao_v1` |
| 公开账号 | `PUBLIC_WEB_AUTH_ENABLED`、`SESSION_COOKIE_SECURE`、`PUBLIC_WEB_SESSION_LIFETIME_SECONDS` | 需 Database V2 + MySQL 就绪后开启 |
| 邮件注册 | `EMAIL_DELIVERY_ENABLED`、`SMTP_*` | 需真实 SMTP 就绪后开启 |
| 网页 TTS | `PUBLIC_WEB_TTS_*` | 默认关闭；需认证 + 已验收音色 |
| 音频输入 | `ASR_FILE_PRESETS`、`ASR_REPAIR_PRESETS`、`AUDIO_EMOTION_ENABLED`、`AUDIO_EMOTION_MODEL` | 转写预设与情绪线索 |
| 语义记忆 | `SEMANTIC_MEMORY_*` | 默认关闭；更换嵌入模型须重建索引 |
| 世界工具 | `WORLD_AWARENESS_ENABLED`、`WORLD_SOURCE_ENABLED_IDS`、`WORLD_SOURCE_LEGAL_APPROVED_IDS`、`AMAP_*`、`QWEATHER_*` | 全局开关 + 单来源启用 + 许可审核，全部默认关闭 |
| 相机与工作台 | `CAMERA_*`、`VISUAL_WORKBENCH_ENABLED`、`VISUAL_WORKBENCH_ADMIN_SECRET` | 默认关闭；工作台口令只存 `.env` |

正确顺序是：依赖就绪 → 迁移 → 单项 smoke → 备份 → 启用 → 验收，再进入下一项；不要一次打开全部开关。

## 8. API 概览

### 8.1 用户与客户端 API

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `/health` | GET | 健康检查 |
| `/api/v1/chat` | POST | 非流式文本聊天 |
| `/api/v1/chat/stream` | POST | 流式文本聊天（Desk 主路径） |
| `/api/v1/dialogue-context` | GET | 当前会话状态、跟进事项与待确认问题 |
| `/api/v1/memories` | GET | 当前账号记忆列表 |
| `/api/v1/memories/{memory_id}` | DELETE | 删除当前账号单条记忆 |
| `/api/v1/audio/transcribe/file` | POST | 单独音频文件转写 |
| `/api/v1/audio/chat/prepare/file` | POST | 音频聊天准备（转写与质量门） |
| `/api/v1/audio/chat/file` | POST | 转写后进入聊天链路 |
| `/api/v1/audio/transcribe/stream` | WebSocket | 流式转写 |
| `/api/v1/voice/status` | GET | 网页语音播放非敏感状态 |
| `/api/v1/voice/synthesize` | POST | 为已登记回复合成短时音频（条件挂载） |

公开认证开启后，聊天、音频聊天与记忆写操作要求 HttpOnly 会话 + CSRF；前端提交的 `user_id`、`session_id` 不作为授权依据。

### 8.2 账号 API（条件挂载）

`GET /api/v1/auth/status` 始终可用，只返回认证/注册/密码重置开关状态。以下路由仅在 `PUBLIC_WEB_AUTH_ENABLED=true` + `DATABASE_V2_ENABLED=true` + MySQL 配置完整时挂载，注册与密码重置还要求 SMTP 完整：

`POST /api/v1/auth/register`、`POST /api/v1/auth/verify-email`、`POST /api/v1/auth/login`、`POST /api/v1/auth/logout`、`GET /api/v1/auth/me`、`POST /api/v1/auth/password-reset/request`、`POST /api/v1/auth/password-reset/confirm`。

密码使用 Argon2id；数据库只保存会话 Token、CSRF Secret、验证码与重置码的哈希。重置码只发往邮箱。

### 8.3 OpenAI-Compatible 接口

- `GET /v1/models`、`POST /v1/chat/completions`：OpenAI 兼容入口，可用模型 ID `hutao-chatcore`（或服务端配置的 `MODEL_NAME`）。

### 8.4 管理与内部接口

`/control`、`/api/control/*`（含 `/api/control/database-v2`、`/api/control/knowledge`、`/api/control/personas`）、`/docs`、`/redoc`、`/openapi.json` 均不得默认向公网开放；公开部署必须在反向代理层阻断。

## 9. 测试与验收

```powershell
python -m compileall -q app scripts
python -m pytest tests -q -p no:cacheprovider
```

不要在仓库根目录直接运行无范围的 `pytest`（`external/` 含第三方自带的测试与运行时，会被错误收集）。项目正式口径是 `pytest tests`。

微信小程序客户端测试：

```powershell
node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js
```

启动预检：

```powershell
.\启动控制中心.bat --check-only
```

最新实测（2026-08 项目清理后）为 `814 passed, 2 skipped`，见根目录完整架构与运行验收手册；这些是历史记录，每次变更后必须重新执行同一门禁。在未下载本地模型/语音样本、未安装 Playwright 的干净克隆环境中，依赖本地资产的测试会自动跳过（本轮导出仓库实测 `810 passed, 6 skipped`），两种环境都是绿。**自动化通过不等于真实模型、MySQL、SMTP、语音、视觉或世界数据源已经线上验收**；最终完成标准以完整架构与运行验收手册为准。

## 10. 部署

- `Dockerfile`：Python 3.11 slim，安装 ffmpeg 与 libsndfile1，以非 root 用户 `hutao` 运行 Core。镜像不含 `external/` 与模型权重。
- `deploy/compose.staging.yml`：MySQL 8.4 + Core（仅绑定主机 `127.0.0.1:8000`，MySQL 不映射公网端口），另含 `database-v2` 迁移 profile 与 `semantic-memory`（Qdrant + 同步 worker）profile。详见 `deploy/README.md`。
- Database V2 迁移不随启动自动执行：先备份，再按编号顺序应用 `migrations/v2/001` 至 `005`（可经 `scripts/apply_database_v2_migrations.py`）；`006_semantic_memory_outbox.sql` 仅在启用语义记忆时应用。通过 readiness 检查后才启用 `DATABASE_V2_ENABLED`。
- 运维脚本：`scripts/auth_expiry_cleanup.py`（清理过期会话/验证码/重置码/限流计数，默认 dry-run，`--apply` 才删除）；`scripts/run_self_reflection.py --user-id <id>`（脱机自我档案反思，规则版）；`scripts/evaluate_world_model_counterfactuals.py`（反事实推演离线评估）；`scripts/evaluate_world_model.py`（世界模型固定评测集，12 例四类，输出通过率与 margin，附诚实声明）。建议定期手动或定时执行。
- 生产前必须补齐：域名/HTTPS、反向代理白名单、上传大小与速率限制、备份与恢复演练、监控告警。

## 11. 安全与默认关闭边界

- 所有高风险能力默认关闭、逐级启用，配置缺失时一律 fail-closed。
- API Key、密码、Token 只存 `.env`；日志与审计只记录脱敏投影，不回显秘密原文。
- 公开账号使用 HttpOnly Cookie + CSRF；前端提交的身份字段不被信任。
- 网页 TTS 只接受服务端为本次流式回复签发的短时 `reply_id`，并受字数、频率、并发与临时文件生命周期限制。
- 相机默认关闭：不保存原始帧、不做人脸身份识别、不上传云端；视觉工作台要求独立管理员口令、短时 HttpOnly 会话与 CSRF。
- 世界工具：每个来源必须显式启用并通过许可审核；不静默抓取网页全文或精确位置，冲突信息保留不确定性。
- 自杀/自伤类输出在本地回复门禁中被拦截或替换，不依赖模型自觉。
- 公开部署不得暴露 `/control`、`/api/control/*`、`/docs`、`/openapi.json` 与 OpenAI 兼容接口。

## 12. 已退役模块

以下历史方案已删除或退役，不参与当前运行，仅保留 `docs/archive/` 中的归档说明：QQ/微信 Bot 通道（NapCat/OneBot 等）、CosyVoice2 语音克隆训练、Bert-VITS2 TTS、Ollama 视觉、旧 MySQL V1 后端入口、旧 Desk UI、旧架构手册及其出版工具链、新闻渲染浏览器方案。不重新接入、不重新配置。完整清理清单见 `logs/project-cleanup/2026-08-14/project-cleanup-report.md`（本地日志，不入库）。

## 13. 只上传框架与代码的 GitHub 发布流程

仓库只提交框架、源码、配置模板和文档；`data/models/`、`external/`、`model_training/`、日志、运行输出、`node_modules` 均被 `.gitignore` 排除。上传前先自检：

```powershell
git check-ignore -v data/models/modelscope/iic/SenseVoiceSmall/model.pt
git ls-files data/models external model_training   # 应为空
git status --short
```

如果旧 Git 历史曾经跟踪过模型权重，不要直接把旧仓库推送到 GitHub（历史对象仍可能携带大文件）。从当前提交导出干净快照并在新目录初始化：

```powershell
git archive --format=zip --output=..\HutaoChatCore-code-only.zip HEAD
Expand-Archive -LiteralPath ..\HutaoChatCore-code-only.zip -DestinationPath ..\HutaoChatCore-code-only
Set-Location ..\HutaoChatCore-code-only
git init -b main
git add .
git commit -m "Initial code-only import"
git remote add origin https://github.com/<你的用户名>/<你的仓库名>.git
git push -u origin main
```

在 GitHub 先创建空仓库，不要勾选自动生成 README、`.gitignore` 或 License。

## 14. 文档索引

- `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`（根目录，唯一编辑源）与 `docs/HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`（同步发布副本）
- `docs/HUTAOCHATCORE_TECHNICAL_REPORT.md`：源码、架构、功能、测试、安全与发布审计报告
- `docs/WEB_PRODUCT_ROADMAP.md`：网页三端设计、交互逻辑与研发顺序
- `docs/LOCAL_MODEL_INSTALLATION_MAP.md`：本地模型安装清单与规则
- `docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md`：本地优先视觉世界模型设计
- `docs/systems/README.md`：S1-S8 系统划分与并行开发规则
- `docs/deployment/LOCAL_MODEL_LAYOUT.md`：模型目录规划
- `docs/history/agent-handoff-archive.md`：历史开发交接记录归档
- `docs/archive/`：退役模块归档说明
- `deploy/README.md`：Compose 部署基线说明

---

# HutaoChatCore

> A Hu Tao persona chat backend built around **HeadCore** as its single cognitive subject. The current product mainline is a FastAPI Core HTTP service, the Web Desk/PWA, an OpenAI-Compatible text endpoint, file-based speech recognition, and a set of opt-in capabilities that stay disabled by default (public accounts, web TTS, local visual workbench, Database V2, semantic memory, world evidence tools). The native WeChat Mini Program (`miniprogram/`) is a current client project and is unrelated to the retired WeChat Bot.

> This README is a repository overview. Architecture, acceptance, operations, and deployment details live in the root `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md` (single source of truth); this file does not contradict it or duplicate its full acceptance checklist.

---

## 1. What This Project Is

HutaoChatCore is not a thin shell that forwards user messages to an LLM. It adds identity, relationship, session, self-state, memory, world evidence, expression planning, and reply quality gates around the model call:

- Every client (web, PWA, future apps, WeChat Mini Program) connects to the same HeadCore; no persona, relationship, memory, or decision system is duplicated per client.
- The single built-in runtime persona is `hutao_v1`. Models, ASR, TTS, vision, and world tools are capability providers only; they cannot create a second Self or write long-term memory directly.
- The text model understands and generates candidate expressions; HeadCore owns identity, relationship boundaries, context, factual boundaries, decisions, and final output normalization.
- The ordinary user UI, the profile page, and the admin control center are strictly separated.

## 2. Current Status and Boundaries

The current stage is "local web mainline runnable", **not** a production system open for public registration.

- **Runnable locally**: `/desk` text and push-to-talk streaming chat, dialogue context, memory list/delete, login/registration and profile pages (they degrade to preview when services are off), the local control center, the PWA shell, the OpenAI-Compatible endpoint, file speech transcription, and the cross-session self profile with its consistency gate (internal mechanisms that change nothing while no profile exists).
- **Conditionally available (off by default)**: public accounts with SMTP email verification (on 2026-08-17 switched to a real QQ mailbox over smtp.qq.com:587 STARTTLS and verified by a direct delivery smoke; the local debug sink `scripts/dev_smtp_sink.py` remains for SMTP_HOST=127.0.0.1 setups), web TTS (on 2026-08-15 the full chain was integration-tested against the local GPT-SoVITS Hu Tao weights on CUDA: chat replies are planned per-emotion into reference-audio segments and `/api/v1/voice/synthesize` returns mp3; it requires the GPT-SoVITS API on 9880 plus `PUBLIC_WEB_TTS_ENABLED=true`; `scripts/watch_gpt_sovits.py` is auto-started by the launcher when TTS is on and restarts a dead service), the local visual workbench (on 2026-08-17 vision L1 was wired: temporally-confirmed allowlisted camera labels flow through `app/camera/evidence_store.py` into the chat evidence chain, answered only for explicit visual questions, with emotion/identity/intent inference forbidden), Database V2 (MySQL), semantic memory (Qdrant + embedding model), and world evidence tools (Amap maps and Amap weather, gated news/policy sources, with the QWeather adapter kept as a fallback; automatic ingestion now covers weather/news/policy/routes with whitelisted fields only; the world model applies time decay and belief strength so old evidence is downweighted automatically; non-streaming chat supports a restricted single-step tool loop where the model may request one round of live evidence before answering). ASR cold start is moved to a background warmup (`AUDIO_WARMUP_ENABLED=true`) so the first transcription is fast.
- **Not finished yet**: domain + HTTPS, reverse-proxy allowlists, shared rate limiting, CAPTCHA and per-day email caps (mandatory before any public exposure), backup/restore drills, and real voice/vision hardware acceptance.
- **Retired**: see "12. Retired Modules".

Status vocabulary: implemented / conditionally available / partially implemented / planned / retired. Passing automated tests does **not** mean real DeepSeek, MySQL, SMTP, speech, vision, or world sources have been accepted online; only "real integration passed" records in the manual count as real acceptance evidence.

## 3. Architecture Overview

### 3.1 Main request path

```text
Client input (text / recorded audio / controlled vision)
  -> S2 unified ChannelEvent
  -> identity resolution and permission (S1)
  -> attachment perception (S3, executed via S6 provider routing)
  -> memory candidates and read-only projection (S4)
  -> persona runtime projection (S5, hutao_v1)
  -> ChatService / model call (S6)
  -> expression planning and output normalization (S7)
  -> client delivery (S2)
  -> status, trace, and audit projection (S8)
```

### 3.2 HeadCore, the single cognitive subject

HeadCore (`app/head/`) maintains cognitive state, world state, decisions, long-term plans, feedback, and calibration, and composes channel events, user subjects, sessions, and ChatService into one runtime entry point. The model must not directly:

- decide who the current user is;
- modify other users' profiles;
- write external page content into long-term memory;
- enable the camera, location, news crawling, or expensive tools on its own;
- return or record API keys, passwords, cookies, CSRF tokens, or database credentials.

### 3.3 S1-S8 system split

| ID | System | Responsibility |
| --- | --- | --- |
| S1 | Database V2 control plane | Authoritative source of identity, permission, and persistence readiness |
| S2 | Unified platform events | Normalizes raw client input into `ChannelEvent` |
| S3 | Multimodal perception | Audio/visual attachment perception executed through provider routing |
| S4 | Memory and portrait lifecycle | Memory candidates, read-only projections, review, and revocation |
| S5 | Persona management control plane | `hutao_v1` runtime projection, publish, and rollback |
| S6 | Provider routing | Text/ASR/TTS/vision provider registry, timeout, retry, circuit breaker |
| S7 | Expression planning | Normalizes candidate replies into deliverable expression bundles |
| S8 | Control plane and observability | Status aggregation, test reports, error classification, and audit |

Design and parallel-development rules: `docs/systems/README.md`.

## 4. Directory Structure

| Path | Responsibility |
| --- | --- |
| `app/main.py` | FastAPI assembly, page routes, chat/audio/memory APIs, auth switch wiring |
| `app/head/` | HeadCore: state, decisions, planning, feedback, world state and evidence |
| `app/services/` | Main chat service, model calls, memory and world context wiring |
| `app/persona/`, `app/mind/` | `hutao_v1` persona, relationships, tone; conversation/self/social state |
| `app/dialogue/`, `app/expression/` | Dialogue policy and repair; output planning and text normalization |
| `app/providers/` | Text/ASR/TTS provider registry, routing, circuit breakers, redacted traces |
| `app/storage/` | JSONL default backend and Database V2 repositories |
| `app/knowledge/` | Memory candidates, lifecycle, projection permissions, semantic memory |
| `app/auth/` | Public accounts, sessions, CSRF, audit, rate limits, SMTP (off by default) |
| `app/audio/`, `app/voice_chat/` | File transcription, audio quality and emotion cues; TTS adaptation and planning |
| `app/camera/`, `app/workbench/` | Short-lived local visual perception and the protected workbench (off by default) |
| `app/world/` | Map/weather/news/policy evidence, caching, licensing, conflict handling (off by default) |
| `app/control/`, `app/operations/` | Local control center; status aggregation, audit, probes, reports |
| `app/static/web/studio/` | `/desk` Web Desk and PWA (manifest, service worker) |
| `app/static/auth/`, `profile/`, `control/`, `workbench/` | Static assets for the corresponding pages |
| `app/static/web/site/` | Public landing page build; source in `frontend/site/` (Vite/React) |
| `app/static/shared/` | Shared theme, ambient animations, and cursor assets |
| `miniprogram/` | Native WeChat Mini Program client (chat, auth, profile) |
| `migrations/v2/` | MySQL V2 migrations (apply in numbered order) |
| `deploy/` | Docker Compose deployment template |
| `docs/` | Manual, technical report, design and archive documents |
| `tests/`, `scripts/` | Automated tests; operations and smoke scripts |

## 5. Quick Start

### 5.1 Requirements

- Python 3.11 (per `Dockerfile` and dependencies).
- Text capability needs a working model provider key (DeepSeek by default).
- Local speech recognition needs the models in Section 6; a text-only Core needs no local weights.

### 5.2 Install dependencies

```powershell
pip install -r requirements.txt
# Only when enabling local vision (optional):
pip install -r requirements-vision.txt
```

### 5.3 Configuration

```powershell
Copy-Item .env.example .env
```

Minimal text Core configuration (everything else can stay at defaults):

```env
MODEL_PROVIDER=deepseek
MODEL_NAME=deepseek-v4-pro
MODEL_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=<fill in your key>
PERSONA_PROFILE=hutao_v1
STORAGE_BACKEND=jsonl
```

Secrets belong in `.env` only — never in code, README, AGENTS, or logs; `.env.example` contains no secrets.

### 5.4 Run

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows, a one-click launcher starts Core and opens the control center; `--check-only` only performs the startup precheck:

```powershell
.\启动控制中心.bat
.\启动控制中心.bat --check-only
```

### 5.5 Common addresses

- `http://127.0.0.1:8000/health` — health check
- `http://127.0.0.1:8000/docs` — OpenAPI docs (development only)
- `http://127.0.0.1:8000/desk` — Web Desk (ordinary user chat entry)
- `http://127.0.0.1:8000/auth` — login/registration (preview only while services are off)
- `http://127.0.0.1:8000/me` — profile page
- `http://127.0.0.1:8000/control` — local control center (never expose publicly)
- `http://127.0.0.1:8000/` — public landing page

## 6. Local Model Manifest

Models are not uploaded with the source. The GitHub repository only carries framework, code, config templates, and docs; the weights below are downloaded locally to the listed directories.

| Capability | Model ID | Local directory | Required? |
| --- | --- | --- | --- |
| Default speech recognition | `iic/SenseVoiceSmall` | `data/models/modelscope/iic/SenseVoiceSmall` | Required for file/Desk voice input |
| Voice activity detection | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | `data/models/modelscope/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | Required for the default ASR preset |
| CN/EN punctuation restore | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | `data/models/modelscope/iic/punc_ct-transformer_cn-en-common-vocab471067-large` | Required for the default ASR preset |
| Audio emotion cue | `iic/emotion2vec_plus_large` | `data/models/modelscope/iic/emotion2vec_plus_large` | Required when `AUDIO_EMOTION_ENABLED=true` |
| Backup high-quality ASR | `FunAudioLLM/Fun-ASR-Nano-2512` | `data/models/modelscope/FunAudioLLM/Fun-ASR-Nano-2512` | Only for the `fun-asr-nano` preset |
| Semantic memory embedding | `BAAI/bge-m3` | Any local path via `SEMANTIC_MEMORY_EMBEDDING_MODEL_PATH` | Optional; off by default, rebuild the index after switching models |
| Local visual detection | YOLO11n/YOLOv8n ONNX | `data/models/vision/yolo/yolo11n.onnx` via `CAMERA_YOLO_MODEL_PATH` | Optional; only when the local visual workbench is enabled |
| Pose/gesture/face cues | Official MediaPipe task assets | `data/models/vision/mediapipe/` | Optional planned pinned assets |
| OCR | RapidOCR ONNX assets | `data/models/vision/ocr/rapidocr/` | Optional |
| Speech-generation timbre | Local GPT-SoVITS voice weights and reference audio | `external/GPT-SoVITS-v2pro-20250604/` (not committed) | Optional; only with web TTS enabled and timbre accepted |

ModelScope download example (`app/audio/model_paths.py` resolves these local directories first; if absent, ModelScope may resolve by model ID over the network, so offline deployments must download first):

```python
from modelscope import snapshot_download

models = {
    "iic/SenseVoiceSmall": r"data\models\modelscope\iic\SenseVoiceSmall",
    "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch": r"data\models\modelscope\iic\speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "iic/punc_ct-transformer_cn-en-common-vocab471067-large": r"data\models\modelscope\iic\punc_ct-transformer_cn-en-common-vocab471067-large",
    "iic/emotion2vec_plus_large": r"data\models\modelscope\iic\emotion2vec_plus_large",
}
for model_id, target_dir in models.items():
    snapshot_download(model_id, local_dir=target_dir)
```

TTS note: web voice playback is off by default. The GPT-SoVITS program, the authorized and accepted Hu Tao voice weights, and reference audio stay under `external/` and are not committed; the related settings are `PUBLIC_WEB_TTS_ENABLED=false`, `PUBLIC_WEB_TTS_PROVIDER=gpt_sovits`, `PUBLIC_WEB_TTS_BASE_URL`, `PUBLIC_WEB_TTS_OUTPUT_DIR`, plus the reply TTL/interval/length limits. Keep it off without real timbre acceptance; Desk stays text-only.

Full layout rules: `docs/deployment/LOCAL_MODEL_LAYOUT.md` and `docs/LOCAL_MODEL_INSTALLATION_MAP.md`.

## 7. Configuration Essentials

`.env.example` is a secret-free template, organized in groups; `.env` is never committed. Key groups:

| Group | Key keys | Notes |
| --- | --- | --- |
| Core model | `MODEL_PROVIDER`, `MODEL_NAME`, `MODEL_BASE_URL`, `DEEPSEEK_API_KEY`, `API_TEMPERATURE`, `API_TIMEOUT_SECONDS` | Text provider; keys only in `.env` |
| Context window | `RECENT_CONTEXT_MAX_MESSAGES`, `RECENT_CONTEXT_MAX_CHARS` | Recent-dialogue injection window (default 8 messages / ~80 chars each) |
| Provider routing | `TEXT_PROVIDER_ORDER`, `TEXT_PROVIDER_RETRIES`, `TEXT_PROVIDER_CIRCUIT_*`, `TEXT_STREAM_TTFT_TIMEOUT_SECONDS`, `TEXT_STREAM_TOTAL_BUDGET_SECONDS`, `ASR_PROVIDER_*` | Ordered fallback, retry, circuit breaker, and stream latency-budget parameters |
| Storage and database | `STORAGE_BACKEND`, `JSONL_STORAGE_DIR`, `MYSQL_*`, `DATABASE_V2_ENABLED`, `POSTGRES_*` | JSONL is default; V2 is off by default |
| Persona | `PERSONA_PROFILE=hutao_v1` | The only built-in persona; legacy names fall back to `hutao_v1` |
| Public accounts | `PUBLIC_WEB_AUTH_ENABLED`, `SESSION_COOKIE_SECURE`, `PUBLIC_WEB_SESSION_LIFETIME_SECONDS` | Enable only after Database V2 + MySQL are ready |
| Email registration | `EMAIL_DELIVERY_ENABLED`, `SMTP_*` | Enable only after a real SMTP is ready |
| Web TTS | `PUBLIC_WEB_TTS_*` | Off by default; requires auth plus accepted voice |
| Audio input | `ASR_FILE_PRESETS`, `ASR_REPAIR_PRESETS`, `AUDIO_EMOTION_ENABLED`, `AUDIO_EMOTION_MODEL` | Transcription presets and emotion cue |
| Semantic memory | `SEMANTIC_MEMORY_*` | Off by default; switching the embedding model requires reindexing |
| World tools | `WORLD_AWARENESS_ENABLED`, `WORLD_SOURCE_ENABLED_IDS`, `WORLD_SOURCE_LEGAL_APPROVED_IDS`, `AMAP_*`, `QWEATHER_*` | Global switch + per-source enable + license review; all off by default |
| Camera and workbench | `CAMERA_*`, `VISUAL_WORKBENCH_ENABLED`, `VISUAL_WORKBENCH_ADMIN_SECRET` | Off by default; workbench secret only in `.env` |

Correct order: dependencies ready → migrations → single-item smoke → backup → enable → acceptance, then the next item; never flip every switch at once.

## 8. API Overview

### 8.1 User and client APIs

| Path | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Health check |
| `/api/v1/chat` | POST | Non-streaming text chat |
| `/api/v1/chat/stream` | POST | Streaming text chat (Desk main path) |
| `/api/v1/dialogue-context` | GET | Current conversation state, follow-ups, and open questions |
| `/api/v1/memories` | GET | Current account memory list |
| `/api/v1/memories/{memory_id}` | DELETE | Delete one memory of the current account |
| `/api/v1/audio/transcribe/file` | POST | Transcribe a single audio file |
| `/api/v1/audio/chat/prepare/file` | POST | Prepare audio chat (transcription and quality gates) |
| `/api/v1/audio/chat/file` | POST | Transcribe, then enter the chat pipeline |
| `/api/v1/audio/transcribe/stream` | WebSocket | Streaming transcription |
| `/api/v1/voice/status` | GET | Non-sensitive web voice playback status |
| `/api/v1/voice/synthesize` | POST | Synthesize short-lived audio for a registered reply (conditional mount) |

Once public auth is enabled, chat, audio chat, and memory writes require an HttpOnly session plus CSRF; client-submitted `user_id` and `session_id` are never trusted as authorization.

### 8.2 Account APIs (conditionally mounted)

`GET /api/v1/auth/status` is always available and only reports the auth/registration/password-reset switches. The routes below mount only when `PUBLIC_WEB_AUTH_ENABLED=true` + `DATABASE_V2_ENABLED=true` + complete MySQL settings; registration and password reset additionally require complete SMTP settings:

`POST /api/v1/auth/register`, `POST /api/v1/auth/verify-email`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, `POST /api/v1/auth/password-reset/request`, `POST /api/v1/auth/password-reset/confirm`.

Passwords use Argon2id; the database stores only hashes of session tokens, CSRF secrets, verification codes, and reset codes. Reset codes are delivered by email only.

### 8.3 OpenAI-Compatible endpoints

- `GET /v1/models`, `POST /v1/chat/completions`: OpenAI-compatible entry, model ID `hutao-chatcore` (or the configured `MODEL_NAME`).

### 8.4 Admin and internal endpoints

`/control`, `/api/control/*` (including `/api/control/database-v2`, `/api/control/knowledge`, `/api/control/personas`), `/docs`, `/redoc`, and `/openapi.json` must not be exposed publicly; block them at the reverse proxy in public deployments.

## 9. Testing and Acceptance

```powershell
python -m compileall -q app scripts
python -m pytest tests -q -p no:cacheprovider
```

Do not run an unscoped `pytest` from the repository root (`external/` ships third-party tests and runtimes that would be collected wrongly). The official project scope is `pytest tests`.

WeChat Mini Program client tests:

```powershell
node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js
```

Startup precheck:

```powershell
.\启动控制中心.bat --check-only
```

The latest recorded run (after the 2026-08 cleanup) is `814 passed, 2 skipped`, see the root architecture and acceptance manual; these are historical numbers — rerun the same gates after every change. In a clean clone without local models/audio samples or Playwright, tests that depend on those local assets skip automatically (the exported repository measured `810 passed, 6 skipped` in this round); both environments are green. **Automated passing does not mean real model, MySQL, SMTP, speech, vision, or world sources have been accepted online**; the complete architecture and acceptance manual is the final completion standard.

## 10. Deployment

- `Dockerfile`: Python 3.11 slim, installs ffmpeg and libsndfile1, runs Core as the non-root `hutao` user. The image contains no `external/` and no model weights.
- `deploy/compose.staging.yml`: MySQL 8.4 + Core (Core binds host `127.0.0.1:8000` only; MySQL publishes no public port), plus a `database-v2` migration profile and a `semantic-memory` (Qdrant + sync worker) profile. See `deploy/README.md`.
- Database V2 migrations never run automatically at startup: back up first, apply `migrations/v2/001` through `005` in order (e.g., via `scripts/apply_database_v2_migrations.py`); apply `006_semantic_memory_outbox.sql` only when semantic memory is enabled. Pass the readiness check, then enable `DATABASE_V2_ENABLED`.
- Operations scripts: `scripts/auth_expiry_cleanup.py` (purge expired sessions/verification/reset codes and rate-limit counters; dry-run by default, `--apply` deletes); `scripts/run_self_reflection.py --user-id <id>` (offline rule-based self-profile reflection); `scripts/evaluate_world_model_counterfactuals.py` (offline counterfactual-trial evaluation); `scripts/evaluate_world_model.py` (fixed world-model evaluation set, 12 cases across four categories, with pass rate, margin, and an honesty disclaimer). Run them manually or on a schedule.
- Required before production: domain/HTTPS, reverse-proxy allowlists, upload size and rate limits, backup/restore drills, and monitoring/alerting.

## 11. Security and Fail-Closed Defaults

- All high-risk capabilities are off by default and enabled step by step; missing configuration always fails closed.
- API keys, passwords, and tokens live only in `.env`; logs and audits carry redacted projections only and never echo secrets.
- Public accounts use HttpOnly cookies + CSRF; client-submitted identity fields are not trusted.
- Web TTS only accepts a short-lived `reply_id` issued by the server for the current streamed reply, bounded by length, frequency, concurrency, and temp-file lifetime.
- The camera is off by default: no raw frame retention, no face identity recognition, no cloud upload; the visual workbench requires a unique admin secret, short-lived HttpOnly sessions, and CSRF.
- World tools: every source must be explicitly enabled and pass license review; full page text or precise locations are never crawled silently, and conflicts keep their uncertainty.
- Self-harm/suicide outputs are blocked or replaced by local response gates, not left to model discretion.
- Public deployments must never expose `/control`, `/api/control/*`, `/docs`, `/openapi.json`, or the OpenAI-Compatible endpoint.

## 12. Retired Modules

The following historical paths are removed or retired, take no part in the current runtime, and survive only as archive notes under `docs/archive/`: QQ/WeChat Bot channels (NapCat/OneBot and related), CosyVoice2 voice-cloning training, Bert-VITS2 TTS, Ollama vision, the legacy MySQL V1 backend entry, the old Desk UI, the old architecture manual with its publication toolchain, and the rendered-browser news scheme. They are not reconnected or reconfigured. The full cleanup list is in `logs/project-cleanup/2026-08-14/project-cleanup-report.md` (local log, not committed).

## 13. GitHub Publishing Flow (Framework and Code Only)

The repository carries only framework, source, config templates, and docs; `data/models/`, `external/`, `model_training/`, logs, runtime outputs, and `node_modules` are excluded by `.gitignore`. Self-check before uploading:

```powershell
git check-ignore -v data/models/modelscope/iic/SenseVoiceSmall/model.pt
git ls-files data/models external model_training   # must be empty
git status --short
```

If the old Git history ever tracked model weights, do not push that repository to GitHub directly (history objects may still carry large files). Export a clean snapshot from the current commit and initialize a new repository:

```powershell
git archive --format=zip --output=..\HutaoChatCore-code-only.zip HEAD
Expand-Archive -LiteralPath ..\HutaoChatCore-code-only.zip -DestinationPath ..\HutaoChatCore-code-only
Set-Location ..\HutaoChatCore-code-only
git init -b main
git add .
git commit -m "Initial code-only import"
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

Create the GitHub repository empty first; do not check the auto-generate README/`.gitignore`/License boxes.

## 14. Document Index

- `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md` (root, single source of truth) and `docs/HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md` (synced public copy)
- `docs/HUTAOCHATCORE_TECHNICAL_REPORT.md`: source, architecture, features, tests, security, and release audit
- `docs/WEB_PRODUCT_ROADMAP.md`: three-device web design, interactions, and development order
- `docs/LOCAL_MODEL_INSTALLATION_MAP.md`: local model manifest and rules
- `docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md`: local-first visual world model design
- `docs/systems/README.md`: S1-S8 system split and parallel development rules
- `docs/deployment/LOCAL_MODEL_LAYOUT.md`: model directory layout
- `docs/history/agent-handoff-archive.md`: archived development handoff records
- `docs/archive/`: retirement notes for removed modules
- `deploy/README.md`: Compose deployment baseline
