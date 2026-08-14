# S5 集成说明

日期：2026-07-14

## 新增公开入口

从 `app.persona_management` 导入：

- 管理契约：`PersonaDraft`、`PersonaVersion`、`PersonaRelease`、`PersonaBinding`、`PersonaValidationResult`。
- 运行时契约：`PersonaRuntimeProjection`。
- 服务 fake：`InMemoryPersonaManagementService`。
- 持久化端口：`PersonaManagementRepository`。
- 内存适配器：`InMemoryPersonaManagementRepository`。
- 异步持久化服务：`PersistentPersonaManagementService`，消费 S1
  `PersonaPersistenceStore`，不使用阻塞事件循环桥接。
- 绑定解析：`resolve_binding()`。
- 投影构建：`build_runtime_projection()`。
- 只读路由工厂：`create_persona_management_router(service, actor_resolver)`。
- API 版本摘要：`PersonaVersionSummary`，不返回 core lines 或完整 prompt。

## 只读 API

独立 router 提供：

- `GET /api/control/personas/status`
- `GET /api/control/personas/{profile_id}/versions`
- `GET /api/control/personas/{profile_id}/releases`
- `GET /api/control/personas/versions/{version_id}`
- `GET /api/control/personas/bindings/all`
- `GET /api/control/personas/{profile_id}/runtime-projection`

所有接口复用 S1 的 `ActorIdentity`、`DatabaseActor` 和管理员权限规则。router 本身不信任
请求中的 role，也不提供任何写操作。集成人员应传入实现 `PersonaActorResolver` 的 S1 adapter，
并在共享入口注册 router；S5 工作包不修改 `app/main.py`。

`status` 可由 S8 作为公开 status contract 消费，只返回 backend 名称、持久化/写就绪能力、
对象计数和 active profile ID。内存 repository 固定报告 `durable=false`、
`write_ready=false`，不得因其单元测试可写而当作生产管理存储。

## 集成要求

1. S1 持久化适配器应保存 immutable version 和 append-oriented release audit，不应把 draft 当成 active version 返回。
2. runtime 只读取 `PersonaRuntimeProjection`，不得依赖管理 API 请求/响应 DTO。
3. binding 优先级固定为 `conversation > profile > relationship > platform > global`。
4. surface 中的显示名、声音、头像等只能作为 projection surface，不能覆盖 `profile_id`。
5. `SYSTEM_REQUIRED_GATES` 必须与现有本地响应 gate 取并集，不能由数据库字段关闭。
6. `hutao`、`hu_tao`、`genshin_hutao` 在草稿 schema 阶段拒绝，不得转换成可激活 alias。

## Database V2 持久化缺口

当前 `DatabaseV2Repository` 只公开 `ensure_default_personas()` 和
`resolve_persona_context()`，没有人格管理写入能力。S5 因此只交付 repository port 和
内存适配器，不调用 `MySQLDatabaseV2Repository` 的 `_fetch*`、`_execute*` 等私有方法。

S1/集成人员需要提供以下公开事务能力后，才能实现 MySQL adapter：

1. 创建/更新草稿并保存分阶段 validation result；
2. 原子分配同一 profile 的下一个 version number，并写入 immutable version；
3. 在单事务中把旧 active release 标为 superseded/rolled_back，并激活新 release；
4. 保存 binding，数据库外键必须保证其指向已存在的 approved version；
5. 查询 active release、profile versions、release audit 和 bindings；
6. 通过 optimistic lock 或行锁防止两个版本同时成为 active。

adapter 需实现 `PersonaManagementRepository`，但 runtime 仍只消费
`PersonaRuntimeProjection`。不得把草稿表或管理 API DTO 暴露给 prompt builder。

运行时 binding 还必须满足 active release 约束：保存时只有当前 active version 可绑定；
后续发布新版本后，旧 binding 不再投影 surface，直到绑定显式迁移到新 active version。

## 异步持久化服务

`PersistentPersonaManagementService` 已实现 draft 创建、结构化 JSON codec、分阶段验证、
原子版本审批、带 `operation_id` 的发布/回滚、active-version binding 和 runtime projection。
损坏或类型错误的持久化 JSON 会被拒绝，不会进入 runtime。

同步内存 service 仍供独立 router 和单元测试使用；不得通过 `asyncio.run()` 把异步 store
塞入同步 service。生产 router 接线前应抽取统一 async read service protocol，或提供原生异步
router。

## 原生异步控制面

新增 `AsyncPersonaManagementService` protocol 和
`create_async_persona_management_router()`，路由前缀为 `/api/control/personas-v2`。

读接口覆盖 status、draft summary、validation、versions、releases、bindings 和 runtime
projection。写接口覆盖 draft 创建、验证、评估、审批、发布、回滚和 binding 保存。

写入同时要求：

1. 工厂显式传入 `enable_writes=True`；
2. actor 通过 S1 数据库身份解析且具备 `mutate_admin`；
3. service storage 报告 `durable=true`；
4. readiness provider 报告 Database V2 `ready=true` 且 `database_v2_enabled=true`。
5. 提供实现 `PersonaControlAuditSink` 的持久化审计 sink。

任一条件不满足均拒绝写入。默认工厂参数关闭写入。管理响应只返回 draft/version 摘要，
不会回显 core lines 或完整人格定义。

当前 router 未注册到 `app/main.py`。在真实 MySQL store 和新版 schema 完成前，不得把测试用
`DurableTestStore` 或内存 fake 用于生产装配。

所有已解析 actor 的写入成功、权限/readiness 拒绝、领域 conflict 和内部失败都会产生脱敏
审计事件。未认证请求无法解析可信 profile，因此返回 `401`，且不会把请求头中的平台原始账号
写入审计。审计事件不接收请求 payload。

## 共享文件待集成人员更新

- 在 `README.md` 的系统状态中将 S5 标记为“后端契约和内存 fake 已实现，尚未接入 runtime/API”。
- 在 `AGENTS.md` 记录本文测试结果及仍未接入 S1/S4 的边界。
- 连接 S1 repository 时新增持久化 contract test；连接运行时时保留现有 `xiaohe_v1@1` 行为字段。
- 在 `app/main.py` 构建 S1 actor resolver 后注册独立 S5 router。

本工作包遵守共享文件冻结规则，未直接修改上述文件。

## 2026-07-15 只读运行时接入

- 六个 GET 接口已注册到主 FastAPI 应用。
- actor resolver 复用 S1 `MySQLDatabaseControlAdapter.resolve_actor()`，不信任请求 role。
- 当前管理 service 为隔离内存 backend，报告 `durable=false`、`write_ready=false`。
- API 没有写方法，内存 projection 不进入 persona prompt/runtime，`xiaohe_v1@1` 保持不变。
- Durable draft/version/release/binding 写入仍需新的 Database V2 lifecycle migration。
