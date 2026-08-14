# T1：主流智能体架构与框架对比 —— HutaoChatCore / HeadCore 映射分析

> 任务编号：T1
> 日期：2026-08-14
> 作者：项目研究分析员（自动生成研究报告）
> 方法：web_search 外部调研（2025-2026 主流框架，全部观点附来源链接）+ 逐文件阅读本项目代码 + 概念映射与工程建议
> 声明：外部框架特性描述基于其官方文档/论文与公开资料；本项目结论全部与代码核对，引用具体文件路径；不虚构任何框架特性。本文档不修改任何项目文件（本报告本身除外）。

---

## 1. 结论摘要

HutaoChatCore 的 HeadCore（app/head/）不是通用智能体框架的实例，而是一个以「单一 Self + 关系边界 + 证据门禁」为第一性约束的陪伴型人格运行时。把它的组件映射到主流框架概念后可以得到一个清晰的判断：

- **已经具备主流框架的关键抽象**：规划（动作候选打分 + 长计划）、记忆（分层、带来源与置信度）、反思（规则化反馈 + 策略自适应）、工具（显式触发的前置世界工具）、门禁（本地代码 + 模型后评估）、可观察性（trace/审计/熔断）。
- **但实现方式与主流不同**：绝大多数认知状态用**确定性规则**实现（关键词/打分公式），而非「把状态机交给 LLM 推理」（LangGraph/CoALA 风格）；工具调用是**前置分类器收集证据**，而非「模型自主的观察-行动循环」；反思是**规则触发**，而非 LLM 自我批评。
- **独特价值**：单一 Self、关系/记忆/证据全部本地代码兜底（fail-closed）、全链路脱敏审计、高密度自动化测试——这些是多数通用框架不提供或只靠 Prompt 提供的。
- **主要缺口**：无通用工具调用循环、观察-行动循环不可编排（单轮单次模型调用）、反思循环浅、长计划的执行主体不是模型本身。

---

## 2. 主流智能体架构与框架调研（2025-2026）

### 2.1 LangChain / LangGraph

