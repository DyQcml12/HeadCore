# HutaoChatCore Agent Handoff

## 当前状态（2026-08-14 项目清理后）

- 项目主线：HeadCore（唯一认知主体）为核心、唯一内置人格 `hutao_v1`（胡桃）的多模态角色陪伴后端。当前公开形态是 FastAPI Core HTTP + Web Desk PWA（`app/static/web/studio`）+ OpenAI-Compatible 接口 + 文件语音识别 + 原生微信小程序（`miniprogram/`）。
- 已退役并从源码移除：QQ/微信 Bot（NapCat/OneBot/Hermes）、CosyVoice2 语音克隆训练、Bert-VITS2 TTS provider、Ollama 视觉（`app/vision`）、MySQL V1 后端入口、旧 Desk UI（`app/static/desk`）、旧架构手册与旧出版工具链、新闻渲染浏览器方案。完整清理清单与理由见 `logs/project-cleanup/2026-08-14/project-cleanup-report.md`。
- `app/storage/mysql_repository.py` 保留：它是 Database V2、PostgreSQL、auth、knowledge、persona_management 的共享 SQL 传输基类，不是独立可删除的"V1 后端"。
- 实测基线（2026-08-17，`python -m pytest tests -q -p no:cacheprovider`）：`911 passed, 2 skipped`（在 902 基础上新增 GSV 守护 7 条 + ASR 预热 2 条）。
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

### 2026-08-14 智能体架构研究：主流对比、可靠性、存储、视觉、世界模型、伪自我意识（T1-T6）

