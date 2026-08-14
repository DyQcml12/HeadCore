# T5 世界模型与人类思维差距：研究分析报告

> 任务编号：T5（agent-architecture 研究系列 05）
> 分析对象：HutaoChatCore 的 HeadCore 世界模型层（app/head/world_model.py 及其配套）
> 撰写日期：2026-08-14
> 口径承诺：结论与当前代码一致（逐条引用文件路径）；只把"已实现"写为已实现；外部观点一律附链接。

## 0. 摘要

本项目文档已明确声明："世界模型在当前代码中是受证据、来源许可、缓存和显式意图约束的工具层"，"当前没有已训练、可自主模拟现实的通用世界模型"（见 docs/WORLD_MODEL_AND_PROJECT_CAPABILITIES.md 第 1 节、第 7 节）。本报告的结论与该声明一致，并从认知科学与 LLM 表征研究的证据出发，给出更精确的分界：

- **可被工程弥补的差距（3 条）**：外部事实校准、结构化世界状态与时间延续、不确定性/冲突管理与审计。
- **不可被当前范式弥补的根本差距（3 条）**：具身感知-行动闭环与因果干预、主观体验（现象意识）、常识默认与默会知识的地基。
- **升级路线**：现有"实体/关系/事件图"上叠加时间衰减与信念强度 → 规则引擎上的反事实推演（Hypothesize-Simulate-Verify 式）→ 与世界工具证据的自动校准 → 用固定评测集与盲评闭环验证。每步一个小实验与验收标准，见第 6 节。

核心判断：**LLM 的"世界模型"是语言分布里沉淀的、可被探针发现的内部表征，它是"模型世界（model world）"而不是对外部因果结构的可靠模拟器；本项目的工程方向（外部证据 + 结构化状态 + 时间/不确定性管理）正是当前范式下能把差距缩到最小的正确路线，但不应把接口聚合或内部表征包装成"世界模型"。**

---

## 1. 本项目世界模型层现状盘点（以代码为准）

### 1.1 内源性认知图（HeadCore 自有）

- app/head/world_model.py：第一版内存态认知图。WorldEntity / 带 valid_from、valid_until 的 WorldRelation / 按时间排序的 WorldEvent / CausalHypothesis 四类对象；构建时强制引用完整性、ISO-8601 时区时间戳、置信度 [0,1]；关系过期自动置 STALE，同一 (subject, predicate) 出现多个有效对象时置 CONFLICTED；事件超过 DEFAULT_EVENT_CONTEXT_MAX_AGE=30 天不再投影；未确认因果假设在投影中强制标注"因果假设(不得当作事实)"，确认因果要求证据且置信度 >= 0.8。
- app/head/world_model_store.py：带 schema 版本与容量上限（实体 64 / 关系 128 / 事件 128 / 假设 64）的跨进程快照持久化，损坏快照回退上一份有效版本。
- app/head/cognitive_facts.py：持久认知事实生命周期（active/conflicted/stale/revoked/superseded），版本取代、显式撤销、同键多值冲突检测；多来源一致事实按 1-Π(1-c_i) 强化为 BELIEF；每用户上限 64 条。
- app/head/world_evidence.py：世界证据到事实的"受控自动摄取"——目前只允许 WEATHER_CURRENT 能力、PUBLIC 敏感级、置信度 >= 0.8 的观察，且只落 condition/temperature/humidity 三个受限字段。
- app/head/world_state.py：把世界工具投影归为 known / uncertain / needs_input / unavailable / idle，can_answer 门禁决定能否陈述实时事实；uncertain 必须保留冲突，needs_input 必须追问。
- app/head/state.py：known_context 由认知事实 + 工作记忆 + 世界模型投影 + 长期计划拼接；uncertainties 汇总冲突/过期/未验证因果，进入决策与计划。

### 1.2 外源性证据工具（全部默认关闭、需许可）

