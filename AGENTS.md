# HutaoChatCore Agent Handoff

## 当前状态（2026-08-14 项目清理后）

- 项目主线：HeadCore（唯一认知主体）为核心、唯一内置人格 `hutao_v1`（胡桃）的多模态角色陪伴后端。当前公开形态是 FastAPI Core HTTP + Web Desk PWA（`app/static/web/studio`）+ OpenAI-Compatible 接口 + 文件语音识别 + 原生微信小程序（`miniprogram/`）。
- 已退役并从源码移除：QQ/微信 Bot（NapCat/OneBot/Hermes）、CosyVoice2 语音克隆训练、Bert-VITS2 TTS provider、Ollama 视觉（`app/vision`）、MySQL V1 后端入口、旧 Desk UI（`app/static/desk`）、旧架构手册与旧出版工具链、新闻渲染浏览器方案。完整清理清单与理由见 `logs/project-cleanup/2026-08-14/project-cleanup-report.md`。
- `app/storage/mysql_repository.py` 保留：它是 Database V2、PostgreSQL、auth、knowledge、persona_management 的共享 SQL 传输基类，不是独立可删除的"V1 后端"。
- 实测基线（2026-08-14，`python -m pytest tests -q -p no:cacheprovider`）：`814 passed, 2 skipped`。
- Git 现状：本地仓库含旧历史 2 个提交（曾跟踪模型权重，.git 约 8.9 GB，含 LFS 5.85 GB）+ 清理后的 3 个新提交；旧远程 origin/upstream（原指向 https://github.com/DyQcml12/HutaoChatCore.git）已移除。上传 GitHub 使用导出的 code-only 新仓库（`..\HutaoChatCore-code-only`，约 8MB）推送；旧仓库只保留在本机，绝不 push。
- 文档唯一编辑源：根目录 `HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md`（其 `docs/` 副本与根目录同步）。技术审计报告：`docs/HUTAOCHATCORE_TECHNICAL_REPORT.md`。产品路线：`docs/WEB_PRODUCT_ROADMAP.md`。
- 历史开发交接记录已归档到 `docs/history/agent-handoff-archive.md`（只读），不再追加；新交接只写在本文档"当前对话交接"一节。
## 历史交接索引

完整开发日志（170 条交接记录，2026-07-07 至 2026-08-10）已归档到 docs/history/agent-handoff-archive.md（只读，410KB）。以下为全部条目索引：

<details>
<summary>展开查看全部 170 条历史交接记录</summary>