- 用户要求：把六类请求拆分成任务（拆分表见 docs/research/agent-architecture/README.md），对比主流智能体设计/框架、分析运行时生成慢/错误/不生成、网页端账号/人格/记忆/上下文数据库选型、视觉设计、世界模型与人类思维差距、伪自我意识方案；**实验完成并验收前不上传仓库**。
- 执行：6 个并行研究任务（T1 框架对比 / T2 运行可靠性 / T3 网页端数据库 / T4 视觉 / T5 世界模型 / T6 伪自我意识），全部完成并写入 docs/research/agent-architecture/01-06 + 00-SUMMARY.md 汇总；结论均与代码核对、外部观点附来源链接；未修改任何源码。
- 关键结论：HeadCore 相对主流框架最强的是单一 Self 代码化、证据边界、fail-closed 门禁；最大缺口是结构化工具调用循环、浅反思、链路不可编排。运行可靠性 Top5 失败模式（流式中断无标记/流式绕过评估门/静默截断/最坏延迟无界/存储线性劣化）。网页端最大问题是账号体系双轨并存需强制单一主库。视觉第一优先是把断开的标签层接进对话证据链，云 VLM 永不默认启用。世界模型只能缩小差距不能模仿（具身因果/主观体验/常识地基不可弥补）。伪自我意识=5 组件机制包+伦理红线（不宣称意识、不欺骗用户、安全门禁优先）。
- 上传门禁：本批研究文档只提交本地仓库，**未 push 到 GitHub**；后续任何实验落地须先出计划经用户确认、跑测试写报告，验收通过后才同步 code-only 目录并上传。
- 已落地第一批 P0 实验（T2-E1~E4 流式可靠性，2026-08-14）：截断标记、流式尾部门禁（关键违规追加纠正、非关键只审计）、模型流错误帧显式抛错、首字/总预算超时（默认 20s/90s）。全量 820 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t2-stream-reliability-report.md。视觉 T4 按用户要求暂缓。仍只提交本地，未上传。
- 已落地第二批 P0 实验（T6-L0 + T3-A/B/C，2026-08-14）：持久自我档案 SelfProfile（白名单校验+损坏兜底+save/load/reset，未接对话链路，零行为变化）；网页主库唯一性启动校验（postgres/MySQL V2 二选一，半开组合报错）；上下文窗口配置化（RECENT_CONTEXT_MAX_MESSAGES/CHARS，默认 8/80）；进程内限流回退 InMemoryRateLimitRepository。全量 834 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t6-l0-and-t3-abc-report.md。仍只提交本地，未上传。
- 已落地 T6-L1/L2（2026-08-14）：自我档案投影接入 system prompt（档案缺失输出空串、不向用户复述、不宣称意识）+ 自我一致性门禁（身份否认/能力越界/违背"不宣称意识"边界 → 触发既有 REPAIR 或流式纠正句，写 head_self_conflict 审计）。无档案时零行为变化。全量 843 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t6-l1-l2-report.md。仍只提交本地，未上传。
- 已落地 T6-L3 + T3-D（2026-08-14）：脱机反思循环（规则版，scripts/run_self_reflection.py，身份字段永不改、单次至多 2 个行为字段、写 head_reflection_audit、幂等）；认证过期数据清理脚本（scripts/auth_expiry_cleanup.py，默认 dry-run，逐表容错）。全量 853 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t6-l3-and-t3-d-report.md。仍只提交本地，未上传。
- 已落地 T5-R1（2026-08-14）：世界模型时间衰减与信念强度（belief_strength 指数半衰期 30 天、陈旧关系进 uncertainties 且退出投影、投影按 confidence×recency 排序、认知事实按 observed_at 衰减排序；同强度条目保持原有顺序语义）。全量 856 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t5-r1-report.md。仍只提交本地，未上传。
- 已落地 T5-R2（2026-08-14）：反事实推演轻量版（CounterfactualTrial 状态机 pending→supported/refuted/expired，反例优先；supported 且 conf≥0.8 才 confirmed，refuted 从可投影移除；离线场景集 4 例 PASS margin=1.0，评估脚本 scripts/evaluate_world_model_counterfactuals.py，报告 logs/world-model-effects-eval/2026-08-14/）。全量 864 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t5-r2-report.md。仍只提交本地，未上传。
- 已落地 T5-R3（2026-08-14）：世界证据自动校准——摄取从天气扩展到新闻/政策/路线（per-capability 白名单字段，三道门保留，正文不入事实，天气 condition 键兼容）；world_calibration.py 事实对账（同键同值去重、同源高版本取代、跨源冲突交 resolve 标记）。全量 870 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t5-r3-report.md。仍只提交本地，未上传。
- 已落地 T5-R4（2026-08-14）：世界模型评估闭环——固定评测集 data/world_model_evaluation_cases.json（去重/时间衰减/反事实/冲突/问题式 12 例）+ scripts/evaluate_world_model.py（六条确定性管线、PASS 12/12 margin=1.0、报告落 logs/world-model-effects-eval/2026-08-14/，附"不构成对 AGI 或意识的主张"声明）。全量 872 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t5-r4-report.md。仍只提交本地，未上传。世界模型方向 R1-R4 全部完成。
- 已落地 T1 受限单步工具循环（2026-08-14）：USE_WORLD_TOOL 严格标记协议（整条匹配才触发、中英文能力词、天气/新闻/政策白名单）+ 单步证据再生成 + 无证据/二次标记/异常一律替换拒绝话术；仅非流式 reply()，默认无 provider 零变化；流式防御替换标记。全量 883 passed, 2 skipped；报告 logs/project-cleanup/2026-08-14/t1-tool-loop-report.md。仍只提交本地，未上传。
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
- GitHub 已推送：新仓库 https://github.com/DyQcml12/HeadCore（公开，code-only，586 个文件，无模型/密钥/日志）；本机 git 配置了 schannel SSL 后端解决证书链问题。旧仓库（含模型历史）仍只保留在本机，绝不 push。未删除任何大件本地资产（`external/`、`data/models/`、`data/hutao_voice/`、`data/stickers/` 等按用户要求保留不动）；未执行真实外部服务验收。
### 2026-08-15 天气源切换至高德 weatherInfo

