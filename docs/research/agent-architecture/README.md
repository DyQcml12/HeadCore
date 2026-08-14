# 智能体架构研究：主流对比、运行可靠性、存储、视觉、世界模型与伪自我意识

> 状态：研究完成（2026-08-14，T1-T6 全部交付）。汇总与决策入口见 `00-SUMMARY.md`。本目录所有文档均为**本地研究资料，实验完成并验收前不上传 GitHub**（上传门禁见文末）。
> 与权威手册的关系：本目录是研究与实验设计材料，不修改 HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md 的结论；任何实验落地前必须先出实现计划并经用户确认。

## 任务拆分总表

| 编号 | 任务 | 产出文档 | 状态 |
| --- | --- | --- | --- |
| T1 | 主流智能体架构/框架对比（LangGraph / Agents SDK / AutoGen / CrewAI / MetaGPT / Letta / CoALA / MCP / Dify）与 HeadCore S1-S8 的映射与缺口 | `01-framework-comparison.md` | 已完成 |
| T2 | 运行可靠性：生成慢/生成错误/不生成的失败模式清单、现有防护与缺口、优化实验清单 | `02-runtime-reliability.md` | 已完成 |
| T3 | 网页端存储选型：账号密码/人格/记忆/上下文各放什么数据库，数据分类总表与迁移顺序 | `03-web-database-design.md` | 已完成 |
| T4 | 视觉设计：本地受限标签 → 本地小 VLM → 云 VLM 的分层方案与分阶段实验 | `04-vision-design.md` | 已完成 |
| T5 | 世界模型与人类思维差距：认知科学边界、可弥补/不可弥补清单、升级路线 | `05-world-model.md` | 已完成 |
| T6 | 伪自我意识：机制包设计（自我档案/投影/反思/一致性门禁/时间感）与伦理红线 | `06-pseudo-self-awareness.md` | 已完成 |

## 执行与上传门禁

1. 研究文档只写本地（本目录），可以提交到**本地**旧仓库（HutaoChatCore），**绝不 push 到 GitHub（DyQcml12/HeadCore）**。
2. 每个方向若进入实现：先给用户完整实现计划 → 确认后小步实现 → 跑聚焦测试 + 写 logs 报告 → 记录 AGENTS.md 与 README。
3. 只有对应**实验完成并通过验收**后，才把该方向的代码与文档同步到 HutaoChatCore-code-only 并 push。
4. 验收口径沿用项目约定：自动化通过 ≠ 真实验收；真实模型/数据库/设备/外部服务的联调必须单独记录。