- **2026-07-21 Current Architecture And Acceptance Manual**
- **2026-07-17 Amap Place, Route And Consequence Planning**
- **2026-07-17 Amap District Resolution For Natural Weather Requests**
- **2026-07-17 Brain World Tool Decision And Chat Context Integration**
- **2026-07-17 Government Policy Metadata And Shared News Digest**
- **2026-07-17 News API And Official RSS Runtime Foundation**
- **2026-07-17 Amap Reference Alignment And News Source Catalog**
- **2026-07-17 Full Offline Acceptance Recovery**
- **2026-07-17 HeadCore World Awareness Foundation**
- **2026-07-16 Standalone Architecture HTML And PDF Publication**
- **2026-07-16 Architecture And Operations Documentation Reorganization**
- **2026-07-16 End-to-End Completion Development And Acceptance Audit**
- **2026-07-15 Weixin Multi-User Pairing Management**
- **2026-07-15 QQ Voice Test Fixture Repair**
- **2026-07-15 FunASR And Provider Runtime Completion**
- **2026-07-15 Control Observability Completion**
- **2026-07-15 QQ FunASR Inbound Audio Perception**
- **2026-07-15 Memory And Persona Read-Only Integration**
- **2026-07-15 Database Control Hardening And Acceptance Tooling**
- **2026-07-14 Core API Unified Channel Event Integration**
- **2026-07-14 Control Center Write Authorization**
- **2026-07-14 Core API Expression Planning Integration**
- **2026-07-14 QQ Vision Providers Routed Through S6**
- **2026-07-14 QQ TTS Provider Routing Integration**
- **2026-07-14 Control Observability UI Integration**
- **2026-07-14 S2 + S3 + S6 QQ First Runtime Integration**
- **2026-07-14 QQ Expression Planning Runtime Integration**
- **2026-07-14 Streaming And Repair Provider Routing Integration**
- **2026-07-14 Control Observability Read-Only Integration**
- **2026-07-14 DeepSeek Provider Routing Integration**
- **2026-07-14 Database V2 Write Control Plane Integration**
- **2026-07-14 Database V2 Read Control Plane Integration**
- **2026-07-14 Parallel System Design Work Packages**
- **2026-07-14 Project-Wide Test And Systemization Documentation Audit**
- **2026-07-14 GPT-SoVITS Retirement And Runtime Acceptance**
- **2026-07-14 Generic Persona System Redesign V3 And Legacy Hu Tao Removal**
- **2026-07-09 Ellie Bert-VITS2 Local Voice Fix**
- **2026-07-07 Control Center Launcher Integrates Hermes Weixin**
- **2026-07-07 Weixin Voice And Call Capability Boundary**
- **2026-07-07 Weixin Rescan Switch And Profile Boundary**
- **2026-07-07 Nameless Persona Core And Weixin Capability Gap**
- **2026-07-07 Weixin Pairing Onboarding Console**
- **2026-07-07 Standalone Weixin Bot Workspace**
- **2026-07-07 Xiaohe runtime audit and cleanup**
- **2026-07-07 Hermes Weixin And QQ Voice Repair**
- **2026-07-07 Bot-Only Control Console Redesign**
- **2026-07-07 Control Center Bot Console UI Redesign**
- **2026-07-07 Control Center Mojibake And Weixin Panel Fix**
- **2026-07-06 Web Control Center v1**
- **2026-07-06 GPT-SoVITS Runtime TTS Removal**
- **2026-07-06 Xiaohe Environment Template Refresh**
- **2026-07-06 Environment Unused Key Cleanup**
- **2026-07-06 Environment Config Sync**
- **2026-07-06 Volcengine Config Cleanup**
- **2026-07-06 Volcengine Doubao TTS 1.0 Defaults**
- **2026-07-06 Volcengine TTS API-Key Mode**
- **2026-07-06 Xiaohe/Ellie Bert-VITS2 Voice Provider And Volcengine TTS Config**
- **2026-07-06 QQ Relationship Simplification And Xiaohe Persona Profile**
- **2026-07-06 Hermes Weixin OpenAI-Compatible Endpoint**
- **2026-07-06 Final Project Acceptance Runner**
- **2026-07-06 QQ Attachment Context And Owner History Visibility**
- **2026-07-06 QQ Vision Intake v1**
- **2026-07-06 QQ Vision Provider v1**
- **2026-07-06 QQ OCR Cache And RapidOCR Install**
- **2026-07-06 QQ Local Open-Source VLM Provider v1**
- **2026-07-06 QQ Vision Naturalization Fix**
- **2026-07-06 Structured Vision Observation Layer**
- **2026-07-06 QQ Vision Image Quality Gate**
- **2026-07-03 Persona Live Continuity Stress v1**
- **2026-07-03 Persona Continuity Eval With Research Basis**
- **2026-07-03 Persona Social State v3**
- **2026-07-03 Persona Live Adversarial Smoke And Gate Fixes**
- **2026-07-03 Persona State And Context Layer**
- **2026-07-03 Persona Redesign v2 Foundation**
- **2026-07-02 QQ Reply Self-Harm And Insult Guard**
- **2026-07-02 Relative Claim And Reply Safety Fix**
- **2026-07-02 Stranger Sensitive Permission Guard**
- **2026-07-02 Owner Permission Query Fix**
- **2026-07-02 QQ Relationship Approval v1**
- **2026-07-02 Project Smoke After Expression Algorithms**
- **2026-07-02 QQ Semantic Voice Trigger v1**
- **2026-07-02 QQ Semantic Sticker Trigger v2**
- **2026-07-02 Normal Chat Response Length Control v1**
- **2026-07-02 Eval Scripts Test Split**
- **2026-07-02 Storage Database Test Split**
- **2026-07-02 Project Run Validation**
- **2026-07-02 Response Evaluator Test Split**
- **2026-07-02 Persona Memory Test Split**
- **2026-07-02 Chat Service Test Split**
- **2026-07-02 API Test Split**
- **2026-07-02 Audio Pipeline Test Split**
- **2026-07-02 Voice Test Split**
- **2026-07-02 QQ Test Split**
- **2026-07-02 Dialogue Test Split**
- **2026-07-02 Dialogue Policy Phase 1**
- **2026-07-02 Architecture Governance And Normal Chat Optimization**
- **2026-06-29 ASR emotion recognition**
- **2026-06-29 ASR emotion web sample effect test**
- **2026-06-29 emotion2vec+ deployment**
- **2026-06-29 GPT-SoVITS TTS preparation**
- **2026-06-29 Hu Tao voice auto-label pass**
- **2026-06-29 GPT-SoVITS training preparation update**
- **2026-06-29 GPT-SoVITS official install interrupted**
- **2026-06-29 GPT-SoVITS v2Pro modified build training test**
- **2026-06-29 胡桃 GPT-SoVITS v2Pro balanced 训练完成与合成测试**
- **2026-06-29 用户试听反馈与二次诊断**
- **2026-06-29 试听反馈：电流声与韵律不足**
- **2026-06-29 后续规划：聊天模型与唱歌模型分离**
- **2026-06-29 聊天模块真人感方案**
- **2026-06-29 真人感聊天语音流水线原型**
- **2026-06-30 真人感聊天语音流水线：克制情绪改版**
- **2026-06-30 试听反馈：口齿不清与拼接问题**
- **2026-06-30 试听反馈：电流声仍在与部分音频低频过重**
- **2026-06-30 试听反馈：后处理压不住电流感，转向训练与参考音频问题**
- **2026-06-30 clean_v2 数据清洗与重训决策**
- **2026-06-30 clean_v2 GPT-SoVITS 重新训练完成与聊天语音测试**
- **2026-06-30 clean_v2 试听反馈与轻量参数优化**
- **2026-06-30 casual_chat ???????????**
- **2026-06-30 casual_chat ?????????????**
- **2026-06-30 GPT-SoVITS clean_v3 胡桃聊天模型训练与有效测试**
- **2026-06-30 情绪增强小版本对照测试**
- **2026-06-30 胡桃听觉系统与说话系统端到端整合**
- **2026-06-30 听觉+说话联调音质问题定位与修复**
- **2026-06-30 项目主链路逻辑修复：音频聊天输入与实时 TTS 文本**
- **2026-07-01 QQ 机器人桥接部署：NapCatQQ + NoneBot2 + OneBot v11**
- **2026-07-01 QQ 接入继续开发：预检、NapCat 下载、本地 Smoke**
- **2026-07-01 QQ 接入一键启动脚本**
- **2026-07-01 QQ 一键启动提示修复：区分 WebUI 和 WebSocket 地址**
- **2026-07-01 NapCat WebUI Token 与 OneBot WebSocket 配置说明**
- **2026-07-01 QQ 私聊免唤醒词与上下文实测**
- **2026-07-02 身份关系系统第一版：主人画像专属与多人聊天隔离**
- **2026-07-02 QQ 语音回复第一版与表情包目录占位**
- **2026-07-02 QQ 一键启动合并语音 API**
- **2026-07-02 QQ 语音回复逻辑修正：去除动作提示、完整合成、避免重复文字**
- **2026-07-02 QQ 撤回取消回复机制**
- **2026-07-02 GPT-SoVITS 开头异响缓解：裁剪淡入样本**
- **2026-07-02 QQ 语音最新 e15 模型接入与 smoke 完善**
- **2026-07-02 QQ 表情包发送第一版：本地索引与明确触发**
- **2026-07-02 QQ 表达增强：自动表情包、情绪池与短回复**
- **2026-07-02 QQ 表情包意图驱动策略**
- **2026-07-02 QQ 启动器 EXE 打包**
- **2026-07-06 Launcher Weixin Integration And Social Logs**
- **2026-07-06 Database V2 Identity/Profile Design**
- **2026-07-06 Database V2 Schema And Repository Boundary**
- **2026-07-06 Database V2 MySQL Repository Core**
- **2026-07-06 Database V2 Relationship Service**
- **2026-07-06 Database V2 Admin Command Policy**
- **2026-07-06 Database V2 Admin Command Executor**
- **2026-07-06 Database V2 Admin Query And Claim Review**
- **2026-07-07 Database V2 Platform Command Service**
- **2026-07-07 Database V2 Runtime Integration**
- **2026-07-07 Database V2 Normal Chat Storage Cutover**
- **2026-07-07 Database V2 JSONL Migration Tooling**
- **2026-07-07 Database V2 Readiness And Completion Criteria**
- **2026-07-07 Database V2 Smoke Test Tooling**
- **2026-07-17 Platform Persona Routing: QQ Hu Tao, Weixin Xiaohe**
- **2026-07-17 Control Center Redesign And Validation**
- **2026-07-17 Persistent NapCat WebUI Token**
- **2026-07-18 NapCat Login And Control Authorization Fix**
- **2026-07-18 CosyVoice2 QQ Runtime And Platform World Policy**
- **2026-07-18 Fantasy Operations Control Center Redesign**
- **2026-07-18 Control Center Multi-Page Navigation**
- **2026-07-18 World Tool Recovery, Live Logs, And Weixin Access Boundary**
- **2026-07-19 QQ 语音触发、TTS 启动依赖与 OCR 安全降级**
- **2026-07-19 QQ 全好友私聊与唯一管理员关系网**
- **2026-07-19 CosyVoice2 可懂度修复与内容验收**
- **2026-07-19 CosyVoice2 生产 checkpoint 回退**
- **2026-07-20 胡桃 CosyVoice2 数据重审与 150 Epoch 正式训练**
- **2026-07-25 Current Development Handoff: Service Desk, Vision Boundary, World APIs**
- **2026-08-10 Technical Architecture And GitHub Publication Audit**

