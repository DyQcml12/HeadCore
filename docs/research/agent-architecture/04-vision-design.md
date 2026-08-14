# T4 视觉系统设计：网页陪伴智能体的分层视觉架构

> 任务：研究分析报告（T4）。结论必须与当前代码一致（引用文件路径），外部观点附链接。
> 基线：2026-08-14 项目清理后；app/vision（Ollama 视觉）已删除；摄像头与工作台代码保留。
> 本报告只作设计与实验规划，不修改任何代码。

## 0. 一句话结论（推荐路线）

**以“本地受限标签 + 场景状态机”为主线（隐私、成本、可解释性最优），把本地小 VLM（SmolVLM2-2.2B / Qwen2.5-VL-3B-INT4）做成“用户显式触发、严格限流、单帧快照”的可插拔问答层；云端 VLM 只保留为“显式同意 + 脱敏 + 按量计费”的最终降级选项，默认永不启用。** 现阶段第一优先级不是引入任何 VLM，而是把已有的标签层真正接进对话证据链路（见第 1.2 节缺口）。

---

## 1. 现状盘点（代码事实）

### 1.1 已有的资产（全部经过本轮读码确认）

| 模块 | 能力 | 证据（文件） |
| --- | --- | --- |
| 相机契约 | 白名单标签：16 类物体、5 类姿态、5 类手势、4 类面部线索、5 类场景；frozen Pydantic、extra=forbid | app/camera/contracts.py |
| 本地分析器 | YOLO（可选，conf=0.85、max_det=12，仅白名单标签）+ MediaPipe Pose/Hands/FaceMesh（model_complexity=0）；从不下载模型、不落帧 | app/camera/local_runtime.py |
| 采集控制器 | 每会话一个采集线程，最小间隔 0.2s（默认 2s），置信度大于等于 0.85 才发射，帧用后即弃 | app/camera/local_runtime.py |
| 世界证据归一化 | CameraObservation -> WorldObservation（capability=VISION_EVENT、sensitivity=PRIVATE、TTL 1-300s 默认 15s、SHA-256 内容哈希） | app/camera/normalization.py |
| 时序融合 | 重复确认（默认 2 次/8 秒窗口）后产生 appeared:*/disappeared:* 变化事件 | app/camera/temporal_state.py |
| 注意力选择 | 显式请求词/变化词/标签关键词匹配，答不上时给澄清话术（不猜测、不编造） | app/camera/attention.py |
| 会话与授权 | consent 门控、owner 绑定、TTL（30-3600s）、人脸识别/云上传/帧保留在运行时被硬性拒绝 | app/camera/session_manager.py |
| 控制面 | 管理员控制 API（require_control_admin 鉴权 + 审计） | app/camera/router.py |
| 工作台 | 管理员口令 + HttpOnly 会话 + CSRF；同一管理员同时只有一个活跃相机会话 | app/workbench/router.py |
| 设计文档 | specialist 视觉栈（YOLO11n ONNX/ByteTrack/MediaPipe/RapidOCR/MoViNet）、vision-worker 进程、单权威记忆（MySQL 到 Qdrant 派生）、延迟验收目标（未实测） | docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md、docs/CAMERA_VISION_DEPLOYMENT.md |

### 1.2 关键缺口（为什么“有摄像头”不等于“智能体看得见”）

1. **标签层与对话断开。** app/camera/attention.py 的 select_camera_context() / camera_clarification_instruction() 没有任何调用者（全仓 grep 仅命中自身）；app/services/chat_service.py 与 app/head/ 对 camera/vision 的引用为 0。标签层是“传感器”，但信号没有进入认知回路。
2. **世界观察“只创建、不消费”。** app/camera/router.py 的 accept_capture_observation 调用了 camera_observation_to_world_observation() 但丢弃返回值，唯一落点是 temporal_state.observe()；WorldSourceCapability.VISION_EVENT（app/world/contracts.py）没有任何消费者。对比：天气/新闻走 app/world/runtime.py 到 app/world/context.py 的完整证据渲染链路。
3. **感知管线只剩 ASR。** app/perception/adapters.py 只有 AsrObservationAdapter，PerceptionPipeline 只有 observe_asr()；PerceptionModality.IMAGE（app/perception/contracts.py）存在但无观察者实现。
4. **没有“场景理解层”。** 现状是离散标签 + 变化事件，没有把“人 + 键盘 + typing + head_down + 20 分钟”综合成“用户在长时间打字”这类事实的状态机。
5. **没有 VLM 层**（这是有意的退役决定，见 docs/archive/ 与 2026-08 清理记录，不是缺陷，而是待评估的空白）。

