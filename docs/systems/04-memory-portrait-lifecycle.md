# S4 记忆与画像生命周期系统

## 目标

把记忆和画像从直接写入记录提升为有来源、审批、冲突、撤销、过期和审计的生命周期系统。

## 独占写入范围

```text
app/knowledge/
tests/knowledge/
docs/systems/worklogs/s4/
```

## 公开契约

- `MemoryCandidate`、`MemoryRecord`、`PortraitPatch`。
- 状态：candidate、active、superseded、revoked、expired、deleted。
- `MemoryScope`：admin_private、profile_private、persona_specific、safe_preference。
- `MemoryDecision`：approve、reject、review 与原因。
- `MemoryProjection`：供 prompt 使用的脱敏只读投影。

## 核心规则

- 每条记忆保留 source message/observation 和 confidence。
- 未验证用户不能借记忆修改关系或管理员身份。
- 撤销必须传播到 prompt projection。
- 冲突信息不静默覆盖，产生 supersede/review 事件。
- blocked 用户和低质量多模态观察不写长期记忆。

## Repository 边界

先定义 `KnowledgeRepository` protocol 和内存 fake。Database V2 adapter 由集成人员或 S1 完成，S4 不直接修改现有 MySQL repository。

### 正式持久化模型

生产 repository 至少包含 `memory_candidates`、`memory_records` 和 `memory_audit_events` 三个逻辑集合。迁移由 S1/集成人员评审后提供，S4 不复用语义不完整的 legacy memory 表。

- candidate 创建、决策、record 激活和审计追加必须处于同一事务边界。
- record 使用乐观版本号；并发 approve/revoke/supersede 只能有一个成功，其余返回 conflict。
- source 以受控引用保存，projection 不返回原始消息、原始观察或私密审计详情。
- 到期判断使用注入时钟；物理清理与逻辑 `expired/deleted` 分离。
- repository 必须按 `profile_id` 强制隔离，调用方不能通过过滤遗漏扩大读取范围。

## 运行时集成

```text
S3 observation / verified text
  -> candidate policy
  -> KnowledgeLifecycleService
  -> durable record + audit
  -> MemoryProjection
  -> prompt composition
```

- ChatService/prompt builder 只能调用 projection port，不得读取 repository 或 `MemoryRecord`。
- projection 查询必须带 `profile_id`、relationship、persona/version 和 conversation context，并应用 scope 权限。
- revoke、expire、supersede 提交成功后必须使 projection cache 失效；下一次 prompt 构建不得再看到旧记录。
- blocked、未验证身份或 `MemoryEligibility != allow` 的输入不得自动创建可审批 candidate。
- S5 可以消费 projection，但不能修改 S4 状态，也不能用人格版本绕过 S4 scope。

## 测试

- candidate 到 active；
- 冲突与 supersede；
- revoke 后不可投影；
- scope/relationship 权限矩阵；
- 过期与时间边界；
- 多账号绑定同 profile 后共享记忆；
- 不同 profile 严格隔离。

## 完成标准

- 生命周期状态机和 projection service 可独立测试。
- 所有变化有审计事件。
- prompt 只读取 projection，不读取原始私密记录。
- 提供 Database V2 adapter 需求说明。
- 持久化 repository 通过事务、并发冲突、重启恢复和跨 profile 隔离测试。
- ChatService 集成测试证明 prompt 只包含 projection，且 revoke 后下一轮立即消失。
- S8 能通过公开 readiness contract 区分 `missing schema`、`read only`、`write ready` 和 `degraded`。

## 禁止修改

ChatService、现有 memory service、V2 migration、QQ 命令和真实数据库。