</details>

## 关键约定

- 只使用唯一 Python 环境 `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`，不要创建或切换其他虚拟环境。
- `.env`、密钥、Token、账号一律不写入代码、文档、日志或 Git；模板只维护 `.env.example`。
- `data/models/`、`external/`、`model_training/`、`data/` 下的模型与训练资产是本地部署资产，不提交 Git、不放 LFS。仓库只上传框架与代码，模型按 README 的本地模型清单自行下载。
- 不进行未经确认的大范围重构；保持 diff 小而可审。
- 开发任何模块前先给出完整实现计划，等用户确认；完成后跑聚焦测试并在 `logs/...` 写 Markdown 报告。
- 每一步开发都必须同步记录到本文档与 `README.md`。
- 人格、记忆、对话、情感、智能体、多模态等模块开发前，先调研论文与成熟开源项目，并把来源与工程映射写进模块报告。
- C 盘/系统级变更（安装、写入、策略）是红线，必须先获得用户明确批准。
- 社交平台接入优先官方或低风险接口；不使用 Hook/注入方案，除非用户明确批准并确认风险。
- 关系、权限、安全与隐私行为必须尽量由本地代码实现，不能只靠 Prompt。
- 任何可能诱导自杀、自伤或死亡的输出必须在发送前拦截或替换。