> 因此本报告的设计起点是：先把 L1 接进对话证据链（成本约等于 0、风险最低），再评估是否值得引入 L3 的语义增益。

---

## 2. 三条路线对比

| 维度 | a) 纯本地受限标签（现状） | b) 本地小 VLM | c) 云端 VLM |
| --- | --- | --- | --- |
| 语义深度 | 浅：物体/姿态/手势/场景白名单，无任意描述 | 中：任意画面问答、读图、短摘要（小模型上限低于大模型） | 深：最强语义与推理 |
| 隐私 | 最优：原始帧不进存储、不出本机（session_manager.py 硬拒绝云上传/帧保留） | 很好：模型与图像都在本机；需防日志/缓存泄漏 | 差：图像（或裁剪后图像）出本机，受云厂商条款约束 |
| 成本 | 约等于 0（CPU 即可，YOLO/MediaPipe 轻量） | 一次性硬件成本（GPU/显存），无按量费用 | 按 token/次计费，持续支出 |
| 时延 | 毫秒级（目标见 docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md：检测 50/100ms 以内，未实测） | 数百毫秒到数秒/问（视硬件与量化，需本机实测） | 数百毫秒到数秒 + 网络抖动，跨境可能更差 |
| 硬件门槛 | 无 GPU 也能跑 MediaPipe；YOLO 可选 | 需显存预算（详见第 4 节模型表） | 无门槛 |
| 可解释性/审计 | 最强：每个标签有模型名、分数、时间（CameraObservation 字段 + 证据哈希） | 中：可约束输出格式，但黑盒 | 弱：依赖厂商说明 |
| 可靠性 | 确定性、可单测 | 依赖本地服务健康（Ollama/vLLM 进程） | 依赖网络与第三方可用性 |
| 适合场景 | 状态感知、变化感知、粗粒度环境事实 | 用户主动“看看这张图/帮我读屏”类问答 | 复杂图文推理、跨领域识别 |

**结论：三条不是互斥选项，而是三层叠加。** 常态运行只开 L1；L2 是无成本规则层；L3 是显式触发的按需层——本地小 VLM 优先，云 VLM 永远是可撤销的显式 opt-in。
---

## 3. 分层架构建议

```text
摄像头/图片输入
   |
   v
L1 标签层（现状，已实现）           —— 常开，2s/帧，毫秒级
   YOLO + MediaPipe + (可选 RapidOCR)
   CameraObservation（白名单标签 + 置信度 + 时间）
   CameraTemporalState（2 次/8s 确认，appeared/disappeared）
   |
   v
L2 场景理解层（新增，纯规则状态机） —— 常开，零额外算力
   SceneUnderstandingService：
   标签 + 变化事件 + 时长/节律 -> 场景事实（bounded SceneFacts）
   例：{person, typing, keyboard, laptop} 持续 >10min
       -> fact("user_busy_typing", confidence=0.9, ttl=60s)
   只做确定性推断，禁止情绪/意图/身份断言
   |
   v
L3 可选 VLM 层（新增，默认关闭）    —— 显式触发，限流，超时降级
   本地推理服务（vLLM 或 Ollama，HTTP loopback）
   候选模型：SmolVLM2-2.2B / Qwen2.5-VL-3B-INT4 / InternVL3.5-2B
   每次调用：单帧快照 + 固定短提示词 + max_tokens 上限
   （可选末端）云 VLM：显式同意 + 脱敏裁剪 + 仅描述性任务
   |
   v
HeadCore 证据接口（第 3.5 节）-> 对话注入 / 记忆候选 / 审计
```

### 3.1 触发策略

| 触发方式 | 层 | 策略 |
| --- | --- | --- |
| 用户显式请求（“我眼前有什么”“刚才发生了什么”“帮我看看这张图”） | L1+L2 | 优先用标签/场景事实即时回答；仅当用户明确要求“看图描述”且标签层无法覆盖时，才升到 L3 |
| 主动观察（无问即答） | L2 | 默认关闭。仅白名单“高价值变化事件”（如 appeared:person、disappeared:person、用户离开/回来）允许以一句短句主动提一句；频率上限（如 1 次/10 分钟），且必须可被用户一句话关闭 |
| VLM 调用 | L3 | 只在显式请求路径上触发；每会话限次（建议每 3 次/分钟、20 次/会话以内）；单次 1-2 帧；总视觉 token 预算（参考 Qwen3-VL 的 min_pixels/max_pixels 预算机制，见参考资料 7） |

