# HutaoChatCore HeadCore、世界模型与功能完整性测试报告

测试日期：2026-07-21  
测试范围：当前工作区离线全量、临时 Core 运行、真实 DeepSeek 连续性、HeadCore 状态与世界认识逻辑  
唯一人格：`hutao_v1`

## 1. 总结结论

| 项目 | 结论 |
| --- | --- |
| Python 运行时 | 通过，Python 3.11.15，核心依赖可导入 |
| 项目编译 | 通过 |
| 全量自动化 | `743 passed, 2 skipped` |
| 启动脚本预检 | 通过 |
| 临时 Core 启动 | 通过，`/health`、普通聊天、流式聊天、OpenAI-compatible 均返回 HTTP 200 |
| 胡桃人格 | 唯一运行时 Profile 为 `hutao_v1` |
| 离线人格连续性 | 3/3 场景通过 |
| 真实模型连续性 | 4/4 场景、48/48 轮通过，覆盖五种人格模式 |
| HeadCore 统一入口 | Core API、文件音频、OpenAI-compatible 已接入；QQ 和 Weixin 分别通过这两个 HTTP 表面进入 |
| 世界模型逻辑 | 具备结构化证据与认识状态，属于受限的工具增强世界状态，不是学习型或预测型世界模型 |
| 类人思考 | 具备有限状态、关系、记忆、纠正、任务承接和不确定性处理；不具备完整人类思考、长期自主目标、反事实模拟和自我学习 |
| 生产完整性 | 未完成。真实 MySQL、QQ、Weixin、ASR、TTS、VLM、高德查询和新闻来源仍需单独授权验收 |

## 2. 本轮开发

### 2.1 HeadRuntime 统一入口

新增 `app/head/runtime.py`，统一接收 `ChannelEvent` 与 `HeadRuntimeContext`。当前主链路：

```text
平台/API输入
  -> ChannelEvent
  -> HeadRuntime
  -> HeadState / HeadDecision / HeadWorldState
  -> ChatService
  -> Provider
  -> Response Gate
  -> 平台表达
```

V2 权限、blocked 关系和管理员命令仍在 Runtime 前处理，这是权限边界，不是第二套认知主体。

### 2.2 HeadCore 状态

当前实现：

- 当前对象、关系、话题、用户状态和胡桃内部状态；
- 当前任务与“继续、接着、下一步”恢复；
- 胡桃提出问题后的待回答事件，以及用户回复后的清除；
- 直接回答、追问、继续任务、修复、支持和拒绝决策；
- 事件服从现有记忆写入权限，不进入普通人格记忆投影。

### 2.3 世界认识状态

新增 `HeadWorldState`：

| 状态 | 含义 |
| --- | --- |
| `known` | 有可用来源或条目，可基于证据回答 |
| `uncertain` | 证据部分可用、冲突或过期，回答必须保留不确定性 |
| `needs_input` | 缺地点、路线端点或存在歧义，必须追问 |
| `unavailable` | 来源禁用、失败或没有结果，不能编造实时事实 |
| `idle` | 用户没有请求世界工具或主动调用被禁止 |

底层 `WorldObservation` 已有来源、观察时间、过期时间、置信度、证据和敏感级别。

### 2.4 测试基础设施恢复

恢复：

- `scripts/build_hutao_consensus_dataset.py`；
- `scripts/evaluate_hutao_flow_checkpoints.py`。

前者只选择主 ASR 共识、原标注一致、物理质量合格且时长达标的数据；后者计算音频指标、按 CER 与音色相似度排序并生成盲听页面，不自动部署 checkpoint。

## 3. 自动化与运行结果

### 3.1 正式离线验收

报告：`logs/final-acceptance/2026-07-21_190805/final-project-acceptance-report.md`

```text
runtime preflight  PASS
compileall         PASS
pytest             PASS
persona continuity PASS
```

最终全量：`743 passed, 2 skipped`。

两个 skipped：

- `tests/database_control/test_mysql_integration.py:20`
- `tests/database_control/test_mysql_integration.py:49`

原因均为 `DATABASE_CONTROL_TEST_DATABASE` 未配置。当前不能宣称真实 MySQL 控制面已经验收。

### 3.2 临时 Core 运行

临时端口：`127.0.0.1:8011`，验证后已停止，无遗留临时 Core 进程。

| 接口 | 结果 |
| --- | --- |
| `GET /health` | HTTP 200 |
| `POST /api/v1/chat` | HTTP 200 |
| `POST /api/v1/chat/stream` | 服务端 HTTP 200 |
| `POST /v1/chat/completions` | HTTP 200 |

测试时空字符串没有覆盖 `.env` 中已配置的 DeepSeek Key，因此三条聊天 smoke 实际进入了真实模型。之后停止临时服务，没有继续以该方式发请求。没有记录或输出 Key 内容。

### 3.3 真实模型连续性

报告：`logs/persona-live-continuity-stress/2026-07-21_190044/persona-live-continuity-report.md`

```text
Provider: deepseek
Model: deepseek-v4-pro
Scenarios: 4
Turns: 48
Passed: 4
Failed: 0
Covered modes: casual, emotional, repair, safety, task
```

自动报告原始结果为 PASS。人工复核发现“手边正好温着一壶茶”虚构现实环境，旧门禁未识别。已扩展 `claims_real_world_experience()` 并增加确定性测试，修复后全量回归通过。没有为此重复执行 48 次付费模型调用。

## 4. 功能完整性矩阵