## 常用命令

```powershell
cd D:\Programming-file\Graduation-Project\HutaoChatCore
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m compileall -q app scripts tests
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests -q -p no:cacheprovider
node --test miniprogram/tests/api-client.test.js miniprogram/tests/session.test.js
cmd /c "启动控制中心.bat --check-only"
```

注意：不要在仓库根目录裸跑 `pytest`，它会收集 `external/GPT-SoVITS` 自带第三方测试。

## 当前对话交接

### 2026-08-14 项目清理与上传前整理

- 用户要求：上传仓库只保留项目框架与代码；模型只写下载清单；删除杂质与废案；精简 logs；重写 README（中英双语）；技术报告更详细；优化 AGENTS.md。
- 执行内容：
  - 删除根目录误存文件（浏览器 devtools 误存、验收截图、旧 .env 备份、QQ 启动器 exe 等）、缓存（tmp/、__pycache__、.playwright-cli、pip_cache、node_modules 链接等）。
  - 删除 QQ/微信 Bot 残留：`integrations/`（仅剩 .pyc）、启动器 bat 中的 Hermes 逻辑（改为 Core-only）、`build/qq_launcher/`、相关文档（`docs/hermes-weixin-setup.md`、`docs/qq-napcat-login-guide.md`、`docs/HEADCORE_MULTI_CLIENT_ARCHITECTURE.md`、`docs/GPT_SOVITS_HUTAO_DEPLOYMENT.md`、`docs/HutaoChatCore-project-overview.md` 等）；QQ/微信退休记录保留在 `docs/archive/`。
  - 删除 CosyVoice2 语音克隆训练工具与 legacy 测试：`scripts/evaluate_hutao_flow_checkpoints.py`、`audit_hutao_voice_quality.py`、`audit_hutao_transcriptions.py`、`auto_label_hutao_voice.py`、`build_hutao_consensus_dataset.py` 与 4 个 `test_hutao_*` 测试。
  - 删除 Bert-VITS2 provider：`app/voice_chat/bert_vits2_tts.py`、`EllieTtsProvider` 与全部 bert_vits2 分支/别名/测试；TTS 只剩 gpt_sovits 一条路由。
  - 删除旧 Desk UI（`app/static/desk/`）与 `app/vision/`（含 `VisionObservationAdapter`/`adapt_vision_result` 与对应测试）；摄像头工作台（`app/camera` + `app/workbench`）保留。二次清理又移除 `app/perception` 的 `normalize_vision_result`/`merge_vision_outputs` 与 `app/providers` 的 `VisionRequest`/`VisionProvider`/`ProviderCapability.VISION` 及 3 个对应测试。
  - 移除 MySQL V1 后端入口：`STORAGE_BACKEND=mysql` 工厂分支、`migrations/000-003`、`scripts/mysql_smoke.py` 与相关测试/文档；`mysql_repository.py` 保留为 V2/PostgreSQL 共享基类。
  - 删除旧架构手册（`docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.*`）、旧手册出版工具链（`scripts/build_architecture_publication.py`、`build_architecture_docx.py`、`print_architecture_pdf.js`、`capture_manual_diagrams.js` 与 `tests/test_architecture_publication.py`）、`output/html` 与 `output/pdf` 旧产物、人格系统旧设计文档（`docs/persona/`、`docs/persona-design.md`、`docs/persona-research.md`）。
  - 移除新闻渲染浏览器方案：`WORLD_RENDERED_FETCH_ENABLED`、`render_fallback_allowed`、`WorldSourceKind.RENDERED_BROWSER` 及 `docs/world/NEWS_SOURCE_STRATEGY.md` 中相关表述。
  - 精简 `logs/`：10.5 MB/1182 文件 -> 4.5 MB/874 文件（保留报告与结果 JSON，删原始日志；`final-acceptance`、`test-runs`、`storage` 完整保留）。
  - 优化文档：AGENTS.md 拆分为本精简版 + `docs/history/agent-handoff-archive.md`；README.md 重写为中英双语；`docs/HUTAOCHATCORE_TECHNICAL_REPORT.md` 重写为更详细版本；权威手册中的过期引用（app/vision、static/desk、STORAGE_BACKEND=mysql、931 passed 等）已修正。AGENTS.md 增加了"历史交接索引"（170 条，折叠块）。
  - GitHub 上传准备：移除旧远程 origin/upstream（原 DyQcml12/HutaoChatCore.git）；本地提交 3 个清理提交；导出 code-only 仓库到 `..\HutaoChatCore-code-only` 并完成初始化提交；导出仓库在干净环境实测 `810 passed, 6 skipped` 全绿，服务启动冒烟测试全部 200。
  - 测试环境守卫：desk/workbench 浏览器测试在无 Playwright 时自动跳过；modelscope 路径与 ASR 样本测试在资产缺失时自动跳过；voice_chat gpt_sovits 用例改为 monkeypatch 参考库；`planner.load_reference_library` 在注释文件缺失时抛出带安装指引的错误。
- 验证：`compileall` PASS；全量 `814 passed, 2 skipped`；控制中心页面测试、部署文件测试、来源清单测试全部通过。
- 未执行：未向 GitHub 实际 push（等用户提供/确认目标仓库后按 README 流程执行）；未删除任何大件本地资产（`external/`、`data/models/`、`data/hutao_voice/`、`data/stickers/` 等按用户要求保留不动）；未执行真实外部服务验收。
