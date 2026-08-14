# S8 控制面与可观察性完成状态

日期：2026-07-15

## 当前状态

S8 核心、只读 API、控制中心 UI、管理员写操作认证、审计写入、审计查询和视觉验证均已完成。

已接接口：

```text
GET /api/control/operations/status
GET /api/control/operations/test-reports
GET /api/control/operations/errors
GET /api/control/operations/actor
GET /api/control/operations/audits
```

现有服务 start/stop、配置更新、测试执行和 Weixin pairing 写操作均要求 Database V2 管理员 actor，并写入安全审计。

## 状态来源

- Core API：当前进程状态；
- S1 Database V2：公开 control repository status；
- S2：公开 channel capability contract；
- 模型与 ASR：配置/readiness 投影；
- QQ：TCP 连接；
- Weixin：受控运行文件和配置存在性。

S5/S6 状态适配器已经实现并测试，但主应用尚无对应共享运行实例。S3/S7 当前没有运行健康 contract，因此不伪报在线。

## 最终验证

- S8/control：`51 passed`；
- S1：`38 passed, 1 skipped`；
- 相关回归：`166 passed, 1 skipped`；
- 全量：`597 passed, 1 skipped`；
- Playwright 移动端无溢出，浏览器控制台零错误。

正式报告：`logs/control-observability/20260715-092814/control-observability-completion-report.md`。