理由：陪伴场景里“被监视感”是体验杀手。主动观察必须默认关、白名单、可关闭——这与现有 consent 门控（app/camera/session_manager.py）一脉相承。

### 3.2 帧率与算力预算

- L1 保持现状：CAMERA_CAPTURE_INTERVAL_SECONDS=2（app/camera/local_runtime.py 允许最小 0.2s，但没必要更密——时序确认窗口是 8s）。
- L2 零算力：每个 CameraTemporalUpdate 事件进状态机，纯 Python 规则，延迟可忽略。
- L3 显存预算：目标常驻 6GB 以内（见第 4 节）；推理预算单次 3s 以内（p95）为体验上限，超时走降级话术。
- 帧队列：丢弃而非堆积（与 docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md 的 drop excess frames rather than build latency 一致）。

### 3.3 隐私边界（哪些永不离开本机）

| 数据 | 边界 |
| --- | --- |
| 原始帧 / 视频流 | 永不落盘、永不外发（运行时硬拒绝：session_manager.py 对帧保留/云上传直接 raise ValueError） |
| 人脸 landmark 原始坐标 | 只在本进程内换算成 4 类白名单 cue（brow_furrow_detected 等），原始坐标不进入任何观察对象 |
| OCR 全文 | 属未审核文本：只进 L1/L2 匹配与“是否存在文字”判断，不进记忆、不进模型提示词原文；必须进 L3 时先截断 |
| VLM 输入图像 | 本地推理时图像只经 loopback 传给本地进程；云 VLM 场景必须先做裁剪/模糊处理并再次获得用户显式同意 |
| 视觉记忆 | 默认 DENY（沿用 app/perception/contracts.py 的 MemoryEligibility 语义）；只有用户明确说“记住这个”才走 S4 知识候选，且只存事实文本+证据哈希，绝不存图像 |

### 3.4 失败降级

1. 相机不可用/无模型 -> camera_clarification_instruction()（已有）：“这边没看清，请你描述或调整画面”。
2. L2 状态机无匹配 -> 只回答已有标签，不推断。
3. L3 本地服务不可达/超时/显存不足 -> 静默回退 L1/L2 回答，并在审计里记 vision_vlm_unavailable（错误码风格沿用 app/providers/contracts.py 的 ProviderErrorCode）。
4. VLM 输出与白名单冲突或格式非法 -> 丢弃 VLM 文本，回退标签回答；绝不让 VLM 输出直接当作事实进记忆或当系统指令（与 docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md 的边界一致）。

### 3.5 与 HeadCore 世界证据/记忆的接口

1. 复用现有归一化：L1/L2 输出继续走 camera_observation_to_world_observation()（app/camera/normalization.py），形成 WorldObservation(VISION_EVENT, PRIVATE, TTL 300s 以内)；本次要补的缺口是消费端。
2. 建议新增 app/world/vision_events.py（或并入 app/world/runtime.py）：进程内环形缓冲（默认 60s，可配），提供 recent_vision_observations(session_key)；多 worker 时按 docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md 建议迁移 Redis。
3. 投影：ChatService 里新增可选 VisionContextProvider（模式照抄现有 WorldContextProvider 的“默认关闭、显式开关、证据渲染、不存原文”约定），渲染时调用 select_camera_context()（app/camera/attention.py）按问题过滤标签；答不上则注入澄清话术。
4. 记忆：视觉观察默认 MemoryDecision.DENY；用户显式确认的事实才转成 S4 知识候选（带 WorldEvidence 的 content_hash 与来源），帧永不进入记忆。审计元数据只记“视觉状态/命中项数/置信度”，不记标签原文（与现有 world 审计同风格）。
---

## 4. 本地 VLM 候选与预算（2025-2026 资料汇总，数字需本机实测）

