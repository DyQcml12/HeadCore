# 06 伪自我意识设计：工程化的一致性机制包

> 研究分析文档（T6）。作者任务边界：本文只做代码盘点、外部调研与可落地方案设计；不修改任何源码、不 git commit/push。
> 项目立场：HutaoChatCore **不宣称意识、AGI 或真实情感**。"伪自我意识"在本项目中只能被实现为**面向用户体验的、可测试、可重置、默认关闭的工程一致性机制**。
> 代码结论以 2026-08-14 清理后的工作区为准；外部观点均附来源链接。

## 1. 现状盘点：项目里"自我"今天是什么

### 1.1 每轮重建、不跨轮持久化的"自我状态"

- `app/mind/self_state.py`：`SelfState` 只有 5 个字段（mood/energy/focus/tension/instruction），`build_self_state(conversation)` 是**确定性规则**（根据话题与降温需求选 mood），每轮由 `ChatService._prepare_chat` 重新计算（`app/services/chat_service.py` L603）。它是"语气连续性控制信号"，**不持久化**，不携带任何自传信息。
- `app/mind/conversation_state.py`：`ConversationState`（current_topic/last_user_correction/recent_user_mood/should_deescalate）由关键词规则推断，只描述"当前这轮"。
- `app/mind/social_state.py`：`SocialState`（familiarity/trust_band/boundary_mode/teasing_allowed/intimacy_allowed）描述本轮关系与边界，同样每轮重建。

### 1.2 人格是"注册表 + 每轮重建的 prompt 行"

- `app/persona/persona_state.py`：5 种 `PersonaMode`（CASUAL/TASK/EMOTIONAL/SAFETY/REPAIR）+ 场景到模式映射（`SCENE_TO_MODE`），全部为静态字典。
- `app/persona/persona_prompt_builder.py`：`build_persona_prompt` **每轮**从 `resolve_persona_profile` 重新生成身份行（`build_profile_lines`），其中已有一句关键的边界话术：身份质疑场景（`IDENTITY_CHALLENGE`）"也不要证明自己有真实意识"。
- 也就是说：今天的"人格连续性"= 固定 profile 文本 + 短窗口记忆 + 每轮重算的状态，**没有"跨会话自我档案"**。

### 1.3 HeadCore 已有"受控状态事件"持久化骨架（可直接复用）

- `app/head/events.py`：通过现有 `ChatRepository` 记忆边界持久化 5 类内部事件（`head_task`/`head_pending_question`/`head_last_action`/`head_feedback`/`head_policy_reset`），读回时"各类型独立恢复最后一条"（`load_head_event_context`，feedback 保留最近 12 条）。**不进入普通人格记忆投影**。
- `app/head/state.py`：`build_head_state` 把 conversation/self/social + 事件上下文 + 认知事实 + 世界模型 + 长期计划合并为单轮 `HeadState` 快照，产出 known_context/uncertainties。
- `app/head/projection.py`：`render_head_projection`（本轮认知快照，明令"不向用户复述"）+ `render_continuity_timeline`（含当前时刻 Asia/Shanghai、self/social 状态、"近期真实经历"只取 known_context 中 `近期经历[` 前缀条目）——**"时间感"已有雏形**。
- `app/head/feedback.py`：确定性反馈识别（accepted/corrected/advice_rejected/continued/stopped）+ `HeadReflection`（mistake_type/cause/evidence/better_action/policy_candidate 受控字段）。架构文档明确："单次反馈只修正当前轮策略，**不自动升级成永久用户偏好**"（`docs/head/HEADCORE_COGNITIVE_ARCHITECTURE.md` 第四阶段）。
- `app/head/calibration.py`：离线成对偏好/多评审标注评估（Fleiss' kappa 等）——这是**评估设施**，可复用来评估"自我一致性"。
- `docs/persona-training-plan.md`：明确"当前不建议直接训练一个模型替代现有链路"，样本沉淀 + 固定回归集优先。伪自我意识机制应遵循同一路线：**先规则与档案，不训练**。

