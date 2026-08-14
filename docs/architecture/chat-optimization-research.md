# 正常聊天优化研究方案

日期：2026-07-02

本文档只做方案研究，不改运行逻辑。目标是解决当前 QQ 私聊里“简单问题回复太长、语气不像真人、表情包/语音触发不自然”的问题。

## 结论

不要把正常聊天优化只做成提示词。更稳的结构是：

1. 对用户输入做轻量 NLU：场景、对话意图、情绪、技术/任务属性、是否需要追问。
2. 用 Dialogue Policy 决定本轮回复形态：短答、普通闲聊、任务说明、安慰、调侃、追问、表情包、语音。
3. 再调用 LLM 生成文本，并把长度、语气、是否可分段作为硬约束传入。
4. 生成后用本地质量门检查：长度、重复、客服腔、AI 自曝、舞台指令、和上一轮冲突。
5. 表情包和语音不要独立随机触发，要挂在同一个表达决策上。

## 可参考研究和数据

### DailyDialog

论文：DailyDialog: A Manually Labelled Multi-turn Dialogue Dataset

链接：https://arxiv.org/abs/1710.03957

价值：

- DailyDialog 是多轮日常对话数据集。
- 数据包含 communication intention 和 emotion 标注。
- 适合参考“日常聊天如何按意图/情绪做短回复和接话”。

本项目落地方式：

- 不直接训练大模型。
- 参考它的标签思想，建立本项目自己的 `dialogue_act` 与 `emotion` 枚举。
- 用规则 + 小模型/LLM 分类逐步替代当前散落的关键词规则。

### EmpatheticDialogues

论文：Towards Empathetic Open-domain Conversation Models: a New Benchmark and Dataset

链接：https://arxiv.org/abs/1811.00207

开源实现：https://github.com/facebookresearch/EmpatheticDialogues

价值：

- 数据集聚焦“识别对方情绪并做合适回应”。
- 对本项目的安慰、撒娇、陪伴场景有参考价值。

本项目落地方式：

- 把“情绪支持”从普通闲聊里拆出来。
- 对悲伤、压力、委屈、开心分享做不同回复策略。
- 表情包的 `support`、`celebrate`、`awkward` 触发可以与情绪策略共用。

### PersonaChat

论文：Personalizing Dialogue Agents: I have a dog, do you have pets too?

链接：https://arxiv.org/abs/1801.07243

价值：

- 解决开放域聊天里角色不稳定、回复泛泛、缺少个性的问题。
- 适合本项目“胡桃人格一致性”和“用户长期偏好记忆”。

本项目落地方式：

- 把角色规则分成稳定人格、场景策略、用户关系记忆三层。
- 回复评估器检查是否违背胡桃人设、是否过度 AI 自曝、是否忘记已确认关系。

### Meena / SSA

论文：Towards a Human-like Open-Domain Chatbot

链接：https://arxiv.org/abs/2001.09977

价值：

- 提出 Sensibleness and Specificity Average，关注回复是否合理、是否具体。
- 说明“像真人”不能只看流畅度，还要看是否接得上、是否有具体信息。

本项目落地方式：

- 增加本地聊天质量评分：
  - sensibleness：是否回答了用户这句话。
  - specificity：是否有具体回应而不是万能套话。
  - brevity：是否符合当前场景长度。
  - persona：是否符合胡桃风格。

### 对话系统工程框架

Rasa、Botpress、Microsoft Bot Framework、LangGraph 都有一个共同思想：对话不是单次文本生成，而是状态驱动的流程。

参考链接：

- Rasa：https://rasa.com/
- Botpress Workflows：https://botpress.com/docs/studio/concepts/workflows/
- Botpress Nodes：https://botpress.com/docs/studio/concepts/nodes/introduction/
- Microsoft Bot Framework Dialogs：https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-concept-dialog
- LangGraph StateGraph：https://reference.langchain.com/python/langgraph/graph/state/StateGraph

本项目不建议直接引入这些大型框架。当前代码体量还不需要。但可以吸收它们的结构：

- State：一轮消息的上下文和历史状态。
- Node：分类、策略、生成、评估、表达输出。
- Policy：决定下一步执行什么。
- Channel Adapter：QQ、API、未来前端只做通道适配。

## 建议算法

### 1. Dialogue Act 分类

建议枚举：

- `greeting`：打招呼。
- `casual_question`：简单闲聊问题。
- `affection`：亲密/撒娇/关系表达。
- `emotion_support`：委屈、压力、难受。
- `celebration`：开心、成功、分享好事。
- `tease`：玩笑、阴阳、互怼。
- `task_request`：让助手做事。
- `technical_debug`：代码、配置、报错、训练。
- `memory_update`：记住、改名、纠正偏好。
- `voice_or_sticker_request`：显式要求语音或表情包。

### 2. Response Mode 决策

建议枚举：

- `micro_reply`：1 句，适合“嗯？在吗？”“想你了”。
- `short_chat`：1-2 句，适合大多数 QQ 私聊。
- `normal_chat`：2-4 句，适合需要解释但不是技术任务。
- `task_answer`：结构化回答，适合开发、配置、训练。
- `supportive`：短安慰 + 轻追问。
- `playful`：短调侃 + 表情倾向。
- `clarify`：不确定时先追问。

### 3. 表达策略

表情包和语音应由同一个 `ExpressionDecision` 输出：

```text
ExpressionDecision
- sticker_intent: none | cute_react | tease | support | celebrate | awkward
- sticker_allowed: true/false
- voice_allowed: true/false
- voice_style: none | soft | playful | comfort | excited
- reason: debug string for logs
```

这样可以避免：

- 文本一大段 + 语音重复。
- 表情包每次同一张。
- 技术问题乱发表情。
- 用户只是短聊时完全不触发表达。

### 4. 回复长度控制

长度控制建议由策略层给出硬目标，而不是只写在 prompt 里：

```text
micro_reply: 6-24 个中文字符
short_chat: 12-55 个中文字符
normal_chat: 40-120 个中文字符
task_answer: 按任务需要，不强制短
supportive: 25-90 个中文字符
```

LLM 生成后本地质量门检查：

- 超出上限 1.8 倍：重写一次。
- 简单问候却超过 80 字：重写。
- 技术任务被短聊策略误伤：放行任务式回答。
- 出现舞台指令：清洗或重写。

## 推荐第一阶段

先不要大重构。第一阶段只新增 `app/dialogue/`，把现有聊天相关散落逻辑往统一策略收口：

- `app/dialogue/types.py`
- `app/dialogue/act_classifier.py`
- `app/dialogue/policy.py`
- `app/dialogue/response_style.py`
- `app/dialogue/expression_decision.py`
- `app/dialogue/quality_gate.py`

第一阶段只接入 QQ 短回复和表情包，不动 ASR、TTS、存储。

## 验证标准

建议做一个固定评测集 `tests/fixtures/dialogue_cases.jsonl`：

- 30 条短闲聊。
- 20 条亲密/玩笑。
- 20 条情绪支持。
- 20 条技术任务。
- 10 条显式语音/表情包。

每条期望：

- `dialogue_act`
- `response_mode`
- `sticker_intent`
- `voice_allowed`
- `max_chars`

先测策略输出，再测真实 LLM 回复质量。
