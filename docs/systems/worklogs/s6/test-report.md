# S6 Provider 路由系统测试报告

- 日期：2026-07-14
- 正式解释器：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`
- Python：3.11.15
- 网络/模型安装：无

## 检查结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 编译 | `python -m compileall -q app/providers tests/providers` | PASS |
| S6 聚焦测试 | `python -m pytest tests/providers -q -p no:cacheprovider` | PASS，11 passed in 0.05s |
| 全量回归 | `python -m pytest tests -q -p no:cacheprovider` | PASS，429 passed in 11.70s |

聚焦测试覆盖 Provider ID 校验、重复注册、健康状态、能力隔离、未配置、模型缺失、超时、限流重试、鉴权停止、fallback 顺序、策略硬上限、熔断恢复及嵌套 trace 脱敏。

## 环境排查记录

首次误用 Anaconda 根解释器运行全量测试时，该环境缺少 FastAPI，收集阶段出现 6 个 `ModuleNotFoundError`。定位项目启动脚本后改用正式 `envs/new` 环境，聚焦和全量测试均通过；该问题未通过安装依赖处理，也没有修改系统环境。

## 2026-07-14 路由完整性复核

本轮复核修复了三个错误边界：

1. `RoutingFailed.last_error` 现在同时脱敏异常文本和嵌套 details，不能绕过已脱敏的
   `ProviderTrace`；仍保留安全诊断文本，兼容 ChatService 审计。
2. 一次调用内达到失败阈值并打开熔断后，不再继续重试同一 provider，直接进入受控
   fallback 顺序。
3. 流式 iterator 的 `aclose()` 异常进入统一 ProviderError/trace；已有主错误时保留主错误码，
   关闭异常只记录非敏感 exception type。

验证结果：

- `compileall app/providers tests/providers -q`：PASS。
- `pytest tests/providers -q -p no:cacheprovider`：`24 passed in 0.08s`。
- S6、ChatService、response evaluator、API 相邻回归：`97 passed in 1.36s`。
- 项目标准全量测试：`543 passed in 15.07s`。

首轮全量测试出现一次 QQ vision 线程 fallback 的 10ms 超时抖动；对应测试组立即独立重跑
`4 passed in 0.50s`，第二次全量测试全部通过。该测试位于 S6 独占范围之外，本轮未修改其
实现或放宽超时断言。