| 能力 | 自动化 | 实际运行 | 结论 |
| --- | --- | --- | --- |
| HeadRuntime 入口 | 通过 | Core API/OpenAI 表面通过 | 已实现 |
| 胡桃身份与五种模式 | 通过 | 48 轮真实模型通过 | 已实现，仍需更大盲评集 |
| 关系与 blocked 边界 | 通过 | 未使用真实平台关系库 | 逻辑通过，生产持久化待验 |
| 短期任务/待回答状态 | 通过 | 未做重启恢复测试 | 部分实现 |
| 记忆写入、撤销与隔离 | 通过 | JSONL 路径已运行 | MySQL V2 待验 |
| 世界证据取得 | 适配器通过 | 本次未调用高德/新闻 | 代码存在，线上结果未知 |
| 世界认识状态 | 通过 | 未使用真实冲突来源 | 已实现一级认识控制 |
| ASR/音频情绪 | 契约与模拟通过 | 本次未跑真实模型样本 | 待真实数据验收 |
| OCR/VLM | 路由测试通过 | 本次未跑真实图片 | 待真实模型验收 |
| TTS/QQ 语音 | 链路测试通过 | 本次未实际发送 | 待真实平台验收 |
| QQ | API 路径通过 | 未登录 NapCat 实测 | 待验收 |
| Weixin/Hermes | OpenAI 表面通过 | 未进行 pairing/真实消息 | 待验收 |
| MySQL V2 | 大部分自动化通过 | 2 个集成测试跳过 | 未完成 |
| 新闻 | 注册 3、启用 0 | 未采集 | 当前不可用 |

## 5. 世界模型评估

采用四级工程分级：

| 等级 | 定义 | 当前状态 |
| --- | --- | --- |
| L0 | 只有提示词，没有外部事实边界 | 已超过 |
| L1 | 工具调用、来源证据、缓存、冲突检测 | 已具备 |
| L2 | HeadCore 明确维护已知、未知、冲突、需追问和不可用状态 | 已具备本轮状态 |
| L3 | 跨轮持久实体/事件/时间/因果图，可预测行动结果 | 未具备 |
| L4 | 学习型世界动力学、反事实模拟与持续校准 | 未具备 |

当前结论：**L2 受限世界认识系统**。

它可以安全回答“是否有证据、能否回答、是否冲突、是否需要追问”，但不能模拟复杂现实、长期心理变化、物理过程或未来结果。因此不应宣传为完整世界模型。

## 6. 类人思考评估

| 维度 | 当前能力 | 评价 |
| --- | --- | --- |
| 稳定自我 | 唯一胡桃 Profile、动态模式和门禁 | 较强 |
| 共同语境 | 最近对话、任务事件、待回答问题 | 有限具备 |
| 长期记忆 | 用户偏好、称呼、撤销和知识投影 | 部分具备 |
| 社会关系 | 管理员、普通朋友、blocked 与亲密边界 | 具备规则化模型 |
| 不确定性 | 模糊指代追问、世界冲突和来源不可用 | 具备 |
| 任务规划 | 只支持当前任务承接和有限工具决策 | 初级 |
| 行动后果预测 | 没有多候选行动与长期结果模拟 | 不具备 |
| 反思 | 没有会话后结构化反思与错误归因 | 不具备 |
| 自主目标 | 没有长期目标层级、调度和主动任务权限 | 不具备 |
| 自我学习 | 不会根据结果安全更新策略或世界动力学 | 不具备 |
| 人类常识与身体经验 | 主要依赖 DeepSeek，且必须防止虚构身体环境 | 不稳定 |

当前结论：**HeadCore 是有状态、有关系、有记忆边界和世界证据控制的工具增强人格代理；它能表现出部分接近人类对话的连续性，但不具备与人相同的思考机制。**

真实 48 轮测试证明它在当前题库中可以保持胡桃身份、接受纠正、维持关系边界和撤销记忆；人工复核同时证明自动门禁仍可能漏掉现实环境虚构。因此只能称为“有限类人对话行为”，不能称为真正像人一样思考。

## 7. 世界工具状态

离线状态检查：

```text
WORLD_AWARENESS_ENABLED=true
高德适配器已注册
高德 Key 已配置
高德法律确认=true
渲染采集=false
新闻候选=8
新闻适配器注册=3
新闻启用=0
政策适配器注册=1
政策启用=0
```

本次没有执行高德、新闻或政策的真实采集请求。

## 8. 剩余完成门

1. 配置隔离 MySQL 测试库，运行两个被跳过的控制面集成测试和 V2 readiness/smoke。
2. 使用真实 NapCat 完成 QQ 文字、群聊、图片、入站语音、出站语音和关系权限闭环。
3. 使用真实 Hermes 完成 pairing、普通聊天、撤销和媒体附件闭环。
4. 使用固定真实数据集评估 ASR、情绪、OCR、VLM 和 TTS，而不是只做接口测试。
5. 明确授权后执行高德天气/地点/路线真实查询，以及缓存、过期和冲突测试。
6. 新闻来源完成法律审核并显式启用后，测试真实多源去重与部分失败。
7. 将 HeadState 从“本轮重建 + 最小事件”升级为带版本和过期策略的持久认知状态。
8. 增加行动结果反馈、结构化反思、多候选计划与反事实评估，之后再重新评定类人思考等级。

## 9. 复现命令

```powershell
cd D:\Programming-file\Graduation-Project\HutaoChatCore

& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m compileall -q app integrations scripts tests
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests -q -p no:cacheprovider -rs
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\final_project_acceptance.py
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\persona_live_continuity_stress.py
& '.\启动控制中心.bat' --check-only
```

`persona_live_continuity_stress.py` 会产生真实模型调用和费用，只有需要重新验证模型行为时才运行。