### 1.4 差距结论

已有：单轮自我状态、本轮投影、确定性反馈反射、可过期短期自适应策略、结构化认知事实（`app/head/cognitive_facts.py`：事实 id/key/value/来源/过期/置信度/版本 + 撤销与冲突检测）。
缺失：**(1) 跨会话持久自我档案；(2) 会话级（而非单轮）事后反思；(3) 自我一致性门禁；(4) 显式的"上次对话与间隔"时间感；(5) 自我陈述类评估集。**

## 2. 外部调研：可以借鉴什么、必须防什么

### 2.1 Generative Agents：记忆流 + 反思（最高价值的工程原型）

Park et al., *Generative Agents: Interactive Simulacra of Human Behavior* (UIST 2023)，[arXiv:2304.03442](https://arxiv.org/abs/2304.03442)，官方介绍 [research.google](https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/)，[开源实现](https://github.com/joonspk-research/generative_agents)。
三个机制：**记忆流**（一切经历入流，检索按 recency/importance/relevance 加权）、**反思**（定期读原始记忆、合成高层抽象结论再写回）、**计划**（日计划驱动行动）。
映射：本项目的 `head_* 事件 + 认知事实` 已是"记忆流"的受控版本；缺的是"**反思**"环节——即低频把原始反馈聚合成高层自我描述再写回档案。与原文不同：我们的反思**默认不调大模型、只写白名单字段、可审计可撤销**。

### 2.2 Reflexion：口头强化学习式自省（已有单轮版，可扩展为会话级）

Shinn et al., *Reflexion: Language Agents with Verbal Reinforcement Learning* (NeurIPS 2023)，[arXiv:2303.11366](https://arxiv.org/abs/2303.11366)，[NeurIPS 页面](https://neurips.cc/virtual/2023/poster/70114)。
核心：失败 → 用语言自我诊断 → 把诊断写进 episodic buffer → 重试。
映射：`app/head/feedback.py` 的 `HeadReflection` 已经是"单轮口头反射"；要扩展的是**会话级反思循环**（本文 3.3），且反思结论默认只进自我档案、不进人格记忆。

### 2.3 MemGPT/Letta：自编辑记忆的护栏教训

Packer et al., *MemGPT: Towards LLMs as Operating Systems* (2023)，[arXiv:2310.08560](https://arxiv.org/abs/2310.08560)；后继项目 [Letta](https://github.com/letta-ai/letta)，[官方文档](https://docs.letta.com)。
核心：把上下文当分页内存，agent 通过 self-edit 工具主动改写长期记忆。
映射：**"持久自我档案"= 常驻"主存块"**，每次会话开头载入；但 MemGPT 的教训是自我编辑必须受控——无约束自编辑会漂移、自我强化错误结论。因此本设计要求：档案字段白名单 + schema 校验 + 修订号 + 用户可查看/重置（见第 4 节红线）。

### 2.4 Self-Consistency：内部监控的采样思路（本项目用"复检"代替"投票"）

Wang et al., *Self-Consistency Improves Chain of Thought Reasoning in Language Models* (ICLR 2023)，[arXiv:2203.11171](https://arxiv.org/abs/2203.11171)。
核心：多次采样取多数答案，以降低单次推理偏差。
映射：面向低成本长聊，**不每轮采样投票**；只在"自我一致性门禁"触发冲突时，做一次低成本复检（同 prompt 带档案再生成一次或用确定性规则比对），避免放大 token 成本与延迟。

### 2.5 自我认知与"镜像测试"类评估：只能测一致性，不能测意识

- Laine et al., *Me, Myself, and AI: The Situational Awareness Dataset (SAD) for LLMs* (NeurIPS 2024 D&B)，[数据集主页](https://situational-awareness-dataset.org/)，[mlanthology](https://mlanthology.org/neurips/2024/laine2024neurips-me/)：把"模型对自己身份/处境/能力的可测知识"做成题目集——**这类题是评估"自我陈述一致性"的正确工具，但作者也强调情境意识 ≠ 意识**。
- *I Ask About Myself, Therefore I Am: Defining and Designing Machine Self-Awareness*，[Academia.edu 页面](https://www.academia.edu/130038107/I_Ask_About_Myself_Therefore_I_Am_Defining_and_Designing_Machine_Self_Awareness)；同类 benchmark 讨论见 [scirate/arxiv 2502.05007](https://scirate.com/arxiv/2502.05007)。
- 映射：本项目可建**本地镜像测试集**（`data/self_statement_scenarios.json`）：问题集只验证"档案-响应-门禁"三方一致，题目措辞与 SAD 对齐；结果**只用于工程验收，绝不解释为意识证据**（与 `docs/head/HEADCORE_COGNITIVE_ARCHITECTURE.md` 对盲评结果的措辞纪律一致）。

### 2.6 叙事身份（narrative identity）与持久 agent

*Sophia: A Framework for Persistent LLM Agents with Narrative Identity and Self-Development*，[arxiv 2512.18202 网页版](https://arxiv.org/html/2512.18202v1)；叙事自我相关综述见 [ACM DL 3795011.3797152](https://dl.acm.org/doi/full/10.1145/3795011.3797152)。
核心：用"自传体叙事"（我是谁、经历过什么、坚持什么）作为跨会话人格锚点。
映射：本项目档案的 `identity_summary/values/boundaries` 就是最小化叙事锚点；但**叙事必须由系统低频合成、证据可溯源，不允许模型在对话中自由扩写自我**。

## 3. 机制包：5 个组件（落地方案）

总原则：**默认全部关闭/零行为变化；数据只走现有 `ChatRepository` 记忆边界（新增 `head_* 内部类型`），第一阶段不新增数据库表；所有组件确定性可测，模型参与为可选且输出必须过 schema 校验。**

### 3.1 a) 持久自我档案 SelfProfile

- **新文件**：`app/head/self_profile.py`（契约 + 白名单校验 + 渲染）+ `app/head/self_profile_store.py`（读写）。
- **数据**：`memory_type="head_self_profile"` 单条 JSON（沿用 `head_task` 的模式：写新值、读最后一条）。字段白名单：
  - `schema_version`、`revision`（递增）、`updated_at`（ISO+时区）、`last_session_at`（ISO 或 null）
  - `identity_summary`（≤120 字，只写"我是胡桃/人格一致性要点"）
  - `values`（≤5 条短句：如"回复短而自然""关系有边界"）
  - `boundaries`（≤5 条：如"不证明自己有真实意识""不猜测用户隐私"）
  - `capabilities_known`/`uncertainties_known`（≤3 条各）
  - `source_stats`（最近反思的 evidence 计数，不含证据原文）
- **禁止**：用户原话、称呼、真实地址/账号、情绪标签推测、任何隐私文本。
- **写入方**：只有系统（反思循环 3.3）与显式重置命令；每字段长度与 JSON schema 校验失败即拒绝写入（参照 `cognitive_facts` 的校验纪律）。

### 3.2 b) 会话开头自我投影 SelfProjection

- **位置**：`chat_service._prepare_chat` 中 `render_head_projection` 之后（L836-838 附近），新增 `render_self_profile_projection`（放 `app/head/self_profile.py`）。
- **内容**：档案要点 3-6 行 + "上次对话=YYYY-MM-DD，距现在约 N 天/小时"（由 `last_session_at` 计算）+ 明令"这是内部一致性信息，不向用户复述、不宣称意识"。
- **关键差异**：现有 `render_continuity_timeline` 是"本轮快照"；本投影是"**跨会话档案**"。
- **兜底**：档案不存在/损坏 → 渲染空串（`""`），行为与今天完全一致（`resolve_persona_profile` 静态人格继续兜底），**保证现有 814 测试零影响**。

### 3.3 c) 事后反思循环 OfflineReflection

- **新文件**：`app/head/reflection_loop.py`（纯函数聚合器）+ `scripts/run_self_reflection.py`（脱机脚本；默认不在请求路径）。
- **输入**：最近 N 个 `head_feedback` + `head_last_action` + 短期自适应策略统计（全部已有、已脱敏）。
- **输出**：只写 3.1 白名单字段 + 一条 `head_reflection_audit`（时间/修订号/变更字段/evidence 计数）；**不写用户内容、不调世界工具、不请求网络**。
- **两级实现**：L1 规则聚合（确定性，借鉴 Generative Agents reflection 的"从原始记录合成高层结论"，但结论模板化）；L2 可选模型提炼（开关 `SELF_PROFILE_REFLECTION_ENABLED=false` 默认关，模型输出必须过白名单校验，违规即丢弃——与 `calibration.py` 的字段校验同一风格）。
- **触发频率**：≥20 轮且新 feedback ≥3 条才考虑；单次只允许修订 ≤2 个字段，防止一次性漂移（Letta 自编辑教训）。

### 3.4 d) 自我一致性门禁 SelfConsistencyGate

- **新文件**：`app/head/self_consistency.py`；在 `app/services/response_evaluator.py` 的现有门禁链之后注册（只读档案，不改变现有身份一致性/自伤拦截/关系边界的判定顺序）。
- **判定**：响应 vs 档案的确定性比对（身份自述、价值观、边界、能力声明关键词 + 档案字段）。
  - 轻微矛盾（语气漂移）→ 不拦截，写 `head_self_conflict` 审计 + 附注提示。
  - 严重矛盾（否定人格/谎称能力/违背档案边界）→ 进入 `PersonaMode.REPAIR` 修复路径（复用现有 repair 策略，不发明新拦截）。
- **硬性优先级**（写入代码注释与测试）：自伤/死亡拦截、关系与隐私边界、记忆撤销 **永远优先于**"自我一致性"；一致性门禁**不得**复活被撤销的记忆、不得否决安全门禁的替换输出。
- **成本**：默认规则比对 0 次额外模型调用；可选模型复检（Self-Consistency 思路的降级版）默认关。

### 3.5 e) 时间感 TemporalSense

- **现状**：`render_continuity_timeline` 已输出"当前时刻=Asia/Shanghai"。
- **扩展**：`self_profile_store` 在每次会话结束写 `last_session_at`；会话开头投影"上次对话与间隔"（3.2）。若档案不存在，退化路径：`repository.list_recent_messages(limit=1)` 的最新消息时间作为近似（**不新增存储**）。
- **数据**：只存时间戳与间隔，不存"上次说了什么"（那是记忆系统的职责，不复制）。

### 3.6 对现有 814 测试的影响（逐项）

| 机制 | 新测试文件 | 现有测试影响 |
| --- | --- | --- |
| a 档案 | `tests/head/test_self_profile.py`（schema 校验/白名单拒绝/修订号/隔离） | 无（新 memory_type 不影响现有 `list_memories` 断言） |
| b 投影 | 并入上述 + `test_chat_service.py` 补 1 条"档案空→prompt 不变"断言 | 现有 prompt 断言靠"档案不存在渲染空串"保持全绿 |
| c 反思 | `tests/head/test_reflection_loop.py` + `test_eval_scripts.py` 加脚本冒烟 | 无（脱机脚本） |
| d 门禁 | `tests/test_response_evaluator.py` 新增 gate 用例；`tests/head/test_self_consistency.py` | 现有身份一致性/自伤/边界测试**顺序不变**，需回归确认 0 失败 |
| e 时间感 | 并入 a | 无 |
| 评估集 | `data/self_statement_scenarios.json` + `scripts/evaluate_self_consistency.py`（仿 `evaluate_head_planning.py`） | 无 |

默认全关 → 现有 814 测试应保持全绿；新增测试预计 +25~40 条。

## 4. 伦理红线（必须执行，写入实现与文档）

1. **不宣称真实意识/情感/权利**：所有对外文案、prompt 与代码注释统一措辞为"工程化的一致性机制"；镜像测试/SAD 类评估结果只能作为一致性指标，严禁在任何文档或对话中解释为意识证据（现有 `SCENE_INSTRUCTIONS[IDENTITY_CHALLENGE]` 的"不要证明自己有真实意识"继续作为模型指令保留）。
2. **不欺骗用户**：不引导用户相信它是真人、不伪造"有身体/有实时感知/记得一切"；**自我档案只由系统低频更新，用户可查看（read-only 导出）与一键重置**（重置=删除 `head_self_profile`，回到静态人格兜底）；档案修订全部留审计。
3. **安全与边界门禁优先于自我一致性**：自伤拦截、关系/隐私边界、记忆撤销永远高于档案一致性；一致性门禁不得复活撤销内容、不得弱化安全替换。
4. **合规提醒**：作为面向中国用户的生成式 AI 服务，需遵守《[生成式人工智能服务管理暂行办法](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)》（2023-08-15 施行：内容安全、真实准确、个人信息保护、不得生成虚假有害信息；提供者义务与安全评估）；涉及未成年人时遵守《[未成年人网络保护条例](https://www.gov.cn/zhengce/content/202310/content_6911288.htm)》（2024-01-01 施行：内容过滤、防沉迷、防诱导）；若对外提供合成的语音/形象，参照《[互联网信息服务深度合成管理规定](https://www.cac.gov.cn/2022-12/11/c_1672221949354811.htm)》的标识与安全评估义务。上线前应由负责人按最新版本逐条核对（本文链接为官方发布页，条款以官方现行文本为准）。

## 5. 实施顺序建议

- L0：`self_profile.py` + `self_profile_store.py` + 单元测试（纯增量，零行为变化）。
- L1：会话开头投影 + 时间感（档案不存在时输出空串，先保 814 全绿）。
- L2：一致性门禁（只读档案、规则版、加回归测试）。
- L3：反思脚本 + 审计 + 自我陈述评估集（脱机，验收后决定是否开默认）。
- 全程遵循 `docs/persona-training-plan.md` 的"先规则、先样本、后训练"路线，不因本机制包引入任何微调。

## 6. 参考链接

1. Generative Agents（Park et al., UIST 2023）— https://arxiv.org/abs/2304.03442 ；https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/ ；https://github.com/joonspk-research/generative_agents
2. Reflexion（Shinn et al., NeurIPS 2023）— https://arxiv.org/abs/2303.11366 ；https://neurips.cc/virtual/2023/poster/70114
3. MemGPT/Letta（Packer et al., 2023）— https://arxiv.org/abs/2310.08560 ；https://github.com/letta-ai/letta ；https://docs.letta.com
4. Self-Consistency（Wang et al., ICLR 2023）— https://arxiv.org/abs/2203.11171
5. Situational Awareness Dataset（Laine et al., NeurIPS 2024）— https://situational-awareness-dataset.org/ ；https://mlanthology.org/neurips/2024/laine2024neurips-me/
6. 机器自我意识定义与设计讨论 — https://www.academia.edu/130038107/I_Ask_About_Myself_Therefore_I_Am_Defining_and_Designing_Machine_Self_Awareness ；https://scirate.com/arxiv/2502.05007
7. Sophia：持久 LLM agent 的叙事身份 — https://arxiv.org/html/2512.18202v1 ；https://dl.acm.org/doi/full/10.1145/3795011.3797152
8. 《生成式人工智能服务管理暂行办法》— https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm
9. 《未成年人网络保护条例》— https://www.gov.cn/zhengce/content/202310/content_6911288.htm
10. 《互联网信息服务深度合成管理规定》— https://www.cac.gov.cn/2022-12/11/c_1672221949354811.htm