- 用户反馈：天气查询不可用（此前默认路由到和风天气，运行时报错并回退世界守卫话术“当前实时天气来源不可用”）；要求改用高德天气 API（参考 https://lbs.amap.com/api/webservice/reference/weatherinfo/ ）。
- 执行：`app/world/runtime.py` 当前天气/预报默认路由到 `AmapWorldSourceAdapter`（`source_id="amap"`、`parameters={"adcode": location}`、缓存 TTL `AMAP_WEATHER_CACHE_TTL_SECONDS`=900）；`app/world/brain.py` 天气地点解析后传 `adcode` 而非城市名；`app/control/health_checks.py` 世界证据详情只提 高德；和风天气适配器保留为备选。
- 同步修改：`tests/world/test_world_context.py` 断言改为 adcode（440100）；`service-worker.js` CACHE_NAME v14→v15（强制浏览器刷新壳，排查用户侧“语言模型用不了”的缓存因素）与 `tests/test_desk.py`；README（中英）、验收手册 7.7、`docs/WORLD_MODEL_AND_PROJECT_CAPABILITIES.md`、技术报告 6.5 改为“高德天气默认路由、和风保留备选”。
- 验证：真实 HTTP `/api/v1/chat` 两轮（自然语言 + adcode 查询）均 200 且回复含真实天气（广州 中雨 26°C 湿度94%）；全量 `883 passed, 2 skipped`；报告 logs/project-cleanup/2026-08-15/weather-amap-routing-report.md。排查中的 500 来自 8010 端口残留旧代码进程，非本次改动缺陷。
- 状态：已提交本地仓库，**未 push GitHub**（上传门禁仍有效）；用户常驻 8000 端口实例为旧代码，需重启启动器生效。
### 2026-08-15 登录注册 + 双库 + SMTP 真实联调

- 用户要求：把公开网页认证真实开起来联调；选择本地测试 SMTP + 两个数据库一起用（一个存数据、一个存记忆）。
- 最终双轨分工：MySQL V2（`DATABASE_V2_ENABLED=true`，库 `hutao_chat`）= 账号/档案数据（web_users/profiles/web_sessions/验证与重置令牌/限流/审计，迁移 004/005）；PostgreSQL（`STORAGE_BACKEND=postgresql`，新建库 `hutao_web_core`）= 聊天记忆（sessions/messages/model_invocations/memories 等，`migrations/postgres/001_web_core.sql` 17 张表）。
- 代码变更：`app/auth/runtime.py` 双库齐开不再拒绝启动，认证主库确定性选 MySQL V2（身份层），单库校验保持 fail-fast；`app/main.py` 新增 `_web_chat_uses_postgres()` 守卫，`STORAGE_BACKEND=postgresql` 时网页聊天/记忆走 PG（三处接线）；`app/main.py` 增加 `__main__` 入口（`python -m app.main`，读 HOST/PORT），`启动控制中心.bat` 改用该入口；新增 `app/loop_factory.py` 解决 Windows 下 uvicorn 硬编码 ProactorEventLoop 导致 psycopg 异步不可用的问题（uvicorn 0.36+ 无视 set_event_loop_policy，必须传自定义 loop factory）。
- 联调修复 4 个真实缺陷：①Windows 事件循环（上述）；②PG 迁移器缺 schema_migrations 建表；③MySQL 旧库 2026-07 schema 漂移（聊天 500）——双轨分工后聊天走 PG 绕开，旧表保留待迁移；④重复注册 500 → 仓库层翻译唯一键冲突为 RegistrationError（回滚保留）→ 422，新增 tests/test_auth_registration_repository.py 3 条。
- 联调结果：注册/验证码/验邮箱/登录/会话+CSRF/me/带 CSRF 聊天/登出/密码重置全链路通过；负路径（401/400/422/429）全部符合预期；双写验证：MySQL 有账号档案会话、PG 有聊天消息与模型调用。全量 `888 passed, 2 skipped`（883 基线 + 新增 5 条）。
- 遗留：本地调试 SMTP 只收不发（真实邮箱按 SMTP_* 填 .env 即可）；MySQL 旧表漂移与语义记忆 006 触发器（binlog 权限）待后续；jsonl 历史不自动进 PG。报告 logs/project-cleanup/2026-08-15/auth-db-smtp-integration-report.md。
- 固化（2026-08-15 用户确认）：`.env` 已写入 `PUBLIC_WEB_AUTH_ENABLED/DATABASE_V2_ENABLED/STORAGE_BACKEND=postgresql/POSTGRES_*/EMAIL_DELIVERY_ENABLED/SMTP_*`（共 14 键）；调试 SMTP 提升为 `scripts/dev_smtp_sink.py`（收件落 `logs/dev-smtp-inbox/`，时间戳文件名），`启动控制中心.bat` 在 `.env` 的 SMTP_HOST=127.0.0.1 且 1025 空闲时自动后台拉起；纯 `.env` 配置的 8010 实例复测 auth/status+登录+聊天全部 200。真实邮箱就绪后改 SMTP_* 即可，无需改代码。
### 2026-08-15 网页 TTS（GPT-SoVITS）真实联调

