# S8 集成说明

## 2026-07-14 只读集成状态

以下接口已经接入现有控制路由：

```text
GET /api/control/operations/status
GET /api/control/operations/test-reports
GET /api/control/operations/errors
```

当前已接 Core API、Database V2、文本模型配置、QQ Bridge 和 Weixin Hermes 状态。控制中心 UI 与管理员写操作审计持久化仍未接入。

## FastAPI 接入

集成人员可在现有控制路由中构造 `OperationsStatusService`，注入 S1-S7 的公开 `StatusProvider`，并将 `OperationsSnapshot` 序列化为只读状态响应。不要从 S8 直接导入其他系统的 repository 私有实现。

建议只读端点：

```text
GET /api/control/operations/status
GET /api/control/operations/test-reports
GET /api/control/operations/errors
```

任何 start、stop 或配置写入端点应先调用 `OperationAuthorizer.require_admin`，成功或失败结果均写入正式审计 repository。`OperationPermissionError.status_code` 为 403。

## Provider 接入

- 服务端口：使用 `TcpStatusProvider`。
- 公开健康端点：使用 `HttpStatusProvider`，仅接无副作用 GET health/readiness URL。
- provider/model、Database V2、QQ/Weixin、S1-S7：优先让对应系统实现 `StatusProvider`；未配置与未就绪分别映射为 `not_configured` 和 `degraded`。
- provider 的 `get_status()` 必须廉价、只读，不得触发模型推理或发送平台消息。

## UI 接入

状态枚举固定为 `online`、`offline`、`degraded`、`missing`、`not_configured`。UI 应显示组件级失败，不应因单组件超时隐藏其余状态。配置项只展示是否配置。

## 共享文档待更新项

由于并行系统规则冻结 `README.md` 和 `AGENTS.md`，本实现没有直接修改它们。集成人员应记录：

- S8 独立控制与观测核心已实现，但尚未接入控制中心路由/UI。
- 新增 `app/operations/` 和 `tests/operations/`。
- 验证结果为 S8 `11 passed`、控制中心回归 `21 passed`、compileall PASS。
- 测试报告位于 `docs/systems/worklogs/s8/implementation-report.md`。
