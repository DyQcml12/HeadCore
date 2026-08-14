# S5 人格管理控制面测试报告

日期：2026-07-14

## 范围

- typed 管理契约与 runtime projection 隔离；
- schema/gate/regression 发布前验证；
- 发布、替换、回滚、归档与审计；
- binding 优先级和 surface 边界；
- 系统安全 gate 不可关闭；
- legacy persona alias 拒绝；
- `xiaohe_v1` 稳定字段等价投影。

## 首轮聚焦测试

命令：

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\python.exe' -m pytest tests/persona_management -q
```

结果：`10 passed`，耗时 `0.06s`。

警告：pytest 无法更新已有 `.pytest_cache`（WinError 5）。测试用例和源码读写不受影响，未修改权限。

## 最终验证

1. `compileall app/persona_management tests/persona_management -q`：PASS。
2. 新增目录聚焦测试：`10 passed`。
3. 人格系统、response evaluator 与 S5 组合回归：`48 passed`。
4. 项目标准全量范围 `python -m pytest tests -q`：`429 passed`，耗时 `12.24s`。
5. `scripts/persona_continuity_eval.py`：PASS，`3/3` 场景通过。

连续性报告：`logs/persona-continuity-eval/2026-07-14_174042/persona-continuity-report.md`。

全量测试仍报告一个既有 `.pytest_cache` 写权限警告，不影响测试结果。直接执行无范围的
`pytest -q` 会误收集 `model_training/` 中需要 Torch 的上游训练测试；项目标准测试入口限定为
`tests`，最终结果使用该入口。

真实模型 live acceptance 未执行，以避免未经确认产生外部 API 调用。公开契约已保留
`ValidationStage.LIVE_ACCEPTANCE`，可由集成验收流程写入结果。

## Repository 边界增量

- 新增 `PersonaManagementRepository` 和 `InMemoryPersonaManagementRepository`。
- service 改为 repository 注入，不再直接持有业务存储字典。
- 新增跨 service 重建状态保持、validation snapshot 隔离和 binding 持久化测试。
- 增量聚焦结果：`13 passed in 0.06s`。
- S1/S4/S5 相邻系统回归：`47 passed in 1.05s`。
- 人格、记忆、Database V2、response evaluator 回归：`120 passed in 0.75s`。
- 最新项目全量正式范围：`469 passed in 12.27s`。
- 真实 Database V2 adapter 暂未实现，因为现有 V2 repository 没有公开人格管理写接口；
  所需事务契约已记录在 `integration-notes.md`。

## 2026-07-14 运行时完整性复核

复核发现并修复三个领域约束缺口：

1. `build_runtime_projection()` 现在拒绝 binding/version 不一致，避免把其他版本的 surface
   应用到当前 active version。
2. `rollback()` 只允许选择历史上确实发布过的版本；仅 approved、从未发布的版本必须走
   `publish()`，不能借 rollback 绕过发布语义。
3. binding 保存会校验 global wildcard、非 global scope key，并拒绝 surface 中的
   `profile_id` 覆盖尝试。

同时保留并验证了并行加入的约束：binding 只能指向当前 active version，管理 router
只暴露只读端点，并通过显式 summary DTO 返回 `version_id`，不返回完整 prompt 或私密记忆。

验证结果：

- `compileall app/persona_management tests/persona_management -q`：PASS。
- `pytest tests/persona_management -q -p no:cacheprovider`：`23 passed in 0.62s`。
- S5、S4、现有人格、Database V2、response evaluator 相邻回归：
  `152 passed in 1.14s`。
- `scripts/persona_continuity_eval.py`：`3/3 PASS`；报告位于
  `logs/persona-continuity-eval/2026-07-14_221033/persona-continuity-report.md`。

本轮全量 `pytest tests` 在收集阶段被并行中的 S3 perception 代码阻断：
`app.perception.contracts` 缺少 `ObservationQuality`，且 `app.perception.adapters` 缺少
`adapt_vision_result`。该问题不在 S5 独占目录，本轮未跨范围修改；S5 及其相邻回归均已通过。

## 只读 API 增量

- 增加独立只读 FastAPI router，不修改共享应用入口。
- 复用 S1 数据库 actor 鉴权契约，覆盖未认证 `401`、非管理员 `403` 和缺失资源 `404`。
- OpenAPI 锁定五个 GET endpoint，不提供人格管理写接口。
- 版本摘要不返回 core lines 或完整 prompt。
- binding 保存要求版本已经 active；发布新版本后旧 binding surface 不再投影。
- 最新 S5 聚焦结果：`23 passed in 0.55s`。
- S1/S4/S5 相邻回归：`57 passed in 1.19s`。
- API、人格、记忆、Database V2、response evaluator 回归：`136 passed in 1.16s`。
- `compileall`：PASS。

本轮项目全量测试在收集阶段被 S3 perception 的并行契约不一致阻断：

- `app/perception/quality.py` 导入当前 contracts 不再提供的 `ObservationQuality`；
- `integrations/qq_bot/vision_intake.py` 导入当前 adapters 不再提供的 `adapt_vision_result`。

S5 未修改或回退这些其他工作包文件。上述错误发生前，本轮上一阶段全量基线为
`469 passed`；本次 S5 新增代码已由聚焦及相邻 `57/136 passed` 覆盖。

## 状态契约增量

- 新增 `PersonaManagementStatus` 和管理员只读 `GET /api/control/personas/status`。
- 状态只包含 backend/能力标记、计数和 active profile ID，不包含人格正文或私密数据。
- 内存 repository 明确返回 `durable=false`、`write_ready=false`。
- 最新 S5 聚焦结果：`24 passed in 0.59s`。
- S1/S4/S5/S8 状态相邻回归：`70 passed in 1.17s`。
- API、人格、记忆、Database V2、response evaluator 回归：`136 passed in 1.07s`。
- 最终项目全量回归：`515 passed in 12.93s`。

全量首次复验曾出现一个 QQ 语音响应测试的顺序性失败（`513 passed, 1 failed`）；
该用例单独重跑 `1 passed`，随后完整套件重跑 `515 passed`。S5 未修改 QQ 模块。
先前 S3 perception 收集错误也已由对应工作包恢复，本轮最终全量不再出现该错误。

## 异步持久化服务增量

- 新增安全 `PersonaDefinition`/surface JSON codec。
- 新增 `PersistentPersonaManagementService`，原生 await S1 store。
- 覆盖完整发布/绑定/投影/回滚流程、重复审批发布、验证前审批拒绝、损坏 JSON 拒绝、
  system gate 与 surface 边界。
- S1/S5 最新聚焦结果：`60 passed in 1.27s`。
- S1/S4/S5/Database V2 相邻回归：`125 passed in 1.30s`。
- API/人格/记忆/response evaluator/project surface 回归：`85 passed in 1.00s`。
- `compileall`：PASS。
- 最终项目全量回归：`550 passed in 13.31s`。

## 原生异步 API 增量

- 新增统一 async service protocol 和 `/api/control/personas-v2` router。
- 写 API 默认关闭，并组合管理员 mutate 权限、durable storage 和 Database V2 readiness。
- 覆盖 `401/403/404/409/503` 映射基础、完整发布流程、OpenAPI 方法矩阵及敏感字段不回显。
- async router/persistent store 核心测试：`17 passed in 0.80s`。
- S1/S5 聚焦：`72 passed, 1 skipped`；跳过项是未配置
  `DATABASE_CONTROL_TEST_DATABASE` 的既有真实 MySQL 集成测试。
- async router/persistent store 最终核心测试：`18 passed in 0.85s`。
- S1/S4/S5/Database V2 相邻回归：`141 passed, 1 skipped in 1.83s`。
- API/人格/记忆/S8 相邻回归：`109 passed in 1.20s`。
- 最终项目全量回归：`597 passed, 1 skipped in 14.19s`。
- 唯一跳过项仍为未配置隔离测试库的真实 MySQL integration test；未连接真实数据库。

## 写操作审计增量

- 新增 `PersonaControlAuditEvent`、`PersonaControlAuditSink` 和并发安全内存 fake。
- 启用写 API 时 audit sink 为强制依赖，缺失返回 `503`。
- accepted、权限/readiness rejected、领域 conflict 和 failed 使用统一 wrapper 记录。
- 审计仅记录 actor profile、操作、目标、结果和原因，不接收 definition/core lines/surface。
- 审计与事务核心聚焦：`16 passed in 1.04s`。
- S1/S4/S5/Database V2 相邻回归：`145 passed, 1 skipped in 1.92s`。
- API/人格/记忆/S8 相邻回归：`109 passed in 1.26s`。
- `compileall`：PASS。
- 最终项目全量回归：`600 passed, 1 skipped in 13.74s`。
