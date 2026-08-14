# S4 集成说明

## 当前可用公开入口

- `app.knowledge.KnowledgeLifecycleService`
- `app.knowledge.KnowledgeRepository`
- `app.knowledge.InMemoryKnowledgeRepository`
- `MemoryCandidate`、`MemoryRecord`、`PortraitPatch`、`MemoryProjection`
- `MemoryState`、`MemoryScope`、`MemoryDecision`、`MemoryDecisionKind`

S4 当前是独立模块，没有修改或接入 ChatService、现有 persona memory service、FastAPI、QQ 命令、migration 或真实数据库。

## 2026-07-15 Readiness 接入

新增 `assess_knowledge_persistence()`，只根据表集合判断 lifecycle persistence 能力。当前 V2 schema 缺少 `memory_candidates`、`memory_records` 和 `memory_audit_events`，因此报告 `durable=false`、`write_ready=false`，不得把旧 `memories` 或 `profile_portraits` 当成完整生命周期存储。

## Database V2 adapter 需求

适配器应实现 `KnowledgeRepository` 的全部异步方法，并满足：

1. candidate、record 和 audit event 使用独立持久化实体；审计事件只追加。
2. `update_candidate_state`、冲突 record 的 supersede 和新 record 激活应放在一个数据库事务中。
3. 对 active 事实建立 `(profile_id, scope, persona_id, key, state)` 查询索引。
4. 乐观锁或行锁必须阻止两个冲突 candidate 同时激活。
5. profile 合并由 S1 负责；adapter 接收合并后的 canonical `profile_id`。
6. 删除记录保留 tombstone 和审计，不向 projection 返回原始内容。
7. 时间统一存储为 UTC；读取时返回 timezone-aware `datetime`。

## 运行时接入要求

集成人员应让 prompt builder 只调用 `KnowledgeLifecycleService.project()`，禁止读取原始 candidate、record source 或 repository 私有方法。多模态入口需传入 `observation_quality`；平台关系上下文需映射到 `KnowledgeActor`，尤其是 `relationship_type`、`verified`、`is_admin` 和 `can_write_long_term_memory`。

## 共享文件待办

- 由集成人员在 README 和 AGENTS 中登记 S4 实现与测试结果。
- 由 S1/集成人员实现 Database V2 adapter 和事务边界。
- 在启用运行时前增加 projection 到 prompt 的集成测试和隐私回归测试。
