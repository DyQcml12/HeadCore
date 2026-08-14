# HutaoChatCore 技术审计报告

> 报告版本：2.0（2026-08-14 项目清理后全量重写）
> 审计日期：2026-08-14
> 审计基线与运行验证：本报告依据 2026-08-14 项目清理后的工作区源码逐文件核对，并在当日用唯一项目 Python 环境实际执行了编译检查、全量测试与小程序测试。清理前的旧版报告（v1.x）已被本文件整体替换。
> 本地项目路径：`D:\Programming-file\Graduation-Project\HutaoChatCore`
> 唯一 Python 环境：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`

---

## 1. 报告摘要与审计口径

### 1.1 摘要

HutaoChatCore 是一个以 **HeadCore 为唯一认知主体、以 `hutao_v1`（胡桃）为唯一内置运行时人格**的多模态角色陪伴后端。它不是在模型调用外层加一层薄壳的转发程序，而是在大语言模型调用前后叠加了身份、关系、会话状态、自我状态、社会状态、长期记忆、世界证据、表达计划、回复质量门禁与审计持久化的完整认知运行时。

2026-08-14 项目清理后，当前产品主线收敛为七项：

1. **FastAPI Core HTTP 服务**：文本聊天、流式聊天、文件语音识别、语音对话、记忆管理与 OpenAI-Compatible 文本接口。
2. **Web Desk PWA**：`app/static/web/studio` 提供的渐进式网页对话界面，支持离线壳、文字流式回复与受保护的语音播放闭环。
3. **静态页面族**：`/auth`（登录注册）、`/me`（个人中心）、`/credits`、`/`（Vite 构建的公开落地页）、`/control`（控制中心）、`/workbench`（默认关闭的视觉工作台）。
4. **原生微信小程序**：`miniprogram/`，对话、登录注册、个人中心三页，只使用公开用户能力。
5. **HeadCore 认知内核**：`app/head/` 的场景、规划、决策、世界模型、认知事实、长期计划、校准与盲评体系。
6. **条件可用能力**（默认全部关闭）：公开账号与 SMTP 邮件验证、网页 TTS、本地摄像头视觉工作台、MySQL Database V2、Qdrant 语义记忆、世界工具（高德/新闻/政策）。
7. **数据库双轨**：JSONL 默认存储；MySQL Database V2（`migrations/v2/001-006`）与 PostgreSQL Web 核心（`migrations/postgres/001_web_core.sql`）两条条件启用路径。

本次审计当日实际执行并记录在案的验证结果：

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| Python 语法编译 | `python -m compileall -q app scripts tests` | **PASS（exit 0）** |
| 全量 Python 测试 | `python -m pytest tests -q -p no:cacheprovider` | **814 passed, 2 skipped, 2 warnings，用时 17.71s**（最终定稿复跑） |
| 小程序 Node 测试 | `node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js` | **5 passed, 0 failed（71.4ms）** |

上述数字只代表本地自动化验证。真实 DeepSeek、MySQL、PostgreSQL、SMTP、Qdrant、FunASR/SenseVoice、emotion2vec、GPT-SoVITS、高德、和风天气、新闻/政策来源与摄像头硬件均**未在本轮离线审计中做端到端验收**，第 13 章逐项列出仍待真实验收的边界。

### 1.2 审计方法

本报告不是 README 的转述，而是对以下证据的交叉核对：

- `app/` 全部 231 个 Python 模块的逐文件阅读或函数级盘点（含行数统计）；
- `app/main.py`、`app/openai_compat.py` 与全部子路由文件的**路由装饰器级清单**（第 7 章）；
- `app/core/config.py` 的 `Settings` 字段与 `.env.example` 的键级对照（第 8 章）；
- `migrations/v2/` 与 `migrations/postgres/` 的全部建表语句（第 9 章）；
- `tests/` 的 131 个测试文件（749 个测试函数）清单与实际运行结果（第 12 章）；
- `deploy/`、`Dockerfile`、`.dockerignore`、`.gitignore`、`miniprogram/`、`frontend/site/` 的现状；
- 权威手册 `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`、`docs/WEB_PRODUCT_ROADMAP.md`、`docs/deployment/LOCAL_MODEL_LAYOUT.md` 等文档与代码的一致性；
- `logs/project-cleanup/2026-08-14/project-cleanup-report.md` 与 `docs/history/agent-handoff-archive.md` 中的清理与历史记录。

### 1.3 事实来源优先级

仓库在清理前后曾存在文档漂移（旧 README 正文仍保留 NapCat/Hermes 描述并引用已删除的脚本）。清理当日已通过 README 双语重写、权威手册过期引用修正与 `docs/` 副本同步消除该类漂移。日后出现冲突时，本报告按以下优先级取信：

1. **当前运行时代码与配置默认值**（`app/`、`app/core/config.py`、`.env.example`）；
2. **本次实际测试结果**（第 1.1 节表）；
3. **最新完整架构与验收手册**（根目录 `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`）；
4. `README.md` 顶部的当前状态声明；
5. 旧手册、历史文档与 `docs/history/`、`docs/archive/` 中的退役记录。

### 1.4 状态定义

| 状态 | 本报告中的含义 |
| --- | --- |
| 已验证 | 当前源码存在，并由本次自动化检查、静态审计或本地契约测试覆盖 |
| 条件可用 | 实现存在且被测试覆盖，但需要开关、密钥、数据库、模型、设备、许可证或外部服务才生效 |
| 部分实现 | 接口或基础结构存在，但尚未形成完整端到端能力 |
| 已退役/历史 | 代码或文档已从当前源码移除，仅存在于历史档案或本附录的清理记录中 |
| 未验证 | 本次没有连接真实外部系统，不能据此宣称生产可用 |

---

## 2. 项目定位、目标与明确边界

### 2.1 产品定位

核心价值是"**统一人格与长期关系**"，而不是"多客户端各自调用模型"。所有接入面（当前为 Core HTTP、OpenAI-Compatible、网页 Desk、未来小程序/App）都应转换为统一事件再进入同一个 HeadCore；客户端只是输入输出器官，不拥有独立人格，也不能绕过认知核心直接写长期记忆。

### 2.2 主要目标

- 在不同会话与未来不同客户端之间维持稳定的胡桃人格（`hutao_v1`）。
- 用关系状态、场景、历史、记忆与世界证据增强回复，而非只依赖单轮 Prompt。
- 把模型、ASR、TTS 与视觉能力视为可替换 Provider（S6 Provider 路由）。
- 对长期记忆建立候选、审核、撤销、审计与可选语义索引流程（S4）。
- 将普通用户界面、账号空间与高权限控制面分离。
- 高风险能力默认关闭（fail-closed），逐级启用。

### 2.3 明确边界

- 当前唯一内置人格是 `hutao_v1`；注册表只有这一个 profile，未知名称一律回退并记录 `unknown_profile` 原因。
- 项目没有实现、也不宣称人类意识、AGI 或完整物理世界模拟。"世界模型"在当前代码中是受证据、来源许可、缓存与显式意图约束的**工具编排层**。
- 实时麦克风流式 ASR 的 WebSocket 协议存在（`app/audio/websocket_routes.py`、`AsrStreamSession`），但当前主线是"录制文件后上传"的链路。
- 摄像头能力不做人脸识别（`CAMERA_FACE_IDENTIFICATION_ENABLED` 默认关闭），不保留原始帧（`CAMERA_RAW_FRAME_RETENTION_SECONDS=0`），不默认开启。
- QQ/微信 Bot（NapCat/OneBot/Hermes）已于 2026-08-03 宣布退役，2026-08-14 已从源码移除；原生微信小程序是另一套当前客户端，与微信 Bot 无关。
- 项目不使用 Ollama/Qwen VLM 做图片理解；视觉走本地专用管线（YOLO/MediaPipe/RapidOCR，默认关闭）。
- 任何可能诱导自杀、自伤或死亡的输出必须在发送前拦截或替换（本地代码门，见第 11 章）。

---

## 3. 技术栈与依赖全表

### 3.1 后端技术栈

| 层次 | 技术/版本（锁定于 requirements.txt） | 用途 |
| --- | --- | --- |
| 语言 | Python 3.11（唯一环境 `D:\Tool\Progrmming-Tool\anaconda\envs\new`） | Core、脚本、迁移、测试 |
| Web 框架 | fastapi==0.124.2 | 全部 HTTP/WebSocket 路由与 OpenAPI |
| ASGI 服务器 | uvicorn==0.38.0 | 本地与 Docker 启动 |
| HTTP 客户端 | httpx==0.28.1 | DeepSeek Provider、世界工具适配器的共享异步 HTTP 协议 |
| 数据校验 | Pydantic（随 FastAPI） | 所有请求/响应模型、契约模型 |
| 测试 | pytest==9.0.3 | 全量离线测试 |
| MySQL 驱动 | asyncmy==0.2.10 | MySQL Database V2 与共享 SQL 基类 |
| PostgreSQL 驱动 | psycopg==3.3.4 | PostgreSQL Web 核心（auth/chat 存储） |
| 密码哈希 | argon2-cffi==25.1.0 | 账号密码 Argon2 哈希 |
| ASR | funasr==1.3.14 + modelscope==1.37.1 | SenseVoice/Fun-ASR 文件语音识别与模型解析 |
| 音频 | soundfile==0.14.0、torchaudio==2.11.0 | 音频读写与声学特征 |
| 嵌入模型 | sentence-transformers==3.4.1 + transformers==4.51.3 + tokenizers==0.21.4 + huggingface-hub==0.30.2 | 本地 bge-m3 语义记忆嵌入 |
| 表单/上传 | python-multipart==0.0.32 | `UploadFile` 与 `Form` 字段 |

### 3.2 requirements-vision.txt（可选，摄像头批准后显式安装）

| 依赖 | 用途 |
| --- | --- |
| rapidocr==3.9.1 + onnxruntime==1.27.0 | 图像文字 OCR（未来视觉 worker 输入） |
| opencv-python==4.11.0.86 | `OpenCvFrameSource` 本地摄像头取帧 |
| mediapipe==0.10.21 | 姿态/手势/面部特征点（本地视觉分析器） |
| ultralytics==8.3.221 | YOLO11/YOLOv8 ONNX 目标检测加载 |
| numpy==2.1.3 | 视觉管线数值计算 |

### 3.3 前端技术栈

| 端 | 技术 | 说明 |
| --- | --- | --- |
| Web Desk PWA | 原生 HTML/CSS/JS，`app/static/web/studio/` | `app.js`、`style.css`、`mobile.css`、`manifest.webmanifest`、`service-worker.js`，无构建步骤 |
| 静态页 | 原生 JS + `app/static/shared/` 主题 | auth/profile/credits/control/workbench 各自独立 JS |
| 公开落地页 | React 19 + Vite 6 + three.js 0.180 + gsap + motion | `frontend/site/` 源码，构建输出到 `app/static/web/site/` |
| 微信小程序 | 原生 WXML/WXSS/JS | `miniprogram/`，3 页 + 2 个测试文件 |

### 3.4 运行依赖（外部服务）

| 服务 | 用途 | 默认状态 |
| --- | --- | --- |
| DeepSeek API（`MODEL_BASE_URL` 可替换为兼容端点） | 唯一文本模型 Provider | 必需（纯文字 Core 唯一外部依赖） |
| MySQL 8.x | Database V2、auth（V2 路径）、knowledge、persona_management | 默认关闭 |
| PostgreSQL | 公开 Web auth + 聊天存储（`STORAGE_BACKEND=postgresql`） | 默认关闭 |
| SMTP | 注册验证码与密码重置邮件 | 默认关闭 |
| Qdrant | 语义记忆派生向量索引（MySQL 之外的可重建索引） | 默认关闭 |
| GPT-SoVITS HTTP 服务（127.0.0.1:9880） | 网页 TTS 合成（`gpt_sovits` 唯一 provider） | 默认关闭 |
| 高德/和风天气/新闻与政策源 | 世界工具证据 | 全部关闭且未批准 |
| ffmpeg | 网页 TTS 音频转码（Dockerfile 已安装） | 按需 |

---

## 4. 系统架构与模块职责

### 4.1 分层架构图（文字/ASCII）

```text
┌────────────────────────── 接入表面层（Surface） ──────────────────────────┐
│ /desk PWA  /auth /me /credits /(Vite site)  /control  /workbench(默认关)    │
│ /api/v1/chat(+stream)  /v1 OpenAI-Compatible  /api/v1/audio/* 小程序 HTTPS │
└───────────────┬───────────────────────────────────────────────────────────┘
                │ CoreApiEventAdapter → S2 ChannelEvent（统一事件）
┌───────────────▼───────────────────────────────────────────────────────────┐
│ FastAPI 装配层 app/main.py、app/openai_compat.py                           │
│   鉴权/CSRF（app/auth）· 公开身份绑定 · Database V2 平台命令前置拦截        │
└───────────────┬───────────────────────────────────────────────────────────┘
                │ HeadRuntime.handle / stream（app/head/runtime.py）
┌───────────────▼───────────────────────────────────────────────────────────┐
│ HeadCore 认知内核（app/head、app/mind、app/persona、app/dialogue、          │
│ app/expression、app/perception、app/knowledge、app/world）                  │
│   场景→关系→记忆→自我/社会状态→世界证据→计划→决策→表达计划→质量门禁→审计     │
└───────────────┬───────────────────────────────────────────────────────────┘
                │ ChatService（app/services/chat_service.py）
┌───────────────▼───────────────────────────────────────────────────────────┐
│ S6 Provider 路由（app/providers/router.py：超时/重试/熔断/脱敏 trace）      │
│   DeepSeekTextProvider · FunAsrProvider · GptSoVitsTtsProvider             │
└───────────────┬───────────────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────────────────┐
│ 存储层（S1/S4）：JSONL（默认）· MySQL Database V2 · PostgreSQL Web 核心     │
│   Qdrant 派生向量索引（semantic_memory_outbox）                            │
└───────────────────────────────────────────────────────────────────────────┘
```

### 4.2 S1–S8 系统映射表（源自 `docs/systems/README.md` 的并行系统化拆分）

| 编号 | 系统 | 代码位置 | 集成状态 |
| --- | --- | --- | --- |
| S1 | Database V2 控制面（身份/权限/关系权威源） | `app/database_control/`、`app/storage/v2_*` | 读控制面 + 写控制面已集成；真库验收未完成 |
| S2 | 统一平台事件 | `app/channels/` | 契约 + CoreApiEventAdapter 已集成 |
| S3 | 多模态感知 | `app/perception/`、`app/audio/`、`app/camera/` | ASR 观察已集成；视觉观察受工作台门控 |
| S4 | 记忆与画像生命周期 | `app/knowledge/`、`app/persona/memory_*` | 候选/审核/撤销/审计 + 语义 outbox 已实现；持久化需 MySQL |
| S5 | 人格管理控制面 | `app/persona_management/` | 内存版 + MySQL 持久版 + 沙箱人格均实现；写开关默认关 |
| S6 | Provider 路由 | `app/providers/` | 文本/流式/ASR/TTS 已路由，含熔断与运行时监视 |
| S7 | 表达计划 | `app/expression/`、`app/voice_chat/` | 文本规范化已接入；TTS/贴纸计划保留（贴纸无当前投递通道） |
| S8 | 控制面与可观察性 | `app/control/`、`app/operations/` | 状态聚合、测试报告、错误分类、审计查询已集成 |

依赖方向（原文摘录）：`S2 → S3、S2 → S7、S6 → S3、S6 → S7`；S1 是身份、权限与持久化 readiness 的权威来源；S4 只向 prompt 暴露脱敏投影；S5 只向运行时暴露已发布人格投影；S8 只读取公开状态，不根据模块是否可导入推断在线。

### 4.3 app/ 包职责总表（行数统计，共 231 个文件 / 31,393 行）

| 包 | 文件数 | 行数 | 职责 |
| --- | --- | --- | --- |
| `app/main.py` | 1 | 845 | FastAPI 装配：静态页挂载、全部路由器注册、公开 API 端点、公开鉴权装配 |
| `app/head/` | 22 | 约 3,900 | HeadCore 认知内核：状态、规划、决策、长期计划、认知事实、世界模型、校准、盲评 |
| `app/storage/` | 13 | 约 4,950 | ChatRepository 协议、JSONL 实现、MySQL 共享基类、Database V2 仓储（2,307 行）、PostgreSQL 传输 |
| `app/services/` | 5 | 约 1,910 | ChatService（1,266 行）、DeepSeekClient、ResponseEvaluator（441 行）、模型调用审计 |
| `app/world/` | 17 | 约 3,430 | 世界工具：runtime、brain、context、news_digest、source_manifest、amap/news/qweather 适配器 |
| `app/knowledge/` | 17 | 约 2,530 | 记忆生命周期：候选→审核→记录→撤销、语义记忆（352 行）、outbox、控制面 |
| `app/persona/` | 15 | 约 1,320 | 人格注册表（hutao_v1）、场景分类、语气、轮次、记忆策略、Prompt 组装 |
| `app/auth/` | 17 | 约 1,890 | 公开账号：登录/注册/验证/重置、会话、限流、MySQL/PostgreSQL 仓储、SMTP |
| `app/persona_management/` | 16 | 约 2,650 | 人格草稿→验证→发布→回滚、绑定、MySQL 持久化（mysql_store 602 行）、沙箱人格 |
| `app/database_control/` | 9 | 约 1,600 | S1 控制面 service/adapter/router、写入守卫、审计 |
| `app/control/` | 8 | 约 1,000 | 控制中心：状态、配置读写、日志、服务、测试运行器 |
| `app/providers/` | 8 | 约 790 | S6 契约、注册表、路由器（362 行）、DeepSeek/FunASR/TTS provider、运行时监视 |
| `app/audio/` | 16 | 约 1,440 | 文件 ASR 引擎（FunASR/SenseVoice）、候选与修复路由、emotion2vec、质量门、WebSocket 会话 |
| `app/camera/` | 8 | 约 830 | 本地摄像头：会话管理、取帧、YOLO/MediaPipe 分析、时序确认、注意力选择 |
| `app/mind/` | 4 | 约 240 | 会话状态、自我状态、社会状态构建与指令渲染 |
| `app/dialogue/` | 6 | 约 440 | 对话决策、行为分类、表达政策（贴纸/语音决策）、修复政策、类型 |
| `app/expression/` | 5 | 约 450 | S7 表达计划：ResponseBundle、planner、通道能力与 Core API 文本规范化 |
| `app/perception/` | 11 | 约 660 | S3 感知：输入策略、管线、适配器、质量、记忆资格、观察规范化 |
| `app/channels/` | 5 | 约 270 | S2 通道契约、能力集、CoreApiEventAdapter |
| `app/voice_chat/` | 6 | 约 750 | TTS 服务、GPT-SoVITS 适配、网页语音票据（reply_id）、分段计划、自然度清洗 |
| `app/workbench/` | 3 | 约 390 | 视觉工作台路由与短时会话（独立管理员口令 + CSRF） |
| `app/operations/` | 10 | 约 620 | S8 状态聚合、项目状态 provider、控制写入守卫、审计、报告摘要、脱敏 |
| `app/core/` | 3 | 约 460 | Settings（455 行）、项目根路径、密钥正则脱敏 |
| 其他 | 4 | 约 60 | `app/schemas.py`、`app/openai_compat.py`（264 行）、各 `__init__.py` |

### 4.4 HeadCore 内核详解（`app/head/`）

HeadCore 是唯一认知主体边界：模型只负责语言生成，**不负责**身份、关系、记忆取舍与工具调用判断。核心数据结构与函数：

- **`HeadState`**（`app/head/state.py`，`build_head_state()`）：由用户输入、场景、关系、会话状态、记忆投影、认知事实与世界证据综合构建；`render_head_projection()` / `render_continuity_timeline()`（`projection.py`）把状态渲染进系统 Prompt。
- **规划与决策**：`build_head_plan()` + `selected_decision()`（`planning.py`）产生候选动作并按评分选择；`decide_head_action()`（`decision.py`）与 `build_communication_state()`（`communication.py`）确定本轮沟通动作（回复/澄清/结束）。
- **长期计划**（`long_term_planning.py`，246 行）：`build_long_term_plan`、`activate_next_step`、`record_step_result_from_world_events`、`replan_remaining_steps`，把多步目标与执行证据（`build_world_event_evidence`）串起来。
- **认知事实**（`cognitive_facts.py`，311 行）：`resolve_cognitive_facts`、`project_cognitive_facts`、`revoke_cognitive_fact`、`cognitive_facts_from_world_result`；与用户陈述冲突时由 `_reinforce_matching_world_evidence` 对齐。
- **世界模型**（`world_model.py` 174 行 + `world_model_store.py`）：`build_head_world_model`、`project_head_world_model`、`_mark_relation_conflicts`，维护实体/事件/关系/因果假设，带来源与置信度校验。
- **自适应与校准**：`adaptation.py`（`build_adaptive_policy`/反馈结果解码）、`calibration.py`（配对偏好 `evaluate_pairwise_preferences` + Fleiss' kappa 多评审者一致性）、`feedback.py`（上一轮动作 JSON + 建议预算编码）。
- **盲评**（`blind_review.py`）：`build_blind_review_package`、`write_review_csv`、`evaluate_blind_reviews`，把规划样本打包成不带偏好的盲评 CSV，用于人工客观评测。
- **事件与情景记忆**：`events.py`（`load_head_event_context`、`record_head_events`、`record_head_response_event`）、`episodic_memory.py`（`HeadEpisodeKind`、事件记录）。
- **运行时入口**：`runtime.py` 的 `HeadRuntime.handle()` / `stream()` 把 `ChannelEvent` + `HeadRuntimeContext` 转成 ChatService 调用，并把 Head 事件回写（`allow_head_event_write` 控制）。

### 4.5 关键支撑模块

- **`app/mind/`**：`build_conversation_state`（话题/情绪推断）、`build_self_state`、`build_social_state`（边界模式推断），生成对话/自我/社会三层指令。
- **`app/persona/`**：`profile_registry.py` 只注册 `hutao_v1`（别名 `hutao`/`hu_tao`/`genshin_hutao`），`resolve_persona_profile` 对未知名回退并记录 `unknown_profile`；`PersonaGatePolicy` 含禁用身份标记（`小何`）与"现代助手模板"标记；`persona_prompt_builder.py` 组装 `PersonaPrompt`；`scene_classifier.py` 五类场景（casual/task/emotional/safety/repair）；`memory_policy.py`、`tone_policy.py`、`turn_taking.py`、`repetition_policy.py`、`relationship_context.py` 提供各类策略信号。
- **`app/dialogue/`**：`build_dialogue_decision`（是否强制短回复）、`act_classifier`（技术/情绪/对话行为）、`expression_policy`（贴纸/语音决策与阈值）、`repair_policy`（修复指令与标记）、`sanitize_visible_reply`（可见文本清洗）。
- **`app/services/chat_service.py`（1,266 行）**：`ChatService.reply()` / `stream_reply()` 是主链路编排器——`_prepare_chat` 组装 30+ 字段的 `PreparedChat`，`ProviderRouter` 调用模型，`ResponseEvaluator` 评估，必要时 `_repair_live_response` 二次修复，最后 `_write_records` 落库并写审计；`BASE_SYSTEM_PROMPT` 固定"唯一 Self 是 hutao_v1"的边界。
- **`app/services/response_evaluator.py`（441 行）**：30+ 个确定性判定函数（身份问题、自我伤害诱导、越界关系主张、撤销记忆复发、编造现实经历、传统汉字/波浪线装饰、口头禅密度等），是本地回复门禁的主力。
- **`app/providers/`**：`RoutingPolicy`（超时/重试/熔断参数校验）、`ProviderRouter.route()/stream()`（顺序路由、单流只允许首个有效块前换 provider）、`ProviderRuntimeMonitor`（进程级状态监视）、`DeepSeekTextProvider`（错误码映射 401/403/429/超时/空响应）、`FunAsrProvider`、`GptSoVitsTtsProvider`。
- **`app/world/`**：见第 6.6 节数据流与第 4.3 节职责表；`WorldBrainCoordinator` 是唯一被 ChatService 直接消费的入口。
- **`app/control/` + `app/operations/`**：`build_control_status`（`health_checks.py`）、`OperationsStatusService.snapshot`（1 秒聚合超时）、`ControlWriteGuard.authorize/verify/record_result`（写操作授权与审计）、`EnvConfigStore`（带备份的 .env 写入）、`ControlServiceSpec`（`hutao_core`、`gpt_sovits` 两个受管服务）、`ControlTestSpec`（`control_center`/`api_voice`/`full_pytest` 三个受管测试）。


### 4.6 存储层模块逐个说明（`app/storage/`）

- **`chat_repository.py`（680 行）**：`ChatRepository` 协议 + `JsonlChatRepository` 实现；记录类型 `SessionRecord`/`MessageRecord`/`ModelInvocationRecord`/`PersonaEvaluationRecord`/`MemoryRecord`/`ContactRecord`/`PlatformIdentityRecord`/`RelationshipClaimRecord`；工具 `_jsonl_lock()`（线程锁追加）、`new_uuid()`、`utc_now()`。
- **`mysql_repository.py`（727 行）**：`MySQLChatRepository` 共享 SQL 传输基类。私有传输面 `_connect()`/`_execute()`/`_fetchone()`/`_fetchall()`/`_validate_settings()` 与工具 `mysql_datetime()`/`mysql_message_role()` 被 V2、PostgreSQL、auth、knowledge、persona_management 全部继承复用；其 ChatRepository 方法组是兼容契约面。清理后保留本文件的原因即在此（它不是独立可删除的 V1 后端，见附录 A）。
- **`v2_models.py`（345 行）**：Database V2 行映射与领域模型——`V2Permissions`/`V2Profile`/`V2PlatformAccount`/`V2RelationshipContext`/`V2Persona`/`V2PersonaVersion`/`V2PersonaContext`/`V2RecentChat`/`V2ChatMessage`/`V2PendingRelationshipClaim`；映射函数 `profile_from_row()`/`account_from_row()`/`recent_chat_from_row()`/`chat_message_from_row()`/`pending_claim_from_row()`/`persona_from_row()`/`persona_version_from_row()`/`persona_context_from_row()`；关系权限 `permissions_for_relationship()` 与规范化 `normalize_platform_group_id()`/`normalize_relationship_type()`/`fallback_persona_context()`/`build_relationship_context()`。
- **`v2_repository.py`（176 行）**：`DatabaseV2Repository` 协议（30+ 方法：关系解析、控制快照、档案分页、关系更新、bootstrap、绑定、认领、最近会话/历史、平台命令审计）。
- **`v2_mysql_repository.py`（2,307 行，最大单体）**：`MySQLDatabaseV2Repository(MySQLChatRepository, DatabaseV2Repository)` 同时实现控制面与聊天仓储两套协议；关键方法 `find_relationship_context()`/`get_control_status_snapshot()`/`get_admin_profile_snapshot()`/`list_profile_snapshots()`/`get_profile_detail_snapshot()`/`update_profile_relationship()`/`record_database_control_event()`/`list_database_control_events()`/`ensure_default_personas()`/`resolve_persona_context()`/`bootstrap_admin_if_missing()`/`resolve_relationship_context()`/`set_relationship()`/`bind_accounts()`/`import_legacy_jsonl_snapshot()`/`_profile_id_for_legacy_user()`/`_execute_transaction()` 以及覆盖基类的会话/消息/记忆方法。
- **`v2_runtime.py`（100 行）**：运行时装配面——`should_use_database_v2()`（`DATABASE_V2_ENABLED` + qq/wechat 平台身份或 `trusted_core_profile`）、`build_database_v2_platform_command_service()`（前缀 `("胡桃",)`）、`build_database_v2_chat_repository()`、`database_v2_chat_user_id()`（平台前缀合成 ID）、`try_handle_database_v2_platform_message()`（命令前置拦截，见 6.7）。
- **`v2_command_policy.py`（146 行）**：`V2AdminCommand`/`V2CommandDecision`；`decide_v2_admin_command()` 与 `parse_v2_admin_command()`/`parse_set_relationship()`/`parse_platform_user_command()`/`parse_bind_accounts()`/`parse_claim_command()`/`parse_platform()`/`parse_relationship_type()`。
- **`v2_command_executor.py`（155 行）**：`V2CommandExecutionResult` 与 `context_result()`/`platform_arg()`/`relationship_arg()`。
- **`v2_platform_command_service.py`（204 行）**：`DatabaseV2PlatformCommandService.handle_message()`（`is_command`/`should_reply`/`should_enter_chat_service` 判定 + `_record_command_audit()`）；`normalize_platform_command_text()`/`target_platform_user_id()`/`to_adapter_payload()`。
- **`v2_relationship_service.py`（74 行）**：`PlatformIdentity`/`RelationshipResolution`（`to_model_context()`）、`DatabaseV2RelationshipService.resolve()`/`bootstrap_admin_from_settings()`、`parse_bootstrap_ids()`。
- **`postgres_repository.py`（72 行）**：`postgres_is_configured()` + `PostgreSQLChatRepository(MySQLChatRepository)`（psycopg 异步 + dict_row，替换 `_connect/_execute/_fetchone/_fetchall` 四个传输方法，复用基类全部 SQL）。
- **`repository_factory.py`（12 行）**：`create_chat_repository()`——`jsonl` 与 `postgres/postgresql` 两个分支，其余值抛 `ValueError`。

### 4.7 记忆与知识模块逐个说明（`app/knowledge/`）

- **`models.py`（112 行）**：领域枚举与模型 `MemoryState`（pending/approved/revoked 等）、`MemoryScope`、`MemoryDecisionKind`、`KnowledgeActor`、`MemoryCandidate`、`MemoryRecord`、`PortraitPatch`、`MemoryDecision`、`MemoryProjection`、`AuditEvent`；错误族 `KnowledgeLifecycleError`/`EntityNotFoundError`/`InvalidStateTransitionError`。
- **`repository.py`（121 行）**：`KnowledgeRepository` 协议 + `InMemoryKnowledgeRepository`（`apply_approval` 等 13 组方法）。
- **`mysql_repository.py`（456 行）**：`MySQLKnowledgeRepository`——候选/记录/审计三表持久化实现（对应 `migrations/v2/002`）。
- **`service.py`（239 行）**：`KnowledgeLifecycleService`——`submit()`（候选入队）、`decide()`（approve/reject → 记录）、`revoke()`/`delete()`、`expire_due()`、`project()`（只读投影）、`_transition()`（状态机）、`_active_conflicts()`（冲突检测）、`_audit()`、`_validate_candidate()`。
- **`runtime.py`（90 行）**：`MemoryProjectionRequest`/`MemoryProjectionProvider`/`LifecycleMemoryProjectionProvider`/`ReadinessCheckedMemoryProjectionProvider`/`render_memory_projection()`——ChatService 消费的记忆投影面。
- **`intake.py`（89 行）+ `runtime_intake.py`（97 行）**：`MemoryCandidateIntakeService.submit()` 与运行时摄入（`_idempotency_key()` 幂等键、`_reject_reason()` 拒绝原因）。
- **`control.py`（99 行）**：`KnowledgeControlService`——`resolve_actor()`/`status()`/`list_candidates()`/`decide()`/`revoke()`/`_require_ready()`（fail-closed readiness）。
- **`factory.py`（92 行）**：`build_memory_projection_provider()`（按配置选语义/生命周期 provider）、`_semantic_memory_is_configured()`、`_build_embedding_provider()`、`build_semantic_memory_outbox_processor()`。
- **`semantic_memory.py`（352 行）**：`EmbeddingProvider` 协议 + `OpenAICompatibleEmbeddingProvider` + `LocalSentenceTransformerEmbeddingProvider`（懒加载模型、线程池嵌入）；`QdrantSemanticMemoryIndex`（cosine 集合、`ensure_collection`/`upsert`/`remove`/`search`）与 `InMemorySemanticMemoryIndex`；`SemanticMemoryProjectionProvider`（`_validate_vector`/`_cosine_similarity`）。
- **`semantic_outbox.py`（103 行）**：`SemanticMemoryOutboxOperation/State/Event`、仓库协议、`SemanticMemoryOutboxProcessor`（`initialize_index`/`process_once`/`_apply`/`_record_is_indexable`/`_failure_reason`）。
- **`readiness.py`（44 行）**：`KnowledgePersistenceStatus` 与 `assess_knowledge_persistence()`。
- **`router.py`（78 行）**：`create_knowledge_control_router()`（前缀 `/api/control/knowledge`，见 7.8）。

### 4.8 世界工具模块逐个说明（`app/world/`）

- **`contracts.py`（137 行）**：`WorldSourceDefinition`/`WorldQuery`/`WorldObservation`/`WorldObservationBatch`/`WorldAcquisitionResult` 等类型契约（`WorldSourceKind` 已移除 `RENDERED_BROWSER`）。
- **`registry.py`（37 行）**：`WorldSourceAdapter` 协议 + `WorldSourceRegistry`（`register/get/definitions`）。
- **`cache.py`（81 行）**：`AsyncTTLCache`（`get_or_load` 单飞合并、`_remove_expired` 惰性过期、条目上限）。
- **`service.py`（63 行）**：`WorldAcquisitionService.acquire()`（启用 + 法律批准双门）与 `build_world_cache_key()`（SHA-256 规范键）。
- **`source_manifest.py`（161 行）**：`WorldSourceCatalogEntry`/`WorldSourceManifest`/`load_source_manifest()`（HTTPS 强制、hostname 白名单、重复 ID 拒绝、凭证化 URL 拒绝、`automation_policy` 分类）。
- **`runtime.py`（337 行）**：`WorldRuntime`——`status()`（目录/注册/启用/批准计数）、`locate_public_ip()`（同意门控）、`current_weather()`/`weather_forecast()`、`resolve_district()`、`search_places()`、`route()`、`news()`、`policy_updates()`、`news_digest()`；`build_world_runtime()`/`_configured_source_ids()`。
- **`brain.py`（451 行）**：`WorldToolIntent/WorldToolAccessMode/WorldRequestOrigin` 枚举、`WorldToolDecision`、`decide_world_tools()`（显式请求判定、退出短语、IP 不猜测）、`world_tool_access_mode()`、`WorldBrainCoordinator.build_context()/build_context_with_evidence()`、主题与地点抽取函数（`_topic_for_text`/`_weather_location_keyword`/`_travel_endpoints`/`_travel_city`/`_travel_modes`/`_travel_time_budget`）。
- **`context.py`（678 行）**：`WorldConflict`/`WorldContextProjection`/`WorldContextBuildResult`/`DistrictCandidate`/`DistrictResolution`/`PlaceCandidate`/`PlaceResolution`；`WorldContextAssembler`（上限 8 条/3500 字符、`not_requested`/`proactive_denied`/`disabled`/`needs_location`/`needs_travel_endpoints`/`unavailable` 投影、`resolve_district`/`district_confirmation`/`resolve_place`/`place_confirmation`、`from_weather`/`from_travel_plan`/`from_policy`/`from_news_digest`、`_weather_conflicts` 温差 5℃ 判冲突、`_evidence_lines`、`_forecast_weather`/`_travel_weather_buffer`/`_travel_mode_label`、安全提取 `_safe_text/_safe_coordinate/_safe_number/_safe_url`）。
- **`news_digest.py`（247 行）**：`NewsDigestService.build()` 并发获取、部分失败状态、标题去重合并、来源 URL 保留、SHA-256 摘要缓存键（`_digest_cache_key`）、确定性排序。
- **`errors.py`/`http.py`**：类型化错误码与共享 HTTP 协议。
- **`adapters/amap.py`（545 行）**：`AmapWorldSourceAdapter`——`_fetch_ip_location`（仅全局 IPv4 + 同意）/`_fetch_weather`/`_fetch_district`（`/v3/config/district` subdistrict=0）/`_fetch_place`（`/v3/place/text`）/`_fetch_route`（驾车/公交/步行三模式归一化）、`_request_json`（status=1 + infocode=10000 校验）、`_normalized_routes`/`_normalized_casts`、边界化提取 `_bounded_integer`/`_safe_query_text`/`_coordinate`/`_number_text`。
- **`adapters/news.py`（480 行）**：`GdeltNewsAdapter`（JSON 发现、跟踪参数清理、去重、日期归一化）、`OfficialRssNewsAdapter`（RSS/Atom 解析、HTML→文本、hostname 白名单）、`GovCnPolicyAdapter`（政策元数据，不取正文）；`_HtmlTextExtractor`、`_canonical_public_url` 等辅助。
- **`adapters/qweather.py`（147 行）**：`QweatherWeatherAdapter`（`_resolve_location` + 天气归一化 `_normalize_weather`）。

### 4.9 Provider 与音频模块逐个说明（`app/providers/`、`app/audio/`）

- **`providers/contracts.py`（147 行）**：`ProviderCapability`（TEXT/ASR/TTS）、`ProviderHealth`、`ProviderErrorCode`（NOT_CONFIGURED/AUTHENTICATION_FAILED/RATE_LIMITED/TIMEOUT/INVALID_RESPONSE/UNAVAILABLE 等）、`ProviderId`、`TextRequest`/`AsrRequest`/`AsrResult`/`TtsRequest`、`Provider` 协议族、`ProviderError`/`ProviderTrace`/`ProviderAttempt`。
- **`providers/router.py`（362 行）**：`RoutingPolicy`（`__post_init__` 参数校验）、`_CircuitState`、`RoutingFailed`/`StreamingRoutingFailed`、`StreamingRoutingDecision`、`ProviderRouter`（`route/stream/_route_stream/_resolve_provider/_circuit_is_open/_record_failure/_attempt/_skipped_attempt/_publish/_redact/_sanitize_error`）。
- **`providers/registry.py`（36 行）**：`ProviderRegistration`/`ProviderRegistry`（`register/get/health/set_health`）。
- **`providers/runtime.py`（48 行）**：`ProviderRuntimeStatus`/`ProviderRuntimeMonitor`（`record/snapshot/clear`）。
- **`providers/deepseek.py`（49 行）**：`DeepSeekTextProvider`（`generate_text/stream_text/_map_deepseek_error`）。
- **`providers/funasr.py`（57 行）**：`FunAsrProvider`（`transcribe/_optional_text/_optional_float`）。
- **`providers/tts.py`（63 行）**：`VoiceReplyTtsProvider`/`GptSoVitsTtsProvider`/`normalize_tts_provider_id`/`_map_tts_error`（Bert-VITS2 分支已移除）。
- **`providers/fakes.py`（35 行）**：`FakeClock`/`FakeTextProvider`/`FakeProvider`。
- **`audio/funasr_engine.py`（168 行）**：`FunAsrFileEngine`（`from_preset`/`transcribe_file`/`_load_model`/`extract_transcription_result`/`extract_text`/`extract_raw_text`/`extract_sensevoice_emotion`/`clean_asr_text`）。
- **`audio/pipeline.py`（149 行）**：`NamedFileAsrEngine`、`transcribe_with_candidates`/`transcribe_with_repair_candidates`、`select_best_candidate`/`build_selection_reason`、`build_asr_file_response`、字段提取 `extract_candidate_text`/`extract_optional_string`/`extract_optional_float`。
- **`audio/provider_routing.py`（48 行）**：`RoutedFileAsrEngine`（S6 路由包装）。
- **`audio/file_service.py`（104 行）**：`parse_asr_file_presets`/`parse_optional_asr_presets`、`get_engine_for_preset`/`get_emotion_engine`、`build_default_file_asr_engines`/`build_default_repair_asr_engines`/`build_file_asr_engines`、`get_routed_engine_for_preset`、`transcribe_audio_file`、`enrich_with_audio_emotion`。
- **`audio/emotion_engine.py`（98 行）**：`Emotion2VecEngine`（`analyze_file`/`parse_emotion2vec_result`/`normalize_emotion_label`）。
- **`audio/quality.py`（44 行）**：`AsrQuality` 与 `evaluate_asr_text_quality`。
- **`audio/quality_metrics.py`（26 行）**：`normalize_transcript`/`character_error_rate`（CER）。
- **`audio/chat_input.py`（58 行）**：`PreparedAudioChatInput`、`clean_asr_text_for_chat`、`prepare_audio_chat_input`、`clarify_reasons_for_audio_chat`。
- **`audio/model_paths.py`（17 行）**：`resolve_modelscope_model`/`resolve_funasr_aux_model`。
- **`audio/enrichment.py`（23 行）**：`EmotionEnrichedAsrEngine`。
- **`audio/stream_session.py`（25 行）**：`AsrStreamSession`（流式协议包装）。
- **`audio/schemas.py`（65 行）**：`AsrEvent`/`AsrCandidateResponse`/`AsrFileResponse`/`AudioChatFileResponse`/`PreparedAudioChatFileResponse`/`AsrStartMessage`。
- **`audio/websocket_routes.py`（44 行）**：WebSocket 端点（见 7.11）。
- **`audio/asr_engine.py`（18 行）**：`FileAsrEngine`/`StreamingAsrEngine` 协议。

### 4.10 摄像头、工作台与语音模块逐个说明（`app/camera/`、`app/workbench/`、`app/voice_chat/`）

- **`camera/contracts.py`（61 行）**：`CameraSessionStatus`、`CameraSessionStartRequest`（`require_explicit_consent`）、`CameraSession`、`CameraObservation`（`normalize_scene_label`/`validate_labels` 白名单标签）。
- **`camera/local_runtime.py`（210 行）**：`FrameSource`/`FrameAnalyzer` 协议、`OpenCvFrameSource`、`LocalVisionAnalyzer`（`_load_yolo`/`_load_mediapipe`/`analyze`/`_detect_objects`/`_detect_landmarks`）、`CaptureJob`/`LocalCaptureController`。
- **`camera/session_manager.py`（108 行）**：`CameraSessionManager`（`start/get/stop/owned_session_ids/is_active_for_capture/validate_observation/validate_capture_observation`）。
- **`camera/temporal_state.py`（100 行）**：`CameraTemporalState`（`observe/latest/remove_session`，时序二次确认）。
- **`camera/normalization.py`（38 行）**：`camera_observation_to_world_observation`（观察→世界观察，带 TTL）。
- **`camera/attention.py`（85 行）**：`CameraAttentionSelection`（`select_camera_context`/`camera_clarification_instruction`）。
- **`workbench/sessions.py`（153 行）**：`WorkbenchSessionStore`（`login/require/logout` + 失败限流 `_LoginFailureState`）。
- **`workbench/router.py`（233 行）**：工作台路由（见 7.7）。
- **`voice_chat/tts_service.py`（160 行）**：`should_request_voice_reply`/`synthesize_voice_reply`/`convert_audio_for_delivery`（ffmpeg）/`build_voice_file_stem`/`check_tts_api_ready`/`check_voice_provider_ready`/`normalize_voice_provider`。
- **`voice_chat/gpt_sovits_tts.py`（75 行）**：`synthesize_gpt_sovits`/`check_gpt_sovits_ready`。
- **`voice_chat/web_tts.py`（88 行）**：`WebVoiceReplyStore`（`new_reply_id/remember/acquire/release/_purge_expired`）与 `WebVoiceReplyNotFoundError/BusyError/RateLimitError`。
- **`voice_chat/planner.py`（248 行）**：`VoiceReference`/`VoiceSegmentPlan`/`VoiceChatPlan`、`load_reference_library`/`plan_voice_chat`/`infer_reply_emotion`/`emotion_for_segment`/`split_reply_for_voice`/`split_long_text`/`choose_natural_split`。
- **`voice_chat/naturalness.py`（78 行）**：`strip_performance_cues`/`strip_leading_tts_punctuation`/`normalize_reply_for_natural_chat`/`normalize_text_for_tts`/`constrain_reply_for_realtime_tts`/`trim_to_natural_boundary`。
- **`voice_chat/audio_utils.py`（103 行）**：`append_wav_files`/`apply_short_fade`/`trim_wav_start`/`apply_fade_in`/`wav_basic_stats`。

### 4.11 认证模块逐个说明（`app/auth/`，17 个文件）

- **`service.py`（170 行）**：`AuthService`——`login/require_session/logout/current_account` 与 `_audit`；`normalize_email`。
- **`identity.py`（43 行）**：`bearer_session_token`/`resolve_web_identity`（未启用公开认证时直接采用请求身份，启用后强制会话 + 可选 CSRF）。
- **`sessions.py`（31 行）**：`hash_opaque_token`/`issue_session`/`session_is_active`。
- **`passwords.py`（25 行）**：argon2 哈希与校验。
- **`rate_limit.py`（63 行）**：`AuthRateLimitService`（`enforce` + SHA-256 主题哈希 + 滑动窗口 + 封禁期）。
- **`registration.py`（94 行）**：`RegistrationService`（未验证用户 + 一次性验证 token）。
- **`password_reset.py`（110 行）**：`PasswordResetService`（重置码哈希存储、成功后撤销全部会话）。
- **`smtp_delivery.py`（77 行）**：`SmtpEmailVerificationDelivery`（STARTTLS 可配）。
- **`email_delivery.py`（9 行）**：邮件投递协议。
- **`audit.py`（12 行）**：`AuthAuditEvent`/`AuthAuditSink`。
- **`router.py`（135 行）**：`create_auth_router`（login/mobile login/me/logout）。
- **`registration_router.py`（52 行）**：`create_registration_router`（register/verify-email）。
- **`password_reset_router.py`（46 行）**：`create_password_reset_router`（request/confirm）。
- **`runtime.py`（98 行）**：`configure_public_web_auth`（逐层挂载装配，见 6.6.1）。
- **`mysql_repository.py`（414 行）**：`MySQLAuthRepository`（V2 表 `web_users/web_sessions/...` 的实现）。
- **`postgres_repository.py`（269 行）**：`PostgreSQLAuthRepository`。
- **`__init__.py`**：包导出。

### 4.12 数据库控制面与人格管理模块逐个说明（`app/database_control/`、`app/persona_management/`）

- **`database_control/service.py`（178 行）**：`DatabaseControlRepository` 协议 + `DatabaseControlService`（`resolve_read_actor/get_status/get_admin/list_control_operations/list_profiles/get_profile/bootstrap_admin/set_profile_relationship/bind_accounts/review_claim/_require_write_ready`）。
- **`database_control/mysql_adapter.py`（452 行）**：`MySQLDatabaseV2Adapter`（协议实现 + `_profile_from_row/_account_from_row/_encode_cursor/_decode_cursor/_json_safe_mapping/_clean_ids/_redact_id` 与 `build_mysql_database_control_adapter`）。
- **`database_control/actor.py`（36 行）**：`require_actor/require_read_admin/require_mutate_admin/build_actor_identity`。
- **`database_control/contracts.py`（138 行）**：`ActorIdentity/SourceAccount/DatabasePermissions/DatabaseActor/DatabaseStatus/ControlAuditEvent/ProfilePage/BootstrapAdminRequest/BindAccountsRequest` 等 + `redact_platform_user_id/sanitized_account`。
- **`database_control/errors.py`（40 行）**：域错误映射（连接/驱动→503、完整性→409）。
- **`database_control/integration_guard.py`（10 行）**：真实集成库名必须 `test_*` 或 `*_test`。
- **`database_control/persona_audit.py`（102 行）**：`DatabasePersonaControlAuditSink`/`InMemoryPersonaControlAuditSink`。
- **`database_control/persona_persistence.py`（254 行）**：`PersonaDraftRow/PersonaValidationRow/PersonaVersionRow/PersonaReleaseRow/PersonaBindingRow`、`PersonaPersistenceStore` 协议与 `InMemoryPersonaPersistenceStore`。
- **`persona_management/service.py`（242 行）**：`InMemoryPersonaManagementService`（create_draft/validate_draft/record_evaluation/approve/publish/rollback/archive/save_binding/get_runtime_projection/get_status 等）。
- **`persona_management/persistent_service.py`（275 行）**：`PersistentPersonaManagementService`（异步、行映射 `_draft_from_row/_version_from_row/_release_from_row/_binding_from_row`）。
- **`persona_management/mysql_store.py`（602 行）**：`MySQLPersonaPersistenceStore(MySQLChatRepository)`（六张 `persona_management_*` 表 + `_json_text` + 数据库错误映射 `_raise_database_error`）。
- **`persona_management/sandbox.py`（220 行）**：`LocalSandboxPersonaService`（JSONL、按 `owner_id` 隔离、`_normalize_definition` 校验）与 `render_sandbox_persona_projection`。
- **`persona_management/contracts.py`（100 行）**：`DraftStatus/ReleaseStatus/ValidationStage/BindingScope`、`PersonaDefinition/PersonaDraft/PersonaVersion/PersonaRelease/PersonaBinding/PersonaValidationResult/BindingContext/PersonaRuntimeProjection/PersonaManagementStatus`。
- **`persona_management/codec.py`（58 行）**：`encode_definition/decode_definition/encode_surface/decode_surface`（人格定义的持久化编解码）。
- **`persona_management/validation.py`（43 行）**：`validate_schema/validate_gates`。
- **`persona_management/projection.py`（30 行）**：`build_runtime_projection/render_runtime_projection`。
- **`persona_management/bindings.py`（32 行）**：`resolve_binding`。
- **`persona_management/readiness.py`（46 行）+ `mysql_readiness.py`（31 行）**：`assess_persona_management_persistence`/`MySQLPersonaManagementReadiness`。
- **`persona_management/router.py`（169 行）/`async_router.py`（313 行）/`sandbox_router.py`（150 行）**：三个前缀路由（见 7.10）。

### 4.13 控制、运维、表达、感知与通道模块逐个说明

- **`control/routes.py`（248 行）**：控制中心路由 + `ControlWriteGuard` 装配 + `require_control_admin/audit_control_result`。
- **`control/config_schema.py`（73 行）**：`SettingSpec`/`SETTING_GROUPS`/`grouped_setting_specs`（7 组 28 键）。
- **`control/config_store.py`（96 行）**：`EnvConfigStore`（`read_public_values/update_values/_validate_updates/_backup/normalize_setting_value`）。
- **`control/health_checks.py`（86 行）**：`build_control_status`/`check_http`/`check_world_awareness`。
- **`control/log_reader.py`（157 行）**：`list_log_targets/read_log_tail/read_bot_log_summary/read_recent_lines/compact_log_line/strip_ansi/is_noisy_log_line/redact_sensitive_log_text/repair_mojibake/count_cjk`。
- **`control/service_manager.py`（127 行）**：`list_services/start_service/stop_service`（`hutao_core`、`gpt_sovits`）。
- **`control/test_runner.py`（112 行）**：`list_control_tests/run_control_test/write_test_report`（`control_center/api_voice/full_pytest`）。
- **`operations/aggregation.py`（70 行）**：`OperationsStatusService.snapshot`（1 秒聚合超时 + `_propagate_dependencies`）。
- **`operations/project_status.py`（136 行）**：`DatabaseControlStatusProvider/ProviderRuntimeStatusProvider/KnowledgeLifecycleStatusProvider/build_project_status_providers/asr_model_readiness`。
- **`operations/control_write.py`（125 行）**：`ControlWriteGuard`（`authorize/verify/record_result`）。
- **`operations/audit.py`/`observability.py`/`reports.py`/`probes.py`/`redaction.py`/`system_contract_status.py`：操作审计、错误分类（`classify_error_lines`）、测试报告摘要（`summarize_test_report`）、静态/TCP/HTTP 探针、`redact_text/config_presence`、契约状态 provider。
- **`expression/planner.py`（208 行）**：`ExpressionPlanner.plan`（`_plan_voice/_plan_sticker/_plan_attachments/_voice_fallback/_is_controlled_absolute_path`）。
- **`expression/models.py`（81 行）**：`ResponseBundle/DeliveryFallback/VoicePlan/StickerPlan/DeliveryContext/PlatformCapabilities`。
- **`expression/integration.py`（81 行）**：`capabilities_from_channel/delivery_context_from_event/provider_supports_tts/with_provider_capability/response_bundle_to_channel_response`。
- **`expression/core_api.py`（31 行）**：`plan_core_api_text/render_core_api_text/normalize_core_api_text`（Core API 文本单模态计划）。
- **`perception/contracts.py`（110 行）**：`PerceptionModality/PerceptionQuality/MemoryDecision`、`PerceptionInput`（`require_single_payload`）、`ProviderTrace/MemoryEligibility/PerceptionObservation/ProviderOutput`。
- **`perception/pipeline.py`（87 行）**：`PerceptionPipeline.observe_asr/run`（`InputPolicy` 校验 + 观察归一化）。
- **`perception/integration.py`（121 行）**：`perception_input_from_channel_event/routing_trace_to_perception/normalize_asr_result`。
- **`perception/adapters.py`（50 行）**：`AsrObservationAdapter`（`observe/_trace/_error_code`）。
- **`perception/normalization.py`（20 行）**：`redact_text`（脱敏 + 截断）。
- **`perception/quality.py`（30 行）**：`clamp_confidence/assess_memory/text_agreement`。
- **`perception/validation.py`（58 行）**：`InputPolicy/validate_input`（`_validate_local_path/_validate_remote_url`）。
- **`perception/knowledge.py`（33 行）+ `memory.py`（13 行）**：`observation_to_memory_candidate`/`evaluate_memory_eligibility`。
- **`channels/contracts.py`（137 行）**：`ChannelPlatform/ChannelEventType/ChannelThreadType/AttachmentKind/ResponsePartKind`、`ChannelIdentity/ChannelThread/ChannelAttachment/ChannelMessage/ChannelEvent`（`validate_payload`）与 `ChannelCapabilitySet`。
- **`channels/capabilities.py`（49 行）**：`capabilities_for/evaluate_delivery`。
- **`channels/adapters/core_api.py`（57 行）**：`CoreApiEventAdapter.adapt`。
- **`mind/`（4 文件）**、**`dialogue/`（6 文件）**：见 4.5。
- **`services/model_client.py`（107 行）**：`DeepSeekClient`（`chat/stream_chat/_extract_text/_extract_stream_delta`）。
- **`services/model_audit.py`（52 行）**：`text_hash/ModelInvocationAuditLogger.write`。
- **`core/config.py`（455 行）**：`Settings` + `read_env_file/load_env_values/get_setting/sanitize_persona_text/load_settings`。
- **`core/security.py`（5 行）**：`redact_secrets`。
- **`schemas.py`（59 行）**：公开请求/响应模型（见 7.2 引用）。
- **`openai_compat.py`（264 行）**：见 6.8/7.3。

### 4.14 运行时装配小结（`app/main.py`）

模块级变量：`settings`、静态根路径常量、`memory_projection_provider`、`app`、静态挂载（`/site/assets`）、路由器注册顺序（audio → openai_compat → control → camera → workbench → database_control → knowledge_control → persona_management(内存版) → 条件性 persona_management(async 持久版) → auth(条件性) ）、`sandbox_persona_service`、`web_voice_reply_store`、`public_web_tts_configured` 等派生标志；`build_runtime_chat_service()/build_head_runtime()` 工厂；`_authenticated_identity/_authenticated_memory_identity/_authenticated_profile_repository` 身份辅助（`app/main.py` 尾部）。

---

### 4.15 HeadCore 契约类型详解（`app/head/contracts.py`，266 行）

**动作枚举**：`HeadAction`——`answer`（回答）、`clarify`（澄清）、`continue_task`（继续任务）、`repair`（修复）、`support`（支持）、`refuse`（拒绝）；`CommunicationAct`——`answer_question/acknowledge/clarify/emotional_support/accept_correction/continue_task/topic_withdrawal/request_advice/avoid_advice`（九种沟通动作）。

**反馈与状态枚举**：`FeedbackOutcome`——`accepted/corrected/advice_rejected/continued/stopped/unknown`；`CognitiveFactStatus`——`active/conflicted/stale/revoked/superseded`；`CognitiveFactKind`——`observation/belief/hypothesis`；`CognitiveFactSourceKind`——`world_evidence/user_report/model_inference`；`HeadEpisodeKind`——`task_started/task_updated/question_asked/question_answered/feedback_received`；`WorldAssertionStatus`——`active/conflicted/stale`；`LongTermPlanStatus`——`pending/active/blocked/completed/failed`；`PlanStepStatus`——`pending/active/completed/blocked/failed`；`ExecutionEvidenceSource`——`test_runner/tool_result/user_confirmation/world_event/model_claim`。

**执行证据与计划结构**：`HeadExecutionEvidence`（`evidence_id/source/reference/observed_at/succeeded/expires_at`）——长期计划的完成必须挂执行证据，模型声称不能直接作为完成依据（`MODEL_CLAIM` 与 `WORLD_EVENT` 等来源分级）；`HeadPlanStep`（`step_id/objective/depends_on/completion_criteria/status/attempts/max_attempts=2/evidence/failure_reason`）；`HeadLongTermPlan`（`plan_id/goal/steps/status/version/replan_count/max_replans=2/current_step_id`）——重试与重规划次数有硬上限。

**世界模型结构**：`WorldEntity`（`entity_id/entity_type/name`）、`WorldRelation`（`relation_id/subject_id/predicate/object_id/source_id/valid_from/valid_until/confidence/status`——每个关系必须带来源与有效期）、`WorldEvent`/`CausalHypothesis` 等（后续行定义），以及 `HeadState`（含 `communication/plan/uncertainties/feedback` 等聚合字段）与 `HeadDecision`/`HeadCandidateAction`/`HeadActionScore`/`HeadAdaptivePolicy`/`TurnTakingPolicy`/`HeadReflection`/`HeadFeedback`/`HeadEventContext`/`HeadEventRecord`/`HeadEpisodicEvent` 等完整类型族。`contracts.py` 后段为 `load_cognitive_facts/save_cognitive_fact/revoke_cognitive_fact` 等持久化函数声明（实现在 `cognitive_facts.py`/`world_model_store.py`/`long_term_plan_store.py`）。

### 4.16 人格场景分类与策略细节（`app/persona/`、`app/dialogue/`）

**场景分类器**（`scene_classifier.py`）：`classify_scene()` 按 `SCENE_MARKERS` 顺序做确定性子串匹配，首个命中返回（置信度 `0.65 + 0.1×命中标记数`，上限 1.0），无命中落 `daily_chat`（0.5）。九类场景与代表标记：

| 场景 | 代表标记（节选） |
| --- | --- |
| `memory_revoke` | 不要记/别记/不准记/忘掉/撤销/删掉/forget |
| `memory_correction` | 记错/改了称呼/改称呼/纠正/以后叫/不是这个 |
| `debug_frustration` | debug/bug/报错/异常/typeerror/valueerror/attributeerror/traceback/崩了/跑不起来 |
| `life_death` | 死亡/死/去世/离开了/葬礼/告别/往生 |
| `identity_challenge` | 你是谁/你叫什么/自我介绍/你是不是在演/你的设定/你是ai/你是模型/是真人吗/有意识吗 |
| `affection` | 想你/喜欢你/陪我/亲近/抱抱/爱你 |
| `task_support` | 代码/项目/计划/后端/前端/数据库/接口/测试/论文/模型/训练/下一步 |
| `emotional_support` | 累/烦/焦虑/难受/崩溃/没动力/内耗/怕 |
| `daily_chat` | 默认兜底 |

**记忆策略**（`memory_policy.py`）：`build_memory_policy(classification)` 按场景决定是否允许写记忆、是否进入记忆审核候选；敏感/情绪场景收紧写入。**记忆服务**（`memory_service.py`）：`infer_memory_write()`（写入判定）、`normalize_alias_memory/normalize_user_preference/normalize_conversation_preference/compact_memory_text`（记忆规范化）、`build_style_instruction`（记忆风格指令）、`filter_revoked_memories/build_revocation_boundary/is_revoked/extract_memory_terms/split_common_memory_phrase`（撤销边界与词项拆分）。

**语气与轮次**：`tone_policy.py`（`build_tone_policy(role)`/`build_tone_policy_instruction` 按关系角色出语气策略）；`turn_taking.py`（`classify_turn_taking`/`should_minimize_reply`——短确认语降回复长度）；`repetition_policy.py`（`build_repetition_signal`——重复输入检测与去重信号）；`relationship_context.py`（`parse_owner_platform_ids/build_relationship_context`——owner 与普通联系人的关系上下文；`blocked` 角色在 ChatService 层直接短路）。

**对话决策与修复**：`dialogue/policy.py`（`build_dialogue_decision`/`should_force_short_reply`/`build_response_style_instruction`/`constrain_reply_text`）；`dialogue/repair_policy.py`（`build_repair_policy/build_repair_instruction`——修复模式下的指令模板与标记检测）；`dialogue/act_classifier.py`（`is_technical_context/infer_emotion/classify_dialogue_act/has_casual_marker`）。

**响应规则**（`persona/response_rules.py`，116 行）：模块级常量提供 `MODERN_ASSISTANT_MARKERS`（"我是AI/语言模型/无法扮演"等现代助手模板标记，供 `PersonaGatePolicy.assistant_template_markers` 引用）与身份泄漏防护标记（`小何` 负向守卫）——任何旧人格标记回显都会在 `ResponseEvaluator` 层被拦截。

### 4.17 依赖方向与共享文件冻结规则（`docs/systems/README.md`）

- 跨系统只能依赖公开 contract，不允许导入对方 repository 的私有方法、UI 内部状态或测试 helper。
- 共享文件默认冻结：`app/main.py`、`app/services/chat_service.py`、`app/core/config.py`、`app/control/routes.py`、`.env/.env.example`、`requirements.txt`、`migrations/v2/*`、`README.md`、`AGENTS.md`——需要变更时开发者只提交 `integration-notes.md`，由集成人员统一修改。
- 契约优先顺序：1) 在系统自己的 `contracts.py`/`models.py` 定义 typed contract；2) 写 contract/service 单元测试；3) 实现系统内部逻辑与内存 fake；4) 提交集成说明；5) 集成人员按依赖顺序连接。
- 正式实现与兼容实现：需要持久化或 I/O 的接口用异步 protocol/service；内存 repository、同步 service 和 fake 只用于测试/预览，必须显式声明 `durable=false`、`write_ready=false`，不得维护第二份生产状态。
- 集成后唯一运行时主链路：`平台原始事件 → S2 ChannelEvent → 身份解析与权限（S1）→ 附件感知（S3，经 S6 路由）→ 记忆候选与只读投影（S4）→ 人格运行时投影（S5）→ ChatService/模型调用（S6）→ ResponseBundle（S7）→ S2 平台投递 adapter → S8 状态、trace 与审计投影`。

### 4.18 HeadCore 22 个文件逐一说明（`app/head/`）

| 文件（行数） | 职责 |
| --- | --- |
| `__init__.py`（134） | 包导出：60+ 类型与函数集中出口 |
| `contracts.py`（266） | 全部枚举与 frozen dataclass 契约（见 4.15） |
| `state.py`（155） | `build_head_state` + `_infer_active_task/_latest_pending_question/_known_context/_infer_uncertainties/_compact` |
| `events.py`（189） | `load_head_event_context/record_head_events/record_head_response_event` 事件加载与回写 |
| `episodic_memory.py`（107） | 情景事件记录（`HeadEpisodeKind` 五种） |
| `planning.py`（204） | `build_head_plan/selected_decision` + 候选动作生成/去重（`_is_complex_scene/_candidate/_all_acts/_deduplicate`） |
| `decision.py`（63） | `decide_head_action` + `_needs_clarification` |
| `communication.py`（102） | `build_communication_state/_primary_act/_build_turn_policy` |
| `long_term_planning.py`（246） | 长期计划全生命周期（见 4.4） |
| `long_term_plan_store.py`（113） | 长期计划持久化（JSONL） |
| `cognitive_facts.py`（311） | 认知事实编解码/冲突/撤销/世界证据对齐 |
| `world_model.py`（174） | `build_head_world_model/project_head_world_model` + 校验族（`_validate_event/_validate_hypothesis/_validate_source_and_confidence/_require_entities/_validate_identifier/_validate_text`） |
| `world_model_store.py`（129） | 世界模型持久化 |
| `world_evidence.py`（79） | `cognitive_facts_from_world_result`（世界结果→认知事实） |
| `world_state.py`（80） | `HeadWorldState` 构建/渲染/不确定性（`world_state_uncertainties`） |
| `projection.py`（93） | `render_head_projection/render_continuity_timeline` |
| `feedback.py`（79） | `build_head_feedback/encode_head_action/encode_head_feedback`（上一轮动作 JSON + 建议预算） |
| `adaptation.py`（112） | `build_adaptive_policy/apply_adaptive_policy/is_policy_reset_request` + 反馈结果解码 |
| `calibration.py`（169） | 配对偏好/多评审者一致性（`_fleiss_kappa`） |
| `evaluation.py`（128） | 规划场景评估器（`evaluate_planning_scenarios`） |
| `blind_review.py`（195） | 盲评打包/回收/评估（`build_blind_review_package/write_review_csv/write_manifest/load_review_rows/evaluate_blind_reviews`） |
| `runtime.py`（64） | `HeadRuntime`（handle/stream/_prepare_call）与 `HeadRuntimeContext`/`UnsupportedHeadEventError` |

### 6.11 PreparedChat 字段逐项说明（`app/services/chat_service.py` 的 `_prepare_chat()` 产物）

`PreparedChat` 是主链路准备阶段的 30+ 字段聚合快照，分组如下：

- **基础**：`started_at/session/user_message/user_input/user_id`。
- **Prompt 三元组**：`prompt_text/system_prompt/user_prompt`（`build_persona_prompt` 产出的完整人格 prompt 与用户侧 prompt）。
- **感知元数据**：`input_source/input_quality_passed/input_quality_reasons/input_emotion/input_emotion_source/input_emotion_confidence`。
- **关系与会话**：`relationship_context`（含 `role`）、`conversation_state/self_state/social_state`。
- **HeadCore**：`head_state`、`allow_head_event_write`、`head_world_state`、`world_grounding_facts`、`head_runtime_origin`。
- **人格**：`persona_profile_id/persona_profile_version/persona_profile_fallback_reason/persona_mode`。
- **记忆投影**：`knowledge_projection_status/knowledge_projection_count`。
- **人格管理投影**：`persona_management_projection_status`、`sandbox_persona_id/sandbox_persona_name/sandbox_persona_status`。
- **世界工具**：`world_context_status/world_context_item_count/world_context_conflict_count/world_tool_intent`。

这些字段既是 prompt 组装输入，也是 `_write_records()` 审计元数据来源（不落原始投影文本）。

### 6.12 ResponseEvaluator 判定函数清单（`app/services/response_evaluator.py`，441 行）

- **门禁类**：`evaluate()`（主入口）、`world_fact_grounding_reasons()`（事实依据）、`answers_identity_question()`（身份回答检查）、`response_looks_like_plain_assistant()`（通用助手模板识别）。
- **安全类**：`is_life_death_context()`、`disallows_death_joke()`、`is_self_harm_directive_bait()`、`repeats_self_harm_directive()`、`is_low_trust_boundary_context()`。
- **关系与记忆类**：`is_unconfirmed_relationship_claim()`、`repeats_unconfirmed_relationship_term()`、`is_memory_revoke_context()`、`repeats_revoked_term()`。
- **风格类**：`contains_cjk()`、`contains_decorative_wave()`、`contains_common_traditional_chinese()`、`catchphrase_count()`、`contains_marker()`、`continues_stopped_topic()`。
- **身份与语境类**：`is_identity_question()`、`needs_canon_anchor()`、`is_debug_context()`、`is_modern_context()`、`is_emotional_support_context()`、`claims_real_world_experience()`（编造现实经历门）、`has_concrete_next_step()`。
- **辅助**：`_contains_conflicting_weather_number()`。

### 6.13 修复路由细节（`ChatService._repair_live_response_decision/_repair_live_response`）

评估不合格时：`_repair_live_response_decision()` 生成带原因指令的修复请求（身份泄漏→改用中性措辞；编造经历→去掉未证实叙述；撤销记忆复发→尊重撤销边界），作为**第二次独立路由决策**（`repair_provider_trace` 记录）；`_repair_live_response()` 保持字符串兼容面。两次仍失败进入本地兜底（`_evaluation_fallback_reply`），保证最终输出一定经过门禁。

## 5. 项目目录结构与文件地图

```text
HutaoChatCore/
├── app/                         # 后端应用（231 py / 31,393 行）
│   ├── main.py                  # FastAPI 装配与公开 API（845 行）
│   ├── openai_compat.py         # /v1 兼容层（264 行）
│   ├── schemas.py               # 公开 DTO
│   ├── core/                    # Settings、安全脱敏
│   ├── head/                    # HeadCore 认知内核（22 文件）
│   ├── mind/                    # 会话/自我/社会状态
│   ├── persona/                 # hutao_v1 注册表与人格策略
│   ├── dialogue/                # 对话决策与表达政策
│   ├── expression/              # S7 表达计划
│   ├── perception/              # S3 感知管线
│   ├── channels/                # S2 通道契约与适配器
│   ├── providers/               # S6 Provider 路由
│   ├── knowledge/               # S4 记忆生命周期与语义索引
│   ├── world/                   # 世界工具（runtime/brain/adapters）
│   ├── audio/                   # 文件 ASR 与流式协议
│   ├── camera/                  # 本地摄像头感知
│   ├── workbench/               # 视觉工作台（默认关）
│   ├── voice_chat/              # TTS 服务与网页票据
│   ├── auth/                    # 公开账号（默认关）
│   ├── storage/                 # JSONL/MySQL V2/PostgreSQL
│   ├── database_control/        # S1 控制面
│   ├── persona_management/      # S5 人格管理（内存/持久/沙箱）
│   ├── control/                 # 控制中心后端
│   ├── operations/              # S8 状态聚合与审计
│   ├── services/                # ChatService/评估/客户端/审计
│   ├── api/                     # 占位
│   └── static/                  # 页面族：web/studio、web/site、auth、
│                                #   profile、credits、control、workbench、shared
├── scripts/                     # 49 个运维/评估/冒烟脚本
├── tests/                       # 131 个测试文件（根 54 + 10 子目录）
├── migrations/
│   ├── v2/                      # 001-006（MySQL Database V2，924 行 SQL）
│   └── postgres/                # 001_web_core.sql（194 行 SQL）
├── miniprogram/                 # 原生微信小程序（21 文件）
├── frontend/site/               # Vite/React 公开落地页源码
├── deploy/                      # compose.staging.yml 等
├── docs/                        # 手册/路线/模型清单/历史档案/清理记录
│   ├── archive/                 # 退役记录（QQ/微信 Bot 退休等）
│   ├── history/                 # agent-handoff-archive.md（410KB 只读）
│   ├── systems/                 # S1-S8 系统设计
│   ├── architecture/            # 架构提案/优化研究/系统化审计
│   ├── deployment/              # LOCAL_MODEL_LAYOUT.md
│   ├── head/                    # HEADCORE_COGNITIVE_ARCHITECTURE.md
│   ├── testing/                 # HeadCore 世界模型验收记录
│   ├── world/                   # 世界工具设计文档
│   └── assets/                  # UI 截图等
├── data/                        # 本地资产（world/sources.json 等 8 个 JSON 受跟踪；
│                                #   models/hutao_voice/stickers 等大件不入库）
├── logs/                        # 运行日志与报告（精简后 4.6MB/878 文件）
├── external/                    # GPT-SoVITS 等外部程序（本地，不入库）
├── model_training/              # 训练资产（已清理，本地）
├── output/                      # 生成物（旧发布物已删）
├── artifacts/  build/  tmp/     # 本地工作残留（不入库）
├── .env.example                 # 配置模板（唯一入库存的 env 模板）
├── requirements.txt             # 核心依赖（锁定版本）
├── requirements-vision.txt      # 可选视觉依赖
├── Dockerfile  .dockerignore  .gitignore  .gitattributes
├── AGENTS.md                    # 精简交接（约 7KB，当前状态）
├── README.md                    # 项目说明
└── HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md  # 权威手册
```

### 5.5 Git 与发布状态（审计当日实测）

- **提交历史**：本地仓库仅 2 个提交（`frist`、`Initial HutaoChatCore release`），分支 `main`。
- **索引状态**：64 条已暂存变更（主要是 `data/models` 下模型文件的删除，即"取消跟踪模型"已完成到索引层）；29 条未暂存变更（静态页与新站点构建）；5 个未跟踪文件（`app/static/web/site/assets/index-B8o5YgBw.css`、`index-BvyiZDeu.js`、`three.module-BT1pP-6r.js` 与 `frontend/site/src/components/ParticleField.jsx`、`frontend/site/src/hooks/useLandingAnimations.js`）。
- **历史体积**：`.git` 约 8.9GB——对象库约 3GB + `.git/lfs` 约 5.85GB（历史中曾跟踪模型权重）。`git ls-files external model_training data/models` 返回空，索引已是 code-only，但**历史仍在**。
- **受跟踪的数据文件**（8 个合法夹具）：`data/world/sources.json`、`data/head_planning_scenarios.json`、`data/head_planning_pairwise_preferences.json`、`data/head_planning_multi_reviewer_annotations.json`、`data/persona_continuity_scenarios.json`、`data/persona_live_continuity_scenarios.json`、`data/persona_live_scenarios.json`、`data/persona_long_chat_scenarios.json`、`data/persona_training_seed.json`（实际 9 个）。
- **发布流程**（README「仅上传框架与代码」）：`git archive` 导出快照 → 新目录 `git init` → 全新仓库 push；旧仓库仅本机保留。清理报告确认 2026-08-14 未执行任何 git commit。
- **`.gitattributes`** 当前只有一条注释（"Runtime model weights are local deployment assets and are not versioned."），无 LFS 规则残留。

### 5.6 数据目录本地资产明细（`data/`，审计当日，均不入库）

| 目录 | 大小/文件 | 用途与处置 |
| --- | --- | --- |
| `data/models/` | 约 8.4GB / 82 文件 | ASR/情绪等模型权重（ModelScope 目录），本地部署资产 |
| `data/hutao_voice/` | 约 416MB / 1264 文件 | 历史语音训练/审计音频样本，本地保留 |
| `data/stickers/` | 约 194MB / 1093 文件 | QQ 表情包素材（Bot 已退役，本地保留） |
| `data/asr_samples/` | 7.1MB / 30 | ASR 固定语料样本（运营脚本用） |
| `data/asr_online_random/` | 2.8MB / 14 | 随机在线样本 |
| `data/asr_emotion_web_samples/` | 2.5MB / 6 | 情绪样本 |
| `data/generated_voice/` | 8.9MB / 41 | TTS 输出（含历史 cosyvoice2_smoke.wav 等旧产物） |
| `data/qq_vision_cache/` | 0.5MB / 5 | QQ 视觉缓存（已退役） |
| `data/fine_tune/` | 6 文件 | 微调数据集目录 |
| `data/world/` | 1 文件 | `sources.json`（受 Git 跟踪） |
| `data/pip_cache/` | 已删除（83MB） | 清理前为 pip 缓存 |

### 14.7 权威手册 L0–L6 分层验收对照

| 层 | 内容 | 本报告的对应证据 |
| --- | --- | --- |
| L0 文档与配置 | 手册/模板/清单一致性 | 第 8、13 章 + `test_deployment_files.py` |
| L1 本地自动化 | compileall/pytest/node | 本次实测（814 passed / 5 passed） |
| L2 本地浏览器 | Desk/auth/control 页面人工验收 | 历史记录存档（14.6）；本次未重跑真实浏览器 |
| L3 Docker 与数据库 | compose 启动、V2/Postgres 迁移演练 | 未验收（14.2） |
| L4 账号与真实邮箱 | 注册/验证/重置真实 SMTP | 未验收（14.2） |
| L5 服务器封闭测试 | HTTPS/反代/限流下的封闭测试 | 未开始 |
| L6 扩大公开测试 | 邀请制/资源预算 | 未开始 |

当前项目处于 **L1 完整、L2 部分（历史）、L3–L6 未完成** 的状态。

### 15.8 技术债评分表（影响/建议/优先级）

| 债项 | 影响 | 建议 | 优先级 |
| --- | --- | --- | --- |
| `v2_mysql_repository.py` 2307 行单体 | 改动风险高、评审困难 | 按控制面/聊天仓储/迁移拆分 | 中 |
| `chat_service.py` 1266 行 | 主链路难以局部验证 | 拆 prompt 组装/门禁/记录 | 中 |
| Git 历史 8.9GB 含模型 | push 失败/泄露风险 | code-only 导出（15.2） | **高** |
| README 文档漂移 | 误导运行 | 已消除：2026-08-14 双语重写 + 删退役引用 + docs 副本同步 | 已消除 |
| 核心依赖过重 | 镜像/安装成本 | 拆可选依赖组（15.4） | 中 |
| 控制面读端点无鉴权 | 公网误暴露风险 | 反代白名单 + 部署检查清单 | **高**（部署层） |
| 聊天接口无全局限流 | 滥用成本 | 反代限流（手册 19 章） | 中（部署层） |
| `dialogue/policy.py` 默认 `channel=qq` 等遗留默认值 | 语义误导 | 改名清理 | 低 |
| websockets.legacy 弃用警告 | 潜在升级阻断 | 随 uvicorn 升级 | 低 |
| 历史文档与退役结构残留（qq_* 表、HUTAO_OWNER_QQ_IDS） | 误解空间 | 文档标注 + 渐进清理 | 低 |

### 9.10 会话上下文读取路径（Prompt 侧）

- `JsonlChatRepository.list_recent_messages(session_id, limit=8)` 供 `build_recent_context()`（`chat_service.py`）组装近期对话；`list_recent_messages_by_user(limit=12)` 供跨会话背景。
- `render_continuity_timeline()`（`app/head/projection.py`）把近期消息渲染成连续性时间线进入系统 Prompt。
- `build_head_state()` 的 `_known_context()`/`_latest_pending_question()` 从近期消息推导活跃任务与待答问题（`/api/v1/dialogue-context` 暴露 `tracking_task/waiting_for_user` 状态）。
- 记忆投影（`render_memory_projection`）与撤销边界（`build_revocation_boundary`）叠加在会话上下文之上，二者均不覆盖模型 Provider 的原始对话上下文拼接。

## 6. 端到端数据流（逐条标注模块与函数）

### 6.1 文本聊天（非流式，`POST /api/v1/chat`）

1. **入口**：`app/main.py::chat()`。先经 `_authenticated_web_request()` 完成公开鉴权（`public_web_auth_configured` 为真时：校验 `hutao_session` Cookie + `X-CSRF-Token`，并拒绝携带 platform 身份字段的公开请求）；`_validate_sandbox_persona_request()` 校验可选 `persona_id` 是否为沙箱人格（仅 Web 沙箱允许，`LocalSandboxPersonaService.get_runtime_projection()`）。
2. **统一事件**：`_core_api_channel_event()` → `CoreApiEventAdapter.adapt()`（`app/channels/adapters/core_api.py`）把请求映射为 S2 `ChannelEvent`（消息文本、会话、身份、输入质量/情绪元数据）。
3. **V2 命令前置拦截**：`try_handle_database_v2_platform_message()`（`app/storage/v2_runtime.py`）——仅当 `DATABASE_V2_ENABLED` 且 platform 为 qq/wechat 时尝试把消息解释为管理命令（`DatabaseV2PlatformCommandService.handle_message()`，见 6.7）；命中则直接返回本地生成的命令回复，不再调用模型。
4. **存储选择**：`_should_use_database_v2_chat_storage()` 判定是否用 `MySQLDatabaseV2Repository`（`build_database_v2_chat_repository`）；否则 `build_head_runtime()` 用 JSONL（`create_chat_repository` → `JsonlChatRepository`）。
5. **认知运行时**：`HeadRuntime.handle(event, context)`（`app/head/runtime.py`）→ `_prepare_call()` 注入 `head_runtime_origin` → `ChatService.reply()`。
6. **准备阶段**：`ChatService._prepare_chat()` 依次完成：`ensure_session`（会话兜底）→ `save_message`（用户消息落库）→ `resolve_contact` → `build_relationship_context`（关系上下文，`blocked` 角色直接短路返回"这边暂时不接待。"）→ `build_conversation_state`/`build_self_state`/`build_social_state`（`app/mind/`）→ `build_head_state`（`app/head/state.py`）→ `load_memory_context` + `build_memory_policy`（`app/persona/memory_service.py`，记忆投影与撤销边界）→ `resolve_persona_state`（casual/task/emotional/safety/repair 五模式）→ `build_persona_prompt`（`app/persona/persona_prompt_builder.py`，含 `render_head_projection`、`render_continuity_timeline`、`build_style_instruction`、记忆投影、人格运行时投影/沙箱投影、世界上下文投影）→ 可选世界上下文（`WorldBrainCoordinator.build_context_with_evidence()`，见 6.5）。
7. **模型调用**：`ChatService._text_routing_policy()` 构造 `RoutingPolicy` → `ProviderRouter.route()`（`app/providers/router.py`）按 `TEXT_PROVIDER_ORDER` 顺序调用 `DeepSeekTextProvider.generate_text()`（`app/providers/deepseek.py`，底层 `DeepSeekClient.chat()`，`app/services/model_client.py` 直连 `chat_completions_url`）；超时/重试/熔断/错误码映射全在路由层。
8. **评估与修复**：`ResponseEvaluator.evaluate()`（`app/services/response_evaluator.py`）给出 `EvaluationResult`（门禁、事实依据、修饰标记）；不合格时 `_repair_live_response_decision()`/`_repair_live_response()` 带原因指令做一次修复路由；仍不合格走 `_evaluation_fallback_reply`/`_fallback_response` 本地兜底。
9. **世界守卫**：`_world_guard_reply()` 检查回复是否与已获取的世界证据冲突（`_weather_grounding_facts`、`world_fact_grounding_reasons`），冲突则替换为证据一致的守卫文本。
10. **落库与审计**：`_write_records()` 保存助手消息、`ModelInvocationAuditLogger.write()`（`app/services/model_audit.py`，含 `text_hash` 与脱敏）、`record_head_response_event`、`save_persona_evaluation`。
11. **出口**：`normalize_core_api_text()`（`app/expression/core_api.py`）→ `_web_voice_chat_response()`（TTS 开启时经 `WebVoiceReplyStore.remember()` 登记 `reply_id` 并返回 `X-Hutao-Reply-Id` 响应头）。

### 6.2 流式聊天（`POST /api/v1/chat/stream`）

与 6.1 相同直到模型调用，区别在：

- `ChatService.stream_reply()` → `ProviderRouter.stream()`/`_route_stream()`：每个 chunk 独立超时；**只允许在首个有效块之前换 provider**（`StreamingRoutingDecision`），空流归类 `invalid_response`，中断只保存已产出的部分输出。
- 音频输入（`input_source=="audio"`）时 `_limit_audio_stream_if_needed()` → `limit_audio_stream_to_realtime_budget()` 用 `asyncio.timeout` 限制总时长（`VOICE_CHAT_REPLY_TIMEOUT_SECONDS`，默认 25 秒），超时向流内追加"这次回复耗时过长，请点击重试。"。
- TTS 开启时 `_web_voice_streaming_response()` + `_remember_completed_web_voice_reply()` 在流完整结束后才登记 `reply_id`；中途断开（`UnicodeDecodeError`/未完成）不登记，浏览器拿不到票据就无法请求语音。
- 出口经 `stream_core_api_text()` 保持 text/plain 分块边界。

### 6.3 文件语音：ASR → 质量门 → 对话（`/api/v1/audio/*` 三端点）

1. **转写端点** `transcribe_audio_file_endpoint()`：`save_upload_to_temp()`（`app/audio/file_service.py`）临时落盘 → 线程池内 `transcribe_audio_file()`。
2. **转写管线** `transcribe_audio_file()`：`build_file_asr_engines(parse_asr_file_presets(...))` 组装 `NamedFileAsrEngine` 列表（默认 `sensevoice-small`）；`transcribe_with_candidates()`（`app/audio/pipeline.py`）多候选并行，`select_best_candidate()` + `build_selection_reason()` 选优；质量不佳时用 `ASR_REPAIR_PRESETS` 走 `transcribe_with_repair_candidates()`；`evaluate_asr_text_quality()`（`app/audio/quality.py`）给出质量判定与原因；`AUDIO_EMOTION_ENABLED` 时 `enrich_with_audio_emotion()` → `Emotion2VecEngine.analyze_file()`（`app/audio/emotion_engine.py`）附加情绪标签/置信度。
3. **引擎层**：`FunAsrFileEngine`（`app/audio/funasr_engine.py`）经 `resolve_modelscope_model()`（`app/audio/model_paths.py`）优先解析本地目录，缺失时可能按模型 ID 联网；`RoutedFileAsrEngine`（`app/audio/provider_routing.py`）把候选执行挂到 S6 `FunAsrProvider`（`app/providers/funasr.py`）带上超时与熔断；`extract_sensevoice_emotion()` 从 SenseVoice 富标签抽取情绪。
4. **语音对话准备** `prepare_audio_chat_file_endpoint()`：`prepare_audio_chat_input()`（`app/audio/chat_input.py`）清洗文本并判断 `should_clarify`；需要澄清时返回 `clarification_reply` 并旁路模型。
5. **语音对话** `audio_chat_file_endpoint()`：同上，澄清时直接返回 `ChatResponse`（`provider="local"`、`model="audio-chat-quality-gate"`、`used_live_api=False`）；否则 `CoreApiEventAdapter` 组装事件 → `HeadRuntime.handle()`，上下文携带 `input_source="audio"`、`input_quality_passed`/`reasons`、`input_emotion`/`source`/`confidence`——这些元数据随后进入 `build_input_emotion_instruction()` 参与人格 Prompt。
6. **WebSocket 流式协议**（部分实现）：`/api/v1/audio/transcribe/stream`（`app/audio/websocket_routes.py`）按 `AsrStartMessage` 开始、分片 PCM 收 `AsrEvent` 列表、`finish` 收尾；`AsrStreamSession`（`app/audio/stream_session.py`）包装 `StreamingAsrEngine` 协议。该协议有单元契约，但**不是当前主线**（主线为录制文件上传）。

### 6.4 网页 TTS 的 reply_id 闭环（`POST /api/v1/voice/synthesize`）

1. **前置门**：`public_web_tts_configured = PUBLIC_WEB_TTS_ENABLED and 公开鉴权已生效`，否则 404。
2. **身份**：`_authenticated_identity()`（`app/main.py`）校验 Cookie/CSRF（`require_csrf=True`）或 Bearer（小程序用），把请求方映射为 `profile_id` + `session_id`。
3. **票据获取**：`WebVoiceReplyStore.acquire()`（`app/voice_chat/web_tts.py`）校验 `reply_id` 存在、归属用户与会话一致、未在合成中（409）、频率未超限（429，`PUBLIC_WEB_TTS_MIN_INTERVAL_SECONDS`）、文本长度未超 `PUBLIC_WEB_TTS_MAX_REPLY_CHARS`（422，超限即释放并拒绝）——**浏览器不能重传任意文本**。
4. **合成**：线程池 `synthesize_voice_reply()`（`app/voice_chat/tts_service.py`）→ `synthesize_gpt_sovits()`（`app/voice_chat/gpt_sovits_tts.py`）调用独立 GPT-SoVITS HTTP 服务；`convert_audio_for_delivery()` 用 ffmpeg 转 MP3。
5. **路径安全**：输出必须位于 `web_voice_tts_output_root`（`_resolve_web_voice_tts_output_root()` 强制相对路径且解析后必须在项目目录内）下的 `reply_id` 子目录，越界直接 503 并清理。
6. **交付与回收**：`FileResponse`（`audio/mpeg`、`Cache-Control: no-store`）+ `BackgroundTask(_remove_web_voice_output, output_dir)` 响应后删除临时音频；`finally` 中 `web_voice_reply_store.release()` 释放票据。
7. **状态暴露**：`GET /api/v1/voice/status` 只返回 `enabled` 与 `max_reply_chars` 两个非敏感字段。

### 6.5 世界工具证据链（默认关闭）

1. **启用**：`Settings.world_awareness_enabled` 为真时，`ChatService.__init__` 惰性构建 `WorldBrainCoordinator(build_world_runtime(settings))`（`app/world/brain.py`、`runtime.py`）。
2. **意图判定**：`decide_world_tools(user_input)` 纯确定性规则——只有显式询问（天气/预报、新闻摘要、政策、路线）才给 `WorldToolDecision`；显式退出短语与普通提及不触发；`world_tool_access_mode(platform)` 决定来源可信度。
3. **运行时**：`WorldRuntime` 注册 3 类适配器（`AmapWorldSourceAdapter`：IP 定位/实时天气/预报/行政区划/地点/驾车/公交/步行路线；`GdeltNewsAdapter`/`OfficialRssNewsAdapter`/`GovCnPolicyAdapter`：`app/world/adapters/news.py`；`QweatherWeatherAdapter`：`app/world/adapters/qweather.py`）。天气请求（当前天气/预报）默认路由到高德 `/v3/weather/weatherInfo`（`city=adcode`，缓存 TTL 走 `AMAP_WEATHER_CACHE_TTL_SECONDS`），和风天气适配器保留为备选。每个来源必须同时满足：全局开关、来源 `enabled`、`legal_approved`（清单 `data/world/sources.json` + `WORLD_SOURCE_LEGAL_APPROVED_IDS`）与 `WorldAcquisitionService` 门控。
4. **获取**：`WorldAcquisitionService.acquire()`（`app/world/service.py`）经 `AsyncTTLCache.get_or_load()`（`app/world/cache.py`，条目上限/单飞合并）调用适配器；`build_world_cache_key()` 用 SHA-256 规范键，键内不含原始查询文本。
5. **组装**：`WorldContextAssembler`（`app/world/context.py`）做过期过滤、来源标注、字符/条目上限、跨源冲突检测（天气标签不同或温差 ≥5℃ 记 `WorldConflict`）、凭证化 URL 拒绝、天气预测聚合（`_forecast_weather`）与路线后果比较（`_travel_weather_buffer`）。
6. **进入 Prompt**：`ChatService._prepare_chat()` 把投影并入系统 Prompt（不信任外部数据的边界提示）；`_versioned_world_evidence_facts()` 把世界结果转成版本化事实，`cognitive_facts_from_world_result()`（`app/head/world_evidence.py`）写入 HeadCore 认知事实。
7. **守卫**：`_world_guard_reply()`/`_weather_grounding_facts()` 阻止模型输出与已取得证据冲突的天气/事实数字。

### 6.6 公开账号：注册 → 验证 → 登录 → 重置

1. **装配**：`configure_public_web_auth()`（`app/auth/runtime.py`）按条件逐层挂载：①`PUBLIC_WEB_AUTH_ENABLED` 且（`STORAGE_BACKEND=postgresql` 且 `postgres_is_configured` → `PostgreSQLAuthRepository`；或 `DATABASE_V2_ENABLED` 且 MySQL 完整 → `MySQLAuthRepository`，并置 `database_v2_profile_source=True`）；②`EMAIL_DELIVERY_ENABLED` 且 SMTP 四字段完整 → 挂载注册与密码重置路由。
2. **注册** `POST /api/v1/auth/register`（`registration_router.py`）：`AuthRateLimitService.enforce()`（`app/auth/rate_limit.py`，按 email/ip_prefix/device 三键、5 次/10 分钟、封 30 分钟）→ `RegistrationService`（`app/auth/registration.py`）创建未验证用户（`passwords.py` 用 argon2）→ `SmtpEmailVerificationDelivery`（`app/auth/smtp_delivery.py`）发验证码邮件（STARTTLS 可配）→ 返回 202。
3. **验证** `POST /api/v1/auth/verify-email`：校验一次性 token，激活账号并写 `auth_audit_events`。
4. **登录** `POST /api/v1/auth/login`（`router.py`）：`AuthService.login()`（`app/auth/service.py`）——`normalize_email`、`verify_password`（argon2）、`issue_session`（`sessions.py` 生成不透明 token + 哈希）→ 响应设置 `hutao_session` HttpOnly Cookie + 内存下发 `csrf_token`；失败统一"invalid email or password"并审计。
5. **移动端** `POST /api/v1/auth/mobile/login`：返回短期 `Bearer` 会话（小程序用），不写 Cookie。
6. **当前账号** `GET /api/v1/auth/me`：`AuthService.current_account()` 返回脱敏档案；`POST /api/v1/auth/logout`：撤销会话（`revoke_session`）并清 Cookie。
7. **重置** `POST /api/v1/auth/password-reset/request` + `/password-reset/confirm`（`password_reset_router.py`）：`PasswordResetService`（`app/auth/password_reset.py`）邮件发一次性重置码（数据库只存哈希），确认后更新密码并**撤销该账号全部现有会话**。

### 6.7 Database V2 平台消息命令（前置于 ChatService）

1. **入口**：`try_handle_database_v2_platform_message()`（`app/storage/v2_runtime.py`）——`should_use_database_v2()` 为真且 platform ∈ {qq, wechat} 时才走命令服务；普通消息 `is_command=False` 且 `should_enter_chat_service=True` 时返回 None 放行给 ChatService。
2. **管理引导**：`DatabaseV2RelationshipService.bootstrap_admin_from_settings()`（`app/storage/v2_relationship_service.py`）用 `OWNER_BOOTSTRAP_QQ_IDS`/`OWNER_BOOTSTRAP_WECHAT_IDS`（或兼容键 `HUTAO_OWNER_QQ_IDS`）在首次运行时创建唯一管理员。
3. **解析**：`parse_v2_admin_command()`/`decide_v2_admin_command()`（`app/storage/v2_command_policy.py`）识别"胡桃"前缀命令：`set_relationship`（设关系）、`bind_accounts`（跨平台账号绑定，`confirm_merge` 才合并）、`claim_approve/reject`（受控认领审核）、`list_recent_chats` 等。
4. **执行与审计**：`DatabaseV2PlatformCommandService.handle_message()`（`app/storage/v2_platform_command_service.py`）→ `MySQLDatabaseV2Repository` 写 `platform_command_events`（脱敏：不含消息正文与平台 ID 明文，`_redact_id`）；域变更同时写 `relationship_events`。
5. **回包**：命令回复 `provider="local"`、`model="database-v2-platform-command"`、`used_live_api=False`，绝不经模型。

### 6.8 OpenAI-Compatible 路径（`/v1/chat/completions`）

`app/openai_compat.py::create_chat_completion()`：`extract_latest_user_message()` 取最后一条 user 消息（支持字符串或分片 content）→ `build_compat_session_id()` 派生会话 ID → V2 命令前置拦截 → `HeadRuntime`（V2 存储条件与 6.1 相同）→ 非流式回 `build_chat_completion_response()`（usage 全 0 占位）、流式回 `stream_openai_reply()`（SSE chunk + `[DONE]`）。`GET /v1/models` 返回 `hutao-chatcore` 与配置模型两个模型 ID。


### 6.9 错误与降级路径汇总（ChatService 主链路）

| 触发条件 | 行为 | 落点 |
| --- | --- | --- |
| 关系角色 `blocked` | 直接本地回复"这边暂时不接待。"，不调模型 | `chat_service.py` `reply()` 前置 |
| Provider 全挂/无密钥 | `RoutingFailed` → `_fallback_response()` 本地兜底 | `providers/router.py`、`chat_service.py` |
| 流式首块前失败 | 换下一个 provider；首块后失败不换 | `ProviderRouter._route_stream()` |
| 流式中断 | 已产出部分持久化，错误码脱敏落审计 | `chat_service.py` `stream_reply()` |
| 评估不通过 | `_repair_live_response_decision()` 一次修复路由；再失败用 `_evaluation_fallback_reply` | `chat_service.py`、`response_evaluator.py` |
| 世界证据冲突 | `_world_guard_reply()` 用证据一致文本替换 | `chat_service.py` |
| 音频输入流超时 | 流内追加"这次回复耗时过长，请点击重试。" | `main.py` `limit_audio_stream_to_realtime_budget()` |
| ASR 质量门未过 | `clarification_reply` 本地澄清，旁路模型 | `main.py` `audio_chat_file_endpoint()` |
| TTS 未启用/失败 | 文本照常返回，绝不伪造音色 | `main.py`、`voice_chat/tts_service.py` |
| 上传越界/票据无效 | 404/409/422/429 且票据释放 | `main.py` `synthesize_public_web_voice()` |

### 6.10 本地开发形态与正式账号形态的差异

| 维度 | 本地开发（默认） | 正式账号形态 |
| --- | --- | --- |
| `PUBLIC_WEB_AUTH_ENABLED` | false | true |
| 身份来源 | 请求自带 `user_id/session_id`（默认 `default-user/default`） | Cookie `hutao_session` + CSRF（网页）/ Bearer（小程序） |
| 存储 | JSONL（`logs/storage`） | PostgreSQL（`STORAGE_BACKEND=postgresql`）或 MySQL V2（qq/wechat 平台身份） |
| 平台身份字段 | 允许 | 公开请求携带 `platform` 字段直接 400 |
| 语音合成 | 404（`public_web_tts_configured=false`） | 完整 reply_id 闭环 |
| 注册/重置路由 | 不挂载 | 邮件条件满足后挂载 |

## 7. HTTP 接口清单（按路由组）

说明：鉴权列标注的门控以 `app/main.py` 与各 router 文件的实现为准。公开鉴权未开启时，`resolve_web_identity()` 直接采用请求携带的 user_id/session_id（本地开发形态）；开启后强制 Cookie/CSRF 或 Bearer。

### 7.1 静态页面（`app/main.py`、`app/control/routes.py`、`app/workbench/router.py`，均 `include_in_schema=False`）

| 方法 | 路径 | 门控 | 功能 |
| --- | --- | --- | --- |
| GET | `/` | 无 | Vite 构建的公开落地页（`app/static/web/site/index.html`） |
| GET | `/site/assets/*`（mount） | 无 | 落地页构建资源 |
| GET | `/credits`、`/credits/{app.js,style.css,data.json}` | 无 | 致谢页（no-store 缓存头） |
| GET | `/desk`、`/desk/{app.js,style.css,mobile.css,manifest.webmanifest,service-worker.js}` | 无 | Web Desk PWA（`app/static/web/studio/`） |
| GET | `/auth`、`/auth/{app.js,style.css}` | 无 | 登录注册页 |
| GET | `/me`、`/me/{app.js,style.css}` | 无 | 个人中心页 |
| GET | `/ui/{theme.css,liquid-theme.css,ambient.js}` | 无 | 共享主题资源 |
| GET | `/ui/cursors/{cursor_name}.png` | 白名单 5 种光标 | 共享光标（86400 缓存） |
| GET | `/control`、`/control/{app.js,style.css}`、`/control/docs/world-model`、`/control/assets/control-atmosphere.webp` | 无 | 控制中心页与资源 |
| GET | `/workbench`、`/workbench/{app.js,style.css}` | 页面不鉴权，API 鉴权 | 视觉工作台页（功能默认关闭） |

### 7.2 核心 API（`app/main.py`）

| 方法 | 路径 | 鉴权/门控 | 功能 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | 状态、应用名、provider/model、`api_key_configured` 布尔（不泄密钥） |
| GET | `/api/v1/auth/status` | 无 | 三个非敏感布尔：`authentication_enabled`/`registration_enabled`/`password_reset_enabled` |
| GET | `/api/v1/voice/status` | 无 | `enabled` + `max_reply_chars` |
| POST | `/api/v1/voice/synthesize` | 公开鉴权 + CSRF + reply_id 票据 | 网页语音合成（见 6.4） |
| POST | `/api/v1/chat` | 公开鉴权（开启时）+ CSRF；沙箱人格仅 Web | 文本聊天（见 6.1） |
| POST | `/api/v1/chat/stream` | 同上 | 流式聊天（见 6.2） |
| POST | `/api/v1/audio/transcribe/file` | 无（文件上传） | 语音转写 |
| POST | `/api/v1/audio/chat/prepare/file` | 公开鉴权（开启时）+ CSRF | 语音转写 + 澄清判定 |
| POST | `/api/v1/audio/chat/file` | 公开鉴权（开启时）+ CSRF | 语音转写 + 对话 |
| GET | `/api/v1/memories` | 公开鉴权（开启时）；limit 钳制 1–100 | 记忆列表 |
| DELETE | `/api/v1/memories/{memory_id}` | 公开鉴权（开启时）+ CSRF | 删除记忆 |
| GET | `/api/v1/dialogue-context` | 无 | 对话脉络（ready/tracking_task/waiting_for_user 与活跃任务） |

### 7.3 OpenAI-Compatible（`app/openai_compat.py`，tag `openai-compatible`）

| 方法 | 路径 | 鉴权/门控 | 功能 |
| --- | --- | --- | --- |
| GET | `/v1/models` | 无 | 模型列表（`hutao-chatcore` + 配置模型） |
| POST | `/v1/chat/completions` | 无（兼容层不挂账号鉴权） | 聊天补全（stream 支持 SSE）；platform 字段可触发 V2 命令与 V2 存储 |

### 7.4 账号 API（`app/auth/router.py`、`registration_router.py`、`password_reset_router.py`，前缀 `/api/v1/auth`）

| 方法 | 路径 | 门控 | 功能 |
| --- | --- | --- | --- |
| POST | `/login` | 仅当公开鉴权已挂载（否则路由不存在） | 网页登录：发 `hutao_session` HttpOnly Cookie + CSRF token |
| POST | `/mobile/login` | 同上 | 小程序登录：返回短期 Bearer |
| GET | `/me` | 会话 Cookie | 当前账号脱敏档案 |
| POST | `/logout` | 会话 + CSRF | 撤销会话并清 Cookie（204） |
| POST | `/register` | 邮件注册已挂载 + 限流 | 创建未验证账号并发验证邮件（202） |
| POST | `/verify-email` | 邮件注册已挂载 | 验证邮箱激活账号 |
| POST | `/password-reset/request` | 邮件重置已挂载 + 限流 | 发送重置码邮件 |
| POST | `/password-reset/confirm` | 邮件重置已挂载 | 用重置码设置新密码并撤销全部会话 |

### 7.5 控制中心（`app/control/routes.py`，前缀 `/api/control`；页面路由见 7.1）

| 方法 | 路径 | 鉴权/门控 | 功能 |
| --- | --- | --- | --- |
| GET | `/status` | 无 | 控制中心健康状态（`build_control_status`） |
| GET | `/operations/status` | 无 | S8 组件状态聚合（1s 超时） |
| GET | `/operations/test-reports` | 无 | `logs/test-runs` 最新报告摘要（limit ≤ 50） |
| GET | `/operations/errors` | 无 | 错误分类汇总（当前返回空数组占位） |
| GET | `/operations/actor` | 无 | 请求头演员身份的 `configured`/`authorized` 布尔 |
| GET | `/operations/audits` | 演员授权（403 否则） | 控制操作审计（脱敏、最新 100 条） |
| GET | `/config` | 无（secret 值不回显） | 配置分组 schema + 当前公开值（`secret` 标记） |
| POST | `/config` | `ControlWriteGuard` 管理授权 | 写 .env（先备份，返回 `backup_path`/`restart_required`） |
| GET | `/logs` | 无 | 日志目标清单 |
| GET | `/logs/{log_id}` | 无 | 日志尾部（`read_log_tail`，脱敏/乱码修复/噪音过滤） |
| GET | `/services` | 无 | 受管服务清单（`hutao_core`、`gpt_sovits`） |
| POST | `/services/{service_id}/start`、`/stop` | 管理授权 | 启停受管进程 |
| GET | `/tests` | 无 | 受管测试清单（`control_center`/`api_voice`/`full_pytest`） |
| POST | `/tests/{test_id}/run` | 管理授权 | 运行受管测试（`write_test_report` 落报告） |

### 7.6 摄像头控制（`app/camera/router.py`，前缀 `/api/control/camera`）

全部端点要求 `require_control_admin("camera_*")`（`ControlWriteGuard` + `X-Hutao-Actor-*` 头）：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| POST | `/sessions` | 创建需明确同意的摄像头会话（`CameraSessionStartRequest.require_explicit_consent`） |
| GET | `/sessions/{session_id}` | 会话状态（按 owner 隔离） |
| POST | `/sessions/{session_id}/stop` | 停止会话（含采集停止与状态清理） |
| POST | `/sessions/{session_id}/observations` | 提交规范化观察（`validate_observation` + 世界观察转换 + 时序确认） |
| POST | `/sessions/{session_id}/capture/start` | 启动本地采集（`LocalCaptureController`） |
| GET | `/sessions/{session_id}/capture/status` | 采集状态 |
| GET | `/sessions/{session_id}/perception/status` | 最近时序感知（场景/物体/姿态/手势/面部线索） |
| POST | `/sessions/{session_id}/capture/stop` | 停止采集 |

### 7.7 视觉工作台（`app/workbench/router.py`，前缀 `/api/workbench`）

使用独立短时会话（`hutao_workbench_session` HttpOnly + `hutao_workbench_csrf`，`WorkbenchSessionStore`，`VISUAL_WORKBENCH_ENABLED` 默认关闭）：

| 方法 | 路径 | 鉴权 | 功能 |
| --- | --- | --- | --- |
| POST | `/login` | 管理员口令（限流） | 204 + 双 Cookie |
| POST | `/logout` | 会话 + CSRF | 撤销并停止该 owner 全部摄像头会话 |
| GET | `/status` | 会话 | 会话到期时间 + 摄像头能力布尔 |
| POST | `/camera/sessions` | 会话 + CSRF | 开摄像头会话（同 owner 只允许一个 active） |
| GET/POST | `/camera/sessions/{session_id}`、`.../stop` | 会话 + CSRF（写） | 查询/停止 |
| POST | `/camera/sessions/{session_id}/capture/start`、`.../stop` | 会话 + CSRF | 采集启停 |
| GET | `/camera/sessions/{session_id}/capture/status`、`.../perception/status` | 会话 | 采集/感知状态 |

### 7.8 知识（记忆）控制面（`app/knowledge/router.py`，前缀 `/api/control/knowledge`）

`create_knowledge_control_router` 在 `knowledge_control_service` 为 None（MySQL 未配置）时仍注册但返回不可用；全部端点要求数据库解析的只读/写管理演员：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/status` | `KnowledgePersistenceStatus`（durable/write_ready 等） |
| GET | `/candidates` | 记忆候选列表 |
| POST | `/candidates/{candidate_id}/decision` | 审核候选（approve/reject）→ 记忆记录 |
| POST | `/records/{record_id}/revoke` | 撤销记忆记录（写审计） |

### 7.9 Database V2 控制面（`app/database_control/router.py`，前缀 `/api/control/database-v2`）

读端点需 `resolve_read_actor`，写端点需 `require_mutate_admin`（`bootstrap-admin` 例外：仅本机 + 无既有管理员时可用）：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/status` | `DatabaseStatus`（schema/readiness） |
| GET | `/admin` | 唯一管理员档案（脱敏） |
| GET | `/profiles` | 档案分页（opaque cursor + ID 脱敏） |
| GET | `/profiles/{profile_id}` | 档案详情（账号/关系/记忆计数） |
| POST | `/bootstrap-admin` | 首次管理员引导（ID 必须匹配 bootstrap 配置） |
| POST | `/profiles/relationships` | 更新档案关系（幂等；admin_partner 保护） |
| POST | `/platform-accounts/bind` | 跨平台账号绑定（`confirm_merge=true` 才合并档案） |
| POST | `/claims/{claim_id}/approve`、`/reject` | 受控认领审核（404/409 映射；approve 不授予 admin） |

### 7.10 人格管理（`app/persona_management/`，三个前缀）

- `/api/control/personas`（`router.py`，内存版只读，前缀列出）：`GET /status`、`GET /{profile_id}/versions`、`GET /{profile_id}/releases`、`GET /versions/{version_id}`、`GET /bindings/all`、`GET /{profile_id}/runtime-projection`。
- `/api/control/personas-v2`（`async_router.py`，MySQL 持久版，仅 `PERSONA_MANAGEMENT_PERSISTENCE_ENABLED` 时挂载）：上列只读端点 + 写端点 `POST /drafts`、`POST /drafts/{draft_id}/validate`、`POST /drafts/{draft_id}/evaluations`、`POST /drafts/{draft_id}/approve`、`POST /versions/{version_id}/publish`、`POST /{profile_id}/rollback`、`PUT /bindings/{binding_id}`——写端点在 `enable_writes=False` 时失败关闭。
- `/api/v1/sandbox/personas`（`sandbox_router.py`，公开用户可用的本地沙箱）：`GET ""`、`POST ""`、`GET /{persona_id}`、`PUT /{persona_id}`、`DELETE /{persona_id}`，按 `owner_id` 隔离，JSONL 持久化于 `JSONL_STORAGE_DIR`。

### 7.11 音频 WebSocket（`app/audio/websocket_routes.py`，前缀 `/api/v1/audio`）

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| WS | `/transcribe/stream` | 流式 ASR 协议（`AsrStartMessage` → PCM 分片 → `AsrEvent` 流 → 结束）；协议实现为部分实现状态（见 6.3.6） |


### 7.12 关键请求/响应模型字段（`app/schemas.py`、`app/openai_compat.py`、`app/audio/schemas.py`）

**`ChatRequest`**（`app/schemas.py`）：`user_input`（1–4000 字符必填）、`session_id`（默认 `default`，≤128）、`user_id`（默认 `default-user`，≤128）、`platform/platform_user_id/platform_group_id`（可空，≤32/128/128，公开鉴权下禁止）、`response_style_instruction`（≤1000）、`persona_id`（沙箱人格，≤128）、`input_source`（`text/audio/image` 三值）、`input_quality_passed`（默认 true）+ `input_quality_reasons`（≤20 项）、`input_emotion/input_emotion_source/input_emotion_confidence`（0–1）。

**`ChatResponse`**：`text`、`provider`、`model`、`used_live_api`、`fallback_used`、`error`。其中 `provider/model/error` 三字段用于向客户端如实暴露降级来源（`local`/`database-v2-platform-command` 等本地路径一目了然）。

**`WebVoiceSynthesisRequest`**：`reply_id`（16–128 字符）、`session_id`、`user_id`——没有任何文本字段，合成文本只能来自服务端票据。

**`HealthResponse`**：`status/app_name/provider/model/api_key_configured`；**`PublicAuthStatusResponse`**：三布尔；**`PublicWebVoiceStatusResponse`**：`enabled/max_reply_chars`；**`MemoryResponse/DeleteMemoryResponse/DialogueContextResponse`**：记忆与对话脉络 DTO（`status` 为 `ready/tracking_task/waiting_for_user` 三值）。

**`OpenAIChatCompletionRequest`**（`app/openai_compat.py`）：`model`（默认 `hutao-chatcore`）、`messages`（≥1，支持字符串或分片 content）、`stream`（false）、`user/session_id/user_id/platform/platform_user_id/platform_group_id` 扩展字段。

**`AsrFileResponse/PreparedAudioChatFileResponse/AudioChatFileResponse`**（`app/audio/schemas.py`）：转写文本、候选与修复信息、质量判定与原因、可选情绪字段（`emotion/emotion_source/emotion_confidence`）、语音对话响应（`chat` 嵌套 `ChatResponse`）；`AsrStartMessage/AsrEvent` 为 WebSocket 协议 DTO。

**`CameraSessionStartRequest`**（`app/camera/contracts.py`）：`require_explicit_consent()` 强制把 `consent_confirmed=True` 写入请求；`CameraObservation` 的 `normalize_scene_label/validate_labels` 只接受白名单标签，多余字段拒绝（`CameraContract` 为严格 BaseModel）。

**`ActorIdentity/SourceAccount`**（`app/database_control/contracts.py`）：控制面演员身份（平台 + 平台账号 + 可选群组），经 `build_actor_identity()` 从 `X-Hutao-Actor-*` 请求头构造。

### 7.13 鉴权与请求头约定汇总

| 形态 | 凭证 | 校验位置 |
| --- | --- | --- |
| 网页会话 | `Cookie: hutao_session`（HttpOnly、SameSite=lax，secure 可配） | `app/main.py::_authenticated_identity` → `AuthService.require_session` |
| CSRF（写操作） | `Header: X-CSRF-Token` | `require_session(require_csrf=True)`，`compare_digest` 比较哈希 |
| 小程序 | `Authorization: Bearer <token>` | `bearer_session_token()` 解析后走同一会话存储 |
| 控制面写操作 | `X-Hutao-Actor-Platform` / `X-Hutao-Actor-User-Id` /（可选）`X-Hutao-Actor-Group-Id` | `ControlWriteGuard.authorize`（数据库解析演员 + fallback 管理员集合） |
| 工作台 | `Cookie: hutao_workbench_session`（HttpOnly）+ `hutao_workbench_csrf`（非 HttpOnly，供 JS 读回发送） | `WorkbenchSessionStore.require` |
| 语音合成 | 三者其一：Cookie+CSRF 或 Bearer，且 `reply_id` 票据归属匹配 | `WebVoiceReplyStore.acquire` |

失败语义：缺身份 → 401（`authentication required`）；CSRF 失败 → 403（`csrf validation failed`）；控制面演员未解析 → 403（`admin_required`）；票据缺失/占用/超频 → 404/409/429。

### 7.14 错误码使用矩阵（HTTP 状态码约定）

| 状态码 | 使用位置（示例） |
| --- | --- |
| 400 | 公开请求携带平台身份字段；消息不含非空 user 消息（OpenAI 层）；配置更新非法值；摄像头观察会话不匹配 |
| 401 | 缺会话（`authentication required`）；工作台未认证 |
| 403 | CSRF 失败；控制面演员未授权（`admin_required`）；审计查询未授权 |
| 404 | 语音/票据/会话/档案/沙箱人格不存在；TTS 未启用；工作台未启用；日志目标无效 |
| 408 | 控制中心受管测试超时 |
| 409 | 票据合成中；摄像头会话已存在/未激活/已禁用；认领已审核；完整性冲突（域错误映射） |
| 422 | 语音回复文本超长（`PUBLIC_WEB_TTS_MAX_REPLY_CHARS`） |
| 429 | 语音请求超频；认证类限流（`RateLimitError`） |
| 503 | TTS 合成失败/输出越界；审计不可用；知识/人格持久化不可用；数据库驱动错误（脱敏） |

所有域错误经类型化异常映射到上述固定码，外部异常信息不直接透出（`database_control/errors.py`、`app/providers` 错误码映射、`main.py` 显式 `HTTPException` 族）。

### 7.15 Provider 错误码枚举与映射（`app/providers/contracts.py` `ProviderErrorCode`）

| 错误码 | DeepSeek 映射（`deepseek.py` `_map_deepseek_error`） | TTS 映射（`tts.py` `_map_tts_error`） |
| --- | --- | --- |
| `NOT_CONFIGURED` | 缺 `DEEPSEEK_API_KEY` | missing / not configured |
| `AUTHENTICATION_FAILED` | HTTP 401/403 | HTTP 401/403 |
| `RATE_LIMITED` | HTTP 429 | HTTP 429 |
| `TIMEOUT` | 超时异常 | TimeoutError / timed out |
| `INVALID_RESPONSE` | 空/无效 content | empty audio / no audio |
| `UNAVAILABLE` | 其他网络/服务失败 | 其余异常 |

路由失败聚合为 `RoutingFailed(ProviderError)`（携带全量 `ProviderTrace`），上层 ChatService 将其转换为本地兜底；trace 经 `_redact` 清洗后才进入审计（`provider_trace_metadata()` 只保留 provider ID、attempt、success、error code、duration）。

### 7.16 端点计数汇总（本次盘点）

| 分组 | 端点/装饰器数 | 前缀 |
| --- | --- | --- |
| 静态页面与资源 | 33（main.py）+ 6（control 页面）+ 3（workbench 页面） | /、/desk、/auth、/me、/credits、/control、/workbench、/ui/* |
| 核心 API | 12 | /health、/api/v1/* |
| OpenAI-Compatible | 2 | /v1 |
| 账号 | 8 | /api/v1/auth |
| 控制中心 API | 14 | /api/control |
| 摄像头控制 | 8 | /api/control/camera |
| 工作台 API | 10 | /api/workbench |
| 知识控制面 | 4 | /api/control/knowledge |
| Database V2 控制面 | 9 | /api/control/database-v2 |
| 人格管理 | 6 + 14 + 5 | /api/control/personas(-v2)、/api/v1/sandbox/personas |
| 音频 WebSocket | 1 | /api/v1/audio |
| **合计** | **123 个路由装饰器** | — |

## 8. 配置参考（`Settings` 字段与环境变量全表）

`Settings` 定义于 `app/core/config.py`（455 行，frozen dataclass），由 `load_settings()` 读取。取值顺序：进程环境变量 > `PROJECT_ROOT/.env` > `WORKSPACE_ROOT/HutaoPersonaLab/.env`（兼容层）> 代码默认值。布尔解析接受 `1/true/yes/on`。以下按分组列出字段、env 键、默认值与 fail-closed 说明；带 `*` 的字段在控制中心配置页被标记为 secret 不回显。

### 8.1 核心与人格（brain/persona）

| Settings 字段 | env 键 | 默认 | 说明 |
| --- | --- | --- | --- |
| `app_name` | `APP_NAME` | `HutaoChatCore` | 应用显示名 |
| `environment` | `ENVIRONMENT` | `local` | 环境标识 |
| `persona_profile` | `PERSONA_PROFILE`（兼容 `HUTAO_PERSONA_PROFILE`） | `hutao_v1` | 唯一内置人格；未知名回退 hutao_v1 并记录原因 |
| `persona_profile_requested` / `persona_profile_fallback_reason` | 同上 | — | 解析审计字段 |
| `persona_display_name` / `persona_style` | —（注册表派生） | 胡桃 / 注册表默认风格 | 旧显示名配置不再生效 |
| `hutao_owner_name` | `HUTAO_OWNER_NAME`* | `主人` | 管理员称呼（数据库 V2 引导用） |
| `hutao_owner_qq_ids` / `owner_bootstrap_qq_ids` / `owner_bootstrap_wechat_ids` | 同名 env 键 | 空 | V2 管理员引导 ID（保留的跨平台标识，平台 Bot 已退役，仅用于 Database V2 身份引导与本地控制面回退管理员） |

### 8.2 模型 Provider（brain）

| Settings 字段 | env 键 | 默认 | 说明 |
| --- | --- | --- | --- |
| `model_provider` | `MODEL_PROVIDER` | `deepseek` | 控制中心下拉仅 deepseek |
| `model_name` | `MODEL_NAME` | `deepseek-v4-pro` | 请求中的模型名 |
| `model_base_url` | `MODEL_BASE_URL` | `https://api.deepseek.com` | 拼接 `/chat/completions`（`chat_completions_url` property） |
| `deepseek_api_key` | `DEEPSEEK_API_KEY`* | 空 | 未配置时 Provider 映射 `NOT_CONFIGURED` |
| `request_timeout_seconds` | `API_TIMEOUT_SECONDS` | 90 | 单次非流式请求超时 |
| `temperature` | `API_TEMPERATURE` | 0.8 | 采样温度 |
| `text_provider_order` | `TEXT_PROVIDER_ORDER` | 默认取 `MODEL_PROVIDER` | 路由顺序 |
| `text_provider_retries` | `TEXT_PROVIDER_RETRIES` | 0 | 单 provider 重试 |
| `text_provider_circuit_failure_threshold` / `..._recovery_seconds` | 同名 env 键 | 3 / 60 | 熔断参数（`RoutingPolicy` 校验范围） |

### 8.3 存储（storage）

| Settings 字段 | env 键 | 默认 | 说明 |
| --- | --- | --- | --- |
| `storage_backend` | `STORAGE_BACKEND` | `jsonl` | 仅支持 `jsonl` 与 `postgres/postgresql`；`mysql` 分支已随 V1 移除（`repository_factory.py` 会对未知值抛 ValueError） |
| `jsonl_storage_dir` | `JSONL_STORAGE_DIR` | `./logs/storage` | JSONL 会话/消息/记忆/审计落盘目录 |
| `database_v2_enabled` | `DATABASE_V2_ENABLED` | false | V2 只影响 qq/wechat 平台身份与 `trusted_core_profile` 路径 |
| `mysql_host/port/database/user/password` | `MYSQL_*` | 127.0.0.1/3306/空 | 空库名/用户/密码 = 未配置，相关服务不注册 |
| `postgres_host/port/database/user/password` | `POSTGRES_*` | 127.0.0.1/5432/空 | `postgres_is_configured` 判定三字段齐全 |
| `knowledge_candidate_intake_enabled` | `KNOWLEDGE_CANDIDATE_INTAKE_ENABLED` | false | S4 候选摄入开关 |
| `persona_management_persistence_enabled` / `..._writes_enabled` | 同名 env 键 | false / false | S5 持久化与写开关（双门） |

### 8.4 语音与音频（voice/audio）

| Settings 字段 | env 键 | 默认 | 说明 |
| --- | --- | --- | --- |
| `voice_chat_reply_timeout_seconds` | `VOICE_CHAT_REPLY_TIMEOUT_SECONDS` | 25 | 音频输入流式回复实时预算 |
| `asr_file_presets` | `ASR_FILE_PRESETS` | `sensevoice-small` | 逗号分隔候选预设 |
| `asr_repair_presets` | `ASR_REPAIR_PRESETS` | 空 | 质量不足时的修复候选 |
| `asr_provider_timeout_seconds` | `ASR_PROVIDER_TIMEOUT_SECONDS` | 180 | ASR 候选超时（线程超时不能中断同步推理，注释明确） |
| `asr_provider_circuit_failure_threshold` / `..._recovery_seconds` | 同名 env 键 | 3 / 60 | ASR 熔断 |
| `audio_emotion_enabled` | `AUDIO_EMOTION_ENABLED` | true | emotion2vec 情绪线索 |
| `audio_emotion_model` | `AUDIO_EMOTION_MODEL` | `iic/emotion2vec_plus_large` | 情绪模型 ID |
| `public_web_tts_enabled` | `PUBLIC_WEB_TTS_ENABLED` | false | 网页 TTS 总开关（需公开鉴权生效） |
| `public_web_tts_provider` | `PUBLIC_WEB_TTS_PROVIDER` | `gpt_sovits` | 唯一可选 provider |
| `public_web_tts_base_url` | `PUBLIC_WEB_TTS_BASE_URL` | `http://127.0.0.1:9880` | 独立 TTS 服务 |
| `public_web_tts_output_dir` | `PUBLIC_WEB_TTS_OUTPUT_DIR` | `data/generated_voice/web` | 必须相对且解析后位于项目内 |
| `public_web_tts_reply_ttl_seconds` / `..._min_interval_seconds` / `..._max_reply_chars` | 同名 env 键 | 300 / 8 / 800 | 票据 TTL、频率、长度上限 |

### 8.5 世界工具（world）

| Settings 字段 | env 键 | 默认 | 说明 |
| --- | --- | --- | --- |
| `world_awareness_enabled` | `WORLD_AWARENESS_ENABLED` | false | 全局开关；`WORLD_RENDERED_FETCH_ENABLED` 已随渲染浏览器方案移除 |
| `world_fetch_timeout_seconds` / `world_fetch_max_bytes` | 同名 env 键 | 12 / 1048576 | 适配器请求边界 |
| `world_cache_max_entries` / `world_max_cache_ttl_seconds` | 同名 env 键 | 512 / 2592000 | TTL 缓存边界 |
| `world_official_source_manifest` | `WORLD_OFFICIAL_SOURCE_MANIFEST` | `./data/world/sources.json` | 8 个来源清单（全部 enabled=false） |
| `world_source_enabled_ids` / `world_source_legal_approved_ids` | 同名 env 键 | 空 | 来源启用/法律批准白名单 |
| `amap_web_service_api_key`* | `AMAP_WEB_SERVICE_API_KEY` | 空 | 高德密钥（只留在适配器内） |
| `amap_web_service_base_url` / `amap_allowed_hosts` | 同名 env 键 | `https://restapi.amap.com` / `restapi.amap.com` | 域名白名单 |
| `amap_source_legal_approved` | `AMAP_SOURCE_LEGAL_APPROVED` | false | 高德条款批准门 |
| `amap_ip_cache_ttl_seconds` / `..._weather` / `..._district` / `..._place` / `..._route` | 同名 env 键 | 86400/900/2592000/86400/300 | 分层缓存 TTL |
| `qweather_api_key`* / `qweather_api_base_url` / `qweather_allowed_hosts` / `qweather_source_legal_approved` / `qweather_weather_cache_ttl_seconds` | 同名 env 键 | 空/官方端点/devapi.qweather.com/false/900 | 和风天气（与高德同等级门控） |
| `world_domestic_news_api_key` 等 4 个保留字段 | 同名 env 键 | 空 | 为未来受控新闻 API 预留，当前无适配器消费 |

### 8.6 摄像头（camera）

| Settings 字段 | env 键 | 默认 | fail-closed 说明 |
| --- | --- | --- | --- |
| `camera_perception_enabled` | `CAMERA_PERCEPTION_ENABLED` | false | 感知总开关 |
| `camera_local_capture_enabled` | `CAMERA_LOCAL_CAPTURE_ENABLED` | false | 本地采集总开关 |
| `camera_session_max_seconds` | `CAMERA_SESSION_MAX_SECONDS` | 300 | 会话最长时长 |
| `camera_observation_ttl_seconds` | `CAMERA_OBSERVATION_TTL_SECONDS` | 15 | 观察有效期 |
| `camera_raw_frame_retention_seconds` | `CAMERA_RAW_FRAME_RETENTION_SECONDS` | 0 | 原始帧不持久化 |
| `camera_face_identification_enabled` | `CAMERA_FACE_IDENTIFICATION_ENABLED` | false | 不做人脸识别 |
| `camera_cloud_upload_enabled` | `CAMERA_CLOUD_UPLOAD_ENABLED` | false | 不上传 |
| `camera_capture_interval_seconds` | `CAMERA_CAPTURE_INTERVAL_SECONDS` | 2 | 采样间隔 |
| `camera_temporal_confirmation_count` / `..._window_seconds` | 同名 env 键 | 2 / 8 | 时序确认（同一标签需两次确认） |
| `camera_yolo_model_path` | `CAMERA_YOLO_MODEL_PATH` | 空 | 显式本地 YOLO 权重路径 |
| `camera_mediapipe_enabled` | `CAMERA_MEDIAPIPE_ENABLED` | true | MediaPipe 特征点 |

### 8.7 工作台与公开认证（auth）

| Settings 字段 | env 键 | 默认 | fail-closed 说明 |
| --- | --- | --- | --- |
| `visual_workbench_enabled` | `VISUAL_WORKBENCH_ENABLED` | false | 工作台总开关 |
| `visual_workbench_admin_secret`* | `VISUAL_WORKBENCH_ADMIN_SECRET` | 空 | 独立随机管理员口令（不进前端/文档/日志） |
| `visual_workbench_session_lifetime_seconds` | `VISUAL_WORKBENCH_SESSION_LIFETIME_SECONDS` | 1800 | 工作台会话时长 |
| `public_web_auth_enabled` | `PUBLIC_WEB_AUTH_ENABLED` | false | 公开账号总开关（还需存储后端就绪） |
| `session_cookie_secure` | `SESSION_COOKIE_SECURE` | false | HTTPS 前保持 false |
| `public_web_session_lifetime_seconds` | `PUBLIC_WEB_SESSION_LIFETIME_SECONDS` | 604800 | 网页会话 7 天 |
| `email_delivery_enabled` | `EMAIL_DELIVERY_ENABLED` | false | 邮件总开关（还需 SMTP 四字段完整） |
| `smtp_host/port/username/password/from_address` | `SMTP_*` | 空/587/空 | 密码 secret；STARTTLS 可配（`smtp_starttls` 默认 true） |

### 8.8 语义记忆（semantic）

`SEMANTIC_MEMORY_ENABLED`（默认 false）、`SEMANTIC_MEMORY_QDRANT_URL/API_KEY/COLLECTION`（默认 `hutao_memories`）、`SEMANTIC_MEMORY_EMBEDDING_PROVIDER`（`.env.example` 默认 `local_sentence_transformer`，代码默认 `openai_compatible`）、`..._MODEL_PATH/DEVICE/MAX_LENGTH`（8192/cpu）、`..._BASE_URL/API_KEY/MODEL/TIMEOUT_SECONDS`（15）、`SEMANTIC_MEMORY_RETRIEVAL_LIMIT`（8）、`SEMANTIC_MEMORY_MIN_SCORE`（0.35）。

### 8.9 控制中心可见配置分组

`app/control/config_schema.py` 的 `SETTING_GROUPS` 暴露七个分组：brain（核心模型）、persona、clients（`HUTAO_CORE_BASE_URL`）、voice、audio、world、storage；`EnvConfigStore.update_values()` 只接受 `SETTING_SPECS` 中的键，写入前做值规范化并备份旧文件。

---

### 8.10 控制中心可编辑键完整清单（`app/control/config_schema.py` `SETTING_SPECS`，28 键 7 组）

- `brain`（6）：`MODEL_PROVIDER`（select: deepseek）、`MODEL_NAME`、`MODEL_BASE_URL`、`DEEPSEEK_API_KEY`（secret）、`API_TIMEOUT_SECONDS`（number）、`API_TEMPERATURE`（number）。
- `persona`（1）：`HUTAO_OWNER_NAME`（secret）。
- `clients`（1）：`HUTAO_CORE_BASE_URL`。
- `voice`（3）：`PUBLIC_WEB_TTS_ENABLED`（bool）、`PUBLIC_WEB_TTS_PROVIDER`（select: gpt_sovits）、`PUBLIC_WEB_TTS_BASE_URL`。
- `audio`（4）：`ASR_FILE_PRESETS`、`ASR_REPAIR_PRESETS`、`AUDIO_EMOTION_ENABLED`（bool）、`AUDIO_EMOTION_MODEL`。
- `world`（6）：`WORLD_AWARENESS_ENABLED`（bool）、`AMAP_WEB_SERVICE_API_KEY`（secret）、`AMAP_SOURCE_LEGAL_APPROVED`（bool）、`WORLD_OFFICIAL_SOURCE_MANIFEST`、`WORLD_SOURCE_ENABLED_IDS`、`WORLD_SOURCE_LEGAL_APPROVED_IDS`。
- `storage`（7）：`STORAGE_BACKEND`（select: jsonl/postgresql）、`JSONL_STORAGE_DIR`、`MYSQL_HOST`、`MYSQL_PORT`（number）、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`（secret）。

所有键 `restart_required=True`（默认）；`EnvConfigStore` 只接受上述 28 键，写入前先备份（`_backup`）并做值规范化（`normalize_setting_value`）。

### 6.15 音频质量门与情绪链路细节

- **质量判定**（`app/audio/quality.py` `evaluate_asr_text_quality()`）：对转写文本做确定性检查（空文本、低置信度、过短、非中文比例异常、候选分歧等），产出 `AsrQuality`（`quality_passed` + `quality_reasons`）。候选间一致性由 `text_agreement()`（`app/perception/quality.py`）辅助判定。
- **情绪抽取双源**：SenseVoice 富标签（`extract_sensevoice_emotion()`，从文本标签解析）与 emotion2vec 概率分布（`Emotion2VecEngine.analyze_file()` + `normalize_emotion_label()` 归一化）。`AsrFileResponse` 同时携带 `emotion`/`emotion_source`（sensevoice/emotion2vec）/`emotion_confidence`，标明来源不混用。
- **进入 Prompt**：`build_input_emotion_instruction()`（`app/persona/persona_prompt_builder.py`）把输入情绪元数据渲染为轻量语气线索（弱信号，不改变人格）。
- **澄清链路**：质量门未过时 `prepare_audio_chat_input()` 产出 `should_clarify=True` + `clarify_reasons` + `clarification_reply`，端点直接返回澄清文本并旁路模型（`main.py` 两处：`prepare` 端点只转写不对话，`chat/file` 端点带 `fallback_used=True` 与原因码）。
- **实时预算**：`VOICE_CHAT_REPLY_TIMEOUT_SECONDS`（25s）只作用于流式对话出口（`main.py`），转写超时由 `ASR_PROVIDER_TIMEOUT_SECONDS`（180s）在路由层控制；注释明确线程超时不能中断同步 FunASR 推理。

### 6.16 记忆生命周期状态机（S4）

```text
用户消息 → MemoryCandidateIntakeService.submit（幂等键 _idempotency_key）
   → memory_candidates（MemoryState: pending）
   → KnowledgeControlService.decide（approve/reject，管理员/策略）
        approve → memory_records（active，可被 prompt 投影）
        reject  → 终止
   → 用户撤销 → KnowledgeLifecycleService.revoke（active → revoked，写 memory_audit_events）
   → 过期 → expire_due（按 TTL）
派生路径：memory_records → semantic_memory_outbox（upsert/remove）
   → SemanticMemoryOutboxProcessor → Qdrant（可重建，非权威）
投影路径：LifecycleMemoryProjectionProvider.get_projection（只读，脱敏）
   → render_memory_projection → 人格 Prompt 的"记忆投影"段
撤销边界：filter_revoked_memories + build_revocation_boundary + is_revoked
   → prompt 中显式"已撤销记忆不得再引用"边界
```

状态枚举：`MemoryState`（pending/approved/revoked 等）、`MemoryDecisionKind`（approve/reject）、`MemoryScope`；候选幂等（同 `idempotency_key` 不重复入队）；冲突检测（`_active_conflicts`）阻止互相矛盾的记忆同时 active。

## 9. 数据与存储

### 9.1 JSONL 默认后端（`app/storage/chat_repository.py`，680 行）

- `JsonlChatRepository` 实现 `ChatRepository` 协议：`ensure_session`、`save_message`、`save_model_invocation`、`save_persona_evaluation`、`save_memory`/`list_memories`/`delete_memory`、`list_recent_messages(_by_user)`、`list_recent_user_ids`、`resolve_contact`/`list_contacts`/`update_contact_relationship`、`save_relationship_claim` 等。
- 每用户/会话独立的 JSONL 追加文件，`_jsonl_lock()` 用线程锁串行化追加；`new_uuid()`/`utc_now()` 统一 ID 与时间格式。
- 数据类：`SessionRecord`、`MessageRecord`、`ModelInvocationRecord`、`PersonaEvaluationRecord`、`MemoryRecord`、`ContactRecord`、`PlatformIdentityRecord`、`RelationshipClaimRecord`。
- 记忆删除是软删（`delete_memory` 返回 bool），配合 `persona/memory_service.py` 的 `filter_revoked_memories`/`build_revocation_boundary` 在 prompt 层形成撤销边界。

#### 9.1.1 JSONL 文件组织与记录示例

`JsonlChatRepository` 在 `JSONL_STORAGE_DIR` 下按 `<user_id>/<session_id>/` 分层建目录；每类记录独立文件追加（`sessions.jsonl`、`messages.jsonl`、`model_invocations.jsonl`、`persona_evaluations.jsonl`、`memories.jsonl`、`contacts.jsonl`、`relationship_claims.jsonl`）。每条为一行 JSON，公共字段 `id`（UUID）+ `created_at`（ISO 8601 UTC）。消息行示例（字段名取自 `MessageRecord`）：

```text
{"id":"<uuid>","session_id":"<sid>","user_id":"<uid>","role":"user",
 "content":"今天天气怎么样","created_at":"2026-08-14T12:00:00Z"}
```

记忆行含 `memory_type/confidence`；模型调用行含 `provider/model/used_live_api/fallback_used/error` 与脱敏后的元数据（写入前经 `redact_secrets`）。JSONL 是默认且唯一的零外部依赖存储路径，也是 `migrate_jsonl_to_database_v2.py` 与 `import_legacy_jsonl_snapshot()` 的源格式。

### 9.2 MySQL Database V2（`migrations/v2/`，001–006，共 924 行 SQL）

表清单（`001_hutao_chat_core_schema.sql`，585 行，27 张表）：

- 身份与人格：`personas`、`persona_versions`、`profiles`、`admin_profile`、`admin_private_profile`、`profile_portraits`、`profile_emotional_state`、`profile_social_labels`、`persona_runtime_bindings`。
- 账号与关系：`platform_accounts`、`relationship_events`、`relationship_pending_claims`。
- 对话与消息：`conversations`、`conversation_persona_state`、`messages`、`message_attachments`、`model_invocations`、`persona_evaluations`、`safety_guard_events`。
- 记忆：`memories`、`memory_events`。
- 平台事件（保留的跨平台兼容结构，Bot 运行时代码已退役）：`qq_inbound_events`、`qq_outbound_events`、`wechat_inbound_events`、`wechat_outbound_events`、`platform_command_events`。
- `002_knowledge_lifecycle.sql`（73 行）：`memory_candidates`、`memory_records`、`memory_audit_events`。
- `003_persona_management.sql`（104 行）：`persona_management_drafts/validations/versions/releases/bindings/operations`。
- `004_public_web_auth.sql`（81 行）：`web_users`、`email_verification_tokens`、`web_sessions`、`registration_attempts`、`auth_audit_events`。
- `005_public_web_password_reset.sql`（23 行）：`password_reset_tokens`（必须在 004 之后应用）。
- `006_semantic_memory_outbox.sql`（58 行）：`semantic_memory_outbox`。

实现：`MySQLDatabaseV2Repository`（`app/storage/v2_mysql_repository.py`，2,307 行）同时实现 `DatabaseV2Repository`（关系解析、档案快照、bootstrap、绑定、认领、平台命令审计）与 `ChatRepository`（消息/记忆/调用审计，覆盖基类方法落到 V2 表），并含 `import_legacy_jsonl_snapshot` 迁移工具。**它是本仓库最大的单文件**，见第 15 章技术债。`MySQLChatRepository`（`app/storage/mysql_repository.py`，727 行）提供 `_connect/_execute/_fetchone/_fetchall` 传输基类与 `mysql_datetime` 等工具，被 V2 仓储、PostgreSQL 仓储、auth、knowledge、persona_management 共同继承——清理后保留它正是因为它是共享 SQL 传输基类，而不是独立的"V1 后端"。

### 9.3 PostgreSQL Web 核心（`migrations/postgres/001_web_core.sql`，194 行，17 张表）

`schema_migrations`、`profiles`、`web_users`、`email_verification_tokens`、`web_sessions`、`registration_attempts`、`auth_audit_events`、`password_reset_tokens`、`sessions`、`model_invocations`、`messages`、`persona_evaluations`、`memories`、`contacts`、`platform_identities`、`relationship_events`、`relationship_claims`。实现为 `PostgreSQLChatRepository(MySQLChatRepository)`（`app/storage/postgres_repository.py`）与 `PostgreSQLAuthRepository`（`app/auth/postgres_repository.py`，269 行）：只替换 `_connect` 传输（psycopg 异步 + dict_row），复用基类全部 SQL 契约；`.env.example` 将 PostgreSQL 标为"新 Web 部署推荐"，并要求该路径下保持 `DATABASE_V2_ENABLED=false`。部署见 `docs/POSTGRES_WEB_RUNTIME.md` 与 `scripts/apply_postgres_web_migrations.py`。

#### 9.2.1 Database V2 表清单逐表说明（`migrations/v2/001_hutao_chat_core_schema.sql`）

| 表 | 职责 |
| --- | --- |
| `schema_migrations` | 迁移记录 |
| `personas` | 人格定义（唯一 `hutao_v1` 由 `ensure_default_personas` 播种） |
| `persona_versions` | 人格版本 |
| `profiles` | 现实人物档案（profile） |
| `admin_profile` | 唯一管理员标记 |
| `admin_private_profile` | 管理员私有档案 |
| `platform_accounts` | 平台账号（qq/wechat/... 与 profile 的多对一绑定） |
| `persona_runtime_bindings` | 人格运行时绑定（表面绑定） |
| `profile_social_labels` | 档案社交标签 |
| `relationship_events` | 关系变更事件（幂等写入） |
| `relationship_pending_claims` | 待审核的认领请求 |
| `profile_portraits` | 画像快照 |
| `profile_emotional_state` | 档案情绪状态 |
| `conversations` | 会话 |
| `conversation_persona_state` | 会话内人格状态 |
| `model_invocations` | 模型调用记录（审计） |
| `messages` | 消息 |
| `message_attachments` | 消息附件元数据 |
| `persona_evaluations` | 人格评估记录 |
| `safety_guard_events` | 安全门事件 |
| `memories` | 记忆（权威存储） |
| `memory_events` | 记忆事件 |
| `qq_inbound_events` / `qq_outbound_events` | QQ 平台事件（历史兼容结构，Bot 运行时已退役） |
| `wechat_inbound_events` / `wechat_outbound_events` | 微信平台事件（同上） |
| `platform_command_events` | 平台命令/控制操作审计 |

`002` 的 `memory_candidates`/`memory_records`/`memory_audit_events` 是 S4 生命周期三表；`003` 的 `persona_management_drafts/validations/versions/releases/bindings/operations` 是 S5 六表；`004` 的 `web_users/email_verification_tokens/web_sessions/registration_attempts/auth_audit_events` 是公开账号五表；`005` 增加 `password_reset_tokens`；`006` 增加 `semantic_memory_outbox`。

#### 9.3.1 PostgreSQL Web 核心表清单（`migrations/postgres/001_web_core.sql`，17 表）

| 表 | 职责 |
| --- | --- |
| `schema_migrations` | 迁移记录 |
| `profiles` | 网页账号档案 |
| `web_users` | 账号（邮箱/密码哈希/状态） |
| `email_verification_tokens` | 邮箱验证一次性 token |
| `web_sessions` | 网页会话（token 哈希 + CSRF 哈希 + 过期/撤销） |
| `registration_attempts` | 注册限流记录（主题哈希） |
| `auth_audit_events` | 认证审计 |
| `password_reset_tokens` | 密码重置码（只存哈希） |
| `sessions` | 聊天会话 |
| `model_invocations` | 模型调用记录 |
| `messages` | 消息 |
| `persona_evaluations` | 人格评估 |
| `memories` | 记忆 |
| `contacts` | 联系人/关系 |
| `platform_identities` | 平台身份 |
| `relationship_events` | 关系事件 |
| `relationship_claims` | 关系认领 |

该路径由 `scripts/apply_postgres_web_migrations.py` 应用，`STORAGE_BACKEND=postgresql` + `PUBLIC_WEB_AUTH_ENABLED=true` 时 `PostgreSQLChatRepository`/`PostgreSQLAuthRepository` 分别接管聊天与会话存储；官方说明见 `docs/POSTGRES_WEB_RUNTIME.md`（`.env.example` 注释明确该路径下 `DATABASE_V2_ENABLED=false`）。

### 9.4 Qdrant 语义记忆与 outbox（`app/knowledge/semantic_memory.py`、`semantic_outbox.py`）

- 权威数据仍在 MySQL（memory_records）；Qdrant 只存 `record_id`、`profile_id`、向量与修订号，可随时从 outbox 重建（`QdrantSemanticMemoryIndex`：cosine 距离 + profile_id 关键字索引）。
- 嵌入 Provider 两种：`LocalSentenceTransformerEmbeddingProvider`（本地 bge-m3，`_embed_sync` 跑线程池，模型懒加载）与 `OpenAICompatibleEmbeddingProvider`；`_validate_vector`/`_cosine_similarity` 做输入校验与余弦相似度。
- `SemanticMemoryOutboxProcessor`（`claim_pending→process_once→_apply`）是独立 worker（`scripts/semantic_memory_sync.py` + compose `semantic-memory-worker` profile），失败 `reschedule`。
- `SemanticMemoryProjectionProvider` 把检索结果渲染成 prompt 投影，受 `SEMANTIC_MEMORY_RETRIEVAL_LIMIT`/`MIN_SCORE` 约束。

### 9.5 审计与撤销链路

- 模型调用审计：`ModelInvocationAuditLogger`（`app/services/model_audit.py`）写 JSONL（默认 `logs/model-invocations`），`text_hash` 做内容哈希，写入前经 `redact_secrets`（`app/core/security.py` 正则 `sk-[A-Za-z0-9]{20,}`）。
- 控制操作审计：`ControlWriteGuard.record_result` → `platform_command_events`（`ControlAuditEvent`：演员档案 ID、操作名、接受/拒绝/失败、固定原因码，无参数与详情 JSON）。
- 认证审计：`auth_audit_events`（登录/登出/注册/验证/重置各事件与原因码）；限流记录存 `registration_attempts`（subject 只存 SHA-256 哈希）。
- 记忆审计：`memory_audit_events` 记录候选→审核→撤销全生命周期（`KnowledgeLifecycleService._audit`）。
- 人格操作审计：`persona_management_operations` + `DatabasePersonaControlAuditSink`（`app/database_control/persona_audit.py`）。


### 9.8 存储模式切换矩阵

| 模式 | 条件 | 承载 | 限制 |
| --- | --- | --- | --- |
| `jsonl`（默认） | 无 | 会话/消息/记忆/审计全部本地 | 无账号、无跨平台身份、单机 |
| `postgresql` | `STORAGE_BACKEND=postgresql` + POSTGRES 三字段 | 公开 Web 聊天存储 + auth 全部（`001_web_core` 17 表） | 需 `DATABASE_V2_ENABLED=false`；不支持 V2 平台命令 |
| Database V2（MySQL） | `DATABASE_V2_ENABLED=true` + MYSQL 三字段 | qq/wechat 平台身份、关系、平台命令、knowledge/persona_management 持久化、公开账号（V2 路径） | 与 PostgreSQL 路径互斥（按 .env.example 指引）；迁移显式执行 |
| `STORAGE_BACKEND=mysql` | 不再支持 | — | 工厂抛 `ValueError`（V1 已移除） |

## 10. 前端与客户端

### 10.1 Web Desk PWA（`app/static/web/studio/`）

- 纯静态实现：`index.html`（`desk-shell` 容器）、`app.js`（约 23KB：聊天、流式 SSE/text/plain 读取、音频上传、语音播放请求）、`style.css`/`mobile.css`（响应式）、`manifest.webmanifest` + `service-worker.js`（`desk-shell-v14` 离线壳缓存）。
- 路由：`/desk` 页面与资源由 `app/main.py` 显式 FileResponse 提供（no-store 策略）。
- 语音边界：播放必须携带服务端签发的 `X-Hutao-Reply-Id` 调 `POST /api/v1/voice/synthesize`；失败时页面回退纯文字，绝不伪造浏览器系统音色（README 明确要求）。
- 测试：`tests/test_desk.py`（静态路由 + 沙箱人格 + 聊天/音频流）与 `tests/test_desk_streaming_browser.py`（真实 ASGI 流式回复 UTF-8 浏览器断言）。

### 10.2 静态页族（`app/static/`）

- `auth/`：登录、注册、邮箱验证、找回密码两步界面；服务未启用时提交入口保持不可用（配合 `GET /api/v1/auth/status` 的三布尔）。
- `profile/`（`/me`）：个人中心。
- `credits/`：致谢页（`data.json` 驱动）。
- `control/`：控制中心（状态、操作状态、配置分组编辑、日志尾部、服务与受管测试；写操作经 `X-Hutao-Actor-*` 头授权）。
- `workbench/`：视觉工作台（`VISUAL_WORKBENCH_ENABLED` 默认关闭；登录口令、摄像头会话、采集与感知状态）。
- `shared/`：主题（`theme.css`、`liquid-theme.css`）、氛围脚本（`ambient.js`）、光标资源（白名单 5 种）。

### 10.3 Vite 公开落地页（`frontend/site/`）

- React 19 + Vite 6（`vite.config.js`：`base="/site/"`，输出 `app/static/web/site`），依赖 gsap、lucide-react、motion、three（`package.json`）。
- 源码：`src/App.jsx`、`src/main.jsx`、`src/styles.css`、`src/components/ParticleField.jsx`、`src/hooks/useLandingAnimations.js`。
- 构建产物（`index-*.js/css`、`three.module-*.js`）已随仓库维护，保证无 Node 环境也能直接运行；重新构建命令为 `cd frontend/site && npm run build`。

### 10.4 微信小程序（`miniprogram/`，21 个文件）

- 页面：`pages/chat/index`（对话：文字、按住录音上传、回复文本与受控语音播放）、`pages/profile/index`（个人中心）、`pages/auth/index`（登录注册）。
- 工具：`utils/api.js`（统一请求封装：`apiBaseUrl` 来自 `config.js`，默认空值使界面不可用）、`utils/session.js`（Bearer 会话 + CSRF 存储，登出只清 CSRF 的测试已固化在 `tests/session.test.js`）。
- 能力边界：只调用账户、文本聊天、文件语音、回复播放、记忆与对话脉络；不调用 `/api/control/*`、`/workbench`、摄像头、屏幕采集、配置或日志接口。
- 语音约束：只接受服务端登记的 `reply_id` 播放；客户端文本不用于合成；录音是"按住说话、松开发送"的文件上传链路，不是实时电话。
- 测试：`node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js`（本次运行 5 passed）。

### 10.5 控制中心能力（`app/control/` + 页面）

`/control` 提供：状态概览（`build_control_status`）、S8 操作状态（`OperationsStatusService`）、测试报告摘要、错误分类、演员授权校验、审计查询（仅授权演员）、配置分组编辑（带备份）、日志尾部（脱敏 + 乱码修复 + 噪音过滤）、受管服务（`hutao_core`/`gpt_sovits`）启停、受管测试（`control_center`/`api_voice`/`full_pytest`）运行。

---

### 10.6 页面与后端契约（各页面实际调用的端点面）

| 页面 | 读 | 写 |
| --- | --- | --- |
| `/desk`（studio PWA） | `GET /api/v1/auth/status`、`/api/v1/voice/status`、`/api/v1/memories`、`/api/v1/dialogue-context` | `POST /api/v1/chat`、`/api/v1/chat/stream`、`POST /api/v1/voice/synthesize`、`DELETE /api/v1/memories/{id}`、`POST /api/v1/audio/chat/file`（语音输入） |
| `/auth` | `GET /api/v1/auth/status` | `POST /api/v1/auth/login`、`/register`、`/verify-email`、`/password-reset/request`、`/password-reset/confirm` |
| `/me` | `GET /api/v1/auth/me`、`GET /api/v1/memories` | `POST /api/v1/auth/logout`、`DELETE /api/v1/memories/{id}` |
| `/credits` | 静态 `data.json` | — |
| `/`（Vite site） | 纯静态 | — |
| `/control` | `GET /api/control/status`、`/operations/status`、`/operations/test-reports`、`/operations/errors`、`/operations/actor`、`/operations/audits`、`/config`、`/logs`、`/services`、`/tests` | `POST /api/control/config`、`/services/{id}/start|stop`、`/tests/{id}/run`（全部带 `X-Hutao-Actor-*`） |
| `/workbench` | `GET /api/workbench/status`、`/camera/sessions/{id}`、`.../capture/status`、`.../perception/status` | `POST /api/workbench/login|logout`、`/camera/sessions`、`.../stop`、`.../capture/start|stop`（会话 Cookie + CSRF） |
| 小程序 | `GET /api/v1/auth/me`、`/memories`、`/dialogue-context`、`/voice/status` | `POST /api/v1/auth/mobile/login`、`/chat`、`/chat/stream`、`/audio/chat/file`、`/voice/synthesize`（Bearer） |

## 11. 安全与隐私设计

### 11.1 密钥与脱敏

- 正则脱敏：`app/core/security.py` `redact_secrets`（`sk-...` 20+ 位）在模型调用审计、Provider trace（`_SENSITIVE_KEYS`：authorization/api_key/apikey/password/secret/token，`app/providers/router.py` `_redact`）与日志读取（`control/log_reader.py` `redact_sensitive_log_text`）三处生效。
- 配置回显：控制中心 `/api/control/config` 对 secret 键只返回 `configured` 布尔，不回显值；`/health` 只给 `api_key_configured`。
- 数据库层：`database_control/mysql_adapter.py` `_redact_id` 对平台账号 ID 只保留首尾字符；审计事件不落参数与详情 JSON。
- `.env` 不入库（`.gitignore`、`.dockerignore` 双重排除），模板只维护 `.env.example`。

### 11.2 会话与 CSRF

- 网页会话：登录签发不透明 token（`token_urlsafe`），服务端只存 `token_hash`（`app/auth/sessions.py` `hash_opaque_token`）；`hutao_session` Cookie 为 `HttpOnly` + `SameSite=lax`，`SESSION_COOKIE_SECURE` 控制 secure 位。
- CSRF：登录响应下发 `csrf_token`，服务端只存其哈希；写端点（聊天、记忆删除、语音合成、登出、工作台写操作）用 `compare_digest` 校验 `X-CSRF-Token` 头（`AuthService.require_session(require_csrf=True)`，`app/auth/service.py`）。
- 移动端：`/api/v1/auth/mobile/login` 返回短期 Bearer；`bearer_session_token()`（`app/auth/identity.py`）解析并复用同一会话存储。
- 工作台：独立 `WorkbenchSessionStore`（`app/workbench/sessions.py`）：管理员口令登录、30 分钟会话、CSRF、登录失败限流（`_LoginFailureState`）、会话过期清理。

### 11.3 限流与滥用防护

- `AuthRateLimitService`（`app/auth/rate_limit.py`）：按 email/ip_prefix/device 三类主题、滑动窗口（10 分钟）、SHA-256 哈希存储、封禁期（30 分钟）；登录/注册/重置请求共用。
- 语音合成限流：`WebVoiceReplyStore` 每会话 `PUBLIC_WEB_TTS_MIN_INTERVAL_SECONDS` 间隔、并发合成互斥（409）、票据 TTL 300 秒。
- 音频上传：`save_upload_to_temp` 走临时目录；上传大小受 FastAPI/反向代理限制（生产反代白名单见权威手册 17 章）。
- 摄像头会话：每 owner 同时只允许一个 active 会话（`CameraSessionManager`），明确同意请求（`require_explicit_consent`）才能开始。

### 11.4 网页 TTS 短时票据（reply_id）

详见 6.4：票据由服务端在本次回复完成后签发；合成接口只接受 `reply_id`（16–128 字符）+ 会话 + CSRF/Bearer；归属、并发、频率、长度、输出目录全部服务端校验；音频响应后即删。**浏览器无法用任意文本请求合成**，这是防止"把 TTS 当免费朗读 API"的关键边界。

### 11.5 摄像头隐私

`CAMERA_RAW_FRAME_RETENTION_SECONDS=0`（原始帧不持久化）、`CAMERA_FACE_IDENTIFICATION_ENABLED=false`（不做人脸识别）、`CAMERA_CLOUD_UPLOAD_ENABLED=false`（不上传）、`CameraTemporalState` 只保留白名单标签的时序确认（`temporal_state.py`），`LocalCaptureController` 回调只验证并规范化瞬时数据、不保留帧（`camera/router.py` 注释与 `build_camera_control_runtime` 的 `accept_capture_observation`）。

### 11.6 世界来源法律批准门

每个来源必须同时通过：全局 `WORLD_AWARENESS_ENABLED`、清单 `enabled`、`legal_approved`（或 `WORLD_SOURCE_LEGAL_APPROVED_IDS`）、`WorldAcquisitionService` 四重门；清单加载器（`source_manifest.py`）强制 HTTPS、hostname 白名单、禁止凭证化 URL；`WorldContextAssembler` 拒绝凭证化 URL 并过滤过期证据。8 个候选来源当前全部 `enabled=false` 且 `legal_approved=false`（`data/world/sources.json`：1 个 API、2 个 RSS feed、4 个 review_required 页面、1 个 robots_blocked 页面）。

### 11.7 自杀/自伤输出拦截门

`app/services/response_evaluator.py` 的 `is_life_death_context`、`disallows_death_joke`、`is_self_harm_directive_bait`、`repeats_self_harm_directive` 与人格安全场景（`PersonaScene.safety`）共同构成本地代码门：相关输出在模型结果评估阶段被替换/拦截（`_evaluation_fallback_reply`），不依赖 Prompt 兜底；Database V2 亦有 `safety_guard_events` 表结构。

### 11.8 审计链汇总

模型调用审计（JSONL + 脱敏）、控制操作审计（`platform_command_events`）、认证审计（`auth_audit_events`）、记忆审计（`memory_audit_events`）、人格操作审计（`persona_management_operations`）、登录限流记录（`registration_attempts`，哈希主题）——六条审计链均只记录最小必要字段，见 9.5。


### 11.9 威胁模型与已知未加固面（如实说明）

- 控制中心读端点（`/api/control/status`、`/logs`、`/services`、`/tests`、`/operations/*` 除 audits）不要求认证：设计上按"本机或受信任私网"定位（README 原文），公网部署前必须由反向代理白名单隔离（权威手册 17 章）。
- 公开鉴权关闭时，`/api/v1/memories` 与聊天身份直接采用请求携带的 `user_id`：这是本地开发形态，**绝不能**把未启用 `PUBLIC_WEB_AUTH_ENABLED` 的实例暴露到公网。
- `X-Hutao-Actor-*` 头只是查找键，授权权威在数据库解析（`ControlWriteGuard`），但未启用 V2 时回退到 `hutao_owner_qq_ids` 等静态集合——该回退仅适用于本机控制面。
- 聊天主接口无全局限流（`AuthRateLimitService` 只覆盖认证类端点）：公网部署需要反代层速率控制（手册 19 章资源预算）。
- 本地开发默认 HTTP、`SESSION_COOKIE_SECURE=false`：HTTPS 前不得开启注册与 secure cookie。
- 上传文件走临时目录且校验在 ASR 层，但通用上传大小限制依赖 FastAPI/反代配置，需在部署层固化。
- `/v1/chat/completions` 兼容层不挂账号鉴权（设计为内网 Hermes 时代的兼容面，现作为内网工具保留）；公网开放前需评估是否加 key 鉴权。

### 11.10 公开认证装配条件矩阵（`app/auth/runtime.py` `configure_public_web_auth()`）

| 层 | 挂载条件 | 挂载内容 |
| --- | --- | --- |
| 1 认证 | `PUBLIC_WEB_AUTH_ENABLED=true` 且（PostgreSQL 已配置 或 V2+MySQL 完整） | `/login`、`/mobile/login`、`/me`、`/logout` |
| 2 注册 | 层 1 + `EMAIL_DELIVERY_ENABLED=true` + SMTP 四字段 | `/register`、`/verify-email` |
| 3 重置 | 同层 2 | `/password-reset/request`、`/password-reset/confirm` |
| 派生 | 层 1 | `database_v2_profile_source`（V2 路径时为 true）、公开聊天/记忆/语音端点的强身份 |
| TTS | 层 1 + `PUBLIC_WEB_TTS_ENABLED=true` | `/api/v1/voice/synthesize` 开放（`public_web_tts_configured`） |

任一条件缺失即整层不挂载（路由不存在而非返回空壳），`GET /api/v1/auth/status` 用三布尔向客户端如实暴露当前层。

### 10.9 微信小程序页面细节（`miniprogram/pages/`）

- **`pages/chat/index`**：输入框 + 按住录音按钮（`touchstart/touchend` 语义为"按住说话、松开发送"，文件上传链路）；发送走 `utils/api.js` 的 `POST /api/v1/chat` 或 `/chat/stream`；语音回复按钮只播放服务端 `reply_id` 对应的 `POST /api/v1/voice/synthesize` 返回的 ArrayBuffer（`api-client.test.js` 固化该断言）；页面含记忆与对话脉络入口。
- **`pages/auth/index`**：`POST /api/v1/auth/mobile/login` 获取 Bearer，`utils/session.js` 持久化（登出只清 CSRF，会话令牌留在存储中供下次校验——该行为被 `session.test.js` 固化）。
- **`pages/profile/index`**：`GET /api/v1/auth/me` + `/memories` 展示与删除。
- **`config.js`**：`apiBaseUrl = ""` 默认空值使界面不可用（防误暴露本地服务）；真实部署填 HTTPS 域名并在小程序后台配 request/uploadFile 白名单（ICP 备案 + 可信 TLS，禁用 127.0.0.1/localhost/IP）。
- **`app.json`**：三页 + 自定义导航 + 深色主题 + `tabBar`（对话/我的两页）+ 网络超时（request 20s、upload 30s、download 30s）。

### 11.11 隐私数据最小化清单（各链路存什么/不存什么）

| 链路 | 持久化 | 明确不持久化 |
| --- | --- | --- |
| 聊天 | 消息文本、会话/用户 ID、模型调用元数据（脱敏） | API 密钥、原始 Prompt 投影、世界来源响应体 |
| 记忆 | 正文、类型、置信度、状态、审计事件 | 来源密钥、IP |
| 认证 | 密码 Argon2 哈希、会话 token 哈希、CSRF 哈希、验证/重置码哈希 | 明文密码、明文 token、重置码明文 |
| 限流 | 主题 SHA-256 哈希 + 计数 | 原始邮箱/IP 前缀/设备号 |
| 摄像头 | 白名单标签观察（TTL 15s）+ 时序确认 | 原始帧（retention=0）、人脸身份、上传 |
| 世界工具 | 规范化观察（缓存带 TTL）、SHA-256 缓存键 | 原始查询文本、IP、密钥 |
| 控制审计 | 演员档案 ID、操作名、结果、原因码 | 参数、详情 JSON、平台 ID 明文 |
| TTS 票据 | 回复文本（内存/TTL 300s）+ 临时音频（响应后删除） | 用户上传文本合成能力 |

## 12. 测试体系与评估

### 12.1 分层与规模

| 层 | 位置 | 说明 |
| --- | --- | --- |
| 单元/模块测试 | `tests/` 根目录 54 个文件 | 每模块一文件（`test_chat_service.py` 1,107 行级的大文件存在，见技术债） |
| 子系统测试 | `tests/` 10 个子目录 | camera(9)、channels(4)、database_control(9)、expression(4)、knowledge(13)、operations(2)、perception(9)、persona_management(9)、providers(9)、world(9) |
| 契约测试 | `test_*_contracts*`、`tests/persona_management/test_repository_contract.py` | Protocol 契约双实现（内存 fake vs 真仓储） |
| 集成测试（opt-in） | `tests/database_control/test_mysql_integration.py` | 需要 `DATABASE_CONTROL_TEST_DATABASE` 才运行（本次 2 个 skip 全部来自它） |
| 浏览器级测试 | `tests/test_desk_streaming_browser.py`、`test_public_site.py` | ASGI 内联浏览器断言；真实 Edge 浏览器验收在历史报告中 |
| 前端语法检查 | `test_control_center.py` 等 | 静态 JS 内容断言（含"控制页不发布退役 Bot 导航"断言） |

总量：131 个测试文件、17,683 行、749 个 `def test_*` 函数；本次全量 `814 passed, 2 skipped, 2 warnings（17.71s）`。两个 skip 均来自 opt-in 的孤立 MySQL 集成测试（`DATABASE_CONTROL_TEST_DATABASE is not configured`）；两个 warning 来自 `test_desk_streaming_browser.py` 触发的 websockets.legacy 弃用提示（第三方库版本问题，非项目代码缺陷）。

### 12.2 关键测试文件举例

- `tests/test_chat_service.py`：FakeSuccessClient/FakeFailingClient/FakePartialStreamClient/FakeRepairableAiIdentityClient 等假客户端族，覆盖路由、熔断、流中断、修复、门禁、世界守卫与记录写入。
- `tests/test_head_core.py` / `test_head_world_model.py` / `test_head_long_term_planning.py` / `test_head_cognitive_facts.py` / `test_head_blind_review.py` / `test_head_planning_evaluation.py`：HeadCore 状态/世界模型/长期计划/认知事实/盲评/规划评估。
- `tests/providers/test_router.py`、`test_stream_router.py`、`test_runtime.py`：路由顺序、超时、熔断恢复、脱敏 trace、运行时监视。
- `tests/world/test_amap_adapter.py`、`test_news_adapters.py`、`test_qweather_adapter.py`、`test_source_manifest.py`、`test_news_digest.py`、`test_world_context.py`、`test_chat_world_context.py`：适配器规范化、清单校验、冲突检测、缓存键与投影。
- `tests/auth/test_*`（13 个文件）：密码哈希、会话、CSRF、限流、注册、重置、仓储契约。
- `tests/test_project_surface_audit.py`：当前用户可见面使用 HeadCore/hutao 身份、控制页不含退役 Bot 导航、`integrations`/onebot/hermes_weixin 模块不可导入。
- `tests/test_deployment_files.py`：Dockerfile/compose/.env 模板一致性。
- `tests/test_python_runtime_preflight.py`：运行时预检脚本契约。
- `tests/test_desk.py` / `test_desk_streaming_browser.py` / `test_public_site.py`：Desk 静态路由、PWA 资源、流式 UTF-8、公开站资源。
- `tests/camera/test_*.py`（9 文件）：契约、会话管理、时序确认、本地运行时、归一化、注意力选择。
- `tests/test_visual_workbench.py` / `test_sandbox_personas.py` / `test_web_voice_api.py` / `test_web_voice_tts.py`：工作台会话、沙箱人格、语音票据闭环。

### 12.3 评估与盲评体系（scripts/）

- **人格连续性/门禁评估**：`scripts/persona_continuity_eval.py`、`persona_gate_eval.py`、`persona_live_adversarial_smoke.py`、`persona_live_continuity_stress.py`、`persona_system_effect_demo.py`（对应 `data/persona_*.json` 场景夹具，8 个 JSON 受 Git 跟踪）。
- **Head 规划评估**：`scripts/evaluate_head_planning.py`（`app/head/evaluation.py` `evaluate_planning_scenarios`）→ `scripts/export_head_planning_blind_review.py` 导出盲评包 → `scripts/build_head_planning_blind_review.mjs` 渲染 → `scripts/import_head_planning_blind_reviews.py` 回收 → `app/head/calibration.py` 算 Fleiss' kappa（`data/head_planning_*` 三个夹具受 Git 跟踪）。
- **世界模型评估**：`scripts/evaluate_world_model_effects.py`、`scripts/stress_world_model.py`（`tests/test_world_model_effect_evaluation.py`、`test_world_model_stress.py`）。
- **实况压力**：`scripts/live_long_chat_stress.py`、`live_memory_smoke.py`、`live_persona_stress.py`、`live_stream_smoke.py`（需真实模型，离线审计不执行）。
- **语音/ASR 运营**：`scripts/asr_file_smoke.py`、`asr_model_compare.py`、`asr_isolated_model_compare.py`、`asr_isolated_probe_worker.py`、`asr_batch_stress.py`、`build_asr_stress_samples.py`、`download_asr_samples.py`、`audio_api_smoke.py`、`audio_brain_smoke.py`、`audio_chat_api_smoke.py`、`audio_emotion2vec_smoke.py`、`audio_online_random_hutao_smoke.py`。
- **世界工具冒烟**：`world_amap_smoke.py`（`--place`/`--district`/同意门控路由模式）、`world_news_smoke.py`、`world_news_digest_smoke.py`、`world_policy_smoke.py`、`world_source_manifest_check.py`。
- **数据库**：`database_control_smoke.py`（默认只读，`--allow-write` 幂等写）、`database_v2_smoke.py`、`database_v2_readiness_check.py`、`apply_database_v2_migrations.py`、`apply_postgres_web_migrations.py`、`migrate_jsonl_to_database_v2.py`、`semantic_memory_sync.py`。
- **验收**：`final_project_acceptance.py`（最终离线验收）、`run_tests_with_md_log.py`（测试并落 Markdown 报告）、`python_runtime_preflight.py`、`camera_control.py`、`camera_vision_preflight.py`、`postprocess_voice_outputs.py`、`api_smoke.py`。
- **数据集审计（保留）**：`audit_persona_finetune_dataset.py`、`export_persona_finetune_dataset.py`（清理报告注明"仍被测试引用"，属人格微调数据集审计工具，非语音克隆训练工具）。
- **其他**：`generate_pydantic_wdac_supplement.ps1`（本机 WDAC 历史问题的辅助脚本，保留为运维参考）。

#### 12.2.1 根目录 54 个测试文件逐一说明

| 测试文件 | 覆盖点 |
| --- | --- |
| `test_api.py` | /api/v1 核心端点行为 |
| `test_app.py` | 应用装配与静态路由 |
| `test_audio_pipeline.py` | 候选转写、选优与修复管线 |
| `test_audio_quality_metrics.py` | CER 归一化 |
| `test_auth_audit.py` 等 13 件 `test_auth_*` | 审计、邮件投递、身份解析、密码哈希、重置（服务/仓储/路由）、限流、注册（服务/路由）、登录路由、服务、会话 |
| `test_chat_service.py` | 主链路：路由/流式/修复/门禁/记录（超千行） |
| `test_control_center.py` | 控制中心路由与静态资源 |
| `test_database_v2.py` | Database V2 仓储与命令策略 |
| `test_deployment_files.py` | Dockerfile/compose/env 模板一致性 |
| `test_desk.py` | Desk 静态路由 + 沙箱人格 + 聊天/音频流 |
| `test_desk_streaming_browser.py` | 浏览器流式 UTF-8（产生 2 个弃用警告） |
| `test_dialogue_policy.py` | 对话决策与表达政策 |
| `test_eval_scripts.py` | 评估脚本契约 |
| `test_gpt_sovits_tts.py` | GPT-SoVITS 适配（清理后唯一 TTS 测试） |
| `test_head_*`（10 件） | 盲评/认知事实/核心/情景记忆/长期计划/规划评估/运行时/世界证据/世界模型/世界状态 |
| `test_jsonl_repository_concurrency.py` | JSONL 并发追加安全 |
| `test_persona_memory.py` / `test_persona_system.py` | 记忆策略与人格系统 |
| `test_postgres_storage.py` | PostgreSQL 仓储契约 |
| `test_project_surface_audit.py` | 可见面身份断言 + 退役模块不可导入 |
| `test_public_site.py` | 公开落地页资源 |
| `test_public_web_auth_runtime.py` | 认证装配的条件挂载 |
| `test_python_runtime_preflight.py` | 运行时预检 |
| `test_response_evaluator.py` | 30+ 判定函数 |
| `test_sandbox_personas.py` | 沙箱人格 CRUD 与投影 |
| `test_semantic_memory.py` | 嵌入/相似度/Qdrant 契约 |
| `test_storage_database.py` | 存储数据库层（V1 相关用例已移除） |
| `test_visual_workbench.py` | 工作台会话与路由 |
| `test_voice_chat.py` | TTS 服务/自然度/分段 |
| `test_web_voice_api.py` / `test_web_voice_tts.py` | 语音票据闭环与合成 |
| `test_world_model_effect_evaluation.py` / `test_world_model_stress.py` | 世界模型效果评估与压力 |

#### 12.3.1 测试文件全清单（按目录）

- **根目录（54 个）**：`test_api.py`、`test_app.py`、`test_audio_pipeline.py`、`test_audio_quality_metrics.py`、`test_auth_audit/email_delivery/identity/passwords/password_reset(_repository/_router)/rate_limit/registration(_router)/router/service/sessions.py`（认证 13 件）、`test_chat_service.py`、`test_control_center.py`、`test_database_v2.py`、`test_deployment_files.py`、`test_desk.py`、`test_desk_streaming_browser.py`、`test_dialogue_policy.py`、`test_eval_scripts.py`、`test_gpt_sovits_tts.py`、`test_head_blind_review/cognitive_facts/core/episodic_memory/long_term_planning/planning_evaluation/runtime/world_evidence/world_model/world_state.py`（Head 10 件）、`test_jsonl_repository_concurrency.py`、`test_persona_memory.py`、`test_persona_system.py`、`test_postgres_storage.py`、`test_project_surface_audit.py`、`test_public_site.py`、`test_public_web_auth_runtime.py`、`test_python_runtime_preflight.py`、`test_response_evaluator.py`、`test_sandbox_personas.py`、`test_semantic_memory.py`、`test_storage_database.py`、`test_visual_workbench.py`、`test_voice_chat.py`、`test_web_voice_api.py`、`test_web_voice_tts.py`、`test_world_model_effect_evaluation.py`、`test_world_model_stress.py`。
- **`tests/camera/`（9）**：`test_attention/contracts/local_runtime/normalization/router/session_manager/temporal_state.py`、`test_camera_control_script.py`。
- **`tests/channels/`（4）**：`test_capabilities/contracts/core_api_adapter.py`。
- **`tests/database_control/`（9）**：`test_actor/hardening/mysql_adapter/mysql_integration/persona_persistence/router/service.py` + `fakes.py`。
- **`tests/expression/`（4）**：`test_core_api/integration/planner.py`。
- **`tests/knowledge/`（13）**：`test_control_router/factory/intake/lifecycle/mysql_repository/projection_permissions/readiness/runtime/runtime_intake/semantic_memory/semantic_outbox.py` + `conftest.py`。
- **`tests/operations/`（2）**：`test_operations.py`。
- **`tests/perception/`（9）**：`test_adapters/contracts/integration/normalization/pipeline/quality/smoke/validation.py`。
- **`tests/persona_management/`（9）**：`test_async_router/mysql_readiness/mysql_store/persistent_service/persona_management/readiness/repository_contract/router.py`。
- **`tests/providers/`（9）**：`test_contracts_registry/deepseek/funasr/funasr_provider/router/runtime/stream_router/tts.py`。
- **`tests/world/`（9）**：`test_amap_adapter/chat_world_context/news_adapters/news_digest/qweather_adapter/source_manifest/world_context/world_core.py`。

#### 12.3.2 标准验证命令与运行规范

- 禁止在仓库根目录裸跑 `pytest`：会收集 `external/GPT-SoVITS` 自带的第三方测试（AGENTS.md 明确警告）。
- 标准命令（唯一 Python 环境）：`compileall -q app scripts tests` → `pytest tests -q -p no:cacheprovider` → `node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js` → `cmd /c "启动控制中心.bat --check-only"`。
- 聚焦回归惯例：改哪测哪，并在 `logs/...` 写 Markdown 报告（AGENTS.md 用户开发要求第 5、6 条）。
- opt-in 集成：`DATABASE_CONTROL_TEST_DATABASE` 指向 `test_*`/`*_test` 命名的隔离库（`integration_guard.py`）才运行 `tests/database_control/test_mysql_integration.py`（本次 2 个 skip 的来源）。

#### 12.3.3 全量测试基线演进（摘自 `docs/history/agent-handoff-archive.md` 交接记录，均为"当时"数字）

| 日期 | 全量结果 | 备注 |
| --- | --- | --- |
| 2026-07-14 早 | 331 passed | GPT-SoVITS 退役后 |
| 2026-07-14 | 351 passed | 人格系统化审计基线 |
| 2026-07-14 晚 | 469 → 515 → 543 | S6 路由系列集成 |
| 2026-07-15 | 550 → 556 → 581 → 597 → 600 → 604 | 数据库控制/记忆集成系列 |
| 2026-07-16 | 630 | WDAC 前基线 |
| 2026-07-17 | 664 → 670 → 674 → 677 → 685 → 687 → 693 | 世界工具系列 |
| 2026-07-21 | 730 | 人格清理后 |
| 2026-08-14 清理前 | 842 passed, 2 skipped | 含 28 个待删 legacy 测试 |
| **2026-08-14 清理后（本报告）** | **814 passed, 2 skipped** | 本次实测 |

### 12.4 验收证据分层

- **L0/L1 自动化证据**：本次运行记录（1.1 节表）+ `logs/final-acceptance/`、`logs/test-runs/`（精简后保留的完整目录）中的历史报告。
- **L2 浏览器证据**：`logs/` 中历史 Playwright/Edge 桌面 1440x1000 与移动 390x844 验收记录；本次未重跑真实浏览器。
- **历史真实证据**（不在本次范围，仅存档）：2026-07 的记录包括 SenseVoice 真实转写、emotion2vec 5/5 标签样本、DeepSeek 人格连续性 48 轮/4 场景与对抗 12/12、火山 TTS 时长解析等——均见 `docs/history/agent-handoff-archive.md`，本报告不把它们当作当前端到端状态。
- `docs/testing/HEADCORE_WORLD_MODEL_AND_FUNCTIONAL_ACCEPTANCE_2026-07-21.md` 是最近的 HeadCore 世界模型功能验收记录（分层验收清单 L0–L6 在权威手册 21 章）。


### 12.5 scripts/ 全部 49 个脚本分组清单

- **验收与测试运行**（3）：`final_project_acceptance.py`、`run_tests_with_md_log.py`、`python_runtime_preflight.py`。
- **API/音频冒烟**（6）：`api_smoke.py`、`audio_api_smoke.py`、`audio_brain_smoke.py`、`audio_chat_api_smoke.py`、`audio_emotion2vec_smoke.py`、`audio_online_random_hutao_smoke.py`。
- **ASR 运营**（8）：`asr_file_smoke.py`、`asr_model_compare.py`、`asr_isolated_model_compare.py`、`asr_isolated_probe_worker.py`、`asr_batch_stress.py`、`build_asr_stress_samples.py`、`download_asr_samples.py`、`postprocess_voice_outputs.py`。
- **HeadCore 评估**（8）：`evaluate_head_planning.py`、`export_head_planning_blind_review.py`、`build_head_planning_blind_review.mjs`、`import_head_planning_blind_reviews.py`、`evaluate_world_model_effects.py`、`stress_world_model.py`、`audit_persona_finetune_dataset.py`、`export_persona_finetune_dataset.py`。
- **人格实况评估**（5）：`persona_continuity_eval.py`、`persona_gate_eval.py`、`persona_live_adversarial_smoke.py`、`persona_live_continuity_stress.py`、`persona_system_effect_demo.py`。
- **实况压力**（4）：`live_long_chat_stress.py`、`live_memory_smoke.py`、`live_persona_stress.py`、`live_stream_smoke.py`。
- **数据库**（7）：`database_control_smoke.py`、`database_v2_smoke.py`、`database_v2_readiness_check.py`、`apply_database_v2_migrations.py`、`apply_postgres_web_migrations.py`、`migrate_jsonl_to_database_v2.py`、`semantic_memory_sync.py`。
- **世界工具冒烟**（5）：`world_amap_smoke.py`、`world_news_smoke.py`、`world_news_digest_smoke.py`、`world_policy_smoke.py`、`world_source_manifest_check.py`。
- **摄像头**（2）：`camera_control.py`、`camera_vision_preflight.py`。
- **其他**（1）：`generate_pydantic_wdac_supplement.ps1`。

### 12.7 受 Git 跟踪的测试夹具（`data/` 下 9 个 JSON）

| 夹具 | 用途 |
| --- | --- |
| `data/world/sources.json` | 8 个世界来源清单（`source_manifest.py` 加载） |
| `data/head_planning_scenarios.json` | Head 规划评估场景（`head/evaluation.py`） |
| `data/head_planning_pairwise_preferences.json` | 配对偏好校准数据（`head/calibration.py`） |
| `data/head_planning_multi_reviewer_annotations.json` | 多评审者标注（Fleiss' kappa） |
| `data/persona_continuity_scenarios.json` | 人格连续性评估场景 |
| `data/persona_live_continuity_scenarios.json` | 实况连续性压力场景 |
| `data/persona_live_scenarios.json` | 人格实况场景 |
| `data/persona_long_chat_scenarios.json` | 长聊压力场景 |
| `data/persona_training_seed.json` | 人格训练种子（配合 `audit_persona_finetune_dataset.py`） |

其余 `data/` 内容（`models/`、`hutao_voice/`、`stickers/`、`generated_voice/`、`asr_*` 样本等）全部本地化不入库。

#### 12.8 测试风格约定（源自既有代码惯例）

- 异步测试统一 `asyncio.run(...)` 包装（无 pytest-asyncio 插件依赖）。
- 双实现契约：每个 Protocol 至少一套内存 fake + 一套真实实现测试（`tests/persona_management/test_repository_contract.py`、`tests/knowledge/test_mysql_repository.py` 等）。
- 假客户端族命名：`FakeSuccessClient/FakeFailingClient/FakePartialStreamClient/FakeRepairableAiIdentityClient`（`tests/test_chat_service.py`）。
- opt-in 集成用环境变量门（`DATABASE_CONTROL_TEST_DATABASE`），默认 skip 并输出原因。
- 测试产物落 `logs/test-runs/`（`run_tests_with_md_log.py`），控制中心 `/api/control/operations/test-reports` 读取同一目录摘要。
- 前端 JS 语法断言 + 静态内容断言（"控制页不含退役导航"）混用 `node --check` 与 Python 测试。

## 13. 本地模型清单与部署

### 13.1 模型安装清单（模型不随源码上传）

权威清单：`README.md`「模型安装清单」+ `docs/LOCAL_MODEL_INSTALLATION_MAP.md` + `docs/deployment/LOCAL_MODEL_LAYOUT.md`。原则：GitHub 仓库只保存框架、源码、配置示例与文档；`data/models/`、`model_training/`、`external/`、`D:\HutaoModels\` 均为本机部署资产，不进 Git、不放 LFS。

| 用途 | 模型 ID | 本地目录 | 是否必需 |
| --- | --- | --- | --- |
| 默认语音识别 | `iic/SenseVoiceSmall` | `data/models/modelscope/iic/SenseVoiceSmall` | 启用文件/Desk 语音输入时必需 |
| 语音活动检测 | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | `data/models/modelscope/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | 默认 ASR 预设必需 |
| 中英文标点恢复 | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | `data/models/modelscope/iic/punc_ct-transformer_cn-en-common-vocab471067-large` | 默认 ASR 预设必需 |
| 音频情绪线索 | `iic/emotion2vec_plus_large` | `data/models/modelscope/iic/emotion2vec_plus_large` | `AUDIO_EMOTION_ENABLED=true` 时必需 |
| 备用高质量 ASR | `FunAudioLLM/Fun-ASR-Nano-2512` | `data/models/modelscope/FunAudioLLM/Fun-ASR-Nano-2512` | 仅 `fun-asr-nano` 预设需要 |
| 语义记忆嵌入 | `BAAI/bge-m3` | `D:\HutaoModels\embedding\bge-m3`（服务器 `/srv/hutao/models/embedding/bge-m3`） | 启用语义记忆时必需（1024 维，换模型必须重建 Qdrant 索引） |
| 网页 TTS 音色 | 已授权验收的胡桃 GPT-SoVITS 权重 + 参考音频 | `external/GPT-SoVITS-v2pro-20250604/` 或独立模型盘 | 启用网页 TTS 时必需（单独启动的 HTTP 服务） |
| 视觉目标检测 | YOLO11n/YOLOv8n ONNX | `data/models/vision/yolo/yolo11n.onnx`（经 `CAMERA_YOLO_MODEL_PATH` 指定） | 启用摄像头感知时必需 |
| 姿态/手势/面部特征 | MediaPipe Pose/Hand/Face Landmarker | `data/models/vision/mediapipe/*` | 摄像头高级感知的未来固定资产 |
| OCR | RapidOCR ONNX | `data/models/vision/ocr/rapidocr/` | 未来视觉 worker 配置 |

明确禁止：Ollama/Qwen VLM（已随 `app/vision` 移除）、NoneBot/OneBot/NapCat/Hermes（Bot 已退役）、人脸识别、远程帧上传、未通过验收的 MoViNet/情绪分类器。ASR 模型目录缺失时 FunASR/ModelScope 可能按模型 ID 联网解析，离线部署必须预置目录（`app/audio/model_paths.py` `resolve_modelscope_model`）。

### 13.2 部署

- **Dockerfile**：`python:3.11-slim` 基础镜像，apt 装 ffmpeg/libsndfile1，`requirements.txt` 全量安装（含 funasr/torch 重依赖，镜像体积大的代价），非 root 用户 `hutao`，暴露 8000，`uvicorn app.main:app --host 0.0.0.0`。注意：基础镜像无 healthcheck（compose 中 MySQL 有 healthcheck）。
- **`deploy/compose.staging.yml`**：`mysql:8.4`（utf8mb4 + healthcheck）、`core`（挂 `core_data:/data`，仅绑定 127.0.0.1:8000）、`migrate-v2`（`database-v2` profile，显式运行迁移）、`qdrant:1.13.4` + `semantic-memory-worker`（`semantic-memory` profile，Qdrant 不发布公网端口，嵌入模型只读挂载 `/models`）。
- **`deploy/.env.staging.example`**：不含密钥的模板；真实值写入 `deploy/.env.staging`（不入库）。
- **`deploy/README.md`**：明确 `STORAGE_BACKEND` 不切 `mysql`、迁移显式执行、语义记忆需要已迁移的 V2 库 + 本地嵌入模型。
- **`.dockerignore`**：排除 `.env/.env.*`（保留 `.env.example`）、`.git`、缓存、`node_modules`、`model_training`、`external`、`data/models`、`logs`、`output`、`tmp`、`*.exe` 等。
- **启动**：本地 `uvicorn app.main:app` 或 `启动控制中心.bat`（清理后为 Core-only 入口）；反向代理、域名、HTTPS 白名单与资源预算见权威手册 17–19 章。

---

### 10.7 静态资源清单（`app/static/`，审计当日）

| 目录 | 文件与大小（约） | 说明 |
| --- | --- | --- |
| `web/studio/` | `app.js` 23.3KB、`style.css` 22.3KB、`mobile.css` 2.5KB、`index.html` 8.5KB、`manifest.webmanifest`、`service-worker.js` 1.1KB | Web Desk PWA |
| `web/site/` | `index.html` + `assets/index-BvyiZDeu.js` 460KB、`index-B8o5YgBw.css` 17.6KB、`three.module-BT1pP-6r.js` 705KB | Vite 构建产物 |
| `auth/` | `app.js` 19.4KB、`index.html` 11.6KB、`style.css` 25.1KB | 登录注册页 |
| `profile/` | `app.js` 24.2KB、`index.html` 19KB、`style.css` 46.3KB | 个人中心 |
| `credits/` | `app.js` 5.4KB、`index.html` 3.3KB、`style.css` 12.8KB、`data.json` 1.2KB | 致谢页 |
| `control/` | `app.js` 3.4KB、`index.html` 3.7KB、`style.css` 4.5KB、`assets/control-atmosphere.webp` 111KB | 控制中心 |
| `workbench/` | `app.js` 8.8KB、`index.html` 5.5KB、`style.css` 7.1KB | 视觉工作台 |
| `shared/` | `theme.css` 9KB、`liquid-theme.css` 12.3KB、`ambient.js` 6.1KB、`assets/cursors/` 5 个 PNG | 共享主题与光标 |

### 10.8 部署拓扑与网络边界（本地/服务器）

| 组件 | 端口/绑定 | 暴露策略 |
| --- | --- | --- |
| FastAPI Core | 8000；本地 `127.0.0.1`；compose 内 `127.0.0.1:8000:8000` | 公网必须经反向代理（手册 17 章白名单） |
| GPT-SoVITS HTTP | 9880（`PUBLIC_WEB_TTS_BASE_URL` 默认 `127.0.0.1:9880`） | 仅本机，独立进程 |
| MySQL | 3306（compose 内部） | 不发布 |
| PostgreSQL | 5432 | 不发布 |
| Qdrant | 6333（compose `semantic-memory` profile 内部） | `deploy/README.md` 明确不发布公网 |
| 摄像头 | 本机硬件 | 默认关闭 |

### 13.4 本地开发环境与命令全录（唯一 Python 环境）

- 依赖安装：`& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pip install -r requirements.txt`（视觉可选：`requirements-vision.txt`）。
- 模型快照（默认音频链路四件，ModelScope）：`snapshot_download` 到 `data/models/modelscope/...`；备用 ASR `FunAudioLLM/Fun-ASR-Nano-2512` 单独约 2GB；嵌入 `BAAI/bge-m3` 用 huggingface_hub 下载到 `D:\HutaoModels\embedding\bge-m3`。
- 启动 Core：`& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000`；一键入口 `cmd /c "启动控制中心.bat"`（清理后为 Core-only，含 `--core-only`/`--check-only` 参数）。
- 常用地址：`/health`、`/docs`（OpenAPI）、`/control`、`/desk`、`/auth`、`/me`、`/credits`、`/workbench`（默认关）、`/`（落地页）。
- 标准验证四连（见 12.3.2）：compileall → pytest → node --test → 启动器 `--check-only`。
- 禁止：仓库根目录裸跑 `pytest`（会收集 `external/GPT-SoVITS` 第三方测试）；创建其他虚拟环境；把密钥写进代码/文档/日志。

## 14. 验收证据与已知边界

### 14.1 自动化证据（本次已验证）

- `compileall app scripts tests`：PASS。
- `pytest tests -q -p no:cacheprovider`：814 passed, 2 skipped（skip 为 opt-in MySQL 集成测试）。
- `node --test miniprogram/tests/*.test.js`：5 passed。
- 静态断言：控制页无退役 Bot 导航、退役模块不可导入、部署文件一致、来源清单合法（`test_project_surface_audit.py`、`test_deployment_files.py`、`tests/world/test_source_manifest.py`）。

### 14.2 仍需真实验收的外部依赖（逐项列出）

| 依赖 | 已实现 | 未验收 |
| --- | --- | --- |
| DeepSeek/兼容模型 | 路由、超时、重试、熔断、修复 | 本轮未发起任何真实模型调用 |
| MySQL Database V2 | 迁移、仓储、控制面、bootstrap、绑定、认领、命令 | 未在真实 MySQL 上执行迁移/readiness/重启恢复演练 |
| PostgreSQL Web 核心 | 迁移 + 仓储 + auth 集成 | 未做真实 PostgreSQL 联调 |
| SMTP 邮件 | 注册/验证/重置全流程 + 限流 | 未做真实 SMTP 发送与域名验证 |
| Qdrant 语义记忆 | outbox worker + 双嵌入 provider | 未在真实 Qdrant 上建集合/同步 |
| FunASR/SenseVoice | 文件转写、候选路由、质量门 | 本轮未跑真实音频推理（历史记录仅存档） |
| emotion2vec | 情绪引擎与元数据链路 | 同上 |
| GPT-SoVITS | `synthesize_gpt_sovits` + 票据闭环 | 未做音色/性能/听感验收（README 要求保持关闭） |
| 高德/和风天气/新闻/政策 | 适配器 + 门控 + 冲突检测 | 零真实 API 调用；8 个来源全部未启用未批准 |
| 摄像头/视觉 | 会话、采集、YOLO/MediaPipe 分析器、时序确认 | 未接真实摄像头与视觉权重做基准 |
| 微信小程序 | 代码 + 单元测试 | 未在微信开发者工具/真机联调 HTTPS 域名 |

### 14.3 明确不验证/不宣称

- 不宣称任何真实平台消息投递（QQ/微信 Bot 已退役）。
- 不宣称视觉理解或人脸能力（无 VLM、无人脸识别）。
- 不宣称实时电话语音（录音上传链路不是实时电话）。
- 不宣称历史报告中的真实模型/平台证据为当前状态（一律标注存档日期）。


### 14.4 与清理前基线（842 passed）的差值说明

清理前基线 842 passed / 2 skipped 与本报告 814 passed 的差值 28 个测试，来自删除的 legacy 资产（依据清理报告）：

- `tests/test_hutao_flow_evaluation.py`、`tests/test_hutao_consensus_dataset.py`、`tests/test_hutao_voice_audit.py`、`tests/test_hutao_transcription_audit.py`（CosyVoice2 语音克隆训练审计测试，4 个文件）；
- `tests/test_architecture_publication.py`（旧手册出版工具链，1 个文件）；
- `tests/providers/test_tts.py` 与 `tests/test_voice_chat.py` 中 Bert-VITS2 相关用例（改写为 gpt_sovits 版本后的净差）；
- `tests/perception/test_adapters.py` 中 Ollama 视觉（`VisionObservationAdapter`/`adapt_vision_result`）用例；
- `tests/test_storage_database.py` 中 MySQL V1（`STORAGE_BACKEND=mysql` 分支、`migrations/000-003`）用例；
- 视觉死代码二次清理（定稿前）：`tests/perception/test_normalization.py` 的 2 个 `merge_vision_outputs` 用例与 `tests/perception/test_integration.py` 的 1 个 `normalize_vision_result` 用例（3 个测试函数）。

清理报告同时记录：聚焦回归（providers/perception/world/voice_chat/storage/control/api/surface/deployment）189 passed 后修复 `test_project_surface_audit.py` 一处断言，最终 3 passed；世界来源清单测试、控制中心退役断言测试、部署文件测试全部通过。任何后续变更都必须重新执行全部门禁，不能沿用本报告数字。

### 14.6 历史真实证据存档索引（全部来自 `docs/history/agent-handoff-archive.md`，非本次验证）

| 证据 | 记录日期 | 状态 |
| --- | --- | --- |
| SenseVoice 真实转写通过（非空 28/28，历史口径） | 2026-07 早 | 历史存档 |
| emotion2vec 真实标签样本 5/5 通过 | 2026-07 早 | 历史存档 |
| 火山 TTS WAV/MP3 时长 2.786s 解析 | 2026-07-14 | 历史存档（火山已移除） |
| DeepSeek 人格连续性 48 轮/4 场景、对抗 12/12 | 2026-07-14 | 历史存档 |
| 人格 v3 连续性压力 48/48、零回退 | 2026-07-14 | 历史存档 |
| Ellie Bert-VITS2 本地 WAV 195,628 字节 | 2026-07-09 | 历史存档（已退役） |
| Core 运行验收：DeepSeek 实况聊天、FunASR 冒烟、NapCat/Hermes 启动 | 2026-07-14 | 历史存档（Bot 已退役） |
| Edge 桌面/移动 390px 浏览器验收（多轮） | 2026-07-14~16 | 历史存档 |
| HeadCore 世界模型功能验收 L0–L2 | 2026-07-21 | `docs/testing/HEADCORE_WORLD_MODEL_AND_FUNCTIONAL_ACCEPTANCE_2026-07-21.md` |

这些证据只证明"当时的实现曾在真实环境验证"，不构成对当前代码的端到端背书；当前基线以本报告 1.1 节的本次运行记录为准。

## 15. 风险、技术债与后续路线（如实说明）

### 15.1 代码规模与单体

- **`app/storage/v2_mysql_repository.py`（2,307 行，约 88KB）是本仓库最大的单文件**：同时实现 Database V2 控制面、聊天仓储、导入迁移与大量行映射，职责过重。建议按"控制面查询 / 聊天仓储 / 迁移导入"拆包，但属大重构，须按 AGENTS 约定先出方案。
- `app/services/chat_service.py`（1,266 行）与 `app/main.py`（845 行）偏大：前者是主链路编排器（可拆出 prompt 组装/门禁），后者是装配层（静态路由可下沉）。
- `app/world/context.py`（678 行）、`app/world/adapters/amap.py`（545 行）、`app/persona_management/mysql_store.py`（602 行）为次级大文件。
- 测试镜像了同样的集中度：`tests/test_chat_service.py` 超千行，断言密度高但可读性依赖场景分组。

### 15.2 Git 与发布风险（最高优先级）

- 本地仓库历史仅 2 个提交，且历史中曾跟踪模型权重：`.git` 约 8.9 GB（对象约 3 GB + LFS 约 5.85 GB）。**任何直接 push 都可能触发大文件拒绝或泄露历史资产**。
- 必须按 README「仅上传框架与代码」的 `git archive` 流程导出 code-only 快照、在新目录初始化新仓库后推送；旧仓库只保留本机，绝不 push。清理报告确认：截至 2026-08-14 未执行任何 git commit。

### 15.3 文档漂移（已处置）

审计早期快照中，旧 README 正文仍含 QQ/NapCat/Hermes 条目并引用已删除脚本，且权威手册 `docs/` 副本落后于根目录。审计当日随后完成：README 双语重写（663 行，中文/英文对等）、权威手册 9 处过期引用修正、`docs/` 副本与根目录同步、`docs/systems`/`docs/CURRENT_FULLSTACK` 等交叉文档的残留引用清理。本节保留为历史记录，当前已无此漂移。

### 15.4 依赖与部署债

- `requirements.txt` 把 funasr/torchaudio/transformers/sentence-transformers 与 Core 绑死：纯文字部署也要承担重依赖（Docker 镜像数 GB 级）。建议拆分 `requirements-core.txt` 与可选音频依赖。
- Dockerfile 无 healthcheck；核心容器端口只绑定 127.0.0.1 是正确的默认，但公网部署仍需权威手册 17 章的反代白名单。
- `websockets.legacy` 弃用警告来自 uvicorn/websockets 版本组合，属第三方升级项。

### 15.5 遗留兼容字段与结构

- `Settings` 仍保留 `hutao_owner_qq_ids`/`owner_bootstrap_qq_ids`/`owner_bootstrap_wechat_ids` 与 `HUTAO_PERSONA_*` 兼容读取：它们是 Database V2 身份引导与控制面回退管理员的数据源，不是 QQ Bot 运行时依赖，但命名易引起误解，建议后续改名并保留迁移说明。
- `migrations/v2/001` 仍含 `qq_inbound_events`/`wechat_inbound_events` 等平台事件表：为跨平台身份与历史数据兼容保留，Bot 运行时代码已不存在。
- `app/dialogue/policy.py` 的 `channel` 参数默认值仍为 `"qq"`、`expression_policy` 的贴纸/语音决策函数保留但当前无投递通道——历史兼容面，非主线。

### 15.6 后续路线

- **P0**：code-only 发布执行（README 第 13 节的 `git archive` 流程；旧仓库只留本机）。README 双语、手册副本同步、清理报告与 `docs/history` 归档均已完成。
- **P1**：数据库真实验收序列（V2 迁移→readiness→bootstrap→绑定→认领→记忆撤销→人格发布/回滚→重启恢复）；公开账号 + SMTP 联调；反向代理与 HTTPS。
- **P2**：v2_mysql_repository 拆分、依赖拆分、真实 ASR/情绪/TTS 基准与听感验收、摄像头固定语料基准。
- **P3**：小程序真机联调、语义记忆 worker 生产化、世界来源逐个法律审批后启用。

---

### 15.7 清理后的遗留事项清单（依据清理报告第 5 节）

- 未执行任何 git commit；上传按 `git archive` code-only 流程，旧仓库留本机。
- 权威手册的 `docs/` 发布副本已与根目录同步（清理报告撰写时的未同步状态随后完成）。
- `docx/pdf` 旧产物已删除，需要时可重建（重建脚本已随出版工具链移除，需重新评估方案）。
- 真实外部服务验收不在清理范围（DeepSeek、MySQL、SMTP、模型、TTS）。
- 大件本地资产（`external/`、`data/models/`、`data/hutao_voice/`、`data/stickers/`）按要求保留未动，后续处置需单独决策。
- `README.md` 双语重写已完成并落盘（663 行）；视觉死代码二次清理也已完成（见 16.2 Ollama 视觉行）。

## 16. 附录 A：2026-08-14 项目清理记录（源码依据：`logs/project-cleanup/2026-08-14/project-cleanup-report.md` 与 `docs/history/agent-handoff-archive.md`）

### 16.1 杂质清理（已完成）

| 类别 | 内容 | 结果 |
| --- | --- | --- |
| 根目录误存文件 | `s.src)`、`x.disabled).length`、`innerWidth`、`test_localsystem.txt`、`auth-current-mobile.png`、`desk-current-desktop.png`、`胡桃QQ助手启动器.exe`（8.3MB）、`.env.before-ellie-bert-vits2-20260709-144250` | 已删除 |
| 缓存/构建残留 | `tmp/`（256MB/5058 文件）、`__pycache__`（41 目录/613 pyc）、`.playwright-cli`（12.5MB）、`data/pip_cache`（83MB）、`node_modules` 根符号链接（指向 C 盘缓存）、`.codex-docx-render`、`.pytest_cache`、`build/qq_launcher/`、`output/html`、`output/pdf`、`model_training/`（仅剩 3 个 pip wheel）、`integrations/`（仅剩 .pyc） | 已删除/清空 |
| `logs/` 精简 | 10.5 MB / 1182 文件 → 4.6 MB / 878 文件；`final-acceptance/`、`test-runs/`、`storage/` 完整保留，其余只保留 Markdown 报告与 `*-result.json`，新增 `logs/README.md` | 已完成 |

### 16.2 废案删除（已完成）

| 废案 | 删除内容 |
| --- | --- |
| QQ/微信 Bot | `integrations/` 整目录；`启动控制中心.bat` 中 Hermes 逻辑（改为 Core-only）；`docs/hermes-weixin-setup.md`、`docs/qq-napcat-login-guide.md`、`docs/HEADCORE_MULTI_CLIENT_ARCHITECTURE.md`、`docs/GPT_SOVITS_HUTAO_DEPLOYMENT.md`、`docs/HutaoChatCore-project-overview.md`；`docs/CAMERA_VISION_DEPLOYMENT.md` 的 QQ 视频窗口章节；`docs/CURRENT_FULLSTACK_ARCHITECTURE_AND_UI_GUIDE.md` 与 `docs/TECHNICAL_ARCHITECTURE_REFERENCE.md` 中 QQ/NapCat/Bert-VITS2/vision 表述。退休记录保留：`docs/archive/QQ_WEIXIN_BOT_RETIREMENT.md`、`RETIRED_QQ_WEIXIN_BOT_CONFIGURATION.md` |
| CosyVoice2 语音克隆训练 | `scripts/evaluate_hutao_flow_checkpoints.py`、`audit_hutao_voice_quality.py`、`audit_hutao_transcriptions.py`、`auto_label_hutao_voice.py`、`build_hutao_consensus_dataset.py`；`tests/test_hutao_flow_evaluation.py`、`test_hutao_consensus_dataset.py`、`test_hutao_voice_audit.py`、`test_hutao_transcription_audit.py`。保留：ASR 运营脚本与 `audit/export_persona_finetune_dataset.py`（仍被测试引用） |
| Bert-VITS2 TTS | `app/voice_chat/bert_vits2_tts.py`；`app/providers/tts.py` 的 `EllieTtsProvider` 与别名；`app/voice_chat/tts_service.py` 的 bert_vits2 分支/参数/ready 检查；相关测试改写为 gpt_sovits 版本 |
| 旧 Desk UI | `app/static/desk/`（7 个文件，含 `hutao-avatar.png`）；PWA 资源现由 `app/static/web/studio/` 提供 |
| Ollama 视觉 | `app/vision/` 整模块；`app/perception/adapters.py` 中 `VisionObservationAdapter` 与 `adapt_vision_result`；`tests/perception/test_adapters.py` 视觉测试；`docs/vision/` 目录。同日二次清理（审计定稿前）：`app/perception/normalization.py` 的 `merge_vision_outputs/_roughly_agree`、`app/perception/integration.py` 的 `normalize_vision_result`、`app/providers/contracts.py` 的 `VisionRequest`/`VisionProvider` 协议与 `ProviderCapability.VISION`，以及 `tests/perception/test_normalization.py`、`test_integration.py` 中 3 个对应测试；相关 fixture 由 VISION 改为 ASR |
| MySQL V1 后端 | `app/storage/repository_factory.py` 的 `STORAGE_BACKEND=mysql` 分支；`migrations/000-003`；`scripts/mysql_smoke.py`；`tests/test_storage_database.py` 中 V1 相关测试；`docs/database-schema.md`、`docs/mysql-operations.md`、根目录 `DATABASE_BACKEND_API_DESIGN.md`、`DATABASE_SYSTEM_DESIGN.md`。**保留 `app/storage/mysql_repository.py`：它是 Database V2、PostgreSQL、auth、knowledge、persona_management 的共享 SQL 传输基类**（`mysql_datetime` 等工具被广泛引用），不是独立可删的 V1 后端 |
| 旧架构手册与出版工具链 | `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md/.docx`；`scripts/build_architecture_publication.py`、`build_architecture_docx.py`、`print_architecture_pdf.js`、`capture_manual_diagrams.js`；`tests/test_architecture_publication.py`；`output/html`、`output/pdf` 旧发布物 |
| 人格系统旧设计文档 | `docs/persona/`（4 个文件）、`docs/persona-design.md`、`docs/persona-research.md`。保留 `docs/persona-training-plan.md`（被测试引用，且为当前"不建议直接训练"的立场文档） |
| 新闻渲染浏览器方案 | `app/core/config.py` 与 `.env.example` 的 `WORLD_RENDERED_FETCH_ENABLED`；`app/world/source_manifest.py` 的 `render_fallback_allowed`；`app/world/contracts.py` 的 `WorldSourceKind.RENDERED_BROWSER`；`app/world/runtime.py` 的 `rendered_fetch_enabled`；`app/control/config_schema.py` 对应配置项；`data/world/sources.json` 的 8 个字段；`docs/world/NEWS_SOURCE_STRATEGY.md` 相关段落 |

### 16.3 清理后的文档与流程调整

- `AGENTS.md`：5092 行/419KB 拆分为精简版（当前约 7KB：当前状态、关键约定、常用命令、当前对话交接）+ `docs/history/agent-handoff-archive.md`（410KB 只读归档）。
- `.gitignore`：移除 `integrations/` 与乱码 exe 两行；其余保留。
- 验证基线变化：清理前 842 passed 2 skipped → 清理后 **814 passed, 2 skipped**（差值 28 个为删除的 legacy 测试）；聚焦回归与 surface audit 断言同步修复。
- 未执行：任何 git commit；大件本地资产（`external/`、`data/models/`、`data/hutao_voice/`、`data/stickers/` 等）按要求保留不动；真实外部服务验收。

---

## 17. 附录 B：文件与规模统计（2026-08-14 审计当日）

| 范围 | 数量 |
| --- | --- |
| `app/` Python 文件 / 总行数 | 231 个 / 31,304 行 |
| `tests/` 文件 / 总行数 / 测试函数 | 131 个 / 17,683 行 / 749 个 |
| `scripts/` 文件 | 49 个（含 1 个 .mjs、1 个 .ps1） |
| `migrations/` SQL | v2 六份（585+73+104+81+23+58=924 行）+ postgres 一份（194 行） |
| `miniprogram/` 文件 | 21 个 |
| `frontend/site/src` | 5 个源文件 |
| `app/static/` | 6 个页面族（web/studio、web/site、auth、profile、credits、control、workbench、shared） |
| 本地大件资产（不入库） | `external/` 约 18.5GB、`data/models/` 约 8.4GB、`data/hutao_voice/` 约 416MB、`data/stickers/` 约 194MB |
| `.git`（含历史，仅本机） | 约 8.9GB（对象约 3GB + LFS 约 5.85GB） |
| `logs/`（精简后） | 4.6MB / 878 文件 |

## 18. 附录 C：本次运行记录

- 审计日期：2026-08-14（运行时刻约 21:41）。
- 环境：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`；工作目录 `D:\Programming-file\Graduation-Project\HutaoChatCore`。
- `python -m compileall -q app scripts tests` → exit 0（PASS）。
- `python -m pytest tests -q -p no:cacheprovider` → `814 passed, 2 skipped, 2 warnings in 17.24s`（复跑带 `-rs` 一次：17.99s，两个 skip 均为 `tests/database_control/test_mysql_integration.py` 的 `DATABASE_CONTROL_TEST_DATABASE is not configured`；两个 warning 为 `test_desk_streaming_browser.py` 触发的 websockets.legacy/uvicorn 弃用提示）。
- `node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js` → `5 passed, 0 failed（71.4ms）`。
- 本轮未发起任何真实模型、数据库、SMTP、API、摄像头或平台调用；未读取 `.env` 真实值；未修改除本报告以外的任何文件。

---


## 19. 附录 D：路由装饰器完整清单（123 个，按文件）

### `app/main.py`（33 个）

静态页与资源：`GET /`、`/credits`、`/credits/style.css`、`/credits/app.js`、`/credits/data.json`、`/desk`、`/ui/theme.css`、`/ui/liquid-theme.css`、`/ui/ambient.js`、`/ui/cursors/{cursor_name}.png`、`/desk/app.js`、`/desk/style.css`、`/desk/mobile.css`、`/desk/manifest.webmanifest`、`/desk/service-worker.js`、`/auth`、`/auth/app.js`、`/auth/style.css`、`/me`、`/me/app.js`、`/me/style.css`。
API：`GET /health`、`GET /api/v1/auth/status`、`GET /api/v1/voice/status`、`POST /api/v1/voice/synthesize`、`POST /api/v1/chat`、`POST /api/v1/chat/stream`、`POST /api/v1/audio/transcribe/file`、`POST /api/v1/audio/chat/prepare/file`、`POST /api/v1/audio/chat/file`、`GET /api/v1/memories`、`DELETE /api/v1/memories/{memory_id}`、`GET /api/v1/dialogue-context`。

### `app/control/routes.py`（20 个）

`/control`、`/control/app.js`、`/control/style.css`、`/control/docs/world-model`、`/control/assets/control-atmosphere.webp`、`/api/control/status`、`/api/control/operations/status`、`/api/control/operations/test-reports`、`/api/control/operations/errors`、`/api/control/operations/actor`、`/api/control/operations/audits`、`/api/control/config`（GET/POST）、`/api/control/logs`、`/api/control/logs/{log_id}`、`/api/control/services`、`/api/control/services/{service_id}/start`、`/api/control/services/{service_id}/stop`、`/api/control/tests`、`/api/control/tests/{test_id}/run`。

### `app/auth/`（8 个）

`POST /api/v1/auth/login`、`POST /api/v1/auth/mobile/login`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`、`POST /api/v1/auth/register`、`POST /api/v1/auth/verify-email`、`POST /api/v1/auth/password-reset/request`、`POST /api/v1/auth/password-reset/confirm`。

### `app/database_control/router.py`（9 个，前缀 `/api/control/database-v2`）

`GET /status`、`GET /admin`、`GET /profiles`、`GET /profiles/{profile_id}`、`POST /bootstrap-admin`、`POST /profiles/relationships`、`POST /platform-accounts/bind`、`POST /claims/{claim_id}/approve`、`POST /claims/{claim_id}/reject`。

### `app/camera/router.py`（8 个，前缀 `/api/control/camera`）

`POST /sessions`、`GET /sessions/{session_id}`、`POST /sessions/{session_id}/stop`、`POST /sessions/{session_id}/observations`、`POST /sessions/{session_id}/capture/start`、`GET /sessions/{session_id}/capture/status`、`GET /sessions/{session_id}/perception/status`、`POST /sessions/{session_id}/capture/stop`。

### `app/workbench/router.py`（13 个）

`GET /workbench`、`GET /workbench/app.js`、`GET /workbench/style.css`、`POST /api/workbench/login`、`POST /api/workbench/logout`、`GET /api/workbench/status`、`POST /api/workbench/camera/sessions`、`GET /api/workbench/camera/sessions/{session_id}`、`POST .../stop`、`POST .../capture/start`、`POST .../capture/stop`、`GET .../capture/status`、`GET .../perception/status`。

### `app/persona_management/`（25 个）

- `router.py`（6，前缀 `/api/control/personas`）：`GET /status`、`GET /{profile_id}/versions`、`GET /{profile_id}/releases`、`GET /versions/{version_id}`、`GET /bindings/all`、`GET /{profile_id}/runtime-projection`。
- `async_router.py`（14，前缀 `/api/control/personas-v2`）：上列 7 个只读 + `POST /drafts`、`POST /drafts/{draft_id}/validate`、`POST /drafts/{draft_id}/evaluations`、`POST /drafts/{draft_id}/approve`、`POST /versions/{version_id}/publish`、`POST /{profile_id}/rollback`、`PUT /bindings/{binding_id}`。
- `sandbox_router.py`（5，前缀 `/api/v1/sandbox/personas`）：`GET ""`、`POST ""`、`GET /{persona_id}`、`PUT /{persona_id}`、`DELETE /{persona_id}`。

### `app/knowledge/router.py`（4，前缀 `/api/control/knowledge`）

`GET /status`、`GET /candidates`、`POST /candidates/{candidate_id}/decision`、`POST /records/{record_id}/revoke`。

### `app/openai_compat.py`（2）与 `app/audio/websocket_routes.py`（1）

`GET /v1/models`、`POST /v1/chat/completions`；`WS /api/v1/audio/transcribe/stream`。

---

## 20. 附录 E：app/ 最大 40 个文件行数明细（其余文件见 4.3 包级汇总）

| 文件 | 行数 | 文件 | 行数 |
| --- | --- | --- | --- |
| `app/storage/v2_mysql_repository.py` | 2,307 | `app/services/chat_service.py` | 1,266 |
| `app/main.py` | 845 | `app/storage/mysql_repository.py` | 727 |
| `app/storage/chat_repository.py` | 680 | `app/world/context.py` | 678 |
| `app/persona_management/mysql_store.py` | 602 | `app/world/adapters/amap.py` | 545 |
| `app/world/adapters/news.py` | 480 | `app/knowledge/mysql_repository.py` | 456 |
| `app/core/config.py` | 455 | `app/database_control/mysql_adapter.py` | 452 |
| `app/world/brain.py` | 451 | `app/services/response_evaluator.py` | 441 |
| `app/auth/mysql_repository.py` | 414 | `app/providers/router.py` | 362 |
| `app/knowledge/semantic_memory.py` | 352 | `app/storage/v2_models.py` | 345 |
| `app/world/runtime.py` | 337 | `app/head/cognitive_facts.py` | 311 |
| `app/persona_management/async_router.py` | 313 | `app/persona_management/persistent_service.py` | 275 |
| `app/auth/postgres_repository.py` | 269 | `app/head/contracts.py` | 266 |
| `app/openai_compat.py` | 264 | `app/database_control/persona_persistence.py` | 254 |
| `app/control/routes.py` | 248 | `app/voice_chat/planner.py` | 248 |
| `app/world/news_digest.py` | 247 | `app/head/long_term_planning.py` | 246 |
| `app/persona_management/service.py` | 242 | `app/knowledge/service.py` | 239 |
| `app/workbench/router.py` | 233 | `app/camera/router.py` | 229 |
| `app/persona/persona_prompt_builder.py` | 225 | `app/persona_management/sandbox.py` | 220 |
| `app/camera/local_runtime.py` | 210 | `app/expression/planner.py` | 208 |
| `app/persona/memory_service.py` | 208 | `app/storage/v2_platform_command_service.py` | 204 |
| `app/head/planning.py` | 204 | `app/database_control/router.py` | 203 |

---


## 21. 附录 F：历史交接记录索引（`docs/history/agent-handoff-archive.md`，只读档案）

档案按时间倒序保存 2026-07-07 至 2026-08-03 的完整开发交接记录（每条含 Implementation/Validation 两节）。主要条目（索引，细节以档案原文为准）：

- 2026-07-21：当前架构与验收手册重建（730 passed 基线）。
- 2026-07-17（8 条）：高德地点/路线与后果规划、行政区划解析、世界工具决策与聊天集成、政策元数据与新闻摘要、新闻 API 与 RSS 运行时、高德参考对齐与新闻来源目录、全量离线验收恢复、HeadCore 世界意识基础。
- 2026-07-16（3 条）：独立 HTML/PDF 出版物、架构与运维文档重组、端到端完成开发与验收审计（WDAC 阻塞记录）。
- 2026-07-15（8 条）：微信多用户 pairing 管理、QQ 语音测试夹具修复、FunASR 与 Provider 运行时、控制可观察性、QQ FunASR 入站音频感知、记忆与人格只读集成、数据库控制加固、控制中心写授权等。
- 2026-07-14（13 条）：核心 API 统一通道事件、写授权、表达计划集成、QQ 视觉 S6 路由、QQ TTS 路由、可观察性 UI、S2+S3+S6 首次集成、QQ 表达计划集成、流式与修复路由、S8 只读集成、DeepSeek 路由集成、Database V2 写/读控制面、并行系统设计包、项目系统化审计、GPT-SoVITS 退役与运行验收。
- 2026-07-09：Ellie Bert-VITS2 本地语音修复（已随 Bert-VITS2 退役成为历史）。
- 2026-07-07：控制中心启动器集成 Hermes 微信（已随 QQ/微信 Bot 退役成为历史）等更早条目。

档案第 3 行注明："本文件是 2026-07-07 至 2026-08-03 期间的完整开发交接记录，2026-08 项目清理后归档为只读历史。"

## 22. 附录 G：世界来源清单全字段（`data/world/sources.json`，8 个候选，全部关闭）

| source_id | 名称 | kind | capabilities | enabled | legal_approved | automation_policy |
| --- | --- | --- | --- | --- | --- | --- |
| `gdelt-doc` | GDELT DOC API | api | news | false | false | api |
| `un-news-en-rss` | United Nations News RSS | rss | news, policy | false | false | feed |
| `who-news-en-rss` | WHO News RSS | rss | news, policy | false | false | feed |
| `gov-cn-policy` | China Government Policy Updates | http | policy | false | false | review_required |
| `stats-cn-releases` | National Bureau of Statistics Releases | http | news, finance, policy | false | false | review_required |
| `pboc-releases` | People's Bank of China Releases | http | finance, policy | false | false | robots_blocked |
| `csrc-releases` | CSRC Releases | http | finance, policy | false | false | review_required |
| `ndrc-releases` | NDRC Releases | http | news, policy | false | false | review_required |

每个条目还含 `entry_url/allowed_hosts/refresh_seconds/requires_api_key/discovery_only/terms_url/robots_url`。注册的运行时适配器只有 4 个：GDELT、官方 RSS、政府政策、和风天气（另有高德适配器独立注册）；清单中 4 个国内 review_required 页面与 1 个 robots_blocked 页面没有适配器（渲染浏览器方案已移除）。启用任一来源需同时满足 `WORLD_AWARENESS_ENABLED` + 来源 `enabled` + `legal_approved`/`WORLD_SOURCE_LEGAL_APPROVED_IDS` 三重门。

## 23. 附录 H：数据库迁移执行顺序

**MySQL Database V2**（`migrations/v2/`，顺序执行）：

1. `001_hutao_chat_core_schema.sql`（基础 27 表）→ 2. `002_knowledge_lifecycle.sql` → 3. `003_persona_management.sql` → 4. `004_public_web_auth.sql` → 5. `005_public_web_password_reset.sql`（必须在 004 后）→ 6. `006_semantic_memory_outbox.sql`。
- 执行器：`scripts/apply_database_v2_migrations.py`；Docker 形态：`docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml --profile database-v2 run --rm migrate-v2`。
- 启用前必须：隔离库演练 → `scripts/database_v2_readiness_check.py` → bootstrap 管理员 → 再开 `DATABASE_V2_ENABLED`（`deploy/README.md` 原文要求）。

**PostgreSQL Web 核心**（`migrations/postgres/`）：

1. `001_web_core.sql`（17 表）；执行器 `scripts/apply_postgres_web_migrations.py`；启用路径 `STORAGE_BACKEND=postgresql` + `PUBLIC_WEB_AUTH_ENABLED=true`（该路径下 `DATABASE_V2_ENABLED=false`）。

## 24. 附录 I：权威手册章节对照（`HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`）

手册 24 章与本报告的对应关系：`0 文档定位`→本报告 1.3；`1 当前结论`→本报告 14；`2 产品目标与边界`→本报告 2；`3 总体架构`→本报告 4.1；`4 项目目录与模块职责`→本报告 4/5；`5 客户端与界面`→本报告 10；`6 HeadCore 功能逻辑`→本报告 4.4/4.15；`7 端到端功能流程`→本报告 6；`8 API 边界`→本报告 7；`9 数据库设计`→本报告 9；`10 配置设计`→本报告 8；`11 功能状态矩阵`→本报告 1.4/14；`12–18 本地运行/MySQL 联调/服务器/上传/Docker/域名 HTTPS/邮箱/防滥用`→本报告 13/14；`19 资源预算`、`20 服务器资源与本地模型边界`→本报告 13.1；`21 分层验收清单 L0–L6`→本报告 12.4/14；`22 阻塞项与开发顺序 P0–P3`→本报告 15.6；`23 发布完成定义`、`24 文档维护规则`→本报告 15.3。

---


## 25. 附录 J：2026-08-14 清理前后文档对照

**已删除的 docs 文档**：`docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md/.docx`、`docs/hermes-weixin-setup.md`、`docs/qq-napcat-login-guide.md`、`docs/HEADCORE_MULTI_CLIENT_ARCHITECTURE.md`、`docs/GPT_SOVITS_HUTAO_DEPLOYMENT.md`、`docs/HutaoChatCore-project-overview.md`、`docs/database-schema.md`、`docs/mysql-operations.md`、`docs/persona-design.md`、`docs/persona-research.md`、`docs/persona/`（4 件）、`docs/vision/`（2 件）、根目录 `DATABASE_BACKEND_API_DESIGN.md`、`DATABASE_SYSTEM_DESIGN.md`、`docs/HUTAO_COSYVOICE2_TRAINING_HANDOFF_2026-07-20.md`（README 曾引用）、`docs/PROJECT_ACCEPTANCE_REPORT_2026-07-19.md`（移入 `docs/archive/`）。

**保留的 docs 文档**（审计当日 `docs/` 根 17 件 + 子目录）：权威手册（md+docx）、`HUTAOCHATCORE_TECHNICAL_REPORT.md`（本文件）、`WEB_PRODUCT_ROADMAP.md`、`WEB_REDESIGN_AND_PRODUCT_SPLIT_SPEC.md`、`CURRENT_FULLSTACK_ARCHITECTURE_AND_UI_GUIDE.md`、`TECHNICAL_ARCHITECTURE_REFERENCE.md`、`WORLD_MODEL_AND_PROJECT_CAPABILITIES.md`、`LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md`、`LOCAL_MODEL_INSTALLATION_MAP.md`、`CAMERA_VISION_DEPLOYMENT.md`、`auditory-system-design.md`、`auditory-system-acceptance-2026-06-28.md`、`memory-and-storage-design.md`、`persona-training-plan.md`、`POSTGRES_WEB_RUNTIME.md`、`PUBLIC_WEB_AUTH_AND_ABUSE_PREPARATION.md`；子目录 `archive/`（3 件退休/验收档案）、`history/`（交接档案）、`systems/`（S1–S8 九件）、`architecture/`（3 件）、`deployment/`（LOCAL_MODEL_LAYOUT）、`head/`（HEADCORE_COGNITIVE_ARCHITECTURE）、`testing/`（HeadCore 世界模型验收 2026-07-21）、`world/`（2 件设计文档）、`assets/`（UI 截图）。

## 26. 附录 K：.env.example 键分组计数（166 行模板，审计当日）

| 分组 | 键数 | 组内键 |
| --- | --- | --- |
| Runtime/HeadCore | 4 | `ENVIRONMENT`、`STORAGE_BACKEND`、`JSONL_STORAGE_DIR`、`PERSONA_PROFILE` |
| Chat model | 11 | `MODEL_PROVIDER/MODEL_NAME/MODEL_BASE_URL/DEEPSEEK_API_KEY/API_TEMPERATURE/API_TIMEOUT_SECONDS/VOICE_CHAT_REPLY_TIMEOUT_SECONDS/TEXT_PROVIDER_ORDER/TEXT_PROVIDER_RETRIES/TEXT_PROVIDER_CIRCUIT_FAILURE_THRESHOLD/TEXT_PROVIDER_CIRCUIT_RECOVERY_SECONDS` |
| MySQL/公开账号 | 6 | `MYSQL_HOST/MYSQL_PORT/MYSQL_DATABASE/MYSQL_USER/MYSQL_PASSWORD/DATABASE_V2_ENABLED` |
| Semantic memory | 14 | `SEMANTIC_MEMORY_ENABLED/QDRANT_URL/QDRANT_API_KEY/QDRANT_COLLECTION/EMBEDDING_PROVIDER/EMBEDDING_MODEL_PATH/EMBEDDING_DEVICE/EMBEDDING_MAX_LENGTH/EMBEDDING_BASE_URL/EMBEDDING_API_KEY/EMBEDDING_MODEL/EMBEDDING_TIMEOUT_SECONDS/RETRIEVAL_LIMIT/MIN_SCORE` |
| PostgreSQL Web | 5 | `POSTGRES_HOST/PORT/DATABASE/USER/PASSWORD` |
| 认证 Cookie | 3 | `PUBLIC_WEB_AUTH_ENABLED`、`SESSION_COOKIE_SECURE`、`PUBLIC_WEB_SESSION_LIFETIME_SECONDS` |
| 邮件 | 7 | `EMAIL_DELIVERY_ENABLED`、`SMTP_HOST/PORT/USERNAME/PASSWORD/FROM_ADDRESS/STARTTLS` |
| 网页 TTS | 7 | `PUBLIC_WEB_TTS_ENABLED/PROVIDER/BASE_URL/OUTPUT_DIR/REPLY_TTL_SECONDS/MIN_INTERVAL_SECONDS/MAX_REPLY_CHARS` |
| 音频输入 | 7 | `ASR_FILE_PRESETS`、`ASR_REPAIR_PRESETS`、`AUDIO_EMOTION_ENABLED`、`AUDIO_EMOTION_MODEL`、`ASR_PROVIDER_TIMEOUT_SECONDS/CIRCUIT_FAILURE_THRESHOLD/CIRCUIT_RECOVERY_SECONDS` |
| 世界工具 | 8 | `WORLD_AWARENESS_ENABLED/FETCH_TIMEOUT_SECONDS/FETCH_MAX_BYTES/CACHE_MAX_ENTRIES/MAX_CACHE_TTL_SECONDS/OFFICIAL_SOURCE_MANIFEST/SOURCE_ENABLED_IDS/SOURCE_LEGAL_APPROVED_IDS` |
| 高德 | 9 | `AMAP_WEB_SERVICE_API_KEY/WEB_SERVICE_BASE_URL/ALLOWED_HOSTS/SOURCE_LEGAL_APPROVED/IP_CACHE_TTL_SECONDS/WEATHER_CACHE_TTL_SECONDS/DISTRICT_CACHE_TTL_SECONDS/PLACE_CACHE_TTL_SECONDS/ROUTE_CACHE_TTL_SECONDS` |
| 和风天气 | 5 | `QWEATHER_API_KEY/API_BASE_URL/ALLOWED_HOSTS/SOURCE_LEGAL_APPROVED/WEATHER_CACHE_TTL_SECONDS` |
| 摄像头 | 12 | `CAMERA_PERCEPTION_ENABLED/LOCAL_CAPTURE_ENABLED/SESSION_MAX_SECONDS/OBSERVATION_TTL_SECONDS/RAW_FRAME_RETENTION_SECONDS/FACE_IDENTIFICATION_ENABLED/CLOUD_UPLOAD_ENABLED/CAPTURE_INTERVAL_SECONDS/TEMPORAL_CONFIRMATION_COUNT/TEMPORAL_WINDOW_SECONDS/MEDIAPIPE_ENABLED/YOLO_MODEL_PATH` |
| 工作台 | 3 | `VISUAL_WORKBENCH_ENABLED/ADMIN_SECRET/SESSION_LIFETIME_SECONDS` |

合计 101 个模板键；所有高风险组（TTS/摄像头/工作台/认证/邮件/世界/语义记忆）默认关闭或空值，模板注释逐组写明启用前置条件。

---


## 27. 附录 L：关键常量与默认值速查

- `DEFAULT_PERSONA_PROFILE_ID` = `"hutao_v1"`（`app/persona/profile_registry.py`）；别名 `hutao/hu_tao/genshin_hutao`；禁用身份标记 `("小何",)`。
- `BASE_SYSTEM_PROMPT` 固定条款（`chat_service.py`）：中文私聊回复；唯一内置 Self 是 hutao_v1；模式控制活泼/温度/严谨/节奏/长度；专业任务优先正确与完整；不在一场内混合人格；用中文回复。
- `SECRET_PATTERN` = `sk-[A-Za-z0-9]{20,}` → `<REDACTED_API_KEY>`（`app/core/security.py`）。
- `RoutingPolicy` 校验范围：timeout ∈ (0,300]、retries ∈ [0,5]、熔断阈值 ∈ (0,100]、恢复 ∈ (0,3600]。
- Provider 敏感键集合：`authorization/api_key/apikey/password/secret/token`（`providers/router.py` `_SENSITIVE_KEYS`）。
- `AuthRateLimitService` 默认：5 次/10 分钟窗口、封禁 30 分钟、主题 SHA-256 哈希。
- `WorldContextAssembler` 默认：`max_items=8`、`max_characters=3500`；天气冲突阈值：标签不同或温差 ≥5℃。
- `CameraTemporalState` 默认：`confirmation_count=2`、`window_seconds=8`。
- `WebVoiceReplyStore`：`reply_ttl_seconds=300`、`min_interval_seconds=8`（默认值来自 Settings）。
- `HeadPlanStep`：`max_attempts=2`；`HeadLongTermPlan`：`max_replans=2`。
- `JsonlChatRepository` 默认目录：`PROJECT_ROOT/logs/storage`（`DEFAULT_STORAGE_DIR`）。
- 会话 Cookie 名：`hutao_session`（网页）、`hutao_workbench_session`/`hutao_workbench_csrf`（工作台）；CSRF 头：`X-CSRF-Token`。
- V2 命令前缀：`("胡桃",)`（`build_database_v2_platform_command_service` 默认）。
- 受管服务：`hutao_core`、`gpt_sovits`；受管测试：`control_center`、`api_voice`、`full_pytest`。

---


## 28. 附录 M：依赖升级路径与版本策略

- 全部运行时依赖在 `requirements.txt` 锁定精确版本（`==`），升级必须走：聚焦测试 → 全量 pytest → 小程序测试 → 浏览器抽查，并在 `AGENTS.md` 记录。
- 已知升级候选：`websockets`（uvicorn 引用的 `legacy` 模块弃用，等待 uvicorn 上游适配新接口）；`fastapi/uvicorn/pydantic` 随安全公告升级；`pytest` 9.0.3 保持。
- 重依赖拆分方向（15.4）：把 `funasr/torchaudio/transformers/sentence-transformers` 移入可选组（`requirements-audio.txt`/`requirements-semantic.txt`），纯文字部署只装 Core 组；`requirements-vision.txt` 已按此模式独立。
- 模型升级纪律：任何嵌入模型更换必须新建 Qdrant 集合或重建索引（维度不混用）；ASR 模型目录缺失的联网回退风险见 13.1；语音音色权重必须有验收记录才进生产目录（`LOCAL_MODEL_LAYOUT.md`）。

## 29. 附录 N：术语表

| 术语 | 含义 |
| --- | --- |
| HeadCore | 项目唯一认知主体边界：场景、Self、关系、记忆、对话状态、世界证据、Provider 路由与表达规划的总称（`app/head/` + 配套模块） |
| `hutao_v1` | 唯一内置运行时人格（胡桃），注册表唯一条目 |
| HeadState | 每轮对话构建的认知状态聚合（`app/head/state.py`） |
| CognitiveFact | 带来源与状态的认知事实（observation/belief/hypothesis；active/conflicted/stale/revoked/superseded） |
| HeadWorldModel | 实体/事件/关系/因果假设的显式世界模型（非学习式物理模型） |
| WorldEvidence | 世界工具（高德/新闻/政策）产出的受门控证据，进入 prompt 前经冲突检测 |
| reply_id | 网页 TTS 的服务端短时票据：只允许合成服务端本次登记的回复文本 |
| fail-closed | 默认关闭、条件不满足即拒绝的开关设计（TTS/摄像头/世界来源/账号注册） |
| S1–S8 | 并行系统化拆分的八个子系统（数据库控制面/平台事件/感知/记忆画像/人格管理/Provider 路由/表达计划/控制可观察性） |
| Provider | 可替换能力实现（文本/视觉/ASR/TTS），经 `ProviderRouter` 统一路由 |
| 契约优先 | 先定义 typed contract 与测试、再实现与集成的开发顺序（`docs/systems/README.md`） |
| 盲评（blind review） | 把规划样本匿名化打包供人工评审的评估机制（`app/head/blind_review.py`） |
| 校准（calibration） | 用配对偏好与多评审者一致性（Fleiss' kappa）校准 Head 决策评分 |
| JSONL 后端 | 默认零依赖存储：每记录一行 JSON 追加写 |
| Database V2 | MySQL 上的身份/关系/命令/聊天仓储（`migrations/v2/` 001–006） |
| PostgreSQL Web 核心 | 公开网页账号与聊天存储的 PostgreSQL 路径（`migrations/postgres/`） |
| semantic outbox | 语义记忆的 MySQL→Qdrant 派生索引同步队列（可重建） |
| 控制面（control plane） | 只面向管理员的高权限读/写接口族（`/api/control/*`） |
| 工作台（workbench） | 本机视觉工作台：独立口令 + 短时会话 + CSRF（默认关闭） |
| code-only 发布 | 用 `git archive` 从清理后的提交导出无模型历史的快照再推新仓库 |

---


## 30. 附录 O：审计复现清单（本次审计实际操作记录）

1. `python -m compileall -q app scripts tests`（exit 0）——全量语法门。
2. `python -m pytest tests -q -p no:cacheprovider`（814 passed, 2 skipped, 2 warnings, 17.74s）——全量行为门。
3. `python -m pytest tests -q -p no:cacheprovider -rs`（17.99s）——确认两个 skip 均为 `tests/database_control/test_mysql_integration.py` 的 `DATABASE_CONTROL_TEST_DATABASE is not configured`。
4. `node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js`（5 passed, 71.4ms）——小程序客户端门。
5. 静态盘点：`app/` 231 文件行数逐文件统计；`tests/` 131 文件与 749 测试函数统计；`migrations/` 全部建表语句抽取；`app/main.py` 与全部子路由的 123 个装饰器清单；`.env.example` 166 行逐键对照；`deploy/`、`miniprogram/`、`frontend/site/`、`data/world/sources.json` 全文核对。
6. 交叉验证文档：`README.md`、`AGENTS.md`（精简版）、权威手册 TOC、`docs/systems/README.md`、`docs/deployment/LOCAL_MODEL_LAYOUT.md`、`docs/LOCAL_MODEL_INSTALLATION_MAP.md`、`docs/POSTGRES_WEB_RUNTIME.md`、`docs/history/agent-handoff-archive.md`、`logs/project-cleanup/2026-08-14/project-cleanup-report.md`。
7. 约束遵守：未修改除本报告以外的任何文件；未执行 git 命令写操作；未读取 `.env` 真实值；未调用任何真实外部服务。

复现方式：在同一工作区执行上述第 1–4 条命令即可得到相同数字；第 5–7 条的静态清单可由第 4、7、8、9、12 章与本附录重建。

---

*报告结束。本文件是 `docs/HUTAOCHATCORE_TECHNICAL_REPORT.md` 的 2.0 版全量重写；与根目录权威手册不一致时，以 `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md` 与运行时代码为准。*