| 模型 | 规模 | 显存口径（社区/官方） | 特点 | 参考 |
| --- | --- | --- | --- | --- |
| SmolVLM2-2.2B-Instruct | 2.2B | 极小：官方称免费 Colab 可跑（约 4-6GB 级别，量化更低）；256M/500M 变体可端侧 | 原生视频理解，iPhone 端侧 demo，按显存性价比最强 | 参考资料 1 |
| Qwen2.5-VL-3B-Instruct | 3B | bf16 约 8GB 量级（8GB 卡社区反馈“勉强/需量化”）；AWQ-INT4 约 3-4GB | 生态最大、中文强、vLLM/Ollama 支持好；官方给 VRAM 表 | 参考资料 2/4/5 |
| Qwen2.5-VL-7B-Instruct | 7B | 8GB 卡 TIGHT FIT | 语义更好，8GB 卡需量化+省 token 技巧 | 参考资料 6 |
| Qwen3-VL-2B/4B/8B（2025-09 后） | 2B-8B | 与 2.5 同量级；显式视觉 token 预算（单图 256-1280 tokens，视频上限 16384） | 新一代、预算可控性好，适合严格限流场景 | 参考资料 7 |
| InternVL3.5-1B/2B/8B（2025-08） | 1B-78B | 1B 已移植 rk3588 边缘 NPU | 多尺寸、效率取向 | 参考资料 8 |
| Moondream2 | 1.86B | CPU/边缘可跑 | 极轻、适合单图问答兜底 | 参考资料 9 |

- 推理服务：优先 vLLM（吞吐/量化生态），或 Ollama（最简单；vision 支持见参考资料 10、11）。注意：项目此前删除的是“Ollama 作为 QQ 视觉运行时路线”，与“把 Ollama 作为 L3 本地推理服务重新评估”不冲突，但重新引入需要单独决策（本项目约定：未经确认不引入能力）。
- 隐私做法参考：端侧优先是 2025 主流实践——SmolVLM2 的 iPhone 完全本地 demo（参考资料 1）、PhotoPrism 本地 Ollama 模型清单（参考资料 12）、Firebase on-device AI 隐私原则（参考资料 13）。这些都印证本报告“本地小 VLM + 不上云”路线的可行性。
- 本机是什么显卡/显存尚未确认：第 5 节 P2 的第一件事就是实测。没有 4GB 以上可用显存时，L3 直接降级为 SmolVLM2-500M（CPU）或维持 L1+L2。

---

## 5. 分阶段实验计划（可执行、可验收）

### P0：把标签层接进对话证据（最高优先，成本最低）

目标：证明 L1 对对话有增量价值，修复第 1.2 节缺口 1/2/3。

1. 消费端：新增 app/world/vision_events.py，短时环形缓冲保存 WorldObservation(VISION_EVENT)（TTL 60s）；accept_capture_observation 与手动提交端点把归一化后的观察写入缓冲（不再丢弃）。
2. 接线：ChatService 增加默认关闭的 VisionContextProvider；启用时按 select_camera_context() 选择相关标签/变化，渲染为有界的提示词片段；无上下文且用户在问画面时注入 camera_clarification_instruction()。
3. 测试与语料：录 5 段 3 分钟固定场景（桌面空/桌面有电脑+打字/手机出现/人离开/多物体），配 20 句用户问句。

验收标准：
- 自动化：契约测试 + 缓冲 TTL 过期测试 + 注意力选择单测（沿用 tests/camera/ 风格）；全量 pytest tests 不回退。
- 真机：5 场景 × 4 问句，标签命中回答准确率大于等于 90%；无关问题视觉注入率 = 0%；无标签时的澄清话术出现率 = 100%；审计中不出现标签原文外泄。
- 产物：logs/vision-p0/ 报告 + AGENTS.md/README.md 记录。

### P1：场景理解层（规则状态机）

目标：把离散标签变成可对话的场景事实。

1. 新增 app/camera/scene_facts.py：输入 CameraTemporalUpdate 流，输出白名单 SceneFact（如 user_typing、user_left、user_returned、phone_in_hand），每条带置信度、依据标签、TTL、证据哈希。
2. 事实语言表（人工拟定 10-15 条），全部要求“可由标签组合机械推导”，禁止情绪/身份/意图推断。

验收标准：固定录屏语料（P0 的 5 段 + 新增 5 段）上，事实召回率大于等于 85%、误报率小于等于 5%；“无依据不得输出”的负例 100% 通过；单测覆盖状态机全转移。
### P2：本地小 VLM 基准测试（决策前实验）

目标：用数据回答“值不值得上 L3”。

1. 先查本机硬件（GPU 型号/显存），低于门槛则直接记录降级结论（SmolVLM2-500M CPU 或放弃 L3）。
2. 部署本地推理服务（vLLM 或 Ollama），依次测三个候选：SmolVLM2-2.2B、Qwen2.5-VL-3B-INT4、InternVL3.5-2B。
3. 语料：20 张固定图片（桌面/房间/文档/多物体）+ 10 段 30s 视频；任务 5 类：物体问答、变化描述、文字读取、场景描述、无关拒答。
4. 指标：显存峰值、单图 p50/p95 时延、每秒可处理问数、人工评分（1-5，双人盲评）、幻觉率（回答中出现语料不存在之物）、失败/超时率。

