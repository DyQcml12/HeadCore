# S1 人格管理持久化事务契约

日期：2026-07-14

## 已实现

- `PersonaPersistenceStore` 异步 protocol。
- draft、validation、immutable version、release audit、version binding 持久化 DTO。
- `InMemoryPersonaPersistenceStore` 事务语义 fake。
- 草稿状态更新和 profile 版本列表公开方法，可供 S5 原生异步 service 使用。
- `PersonaControlAuditSink` 脱敏审计契约及内存 fake；事件不接受人格 definition/payload。
- profile 内原子版本号分配。
- 发布、替换、回滚和 operation ID 幂等语义。
- active version binding 约束。

## 事务要求

真实 Database V2 实现必须保证：

1. 同一 profile 的 version number 在并发审批时唯一且单调递增。
2. 激活新版本、停用旧版本和写入 release audit 在同一事务完成。
3. 任意时刻同一 profile 最多一个 active release/version。
4. `operation_id` 重放相同请求返回原结果；重用到不同请求返回 conflict。
5. binding 必须引用明确的 version，且保存时该 version 是当前 active version。
6. 所有 actor、时间、替换和 rollback 关系可审计。

## 当前 schema 缺口

现有 `v2.001_hutao_chat_core_schema` 无法完整实现上述契约：

- 没有 persona draft 表；
- 没有分阶段 validation result 表；
- 没有 release/audit 表和幂等 operation ID；
- `persona_versions` 只有字符串 `version_label`，没有 profile 内递增 version number 约束；
- `persona_runtime_bindings` 只引用 `persona_id`，没有 `persona_version_id`；
- 没有数据库级“每个 persona 只有一个 active version”的唯一约束。

因此本阶段未实现 MySQL adapter，也未修改现有 migration 或真实数据库。下一版 migration 应新增
对应表、外键、唯一索引和事务实现，并经过备份与 owner 明确确认后才能应用。

## 安全边界

- DTO 中的人格定义使用 JSON 字符串传递，但普通日志不得记录其内容。
- store 只接受由上层管理员鉴权通过后的 `actor_profile_id`，不能从请求体信任 role。
- fake 用于 contract test，不代表生产持久化 ready。
- 审计事件仅保存 actor profile、操作、目标 ID、状态和原因码；不得保存平台原始账号、
  core lines、surface 内容或完整请求体。