- app/world/contracts.py：WorldObservation 固定 observed_at / expires_at / confidence / evidence / sensitivity；TTL 缓存与单飞合并。
- app/world/brain.py：确定性意图识别（明确请求才触发、opt-out 短语拒绝、平台 REACTIVE_ONLY 策略），不把完整用户消息发给外部源。
- app/world/runtime.py：天气/预报/行政区/地点/路线/新闻/政策按查询类型分缓存分区；精确位置与路线要求 consent_granted。
- docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md：明确"第一个有用的世界模型是状态估计器，不是训练出来的通用模拟器"，并规定视觉层只输出受限标签、不做人脸识别、不宣称情绪诊断。
- docs/head/HEADCORE_COGNITIVE_ARCHITECTURE.md 第三阶段：承认"尚未完成世界工具自动结构化摄取、实体合并、事件版本更新和通用时间/因果推理，因此仍不是完整学习型世界模型"。

**现状一句话**：项目已经具备一个"带证据与有效期的信念登记处 + 一个受控的外部取证管道"，但两者之间只有天气一条自动通路，认知图本身没有时间衰减、没有信念更新规则、没有反事实推演。

---

## 2. 认知科学基线：人类思维的"世界模型"是什么

- **Mental model 传统**：Craik (1943) 提出心智在内部构造与外部世界同构的小尺度模型，用来试演行动的后果；Johnson-Laird 的心智模型理论进一步把推理定义为对模型的操作而非对句法的操作（[Wikipedia: Mental model](https://en.wikipedia.org/wiki/World_models)；[Oxford Reference: mental model](https://www.oxfordreference.com/display/10.1093/oi/authority.20110803100150482)）。
- **预测加工 / 预测编码**：Rao & Ballard (1999) 证明视觉皮层可以用"生成模型自上而下预测 + 预测误差自下而上修正"来解释；Keller & Mrsic-Flogel (2018) 将其总结为皮层的规范计算（[Predictive Processing: A Canonical Cortical Computation, Neuron](https://www.cell.com/neuron/fulltext/S0896-6273(18)30857-2)）。
- **主动推理（active inference）**：Friston 把上述机制推广为自由能原理下的行动选择——智能体的行动就是"改变世界以符合自己的预测"，感知与行动是同一贝叶斯信念更新的两面（[Active inference and artificial reasoning, alphaXiv 2025](https://www.alphaxiv.org/overview/2512.21129)；[Semantic Scholar 条目](https://www.semanticscholar.org/paper/Active-inference-and-artificial-reasoning-Friston-Costa/064bf945ea1ee671db198a5a03dc6df3b104e876)）。

对人类模型的三个启示（也是本项目可工程化的方向）：

1. 模型的价值在于**试演（simulation for action）**，而不在于存储的多少；
2. 信念永远带**不确定性与有效期**，且随新证据更新；
3. 预测必须**接受外部世界的纠错**——感知误差是模型更新的唯一外部锚点。

---

## 3. LLM 内部"世界模型"的实证研究（2023–2026）

### 3.1 支持侧：确实存在可发现的内部表征

- **Othello-GPT**：Li, Hopkins, Bau 等人在合成棋局序列上训练 GPT，用探针在残差流中恢复了棋盘状态表征，且干预该表征会改变预测（[Emergent World Representations, ICLR 2023](https://mlanthology.org/iclr/2023/li2023iclr-emergent/)）。
- **空间与时间**：Gurnee & Tegmark 在 LLaMA-2 的激活中发现可线性解码的世界/空间/时间特征，说明预训练确实把世界的结构"编码"进了权重（[Language Models Represent Space and Time, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/0a6059857ae5c82ea9726ee9282a7145-Abstract-Conference.html)）。
- **心智状态几何**：Xiang 等人证明 Transformer 残差流中存在对"他者信念"的结构化几何表征，能在任务间迁移（[Transformers Represent Belief State Geometry in their Residual Stream](https://openreview.net/forum?id=YIB7REL8UC)；[BAAI 中文介绍](https://hub.baai.ac.cn/paper/3174fea4-7b7d-43d2-be64-23fe7d81dbfa)）。

### 3.2 反驳侧：表征 ≠ 可用的世界模型

- Neel Nanda 对 Othello-GPT 的再分析：线性表征确实存在，但"世界模型"一词被过度解读——它只是任务所需的压缩表征，不证明模型在做因果推理（[Actually, Othello-GPT Has A Linear Emergent World Representation](https://www.neelnanda.io/mechanistic-interpretability/othello)）。
- next-token 目标的下限：代码逻辑理解实验显示，预测下一个 token 并不自动带来逻辑/因果理解（[Is Next Token Prediction Sufficient for GPT? Exploration on Code Logic Comprehension](https://ar5iv.labs.arxiv.org/html/2404.08885v1)）；同方向的更近期证据见 [I Predict Therefore I Am, ICLR 2026](https://mlanthology.org/iclr/2026/liu2026iclr-predict/)。
- **Singleton Fallacy**：把整个 LLM 当作"一个在做一致推理的思想者"本身就是错的，模型内部没有单一、稳定的推理主体（[The Singleton Fallacy, Rogers 2021](https://ar5iv.labs.arxiv.org/html/2102.04310)）。
- 概念层批评：Mitrokhov 区分"模型世界（model world，从数据里拟合出的分布世界）"与"世界模型（world model，可干预、可承担因果责任的表征）"，指出二者在能动性意义上不可混用（[Between world models and model worlds, AI & Society 2024](https://link-hkg.springer.com/article/10.1007/s00146-024-02086-9)）。

### 3.3 差距的形成机制：幻觉与"无世界接触"

- **幻觉的不可消除性（信息论下界）**：Xu, Jain, Kankanhalli 证明对任意 LLM 都存在不可判定的事实类，幻觉有固有下界——只能工程压制，不能根除（[Hallucination is Inevitable, ICLR 2024](https://axi.lims.ac.uk/paper/2401.11817)；[Semantic Scholar 条目](https://www.semanticscholar.org/paper/Hallucination-is-Inevitable%3A-An-Innate-Limitation-Xu-Jain/5cd671efa2af8456c615c5faf54d1be4950f3819)）。
- **意义的地基**：Bender & Koller 论证纯形式训练得不到指称（referential meaning），语言模型是"形式与意义的统计映射"而非理解者（[Climbing towards NLU, ACL 2020](https://aclanthology.org/2020.acl-main.463/)）；Bisk 等提出"经验为语言奠基"——词义最终锚定在感知-行动经验上（[Experience Grounds Language, EMNLP 2020](https://arxiv.org/abs/2004.10151)）。
- **模拟世界的代价**：Genie 2 等视频世界模型展示了交互式生成，但评测边界存疑（[Ars Technica: Google's Genie 2 "world model" reveal leaves more questions than answers](https://arstechnica.com/ai/2024/12/googles-genie-2-world-model-reveal-leaves-more-questions-than-answers/)）；自回归视频世界模型还存在遗忘与纠缠的系统性失效（[From Masks to Worlds: A Hitchhiker's Guide to World Models](https://ar5iv.labs.arxiv.org/html/2510.20668)）。
- 综述性定论：[Understanding World or Predicting Future? A Comprehensive Survey of World Models, ACM Computing Surveys 2025](https://dl.acm.org/doi/10.1145/3746449)；具身智能三层框架（感知/世界建模/策略）的边界见 [Frontiers in Robotics and AI 2025](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1668910/full)；基础模型在决策上的不足见 [Foundation models and intelligent decision-making, ScienceDirect 2025](https://www.sciencedirect.com/science/article/pii/S2666675825001511)。

---

## 4. 诚实结论：哪些差距可被工程弥补，哪些是根本性的

### 4.1 可弥补清单（工程手段有效，且本项目已有地基）

**（1）外部事实校准与"无世界接触"幻觉**
机制：幻觉的根源之一是模型没有实时世界接触（见 3.3）。工程上可以用带来源、带有效期、带许可门的外部证据把"模型常识"替换为"检索到的证据"。
本项目已有：app/world/ 全套取证管道 + app/head/world_evidence.py 的受控事实摄取 + app/head/world_state.py 的 can_answer 门禁。
缺口：目前自动摄取只覆盖天气；其他能力（新闻/政策/路线）只投影不沉淀，模型仍可能用自己的过时知识回答。

**（2）结构化世界状态与时间延续**
机制：人类 mental model 的价值在于跨时间稳定 + 可更新（见第 2 节）。工程上可以用实体/关系/事件图 + 持久化 + 版本/过期/撤销来近似"连续一致的记忆"。
本项目已有：world_model.py 的认知图、world_model_store.py 的持久化、cognitive_facts.py 的事实生命周期。
缺口：图没有信念更新规则（无衰减、无新证据推翻旧关系的机制、无实体合并）。

**（3）不确定性、冲突与审计**
机制：预测加工的核心是"预测误差"被显式表征（见 2）。工程上可以把不确定性显式建模、把冲突显式标记、把来源全程留痕。
本项目已有：conflict 检测、uncertainties 投影、来源/证据/时间戳全链路、conf>0.8 才能成为"已确认"。
缺口：不确定性的数值只做了存储与阈值，没有贝叶斯式更新，也没有"信念强度随时间衰减"的机制。

### 4.2 不可弥补清单（当前范式的根本性缺口）

**（1）具身感知-行动闭环与因果干预能力**
人类世界模型的训练信号是"行动的后果"：推一下杯子、杯子倒了，预测误差立即回传。LLM 只有语言分布，没有可干预的外部世界，也没有"做实验"的权利——它只能读关于因果的文字，不能制造因果证据。因此 Othello-GPT 式的表征永远是旁观者表征，不是行动者表征（见 3.2、Bisk 2020）。本项目即便接了摄像头与 API，也只是"更广的旁观"，不等于拥有了行动者的因果模型。

**（2）主观体验与现象意识（qualia）**
预测加工解释的是"内容"，不是"被体验"这一事实本身；从第三人称的功能描述到第一人称的体验之间存在解释鸿沟，当前任何工程系统都无法被证明具有意识或感受。项目文档已正确声明："没有测试能证明它拥有意识、感受或与人类等同的思维"（docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md）。

**（3）常识默认与默会知识的"地基"**
人类的常识不是一条条命题，而是与身体、环境、社会互动的默会地基（tacit ground）：知道水会湿、知道人饿了会找吃的，靠的是共享的具身与生活形式，而不是词典。LLM 的"常识"是文本共现的统计投影，可以在语料覆盖范围内表现得像常识，但在地基断裂处（未见过的情境、反事实边界、跨模态因果）会系统性失效（Bender & Koller 2020；Hallucination is Inevitable 的下界也是这种断裂的一种形式）。

### 4.3 一张总表

| 差距 | 性质 | 工程手段上限 | 本项目对应层与现状 |
| --- | --- | --- | --- |
| 实时事实过时/幻觉 | 可弥补 | 证据检索 + 有效期 + 门禁 | app/world/ + world_evidence.py：已有，待扩展 |
| 时间延续与遗忘 | 可弥补 | 持久化图 + 衰减 + 版本 | world_model_store.py：已有骨架，缺衰减 |
| 冲突与不确定性 | 可弥补 | 显式不确定性 + 冲突标记 + 审计 | cognitive_facts.py：已有，缺更新规则 |
| 因果干预/试错学习 | 根本性 | 只能模拟有限的"纸面因果"，不能替代 | world_model.py 的 CausalHypothesis 只是登记 |
| 主观体验 | 根本性 | 不可工程化，只能诚实不宣称 | 文档已正确声明 |
| 常识地基/默会知识 | 根本性 | 语料覆盖内的近似，边界处必裂 | 依赖模型 Provider，非本项目可控 |

---

## 5. 升级路线：从"登记簿"到"带衰减与反事实的状态估计器"

> 原则（来自项目自己的文档）：每一步都保持"状态估计器"的定位（docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md）；训练预测/模拟类世界模型只有在有明确数据、目标、评估集、预算与安全边界后才讨论（docs/WORLD_MODEL_AND_PROJECT_CAPABILITIES.md 第 7 节）。因此以下路线全部是**确定性规则层**，不训练新模型。

### R1：时间衰减与信念强度（信念层）

- 目标：给 WorldRelation / WorldEvent / CognitiveFact 增加 recency 与 belief_strength，让旧信念自动降权、新证据自动升权。
- 文件落点（建议）：app/head/world_model.py 增加 decay 函数（如指数半衰期，参考 DEFAULT_EVENT_CONTEXT_MAX_AGE=30 天的现有语义）；app/head/cognitive_facts.py 的 resolve_cognitive_facts 增加按 expires_at 的强度衰减；投影排序由 confidence 改为 confidence×recency。
- 小实验：构造"30 天前的关系 vs 今天的关系"场景，断言投影只含新关系、旧关系进入 uncertainties 且带 world_event_stale 标记（复用现有 project_head_world_model 的 stale 逻辑扩展）。
- 验收标准：新增单元测试全过；投影结果随 now 参数变化可复现；全量 pytest 不回退（当前基线 814 passed, 2 skipped）。

### R2：反事实推演（Hypothesize-Simulate-Verify 的轻量版）

- 目标：在现有 CausalHypothesis 之上增加"反事实试演"：给定一个候选假设，用确定性规则模拟其最小后果，并与后续真实事件比对，未验证则降级、被否定则撤销。
- 文件落点（建议）：app/head/world_model.py 增加 CounterfactualTrial 结构（假设、触发事件、预期后果、horizon、confidence）；新模块 app/head/world_simulation.py 提供纯函数式微模拟（如"关系 A 断言后，若 7 天内出现事件 B 则支持，出现反例事件则否定"）。
- 小实验：用 data/head_planning_scenarios.json 同风格的固定 JSON 场景集（建议 data/world_model_counterfactual_scenarios.json）跑离线评估脚本；每个场景断言 trial 状态机（pending → supported / refuted / expired）。
- 验收标准：反例出现时假设必须被 refuted 且从"可投影"中移除；未验证假设在投影中仍带"因果假设(不得当作事实)"标签；评估脚本输出通过率与 margin，报告存入 logs/。

### R3：与世界工具证据的自动校准

- 目标：把"天气独享"的自动摄取（app/head/world_evidence.py）扩展到新闻/政策/路线；并实现双向校准——新世界观察可以推翻过期认知事实（通过版本取代 + 冲突标记，复用 cognitive_facts.py 已有机制），图内旧关系可与新事实对账。
- 文件落点（建议）：app/head/world_evidence.py 增加 per-capability 的字段白名单表（新闻→标题/日期/来源/摘要；政策→标题/日期/链接；路线→方式/时长/距离）；新模块 app/head/world_calibration.py 实现"事实↔观察"对账（同键新值 → 旧事实 SUPERSEDED；不同源冲突 → CONFLICTED；过期 → STALE）。
- 小实验：用假 adapter（复用 tests/world 的 fake runtime 风格）触发一次新闻摄取，断言产生带来源与有效期的认知事实；再触发一条冲突观察，断言旧事实进入 CONFLICTED 且不再进入 can_answer 投影。
- 验收标准：摄取仍遵守"PUBLIC + conf>=0.8 + 白名单字段"三道门；对账全流程离线可测；不把原文写入事实（沿用现有校验）。

### R4：评估闭环与诚实验收

- 目标：用固定评测集 + 盲评证明"行为可预测、来源可追溯"，而不是证明"会思考"。
- 小实验：建立 world-model 评测集（实体合并、时间衰减、反事实 refute、证据冲突四类，每类 5-10 例），脚本 evaluate_world_model.py 输出通过率；复用 persona/head 盲评流程做一次世界问题盲评（回答是否带来源、是否承认不知道、冲突是否保留）。
- 验收标准：评测报告落盘 logs/；盲评中"编造事实"为 0 例、"承认不知道"达阈值；最终验收报告仍按项目惯例声明"不构成对 AGI 或意识的主张"。

---

## 6. 参考文献与链接汇总

- Li et al., Emergent World Representations (Othello-GPT), ICLR 2023：<https://mlanthology.org/iclr/2023/li2023iclr-emergent/>
- Nanda, Actually, Othello-GPT Has A Linear Emergent World Representation：<https://www.neelnanda.io/mechanistic-interpretability/othello>
- Gurnee & Tegmark, Language Models Represent Space and Time, ICLR 2024：<https://proceedings.iclr.cc/paper_files/paper/2024/hash/0a6059857ae5c82ea9726ee9282a7145-Abstract-Conference.html>
- Xiang et al., Transformers Represent Belief State Geometry in their Residual Stream：<https://openreview.net/forum?id=YIB7REL8UC>；中文介绍：<https://hub.baai.ac.cn/paper/3174fea4-7b7d-43d2-be64-23fe7d81dbfa>
- Xu, Jain, Kankanhalli, Hallucination is Inevitable, ICLR 2024：<https://axi.lims.ac.uk/paper/2401.11817>
- Bender & Koller, Climbing towards NLU, ACL 2020：<https://aclanthology.org/2020.acl-main.463/>
- Bisk et al., Experience Grounds Language, EMNLP 2020：<https://arxiv.org/abs/2004.10151>
- Rogers, The Singleton Fallacy, 2021：<https://ar5iv.labs.arxiv.org/html/2102.04310>
- Mitrokhov, Between world models and model worlds, AI & Society 2024：<https://link-hkg.springer.com/article/10.1007/s00146-024-02086-9>
- Is Next Token Prediction Sufficient for GPT? Exploration on Code Logic Comprehension：<https://ar5iv.labs.arxiv.org/html/2404.08885v1>
- I Predict Therefore I Am, ICLR 2026：<https://mlanthology.org/iclr/2026/liu2026iclr-predict/>
- Understanding World or Predicting Future? A Comprehensive Survey of World Models, ACM Computing Surveys：<https://dl.acm.org/doi/10.1145/3746449>
- From Masks to Worlds: A Hitchhiker's Guide to World Models：<https://ar5iv.labs.arxiv.org/html/2510.20668>
- Ars Technica, Google's Genie 2 "world model" reveal：<https://arstechnica.com/ai/2024/12/googles-genie-2-world-model-reveal-leaves-more-questions-than-answers/>
- Keller & Mrsic-Flogel, Predictive Processing: A Canonical Cortical Computation, Neuron 2018：<https://www.cell.com/neuron/fulltext/S0896-6273(18)30857-2>
- Friston et al., Active inference and artificial reasoning, 2025：<https://www.alphaxiv.org/overview/2512.21129>
- A review of embodied intelligence systems, Frontiers in Robotics and AI 2025：<https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1668910/full>
- Foundation models and intelligent decision-making, 2025：<https://www.sciencedirect.com/science/article/pii/S2666675825001511>
- Wikipedia: Mental model：<https://en.wikipedia.org/wiki/World_models>
- 网易伏羲：行动中的认知：预测加工框架下的具身智能（中文综述）：<http://fuxi.netease.com/database/3010>

## 7. 项目内相关文档

- docs/WORLD_MODEL_AND_PROJECT_CAPABILITIES.md（能力边界与"不是世界模型"的官方口径）
- docs/LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md（"状态估计器"定位与诚实边界）
- docs/head/HEADCORE_COGNITIVE_ARCHITECTURE.md（第三阶段世界状态、长期目标与当前限制）
- app/head/world_model.py、world_model_store.py、world_state.py、world_evidence.py、cognitive_facts.py、state.py
- app/world/contracts.py、context.py、brain.py、runtime.py
