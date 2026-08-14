# S1 Database V2 控制面系统

## 目标

把现有 Database V2 repository、关系服务和命令服务包装成经过鉴权、可审计的应用服务与 HTTP 控制接口。

## 当前基础

- `app/storage/v2_*.py` 已有 repository 和领域服务。
- `DATABASE_SYSTEM_DESIGN.md` 定义目标数据模型。
- `app/database_control/router.py` 已实现并由 `app/main.py` 注册 `/api/control/database-v2` 路由。
- 只读状态、管理员、profile 查询以及受控 bootstrap、关系更新、账号绑定和 claim 审核已经实现。
- 当前机器尚未完成新版 V2 readiness 和隔离 MySQL 验收，运行状态仍为 `degraded`。

## 非目标

- 不修改聊天生成逻辑。
- 不实现前端页面。
- 不自动删除旧库或迁移真实数据。
- 不在路由中直接拼 SQL。

## 独占写入范围

```text
app/database_control/
tests/database_control/
docs/systems/worklogs/s1/
```

建议目录：

```text
app/database_control/
  contracts.py
  actor.py
  service.py
  errors.py
  router.py
```

`router.py` 只创建独立 `APIRouter`，不得自行修改 `app/main.py` 或 `app/control/routes.py`。

## 公开契约

- `DatabaseActor`：profile id、relationship、permissions、source account。
- `DatabaseStatus`：schema version、readiness、enabled、target database。
- `ProfileSummary`、`ProfileDetail`、`PlatformAccountSummary`。
- 分页 contract：cursor、limit、next cursor。
- 领域错误：unauthenticated、forbidden、not found、conflict、not ready。

## 核心服务

- readiness/status 查询；
- 唯一管理员 bootstrap 预检；
- profile 与账号只读查询；
- 关系变更和账号绑定命令；
- claim 审批；
- 所有写操作生成审计事件。

## 跨系统持久化边界

S1 可以为 S4/S5 提供数据库连接、事务执行、schema readiness 与公开 persistence protocol 的 adapter，但不实现记忆决策、人格发布或 binding 优先级等领域规则。

- S4/S5 各自拥有领域 contract；数据库 adapter 只能实现其公开 repository protocol。
- 新表必须通过独立评审 migration 提供，不得把 legacy `memories`、`personas` 表强行解释成生命周期或发布控制面完整模型。
- adapter 向调用方暴露结构化 `not ready`、`conflict` 和事务失败，不暴露 SQL、连接对象或 repository 私有方法。
- S1 readiness 分别报告基础 Database V2、S4 knowledge schema 和 S5 persona management schema，不能因基础数据库可连接就推断后两者可写。
- 跨系统审计共享 correlation id，但审计内容仍由领域 service 生成，S1 只负责可靠持久化和安全查询投影。

## 安全要求

- actor 必须由数据库身份解析产生，不能信任请求体中的 role。
- 普通用户不能读取其他 profile、管理员画像或聊天记录。
- 响应不包含 token、密钥、完整 prompt 或未脱敏平台数据。
- 写操作必须支持幂等或明确 conflict。

## 测试

- fake repository 的 service 单测；
- actor/permission 矩阵；
- 路由 401/403/404/409；
- 分页和脱敏；
- readiness 未通过时拒绝写操作；
- MySQL 集成测试使用隔离测试库。

## 完成标准

- 目标 API 的最小只读子集实现并有 OpenAPI 测试。
- 权限矩阵完整。
- repository 私有方法不从 route 直接调用。
- 提供 `integration-notes.md`，由集成人员注册 router。
- S4/S5 adapter 通过事务回滚、并发 conflict、schema 缺失和重启恢复测试，且不把领域规则下沉到 SQL adapter。

## 禁止修改

`migrations/v2/*`、现有 V2 repository、`app/main.py`、控制中心前端和真实 `.env`。