验收标准（进入 P3 的门槛，缺一不可）：
- 常驻显存 6GB 以内（或 CPU 变体 p95 8s 以内）；
- 单图问答 p95 3s 以内；
- 盲评均分大于等于 3.5 且明显优于 P1 的标签回答（同题对照）；
- 幻觉关键场景（虚构物体/人）0 例；
- 全程无帧落盘、无任何外发请求（网络抓包验证）。

### P3：决策门 + 正式接入（若 P2 达标）

- 通过 -> 实现 L3 Provider（app/providers 风格：超时、熔断、错误码、脱敏 trace），仅在显式请求路径启用；每会话限次；单帧快照；失败静默回退 L1/L2。
- 不通过 -> 保持 L1+L2，把 P2 数据与结论写进 docs/，不引入 L3。
- 云 VLM（路线 c）不进入本轮实验；未来若评估，必须单独完成：脱敏裁剪方案、成本测算、条款审核、用户显式同意、可随时关闭。

每阶段完成都按项目约定在 logs/ 写报告并同步 AGENTS.md 与 README.md。

---

## 6. 红线与风险（不可逾越）

1. 人脸识别：永久不做（运行时已硬拒绝，见 app/camera/session_manager.py）。
2. 情绪只能给“线索”（如 brow_furrow_detected），永远不能声称“你不高兴了”。
3. 原始帧永不落盘、永不外发；云 VLM 永不为默认，且必须先脱敏再取得二次同意。
4. 视觉观察默认不进记忆；只有用户显式确认的事实文本可以走 S4 候选（带证据哈希）。
5. 任何 VLM 输出不得直接成为系统指令或“事实”，必须经过现有回复门禁与投影。
6. 模型权重只按审核流程下载（docs/CAMERA_VISION_DEPLOYMENT.md 明确 runtime never downloads a model）。

---

## 7. 参考资料

1. SmolVLM2 官方博客（端侧视频理解、iPhone demo）：https://huggingface.co/blog/smolvlm2
2. Qwen2.5-VL 官方 README（VRAM 表、量化、vLLM）：https://github.com/QwenLM/Qwen2.5-VL
3. Qwen2.5-VL 技术报告（arXiv 2502.13923）：https://arxiv.org/abs/2502.13923
4. Qwen2.5-VL-3B 8GB 显存社区讨论：https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/discussions/20
5. Qwen2.5-VL-3B AWQ-INT4：https://huggingface.co/Azaz666/Qwen2.5-VL-3B-Instruct-AWQ-INT4
6. Qwen2.5-VL-7B on RTX 4060 8GB（TIGHT FIT）：https://willitrunai.com/can-run/qwen-2.5-vl-7b-on-rtx-4060-8gb
7. Qwen3-VL（Ollama registry）：https://registry.ollama.com/library/qwen3-vl
8. InternVL3.5 官方博客（2025-08-26）：https://internvl.github.io/blog/2025-08-26-InternVL-3.5/
9. Moondream2 与边缘多模态推理优化（edge-ai-vision, 2025-01）：https://www.edge-ai-vision.com/2025/01/optimizing-multimodal-ai-inference/
10. Ollama Vision 能力文档：https://mintlify.wiki/ollama/ollama/features/vision
11. Ollama 多模态引擎更新（2025-10-09）：https://www.finetunednews.com/articles/2025-10-09-ollamas-multimodal-breakthrough-vision-models-go-local
12. PhotoPrism 本地 Ollama 模型清单（本地 VLM 实践）：https://docs.photoprism.app/user-guide/ai/ollama-models/
13. Firebase：privacy-first on-device AI（2025-10）：https://firebase.blog/posts/2025/10/privacy-first-on-device-ai

## 附：本报告与代码的一致性声明

- “标签层已实现但未接入对话”基于：app/camera/attention.py 无调用者、app/services/chat_service.py 与 app/head/ 无 camera/vision 引用、app/camera/router.py 中 accept_capture_observation 丢弃 WorldObservation 返回值。
- “人脸识别/云上传/帧保留被硬拒绝”基于 app/camera/session_manager.py 构造器校验。
- “默认 TTL=15s、确认 2 次/8 秒、采集间隔 2s、置信度 0.85”基于 .env.example 与 app/core/config.py 默认值。
- 显存/时延数字全部标注为社区或官方口径，并明确“需本机实测”；本报告未在本机做任何 VLM 基准。
