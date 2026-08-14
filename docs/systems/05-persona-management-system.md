# S5 人格管理控制面系统

## 目标

在现有六层人格运行时之上定义版本、验证、发布、绑定和回滚控制面，而不是重写 `xiaohe_v1` 行为。

## 前置条件

S1 提供 persona/profile 数据访问边界，S4 提供只读记忆投影。只有一个稳定人格时先做后端契约，不急于做可视化编辑器。

## 独占写入范围

```text
app/persona_management/
tests/persona_management/
docs/systems/worklogs/s5/
```

## 公开契约

- `PersonaDraft`、`PersonaVersion`、`PersonaRelease`。
- `PersonaBinding`：global、platform、relationship、profile、conversation。
- `PersonaValidationResult`：schema、gate、regression、live acceptance。
- `PersonaRuntimeProjection`：运行时只读投影。

## 发布流程

```text
draft -> schema validated -> offline evaluated -> approved -> active
active -> superseded / rolled back / archived
```

## 唯一正式架构

生产运行时以异步 `PersonaManagementService` protocol、持久化 repository 和异步 router 为唯一写入路径。同步内存 service/router 仅用于测试和兼容读取，必须报告 `durable=false`、`write_ready=false`，不得接受生产发布、回滚或 binding 写入。

```text
management API -> async service -> durable repository -> release/binding
                                                     -> runtime projection port
ChatService ------------------------------------------^ (read only)
```

- S1 提供 actor、readiness、事务存储和审计 sink，不向 S5 暴露 repository 私有方法。
- S4 只通过 `MemoryProjection` port 提供上下文；S5 不持久化私密记忆副本。
- ChatService 每次会话按 binding 优先级解析已发布版本；draft、approved 但未发布版本不得进入 runtime。
- projection 可短期缓存，但 publish、rollback、archive 和 binding 更新必须按 profile/binding key 失效。
- 旧同步入口在迁移期只能委托异步 service 的只读方法；不得维护独立 active release。

## 持久化与并发

- draft、validation、version、release、binding 和 audit 均有稳定 id、创建者和时间戳。
- 同一 profile 同时最多一个 active release；发布和回滚使用事务与乐观锁。
- operation id 用于发布、回滚和 binding 写入幂等；复用 operation id 但参数不同返回 conflict。
- binding 优先级固定为 conversation > profile > relationship > platform > global；同级冲突必须拒绝。
- 完整 prompt 内容应加密或受限存储，普通列表和审计响应只返回摘要与 hash。

## 不可变规则

- 系统级自伤、隐私、权限和安全 gate 不允许被人格版本关闭。
- surface binding 不改变 profile id。
- 未知或已移除 alias 不能激活旧人格。
- 完整 prompt 和私密记忆不写普通日志。

## 测试

- binding 优先级；
- draft 不能用于生产 runtime；
- 发布/回滚幂等；
- gate 不可关闭；
- legacy persona alias 拒绝；
- profile version 审计；
- `xiaohe_v1` 行为等价回归。

## 完成标准

- 单一 profile 也能完成版本发布和回滚。
- runtime projection 不依赖管理 API DTO。
- 通过现有人格连续性和 adversarial 测试。
- 提交集成说明，不直接修改当前 registry 或 prompt builder。
- 生产 router 使用持久化异步 service，重启后发布状态和 binding 保持不变。
- ChatService 只读取 `PersonaRuntimeProjection`，并覆盖 publish/rollback/cache invalidation 集成测试。
- 同步内存兼容路径不能执行生产写入，也不能被 S8 报告为 `write_ready`。

## 禁止修改

`app/persona/*`、ChatService、Database V2 migration、控制中心前端。
