# S8 控制面与可观察性系统

## 目标

统一展示服务、provider、数据库、渠道、测试和最近失败状态，并为管理员操作提供审计边界。

## 前置条件

优先读取 S1-S7 的公开 status contract，不直接探测其内部文件或私有 repository。

每个系统必须提供轻量、无副作用的 `StatusProvider`。模块可导入、端口可连接或配置项存在都不等于组件 online。

## 独占写入范围

```text
app/operations/
tests/operations/
docs/systems/worklogs/s8/
```

## 公开契约

- `ComponentStatus`：online、offline、degraded、missing、not_configured。
- `DependencyStatus`：组件依赖及阻塞原因。
- `OperationResult`：动作、actor、时间、结果、审计 id。
- `TestReportSummary`：suite、passed、failed、report path、timestamp。
- `RedactedConfigStatus`：只显示是否配置，不返回值。

## 功能范围

- 服务与端口健康；
- provider/model readiness；
- Database V2 schema/readiness；
- QQ/Weixin capability 和连接状态；
- 最近测试报告索引；
- 最近错误分类；
- 管理员操作审计。

## 状态来源与聚合

- S1：schema version、数据库连接、read/write readiness 和 bootstrap 状态。
- S2：已注册平台 adapter、capability contract 版本和平台连接状态。
- S3：pipeline 可用性、输入策略版本和最近结构化失败；不调用真实模型。
- S4：所需表、repository read/write readiness、projection 可用性和积压 candidate 数量桶。
- S5：storage backend、durable/write ready、active release 与 binding readiness；内存兼容实例不得报告生产就绪。
- S6：registry/runtime monitor 的 provider capability、健康和熔断摘要。
- S7：planner contract 版本和各平台 delivery adapter 注册情况；不发送测试消息。

聚合器对每个 provider 独立设置超时。静态 provider 只允许表示明确的编译期能力，不能长期代替数据库、平台连接、持久化或 runtime 健康状态。未知状态映射为 `missing` 或 `not_configured`，不得默认 online。

## 审计边界

- 管理员写操作采用“先鉴权，后执行，最后持久化结果审计”；拒绝操作也记录固定原因码。
- 审计持久化失败不得放行未授权操作；对于已完成操作，应返回可辨识的审计降级状态并触发告警。
- 普通状态响应不包含 actor profile id、平台 user id、操作参数或原始错误；管理员审计接口也只返回安全投影。
- audit id、operation id 和 request correlation id 分离，便于幂等和追踪且不暴露身份。

## 安全要求

- 不返回 API key、token、密码、完整 `.env`、完整 prompt、私密记忆。
- 日志输出经过统一脱敏。
- start/stop 和写配置必须要求管理员 actor。
- 健康检查不能产生昂贵模型调用或发送平台消息。

## 测试

- 状态聚合与 degraded 传播；
- 密钥脱敏；
- 非管理员写操作 403；
- 组件超时不拖垮整个状态页；
- 测试报告损坏/缺失；
- Windows 路径和日志编码。

## 完成标准

- 聚合服务可用 fake status provider 独立测试。
- 不直接修改现有控制中心 routes/UI。
- 提供 router/UI integration notes。
- 现有 `/control` 与 `/weixin` 测试保持通过。
- S1-S7 均由真实公开 status provider 聚合；不存在用模块导入成功或永久静态状态冒充 online 的组件。
- 控制中心覆盖 read-only 状态、授权写操作、安全审计投影、审计降级和移动端布局。
- 状态 API 有 contract version，新增组件或字段保持向后兼容。

## 禁止修改

`app/control/*`、前端静态文件、其他系统内部模块、真实日志和 `.env`。