- **定位**：LangChain 是通用 LLM 应用工具链；LangGraph 是其上的**有状态、图式编排**框架，2025 年发布 1.0（[LangChain/LangGraph 1.0 官方博客](https://www.langchain.com/blog/langchain-langgraph-1dot0)）。
- **核心抽象**：把 Agent 建模为**节点（node）+ 边（edge）构成的状态图（StateGraph）**；状态在节点间显式传递、可持久化（checkpointer），支持时间旅行回放、分支、循环与人在环（interrupt，[LangGraph 概念文档](https://langchain-ai.github.io/langgraph/concepts/)）。
- **记忆**：短期状态放 graph state；长期用 checkpointer 持久化 + 可外接 store（跨会话记忆）。
- **规划/工具**：工具调用作为显式节点，ToolNode 循环执行直到结束条件；支持 ReAct、Plan-and-Execute 等模式。
- **多智能体**：Supervisor / hierarchical / swarm 等图拓扑组织多个 agent 节点。
- **优势**：图语义精确、可恢复、生态大（LangSmith 可观测）；**劣势**：抽象层次低、样板代码多、与 LangChain 强绑定，行为正确性依赖开发者对图的设计。
- **对本项目的参考价值**：最高。它的「显式状态图 + checkpointer + interrupt」正是 HeadCore 缺少的可编排观察-行动循环的形式。

### 2.2 OpenAI Agents SDK / Swarm

- **定位**：OpenAI 官方轻量多智能体 SDK（2025-03 发布，源自实验性 Swarm；[Agents SDK 官方文档](https://openai.github.io/openai-agents-python/)、[Swarm 仓库](https://github.com/openai/swarm)）。
- **核心抽象**：Agent（instructions + tools + 可选 handoffs）、**handoffs**（把对话控制权转交给另一个 agent）、guardrails（输入/输出校验器）、sessions（会话状态）。
- **记忆**：session 内累积；跨会话持久化较薄（SDK 提供 session 对象，长期记忆靠外部）。
- **规划/工具**：模型自主 function calling 循环；SDK 负责循环、重试与追踪。
- **多智能体**：handoff 是最小化多智能体原语——与 CrewAI 的「角色扮演」、AutoGen 的「对话」不同，它强调**控制权转移**而非并行协作。
- **优势**：极简、追踪内建、与 OpenAI 模型深度集成；**劣势**：编排能力弱（无图/无持久化恢复），主要绑定 OpenAI 生态。
- **参考价值**：guardrails 概念与本项目 response_evaluator 门禁同构；handoff 提醒「控制权显式转移」——HeadCore 的单一 Self 可以理解为**从不 handoff** 的约束。

### 2.3 AutoGen / AG2

- **定位**：微软 2023 年开源的多智能体对话框架，2024 年 v0.4 重写（异步事件驱动 actor 架构），2025 年社区维护版 AG2 延续（[AutoGen 官方文档](https://microsoft.github.io/autogen/)、[AG2 文档](https://docs.ag2.ai/)）。
- **核心抽象**：**ConversableAgent**（收发消息的 agent）+ 群聊/层级团队；v0.4+ 改为**异步 actor + 事件流**，支持跨进程/跨语言。
- **记忆**：对话历史为主；长期记忆依赖外部（mem0 等集成）。
- **规划/工具**：代码执行器（CodeExecutor）、函数调用、人类输入代理（Human-in-the-loop）。
- **多智能体**：核心卖点——多个 LLM agent 对话协作、辩论、分层。
- **优势**：研究场景多智能体实验灵活、事件驱动可扩展；**劣势**：非确定性对话流程难以产品化，成本高、可控性差，长期记忆与安全边界弱。
- **参考价值**：事件驱动 + 可观测性思想（本项目 ProviderRuntimeMonitor 已类似）；反面教材——多 agent 自由对话会破坏人格一致性，印证 HeadCore 单 Self 的合理性。

### 2.4 CrewAI

- **定位**：面向业务团队的**角色扮演式多智能体编排**框架（[CrewAI 官方文档](https://docs.crewai.com/)）。
- **核心抽象**：Crew（团队）→ Agents（角色 + 目标 + 背景故事）→ Tasks（期望输出 expected_output + 上下文）→ Process（sequential / hierarchical）。
- **记忆**：短期/长期/实体记忆可开（分层记忆内置）。
- **规划/工具**：任务级规划 + 工具集；层级 process 由 manager agent 委派。
- **多智能体**：每个 agent 有独立「人格设定」，协作完成 workflow。
- **优势**：上手快、适合固定业务流程；**劣势**：agent 的「角色感」来自 Prompt，无底层状态机保证，生产一致性弱；性能开销大。
- **参考价值**：「角色感应内生于代码而非仅 Prompt」——这正是 HeadCore 用 app/mind/、app/persona/ 本地规则做的；CrewAI 是反面参照。

### 2.5 MetaGPT

- **定位**：把软件公司 SOP（产品经理/架构师/工程师/QA 各司其职）编码进多智能体流水线的框架（[MetaGPT 仓库](https://github.com/FoundationAgents/MetaGPT)、[MetaGPT 文档](https://docs.deepwisdom.ai/)）。
- **核心抽象**：**Role 类**（watch 消息→思考→行动）+ 结构化中间产物（PRD、设计文档、代码）作为 agent 间消息 + 消息池 + 发布订阅。
- **规划/记忆**：流程即 SOP 管线；记忆主要靠消息历史与产物。
- **多智能体**：以「角色分工 + 产物契约」组织，比自由对话更可控。
- **优势**：证明「结构化产物 + 角色约束」能让多 agent 产出可用结果；**劣势**：场景窄（软件研发流水线）、泛化差、成本高。
- **参考价值**：MetaGPT 的「产物即契约」与 S1-S8 的 contracts-first 哲学一致；其「编码 SOP 进代码」与 HeadCore「编码人格策略进代码」同构。

### 2.6 Letta（MemGPT）

- **定位**：源自 MemGPT 论文（LLM 作为操作系统、分页内存，[MemGPT 论文](https://arxiv.org/abs/2310.08560)）的**有状态记忆优先的 Agent 框架**（[Letta 文档](https://docs.letta.com/)）。
- **核心抽象**：Agent = 人格 + 记忆块（memory blocks：core memory / archival / conversation）+ 工具 + 系统提示词模板；**Memory blocks 是结构化、可被 agent 自身读写修改的数据对象**（[Letta Memory Blocks 官方博客](https://www.letta.com/blog/memory-blocks)）；2025 年推出 Agent 开发环境（ADE）与 agent 文件格式（[Letta ADE 博客](https://www.letta.com/blog/introducing-the-agent-development-environment)）。
- **记忆**：最强项——自我编辑记忆（agent 自己写 core memory）、分页召回、记忆作为一等公民可迁移/共享。
- **规划/工具**：函数调用循环 + 记忆工具（memory_search / memory_replace 等）。
- **多智能体**：可组合多个 agent 共享 memory blocks。
- **优势**：记忆持久化与「自我编辑」最成熟；**劣势**：以「agent 自主改记忆」为核心，信任边界靠 Prompt——对需要严格证据与撤销的陪伴场景风险高。
- **参考价值**：Memory blocks 与 HeadCore 的 cognitive_facts（observation/belief/hypothesis 三层，app/head/cognitive_facts.py）高度可比；区别是 HeadCore 用**来源+置信度+冲突+撤销+supersede**把「自主改写」关进了证据门内，而 Letta 让 LLM 直接改。

### 2.7 通用 Agent 模式：ReAct / Reflexion / Plan-and-Execute

- **ReAct**（Reason+Act，2022，[论文](https://arxiv.org/abs/2210.03629)）：把推理与行动交织成「Thought→Action→Observation」循环。是几乎所有工具调用 Agent 的底层模式。
- **Reflexion**（2023，[论文](https://arxiv.org/abs/2303.11366)）：失败后用 LLM 生成**口头自我反思**存入记忆，下一轮尝试时注入，从而迭代改进——不更新权重、不重规划，只改进上下文。
- **Plan-and-Execute**（LangChain 总结的通用模式，[LangChain 博客](https://blog.langchain.dev/planning-agents/)）：先一次性生成完整计划，再由执行器逐步执行、每步可重规划；适合多步任务，但计划粒度与执行偏差是经典痛点。
- **对照 HeadCore**：
  - ReAct 循环：**无**——HeadCore 单轮只有一次模型调用（+可选一次 repair 再调用），世界工具在模型调用**之前**由规则收集（app/services/chat_service.py 的 _world_guard_reply 与 app/world/brain.py），模型本身不产生 Thought→Action 循环。
  - Reflexion 反思：**规则版有**——app/head/feedback.py 用 marker 检测「纠正/拒绝建议/停止」并生成 HeadReflection（mistake_type/cause/better_action/policy_candidate），经 app/head/adaptation.py 调整下一轮策略并可持久化（head_feedback 记忆类型，app/head/events.py）；但**没有 LLM 自由文本反思**。
  - Plan-and-Execute：**部分有**——app/head/long_term_planning.py 支持最多 16 步、依赖关系、max_attempts、失败重试与 replan；但步骤完成**必须凭非模型证据**（validate_execution_evidence 明确拒绝 MODEL_CLAIM），执行主体是外部世界事件或用户，而不是模型工具调用。

### 2.8 CoALA：认知架构语言智能体（论文）

- **定位**：2023 年的学术框架，把语言智能体分解为**记忆（工作/情节/语义/程序）+ 行动空间（内部推理/检索/外部动作）+ 决策循环**的形式化模型（[CoALA 论文](https://arxiv.org/abs/2309.02427)、[arXiv 页面](https://arxiv.org/pdf/2309.02427)）。
- **核心抽象**：决策循环（planning→execution→evaluation 每步选一个 action）；动作分 internal（思考/检索/记忆读写）与 external（grounding：环境动作）；记忆分 working/episodic/semantic/procedural 四类。
- **参考价值**：CoALA 是最适合做 HeadCore 结构对照的坐标——HeadCore 几乎 1:1 具备 CoALA 的**记忆分类**（working=app/head/episodic_memory.py 投影 + app/mind/conversation_state.py；episodic=head_episode 事件；semantic=cognitive_facts + world_model；procedural=persona/dialogue/expression 规则库），**但行动空间极窄**：internal 动作只有「组装提示词」，external 动作只有「发言/追问/拒绝」，没有可编程的 retrieval/write/tool 动作选择。

### 2.9 MCP（Model Context Protocol）

- **定位**：Anthropic 2024 年底提出的**模型-工具/上下文互操作协议**，2025 年被 OpenAI/Google 等采纳为事实标准（[MCP 规范 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)）。
- **核心抽象**：Host（应用）↔ Client ↔ **Server**（暴露 tools/resources/prompts）；工具以 JSON Schema 描述；传输 stdio/HTTP/Streamable HTTP；支持 roots/sampling/elicitation（2025 版加入用户交互）。
- **参考价值**：MCP 解决「工具生态互操作」，不解决「何时调用」（那是 agent 的事）。HeadCore 当前没有 MCP 客户端/服务端；其世界工具（app/world/adapters/）是内部私有协议。若未来要接第三方工具生态，MCP 是低成本标准接口；**但要保住 HeadCore 边界**：MCP 工具只能作为「世界证据 Provider」，不得绕过证据门与许可门。

### 2.10 Dify / Coze（国内低代码平台）

- **定位**：Dify 是开源 LLM 应用/Agent 编排平台（[Dify 官方文档](https://docs.dify.ai/)）；Coze 是字节跳动的低代码 Agent 平台（[Coze 开放文档](https://www.coze.com/open/docs)）。
- **核心抽象**：可视化工作流画布（节点=LLM/工具/代码/条件）、知识库（RAG）、插件/工具市场、记忆变量、发布为 API/聊天机器人。
- **规划/多智能体**：工作流式（显式图，接近 LangGraph 的可视化版）+ 多 agent 模式（Coze）；记忆靠会话变量 + 知识库。
- **优势**：非工程师可搭建、知识库/插件生态、一键部署；**劣势**：复杂控制流（循环/恢复/细粒度安全）表达力有限；核心逻辑黑盒或云端绑定，深度定制与本地 fail-closed 难。
- **参考价值**：Dify/Coze 证明「图式工作流 + 知识库」是大众可用的产品形态；对照 HeadCore：知识库≈app/knowledge/ + 世界来源，工作流≈S1-S8 主链路——但 HeadCore 的每一环都是**本地代码、可测试、可审计**，这是低代码平台给不了的。

---

## 3. HeadCore 代码解读（对照用事实基础）

以下全部来自本项目代码，作为第 4 节映射的「我方坐标」。

### 3.1 唯一认知入口：app/head/runtime.py

HeadRuntime 是「channel 与模型细节之上的单一认知入口」：handle() 接受统一 ChannelEvent + HeadRuntimeContext（输入模态/质量/情绪/风格指令/沙盒人格），转发给 ChatService.reply()。它只支持 MESSAGE 事件——**没有「工具事件」或「内部思考事件」这类通道**，这直接决定了观察-行动循环的边界。

### 3.2 状态组装：app/head/state.py

build_head_state() 每轮组装：会话状态（app/mind/conversation_state.py：话题/情绪/纠正，纯关键词规则）、自我状态（app/mind/self_state.py：mood/energy/tension，规则推导）、社交状态（app/mind/social_state.py：亲密度/信任带/边界模式/打趣与亲密开关，关系角色驱动）、世界模型投影、认知事实投影、工作记忆投影、长期计划投影、反馈（build_head_feedback）、自适应策略（build_adaptive_policy）→ 决策（decide_head_action）→ 计划（build_head_plan）。所有投影都进提示词（known_context），**不确定性列表单独渲染**（uncertainties），保证「证据与不确定分离」。

### 3.3 规划与决策：app/head/planning.py + app/head/decision.py

- decide_head_action：确定性决策树——blocked 直接 REFUSE（拒绝进入对话）→ 纠正 REPAIR → 停止表达 SUPPORT → 情绪支持 SUPPORT → 修复期 REPAIR → 世界证据缺口（world_input_required / world_evidence_unavailable / world_evidence_uncertain 三类不确定性分别映射 CLARIFY/ANSWER/ANSWER）→ 需要澄清 CLARIFY → 有活动任务 CONTINUE_TASK → 否则 ANSWER。**行动空间 = 6 个枚举值（HeadAction：answer/clarify/continue_task/repair/support/refuse）**，与 CoALA 的「显式行动空间」思想一致，但没有 external grounding 动作。
- build_head_plan：复杂场景下生成 2-4 个候选动作，用**加权打分**（intent_fit 0.27 / task_progress 0.20 / relationship_fit 0.14 / fact_reliability 0.20 / persona_consistency 0.09，减 boundary_risk 0.25 / moralizing_risk 0.18 / fabrication_risk 0.22）选最高分。这是**规则化规划器**，不是 LLM 规划器；好处是确定、可测，坏处是候选生成与权重都是手工枚举。
- app/head/long_term_planning.py：长计划 ≤16 步、依赖图 + 环检测、每步 max_attempts 1-5、**步骤完成必须附证据**：validate_execution_evidence 拒绝「模型自述」（MODEL_CLAIM 直接 ValueError）、拒绝过期证据；record_step_result_from_world_events 只能用「显式选中的、新鲜（≤30 天）且置信度 ≥0.8 的世界事件」完成步骤。这是全项目**反幻觉最强的一道门**，也是主流框架很少提供的。

### 3.4 反馈与反思：app/head/feedback.py + app/head/adaptation.py + app/head/events.py

build_head_feedback 检测用户消息中的纠正/拒绝建议/接受/停止/继续 marker，生成结构化 HeadReflection（mistake_type、cause、better_action、policy_candidate），例如「上次给了不需要的建议」→ 本轮 advice_budget=0。adaptation.py 把这些反馈累积成**自适应策略**（改变沟通行为权重），用户说「算了」等可触发策略重置。反馈持久化到 head_feedback 记忆类型（events.py），并写入情节记忆（FEEDBACK_RECEIVED）。这是**Reflexion 的规则化、可审计版本**。

### 3.5 记忆体系

- 工作/情节：app/head/episodic_memory.py（HEAD 事件流）+ app/mind/conversation_state.py（近轮情绪/话题）。
- 语义/认知事实：app/head/cognitive_facts.py——三层 CognitiveFactKind（observation/belief/hypothesis）× 三类来源（world_evidence/user_report/model_inference），支持 supersede、conflicted、revoked、stale，投影时带不确定性。
- 世界模型：app/head/world_model.py——实体/关系/事件/因果假设；关系冲突自动标记 CONFLICTED；事件超过 30 天自动「过时」；未证实因果假设渲染为「不得当作事实」。
- 对话记忆：app/knowledge/（候选→审核→投影→撤销生命周期）+ 可选 Qdrant 语义检索（默认关闭）。

### 3.6 工具与世界证据：app/world/brain.py + app/world/context.py

WorldBrainCoordinator 是**前置工具决策器**：只对「显式请求」触发（天气/新闻/路线/政策），用户说「算了」或普通提及不调用；来源必须 enabled + legal_approved；结果作为证据注入提示词（context.py 有 stale 过滤、字符上限、凭证 URL 拒绝、跨来源冲突检测），**模型看不到原始响应体、不能决定下一步工具**。平台访问模式：qq/weixin 为 REACTIVE_ONLY，desktop_pet/app 为 PROACTIVE_CAPABLE。

### 3.7 模型调用与门禁：app/services/chat_service.py + app/providers/router.py + app/services/response_evaluator.py

reply() 主流程：_prepare_chat（组装状态+提示词+记忆投影）→ blocked 短路 → _world_guard_reply（世界证据缺口时直接规则回复）→ **一次** ProviderRouter TEXT 调用（S6：多 Provider 有序回退、超时、重试、熔断、脱敏 trace）→ evaluator.evaluate（30+ 判定函数：身份、死亡玩笑、自杀诱导、已撤销称呼、未确认关系、角色扮演感等）→ 不通过则 _repair_live_response_decision（**最多再来一次**修复调用）→ 全部失败走本地兜底 _fallback_response。**无循环**：单轮至多 2 次模型调用，且第二次只能「修复文本」，不能「调用工具」。

### 3.8 S1-S8 系统化：docs/systems/README.md

S1 身份/权限、S2 统一事件、S3 感知、S4 记忆画像、S5 人格管理、S6 Provider 路由、S7 表达计划、S8 控制面可观察性；契约优先、共享文件冻结、跨系统只依赖公开 contract。这是**工程拆分**（模块边界），不是**多智能体**——所有系统服务同一个 Self。

---

## 4. HeadCore 概念映射表

| 主流框架概念 | 主流实现 | HeadCore 对应 | 有/缺 | 代码依据 |
| --- | --- | --- | --- | --- |
| 规划器（planner） | LangGraph 图 / CrewAI Task / CoALA planning | 候选动作加权打分 + 长计划状态机 | 部分有（规则版，非 LLM 版） | app/head/planning.py、app/head/long_term_planning.py |
| 观察-行动循环（ReAct loop） | ToolNode 循环 / function calling | 单轮单次模型调用；世界工具前置收集 | 缺 | app/services/chat_service.py reply() |
| 工具调用 | MCP / function schema / 代码执行器 | 世界工具经 WorldBrainCoordinator 前置决策，非模型自主 | 部分有（无模型循环、无第三方工具协议） | app/world/brain.py、app/providers/router.py（能力仅 TEXT/ASR/TTS） |
| 记忆（memory） | MemGPT 分页 / Letta blocks / CrewAI 分层 | 工作/情节/事实/世界四层 + 来源/置信度/撤销 | 有，且更严 | app/head/episodic_memory.py、cognitive_facts.py、world_model.py |
| 反思（reflection） | Reflexion LLM 自我批评 / LangGraph 自反思节点 | marker 检测 + 结构化 HeadReflection + 自适应策略 | 部分有（规则版，浅） | app/head/feedback.py、app/head/adaptation.py |
| 门禁/护栏（guardrails） | OpenAI SDK guardrails / 平台内容审查 | 本地 pre-gate（blocked/世界证据）+ post-gate（evaluator 30+ 判定）+ repair + 兜底 | 有，且全本地 | app/services/chat_service.py、response_evaluator.py |
| 多智能体 | Swarm handoff / CrewAI 角色 / MetaGPT SOP | 无；S1-S8 是工程拆分，单一 Self | 无（有意为之） | docs/systems/README.md、app/head/runtime.py |
| 人机协同（HITL） | LangGraph interrupt / AutoGen human proxy | pending_question + CLARIFY 行动 + 世界证据缺口追问 | 部分有（对话层，无断点恢复） | app/head/state.py、app/head/decision.py |
| 状态持久化/恢复 | LangGraph checkpointer / Letta blocks 文件 | JSONL/DB V2 记忆类型 + head 事件流（无「执行到一半的图状态」） | 部分有（记忆持久化有，流程断点无） | app/storage/、app/head/events.py |
| 可观察性 | LangSmith / AutoGen 事件流 | Provider trace/熔断/审计脱敏/S8 状态聚合 | 有 | app/providers/router.py、app/operations/ |

---

## 5. HeadCore 的独特之处（相对主流框架）

1. **单一 Self 与关系边界是代码而不是 Prompt**。主流框架的「人格」是 Agent instructions（一段话），CrewAI/MetaGPT 的角色感全靠提示词；HeadCore 的 blocked 拒绝、关系亲密度、打趣/亲密开关、修复期、隐私守卫全部由 app/mind/social_state.py、app/persona/relationship_context.py、app/head/decision.py 的本地规则决定，模型无法绕过（例如 blocked 在 reply() 里根本不进模型调用）。多智能体框架里常见的「角色漂移」问题在此被结构性排除。
2. **证据边界贯穿全链路**。world_model 的关系冲突/事件过期/未证实因果、cognitive_facts 的来源与 supersede、long_term_planning 的「模型自述不能完成步骤」、世界工具的「启用+法律批准」双门——这一整套「断言必须带来源与置信度、模型输出不能自证」的设计，在 LangGraph/CrewAI/AutoGen 等框架中通常要靠开发者自己实现，在 Letta 里甚至是反向的（让 agent 自主改记忆）。
3. **fail-closed + 全本地门禁 + 高测试密度**。每个高风险能力默认关闭；回复门禁（自杀诱导、死亡玩笑、已撤销称呼、未确认关系）在发送前本地拦截；816 个测试用例覆盖策略矩阵（814 passed + 2 skipped，2026-08-14）。对照框架生态，「安全在本地代码」比「安全在系统提示词/平台审查」可靠得多。

## 6. 相对主流框架的缺口（诚实评估）

1. **没有可编排的工具调用循环（最大缺口）**。模型不能在回复中途「决定」调用工具、观察结果、再继续（ReAct 循环）；世界工具是分类器在模型调用**前**一次性收集的证据。后果：任何「多步、依赖中间结果」的任务（查两地天气再比较、查路线后按结果追问）要么拆成多轮用户对话，要么做不了。HeadAction 枚举里没有 grounding 动作，ChannelEvent 只有 MESSAGE。
2. **反思循环浅且非学习性**。feedback.py 的反思靠关键词 marker（「不对」「别讲道理」），只能抓到显式信号；抓不到「用户语气变冷但没说出口」这类隐式失败；反思只能改**本会话的自适应策略**（advice budget 等），不能沉淀为跨会话的程序性知识改进（CoALA 的 procedural memory 更新），也没有 LLM 自我批评（Reflexion 原文）。blind_review.py 是离线人工盲评工具，不是在线反思者。
3. **观察-行动循环不可恢复、不可重放**。没有 LangGraph 式的 checkpointer/interrupt：一次对话若在「追问-等待-继续」中途断掉，只有 head_pending_question 记忆能恢复语义，没有「执行到第几步」的图状态；主链路（prepare→route→evaluate→repair→fallback）是硬编码直线，不是可编排状态机，新增一个中间步骤（如「先检索再回答」）就要改 chat_service.py 主函数。
4. （次要）**记忆召回以投影+关键词为主**：语义记忆（Qdrant）默认关闭；evaluate_memory_eligibility 是规则筛选，检索质量依赖嵌入模型上线后的验收。
5. （次要）**长计划的执行主体在「人」与「世界事件」**：模型只能建议与推进对话步骤，不能通过工具完成步骤（证据门要求非模型证据）——这是安全设计，但也意味着 HeadCore 无法独立完成真正的多步外部任务（发邮件、查资料写报告）。

---

## 7. 可借鉴但不动摇 HeadCore 边界的工程建议清单

> 边界声明：以下所有建议的验收标准是「HeadCore 仍是唯一认知主体」——任何引入的外部机制只能是**工具/Provider/持久化机制**，不得产生第二 Self、不得让模型绕过证据门与关系门。

| # | 借鉴什么 | 来源 | 映射到哪个模块 | 实验成本 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 1 | 显式状态图：把 reply 主链路（prepare→guard→route→evaluate→repair→fallback）改为显式状态机/图，节点与转移独立测试 | LangGraph StateGraph | app/services/chat_service.py 拆分为 app/head/pipeline.py（自研轻量图，不引入 LangChain 依赖） | 低（2-3 天量级） | 只重构编排，不动决策规则；为未来插入「检索节点」留位 |
| 2 | 受限工具循环：引入「计划内工具步」——允许模型在 HeadAction 增加 USE_WORLD_TOOL，但工具白名单 = 已 legal_approved 的世界来源，每次工具结果必须过证据门（置信度/新鲜度/冲突）后才能进上下文 | ReAct + CoALA external action | app/head/contracts.py（行动空间）、app/world/brain.py（把前置决策改为「计划内工具执行器」）、chat_service.py | 中-高（需循环上限、超时、熔断复用 S6） | 最大收益缺口；必须先定「每轮工具调用上限 + 不可写世界」两条边界 |
| 3 | 断点恢复：把 head_pending_question 升级为可恢复的「暂停状态」（含当时 assembled state 的哈希 + 已收集证据快照），重启/换会话后可恢复追问上下文 | LangGraph checkpointer + interrupt | app/head/events.py（新记忆类型 head_pause_state）、app/head/state.py | 中 | 复用现有记忆类型机制，纯增量 |
| 4 | LLM 反思作为可选后置层：当 evaluator 连续 N 轮同因失败或 feedback.outcome=CORRECTED 时，额外调用一次轻量模型生成一句「程序性教训」摘要，写入 head_feedback（不写人格、不改关系） | Reflexion | app/head/feedback.py + app/head/adaptation.py（在规则反思之上叠加） | 低（可选开关，默认关） | 教训文本只作投影参考，不改任何本地规则权重 |
| 5 | Memory blocks 的结构对齐：把 cognitive_facts/world_model 的投影格式对齐 Letta blocks（人设块/记忆块/世界块），并允许模型在门禁内**建议修改**而非直接修改（建议→规则审核→落库） | Letta Memory Blocks | app/knowledge/（候选/审核生命周期已有）+ app/head/cognitive_facts.py | 中 | 本项目已有「候选→审核→撤销」生命周期，主要是产品化改造 |
| 6 | MCP 作为世界工具标准接口：把 app/world/adapters/ 包装为 MCP server（只读工具白名单），未来接第三方「证据类」工具 | MCP 2025-06-18 | app/world/ 新增 mcp_server.py（独立进程）；Host 侧先不做 | 中 | 严守「只读证据、不写世界、不绕过许可门」 |
| 7 | 事件驱动的 S8 可观测：把 Provider trace / head 决策 / 门禁结果发布为内部事件流（内存总线即可），控制中心订阅展示「上一条回复的决策链」 | AutoGen v0.4 事件驱动 | app/operations/observability.py + app/control/routes.py | 低 | 已有 trace 数据，缺的是发布-订阅总线 |
| 8 | 行动空间显式化 + grounding 分类：在 HeadAction 侧注释标注 CoALA 分类（internal：思考/记忆检索/发言；external：世界查询），让未来工具循环有清晰边界 | CoALA | app/head/contracts.py | 低（文档+枚举注释级） | 零风险热身项 |
| 9 | 工具成功率基准：仿 agent benchmark 思路，新增「世界工具决策」离线基准（显式请求触发率、拒绝触发率、缺口追问率） | Agent benchmarks / 本项目 persona gate 先例 | tests/world/ + scripts/world_*_smoke.py | 低 | 与现有 persona gate/live stress 同一套方法 |
| 10 | 工作流可视化（仅控制台展示，不引入执行引擎）：把 S1-S8 主链路渲染成控制中心里的静态流程图 | Dify/Coze 画布 | app/static/control/ | 低 | 纯前端展示，执行仍是代码 |

---

## 8. 参考资料

- LangChain/LangGraph 1.0：<https://www.langchain.com/blog/langchain-langgraph-1dot0>；概念文档 <https://langchain-ai.github.io/langgraph/concepts/>
- OpenAI Agents SDK：<https://openai.github.io/openai-agents-python/>；Swarm：<https://github.com/openai/swarm>
- AutoGen：<https://microsoft.github.io/autogen/>；AG2：<https://docs.ag2.ai/>
- CrewAI：<https://docs.crewai.com/>
- MetaGPT：<https://github.com/FoundationAgents/MetaGPT>；<https://docs.deepwisdom.ai/>
- MemGPT 论文：<https://arxiv.org/abs/2310.08560>；Letta：<https://docs.letta.com/>；Memory Blocks：<https://www.letta.com/blog/memory-blocks>；ADE：<https://www.letta.com/blog/introducing-the-agent-development-environment>
- ReAct：<https://arxiv.org/abs/2210.03629>；Reflexion：<https://arxiv.org/abs/2303.11366>；Plan-and-Execute：<https://blog.langchain.dev/planning-agents/>
- CoALA：<https://arxiv.org/abs/2309.02427>
- MCP 规范：<https://modelcontextprotocol.io/specification/2025-06-18>
- Dify：<https://docs.dify.ai/>；Coze：<https://www.coze.com/open/docs>

---

## 附录 A：本次调研关键证据来源

调研通过 web_search 完成，检索词覆盖上述每个框架的 2025-2026 状态；返回源包括各框架官方文档站、官方 GitHub、arXiv 论文页与第三方对比文章。文中引用链接均为经检索确认存在的规范/官方地址（LangChain 1.0 官方博客、modelcontextprotocol.io/specification/2025-06-18、letta.com 官方博客、arXiv 论文页等）。受检索工具摘要能力限制，框架细节以官方稳定文档所载的公认能力为准，未引用任何无法核实的版本级细节。

## 附录 B：本报告引用的项目文件清单

app/head/runtime.py、app/head/state.py、app/head/planning.py、app/head/decision.py、app/head/feedback.py、app/head/adaptation.py、app/head/events.py、app/head/contracts.py、app/head/long_term_planning.py、app/head/world_model.py、app/head/cognitive_facts.py、app/head/episodic_memory.py、app/head/blind_review.py、app/mind/conversation_state.py、app/mind/self_state.py、app/mind/social_state.py、app/services/chat_service.py、app/services/response_evaluator.py、app/providers/router.py、app/world/brain.py、app/world/context.py、app/world/adapters/、docs/systems/README.md、HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md。