- 用户要求：把语音 TTS 开起来联调（视觉继续搁置）。TTS 唯一路由 GPT-SoVITS，部署在本机 `external/GPT-SoVITS-v2pro-20250604`（CUDA/4070，胡桃权重 hutao-e15.ckpt + hutao_e8_s912.pth，`api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml`）。
- 修复真实缺陷：`app/voice_chat/tts_service.py` 合成循环没用 planner 的分段参考（参考音频/提示文本/生成参数），网页 TTS 必然 503；现改为显式传参优先、否则用分段规划值（新增 `_prefer_explicit`）。
- 测试隔离：新增根目录 `conftest.py`，收集前把认证/双库/存储/世界/TTS 键钉为中性默认（本机 `.env` 固化后 24 条用例曾因此失败）；`test_web_voice_api.py` 3 条加 auth 隔离；`test_voice_chat.py` 新增计划参考用例。全量 `889 passed, 2 skipped`。
- 联调结果（8010 纯 .env 实例）：`/api/v1/voice/status` enabled；登录聊天返回 `X-Hutao-Reply-Id`；`/api/v1/voice/synthesize` 200 返回 audio/mpeg 78380 字节；ffprobe 校验 mp3 6.45s/97kbps。报告 logs/project-cleanup/2026-08-15/tts-integration-report.md。
- 使用前提：GPT-SoVITS 服务在 9880 运行（重 GPU 进程，启动器不自动拉起，控制中心服务页手动启动）+ `PUBLIC_WEB_TTS_ENABLED=true`（已固化 .env）。
- 状态：本轮只提交本地，**未 push GitHub**。
### 2026-08-15 注册密码策略报错信息修复

- 现象：用户注册（浅川木里 / 3471764547@qq.com / Aa147258@）报错，只看到笼统 "invalid registration data"。
- 根因：密码策略要求 ≥12 字符（该密码 9 位），`RegistrationService.register` 的 `except Exception` 把 `PasswordPolicyError` 吞掉。
- 修复：`passwords.py` 策略错误中英双语；`registration.py` 单独捕获 `PasswordPolicyError` 透传原因；新增测试 `test_register_surfaces_password_policy_reason`。8010 复测 422 detail 明确，无残留 pending 记录（校验在写库前）。全量 pytest 见本轮结果；报告 logs/project-cleanup/2026-08-15/register-password-policy-message-report.md。
### 2026-08-15 六位数字验证码 + 注册/登录/找回一致性问题修复

- 现象：用户 3471764547@qq.com 注册后登录/找回均“不认”，且验证码是 43 位长令牌。
- 根因：账号卡在 pending_email_verification（验证码邮件落在本地调试 SMTP，用户收不到）；注册查重/登录放行/重置防枚举三条逻辑各自正确但组合起来像“逻辑坏了”；验证码 token_urlsafe(32) 过长。
- 修复：新增 `app/auth/codes.py::new_six_digit_code`，注册与重置验证码统一 6 位数字，邮件文案同步；`/verify-email` 与 `/password-reset/confirm` 增加全局防爆破限流（30 次/10 分钟、封 30 分钟，subject_kind=verification_code/password_reset_code）；新增迁移 `migrations/v2/007_public_web_code_limits.sql`（MySQL ENUM 扩展，手动应用并记录）与 `migrations/postgres/002_public_web_code_limits.sql`（VARCHAR(24)+CHECK 扩展，applier 应用）；清除该邮箱的 pending 脏数据。
- 验证：注册→6 位码→验证→登录全链路 200；密码重置 6 位码全链路 200；防爆破 429 有测试覆盖；全量 `891 passed, 2 skipped`。报告 logs/project-cleanup/2026-08-15/six-digit-code-and-stuck-account-report.md。
### 2026-08-17 视觉 L1 接线：摄像头标签层接入对话证据链

- 任务：T4 指出的“标签层与对话断开”落地修复（L1 本地受限标签接进对话，零新增算力与隐私面）。
- 实现：新增 `app/camera/evidence_store.py::CameraEvidenceStore`（仅存时序确认后的白名单标签上下文，TTL 300s，渲染为 attention 兼容格式，停会话即清）；`app/camera/router.py` 的 `CameraControlRuntime` 增加 `evidence_store` 并在采集回调写入；`app/services/chat_service.py` 新增可选 `camera_context_provider` + `_camera_context_block`（显式画面问题注入标签、标签问题匹配、无上下文给澄清话术、无关/blocked/无 provider 零变化，注入块禁止推断情绪/身份/意图）；`app/main.py` 装配 provider。
- 测试：新增 `tests/camera/test_evidence_store.py` 5 条 + `tests/test_chat_camera_context.py` 6 条；修正 test_api.py 12 处 ChatService fake 接受 **kwargs。全量 `902 passed, 2 skipped`（891 基线 + 11）。报告 logs/project-cleanup/2026-08-15/vision-l1-wiring-report.md。
- 边界：L2 场景状态机与 L3 VLM 待后续任务；主动观察仍默认关闭。
### 2026-08-17 真实邮箱 SMTP + GSV 守护 + ASR 预热

- 真实邮箱：用户提供 QQ 授权码后 `.env` 切到 smtp.qq.com:587 STARTTLS；直连发信冒烟成功；8010 复测三开关全开。本地调试收件器自动启动条件自然失效。公网前仍需图形验证码+每日发送上限（危险清单）。
- GSV 守护：新增 `app/control/service_watchdog.py::GptSovitsWatchdog`（连续失败阈值/重启宽限 120s/每小时上限 5，经控制中心 start_service 重启）与 `scripts/watch_gpt_sovits.py`；启动器在 PUBLIC_WEB_TTS_ENABLED=true 时后台拉起，日志 logs/service_watchdog.log；实测 --once healthy；7 条策略测试。修复 bat 两处反斜杠丢失（scripts\dev_smtp_sink.py / logs\service_watchdog.log）。
- ASR 预热：`file_service.warmup_audio_pipeline` + main.py startup 钩子（AUDIO_WARMUP_ENABLED 默认 false，本机 .env 已固化 true）：后台线程预加载 ASR/情绪引擎（0.5s 静音探针），冷启动 74s 成本转后台；引擎已有模块级缓存。3 条测试；conftest 钉 false。
- 全量 `911 passed, 2 skipped`（902 基线 + 9）。报告 logs/project-cleanup/2026-08-15/smtp-watchdog-warmup-report.md。







