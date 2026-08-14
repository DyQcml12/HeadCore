# T3：网页端数据库与存储选型（研究分析报告）

> 研究分析员视角；只讨论网页端（公开账号 `PUBLIC_WEB_AUTH_ENABLED` 链路 + Web Desk / 微信小程序共用的公开用户 API）。
> 所有结论均与当前代码逐条核对（引用文件路径）；外部实践附来源链接。
> 本文是只读分析：不修改任何源码、不执行 git 操作。

## 0. 结论摘要（TL;DR）

1. **账号/密码/邮箱验证/会话/审计**：继续用"服务端关系型数据库"，不用 SQLite、不用 JWT 无状态方案。项目已有两条等价实现：MySQL Database V2（`migrations/v2/004`、`005`）与 PostgreSQL（`migrations/postgres/001_web_core.sql`）。**当前"双轨并存、按开关选择"是最大问题**：必须明确"网页主库"是哪一个并禁止混用双写。Argon2id 密码哈希、token 只存哈希、一次性消费、改密撤销全部会话——均已做对。
2. **人格分层已正确**：代码注册表（`app/persona/profile_registry.py`）是身份与安全门禁的运行权威；数据库（`personas`/`persona_versions`/`persona_runtime_bindings` + `persona_management_*`）只管版本发布、绑定与审计。不要反转这个分层。
3. **短期上下文**：进程内派生 + 从关系库读最近 8 条（已有上限）是单实例的正确做法；Redis 在多实例或限流热点出现前不需要。
4. **长期记忆**：结构化记忆（关系库生命周期）= 真相源；Qdrant 向量 = 可重建的派生检索索引（outbox 同步）——分工已正确。Redis 缓存层的引入时机：登录限流、会话热点、多实例时。
5. **最小改动清单**（详见第 10 节）：单一网页主库校验 → 上下文窗口配置化 → 限流回退实现 → 过期数据清理脚本 → argon2 参数集中与 verify-and-rehash。

## 1. 任务范围与事实来源

- 范围：仅网页端存储与数据库选型。QQ/微信 Bot 已退役，其事件表（`qq_inbound_events` 等）仅作历史兼容保留，不在本报告讨论。
- 事实优先级：当前运行时代码与 `migrations/*.sql` > `docs/POSTGRES_WEB_RUNTIME.md`、`docs/memory-and-storage-design.md` > 外部调研。
- 外部调研使用 2025-2026 年的公开资料（链接见第 8 节）。

## 2. 现状盘点（代码级事实）

### 2.1 认证链路

| 环节 | 实现 | 文件 |
| --- | --- | --- |
| 密码哈希 | Argon2（argon2-cffi 默认 Argon2id），`time_cost=3`、`memory_cost=65536`(64MiB)、`parallelism=2`；策略：≥12 位且含大小写/数字/符号 | `app/auth/passwords.py` |
| 会话令牌 | `token_urlsafe(32)`（256bit）明文只出现在 HttpOnly Cookie；库中只存 `SHA-256` 哈希；CSRF 令牌同样只存哈希、`hmac.compare_digest` 比对；`SameSite=Lax` + `Secure` 开关；默认 7 天（`public_web_session_lifetime_seconds=604800`） | `app/auth/sessions.py`、`app/auth/router.py`、`app/core/config.py` |
| 邮箱验证/重置码 | 只存哈希 + `expires_at` + `used_at`；消费时 `SELECT ... FOR UPDATE` 一次性使用；新建重置码会使旧的失效；重置成功撤销该用户全部会话 | `app/auth/mysql_repository.py`（`consume_email_verification_token`、`create_password_reset_token`、`consume_password_reset_token`） |
| 登录限流 | 数据库表 `registration_attempts` 内做固定窗口计数（5 次/10 分钟，封禁 30 分钟），主体（email/IP）只存 sha256 哈希 | `app/auth/rate_limit.py`、`app/auth/mysql_repository.py` |
| 审计 | `auth_audit_events`（event_type/outcome/reason_code，不含参数与密钥） | `app/auth/mysql_repository.py` |

### 2.2 存储矩阵

- MySQL Database V2：`migrations/v2/001-006` 共 27 张表——身份/账号（`profiles`、`platform_accounts`、`web_users`…）、关系（`relationship_events`、`relationship_pending_claims`）、会话（`conversations`、`messages`、`model_invocations`、`conversation_persona_state`）、记忆（`memories`、`memory_events` + 002 的 `memory_candidates`/`memory_records`/`memory_audit_events`）、人格（`personas`、`persona_versions`、`persona_runtime_bindings` + 003 的 6 张管理表）、审计与命令事件，以及 006 的 `semantic_memory_outbox`。
- PostgreSQL：`migrations/postgres/001_web_core.sql` 17 张表（`web_users`、`web_sessions`、`email_verification_tokens`、`registration_attempts`、`auth_audit_events`、`password_reset_tokens`、`profiles`、`sessions`、`messages`、`model_invocations`、`memories`、`persona_evaluations`、关系 4 表）。`docs/POSTGRES_WEB_RUNTIME.md` 明确："The Web product uses PostgreSQL for accounts, sessions, chat records, memory records, and relationship records."
- JSONL：开发默认（`app/storage/chat_repository.py`，`STORAGE_BACKEND=jsonl`）。
- Qdrant：语义检索派生索引（`SEMANTIC_MEMORY_ENABLED=false` 默认关闭；`app/knowledge/semantic_memory.py`、`app/knowledge/semantic_outbox.py`）。

### 2.3 人格分层现状

- L1 代码注册表：`app/persona/profile_registry.py` 内 `HUTAO_PROFILE`（identity_name、core_lines、gate_policy 的 forbidden_identity_markers）；`app/persona/persona_state.py` 五种模式（casual/task/emotional/safety/repair）+ 场景映射——全部为代码常量，是运行时权威。
- L2 数据库 S5 控制面：`personas`/`persona_versions`/`persona_runtime_bindings`（`migrations/v2/001`）与 `persona_management_drafts/validations/versions/releases/bindings/operations`（`migrations/v2/003`，实现见 `app/persona_management/mysql_store.py`）——管理草稿、校验、发布、按 profile/relationship 绑定与审计；运行时投影由 `app/persona_management/projection.py` 在进程内渲染。
- L3 关系/语气状态（用户数据）：`profiles`、`profile_emotional_state`、`app/persona/relationship_context.py` —— 属关系库。

### 2.4 记忆链路现状

- `docs/memory-and-storage-design.md` 定调：`messages` 是审计流水；`memories` 只存长期价值；撤销靠 `revocation` 过滤；prompt 注入 ≤8 条；提取目前是规则型。
- 生命周期：`memory_candidates`（候选）→ 审批 → `memory_records`（生效）+ `memory_audit_events`（`app/knowledge/mysql_repository.py`）。
- 语义索引：`semantic_memory_outbox` 表 + 独立 worker（`app/knowledge/semantic_outbox.py`、`scripts/semantic_memory_sync.py`）把"关系库已生效的记忆"嵌入后 upsert 进 Qdrant；撤销/删除则从 Qdrant remove；`initialize_index` 支持全量重建——**Qdrant 是可重建的派生索引**，这一定位在 `docs/POSTGRES_WEB_RUNTIME.md` 中已写明（"Qdrant is not a replacement for PostgreSQL"）。

### 2.5 短期上下文现状

- 每请求从存储读最近消息：`list_recent_messages(limit=8)`（`app/storage/chat_repository.py`）→ 进程内 `build_conversation_state`（话题/情绪/纠偏，`app/mind/conversation_state.py`）与 `build_recent_context`（`app/services/chat_service.py:1170`，取最近 8 条、每条截断 80 字）。
- 无 Redis、无专门缓存；`conversation_persona_state` 表提供可选的会话级人格状态持久化。

## 3. a) 账号、邮箱验证、会话、审计放哪个数据库

**结论：服务端关系型数据库（PostgreSQL 或 MySQL V2 二选一），不用 SQLite，不用纯 JWT。**

- **PostgreSQL vs MySQL V2**：两者在项目里都是完整实现（MySQL：`migrations/v2/004-005` + `app/auth/mysql_repository.py`；PostgreSQL：`migrations/postgres/001_web_core.sql` + `app/auth/postgres_repository.py`）。`docs/POSTGRES_WEB_RUNTIME.md` 已把 Postgres 定位为"网页产品主库"。评审建议：**网页端账号体系跟随"网页主库"**——若整个产品（含关系/记忆/人格）统一走 MySQL V2，则账号表也落在 MySQL V2，Postgres 可整个下线；若网页独立部署，则账号 6 表（web_users/email_verification_tokens/web_sessions/registration_attempts/auth_audit_events/password_reset_tokens）落在 Postgres。**当前的双轨（两个迁移集 + 两个仓库实现 + 开关）必须收敛为"启用网页账号时强制指定唯一主库"，避免同一账号数据在两个库里双写分裂。**
- **为什么不用 SQLite**：uvicorn 多 worker / 容器化后的并发写与锁粒度、备份一致性（WAL）、以及未来与 `profiles`/`memories` 等关系表做 JOIN 都不划算；"零依赖本地开发"已有 JSONL 覆盖，无需再引入第三种引擎。
- **argon2 与 token 哈希的正确做法（现状已正确）**：
  - 密码：OWASP Password Storage Cheat Sheet 推荐 Argon2id，内存 ≥19MiB、可配置迭代——当前 64MiB/t=3/p=2 达标，且策略要求 12 位 + 复杂度（`app/auth/passwords.py`）。建议补充 verify-and-rehash：未来调参后旧哈希自动升级。
  - 会话/验证/重置 token：这些是服务端生成的高熵随机值（`token_urlsafe(32)`），业界共识是**只存单向哈希**（SHA-256 足够，不需要 bcrypt/argon2，因为 token 本身高熵、无字典攻击面）；项目当前正是这么做的（`app/auth/sessions.py:hash_opaque_token`），且消费用 `FOR UPDATE` 防并发重放、改密撤销全部会话——全部正确。唯一注意点：登录/注册响应中的 token 只能出现一次，日志与审计不得落原文（当前审计只记 reason_code，正确）。

## 4. b) 人格放哪：代码注册表 vs 数据库的分层原则

**结论：维持现状分层，不要把人设 prompt 的"运行权威"搬进数据库。**

- **L1 代码注册表 = 运行权威**（`app/persona/profile_registry.py`）：身份、别名、core_lines、forbidden 门禁。理由：①安全门禁与身份锚点必须随代码评审与版本控制，不能被一次 DB 数据错误静默覆盖；②启动即得、无热路径 DB 依赖；③"hutao_v1 不漂移"是产品的核心承诺。
- **L2 数据库 S5 控制面 = 版本仓库与管理面**（`personas`/`persona_versions`/`persona_runtime_bindings` + `persona_management_*`）：草稿、校验、发布、绑定、回滚、审计。DB 存的是"发布历史与管理元数据"；运行时由 `app/persona_management/projection.py` 在进程内渲染投影，ChatService 消费投影（`app/services/chat_service.py`）。这一"DB 管发布、代码管执行"的方向是对的，等于业界 content-addressed 配置 + runtime loader 的模式。
- **关系/语气状态放关系库**（`profiles`、`profile_emotional_state`、`relationship_context.py`）：这是用户数据不是人格源码，正确。
- 需要警惕的反模式：每请求从 DB 拼人设全文（热路径慢、且 DB 故障直接瘫痪人格）。若未来接 DB 版本，应启动时加载 + 进程内缓存 + 发布事件失效，而不是每轮查询。

## 5. c) 短期上下文放哪与容量上限

**结论：维持"关系库读最近 N 条 + 进程内派生"；单实例不需要 Redis；把现有硬编码上限配置化。**

- 现状已有上限：`list_recent_messages(limit=8)` + `build_recent_context` 取 `messages[-8:]`、每条 80 字（`app/services/chat_service.py`、`app/storage/chat_repository.py`）；长期记忆注入同样 ≤8 条（`app/knowledge` 默认 `SEMANTIC_MEMORY_RETRIEVAL_LIMIT=8`）。这套"8+8 条、单条 80 字"的预算约合 1.5k-3k token，对角色聊天合理。
- 存储引擎选择：
  - **内存/进程内**：上下文派生状态（话题、情绪、纠偏）本身就是从 messages 每请求重算的纯函数（`app/mind/conversation_state.py`），无需持久化，天然"请求级"。
  - **Redis**：单实例阶段不引入。Redis 的正当代入点：多实例部署时的跨进程一致性、登录限流、热点会话缓存——见第 6 节触发条件。
  - **JSONL/关系型**：上下文的事实来源是 `messages` 流水，读最近 N 条即可；不需要为"当前轮次"单独建表（`conversation_persona_state` 只存少量会话级人格状态，够用）。
- 建议改动（低成本）：把 8 条/80 字提为配置项（如 `RECENT_CONTEXT_MAX_MESSAGES`、`RECENT_CONTEXT_MAX_CHARS`），便于按模型上下文窗口调参；保持默认值不变。

## 6. d) 长期记忆分工与 Redis 缓存层时机

**结论：结构化记忆=关系库真相源，语义记忆=Qdrant 派生索引，分工已正确；Redis 在出现多实例或限流热点前不需要。**

- 分工（现状即最佳实践）：
  - 结构化记忆：`memory_candidates → memory_records` 生命周期 + `memory_audit_events` 审计/撤销（`app/knowledge/mysql_repository.py`）。规则型提取（称呼/偏好/撤销）保留用户同意边界（`docs/memory-and-storage-design.md`）。
  - 语义记忆：Qdrant 只存"已生效记忆"的向量副本，由 `semantic_memory_outbox` 保证最终一致，撤销即删除，且可全量重建（`app/knowledge/semantic_outbox.py`、`scripts/semantic_memory_sync.py`）。`docs/POSTGRES_WEB_RUNTIME.md` 的定位（"Qdrant 不替代关系库"）正确。
- 向量库选型（外部实践，见第 8 节链接）：pgvector 适合"数据量小、想省一个服务"；Qdrant 在过滤 + HNSW + 轻量运维上平衡好；Milvus 面向亿级向量场景，毕设/早期产品不需要。**项目已选 Qdrant + outbox，保留即可**；若未来想砍服务，可平滑降级到 pgvector（outbox 抽象已把存储引擎隔离）。
- Redis 缓存层触发条件（明确"何时需要"）：
  1. 登录/注册限流：现为 DB 表实现（`app/auth/rate_limit.py`），单实例可接受；多实例或想保护 DB 时切换 Redis 滑动窗口/令牌桶（redis.io 官方限流模式）。
  2. 会话热点：每请求查 `web_sessions`（有 token_hash 索引即可支撑单实例）；QPS 显著上升后再加 Redis 会话缓存或纯 Redis 会话。
  3. 语义检索结果短期缓存：同一查询复用。
  4. 多实例部署：进程内缓存/限流失效时。
- 毕业设计阶段不建议提前引入 Redis；把触发条件写进文档即可。

## 7. e) 数据分类 → 存储引擎 → 保留策略 → 备份策略总表

| 数据分类 | 存储引擎 | 保留策略 | 备份策略 |
| --- | --- | --- | --- |
| 账号与凭证（web_users：argon2id 哈希/状态/邮箱） | 网页主库（Postgres 或 MySQL V2 二选一） | 账号生命周期内保留；注销按隐私流程（伪删→硬删） | 每日全量 + WAL/PITR |
| 邮箱验证码 / 密码重置码（仅哈希） | 同主库 token 表 | 过期即失效；过期行定期清理（建议 ≤7 天） | 随库（不单独备份） |
| 会话（web_sessions，仅哈希） | 同主库 | 7 天过期；登出/改密撤销；过期行定期清理 | 热数据，可不长期留档 |
| 登录限流计数（registration_attempts） | 主库（未来可 Redis） | 窗口滚动；封禁记录 ≤30 天 | 不备份（可重建） |
| 认证审计（auth_audit_events） | 同主库 | 建议 90 天~1 年，视合规 | 随库 |
| 人格注册表（身份/core_lines/门禁） | 代码仓库（profile_registry.py 等） | 随版本 | git |
| 人格版本/发布/绑定（persona_* 表） | MySQL V2 关系库 | 永久（发布历史与回滚依据） | 随库 |
| 关系/画像/情绪状态（profiles、profile_emotional_state） | 关系库 | 用户主导变更，长期 | 随库 |
| 会话流水（messages、model_invocations） | 关系库（Web 主库或 V2） | 审计留档；隐私硬删除流程待补（memory-and-storage-design.md 已列入下一步） | 随库 |
| 短期上下文派生状态（话题/情绪/纠偏） | 进程内（请求级重算；可选落 conversation_persona_state） | 不长期保留 | 不备份 |
| 结构化长期记忆（memory_records） | 关系库（生命周期管理） | 撤销即停用；物理删除走接口 | 随库 |
| 语义向量索引 | Qdrant（派生，outbox 同步） | 与结构化记忆同生命周期；可全量重建 | 不备份（备份 outbox+records，重建索引） |
| 开发期 JSONL | 本地文件（STORAGE_BACKEND=jsonl） | 本地 | 手动拷贝 |

## 8. 外部实践调研（2025-2026）与来源

- 会话状态与存储：Martin Fowler [SessionState](https://martinfowler.com/bliki/SessionState.html)（服务器端会话状态、客户端只持 opaque 标识是经典基线）；Laravel 官方 [HTTP Session](https://laravel.com/docs/master/session)（database/redis 驱动并存，单实例 database 够用）；2025 年 JWT vs 服务端会话的对比 [dev.to](https://dev.to/kharonte/jwt-vs-session-tokens-in-spring-boot-a-senior-devs-decision-guide-380n#comments) 与 [domainindia 2025 指南](https://domainindia.com/support/kb/jwt-login-session-cookies-a-complete-modern-guide-2025)（可撤销、可控登出场景推荐服务端会话）；Redis 会话实践 [Upstash](https://upstash.com/blog/redis-session-storage-nextjs-nodejs)。
- 向量库选型：Milvus 官方博客 [Choosing the right vector database](https://milvus.io/zh/blog/choosing-the-right-vector-database-for-your-ai-apps.md)；Zilliz [ES vs Milvus vs pgvector](https://zilliz.com.cn/blog/ES-vs-Milvus-vs-PGvector-LLM-Guide) 与 [Reddit 上的选型讨论整理](https://zilliz.com.cn/blog/Reddit-vector-database-selection-Pgvector-Redis-Milvus)；2025 指南 [From zero to 1B vectors](https://dev.to/pascal_cescato_692b7a8a20/from-zero-to-1-b-vectors-the-2025-no-bs-picking-guide-4k9o)；[pgvector vs 托管向量库（2025-05）](https://appmaster.io/blog/pgvector-vs-managed-vector-db#1)；社区整理 [vector-database-comparison](https://github.com/Yigtwxx/awesome-rag-production/blob/main/vector-database-comparison.md)。共同结论：小规模/单机 → pgvector 或轻量 Qdrant；需要强过滤+中等规模 → Qdrant；亿级、多租户 → Milvus。
- token/凭证哈希：OWASP [Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)（Argon2id 首选、内存与迭代参数、唯一盐）；社区安全清单 [credential-storage](https://github.com/himself65/auth-spec/blob/main/skills/security-best-practice/rules/credential-storage.md) 与 [authentication-patterns](https://github.com/netresearch/security-audit-skill/blob/main/skills/security-audit/references/authentication-patterns.md)（会话/验证 token 存哈希、过期与撤销）。
- 登录限流：Redis 官方 [Rate limiting 教程](https://redis.io/tutorials/howtos/ratelimiting/)（固定/滑动窗口、令牌桶实现）；[sliding window vs token bucket](https://ipasis.com/blog/redis-rate-limiting-sliding-window-vs-token-bucket)；2026 年模式汇总 [codercops](https://blog.codercops.com/blog/api-rate-limiting-patterns-redis-2026/) 与 [techsaas](https://www.techsaas.cloud/blog/rate-limiting-patterns-token-bucket-sliding-window/)。共同结论：分布式部署用 Redis 原子命令做限流是事实标准；单实例用数据库或内存实现可接受。

## 9. 结论：已正确 / 该改 / 成本与迁移顺序

### 9.1 当前做法已正确（保持不动）

1. Argon2id + 64MiB/t=3/p=2 + 12 位复杂度策略（OWASP 达标）。
2. 会话/验证/重置 token 只存哈希、一次性消费（FOR UPDATE）、改密撤销全部会话、CSRF 双提交 + compare_digest、HttpOnly+SameSite+Secure。
3. 人格"代码注册表=运行权威、DB=版本与管理面"的分层。
4. 记忆"关系库=真相源、Qdrant=可重建派生索引、outbox 最终一致、撤销同步删除向量"的双轨分工。
5. 审计只记 reason_code、限流主体只存哈希。

### 9.2 该改（按成本排序）

| 序号 | 问题 | 建议 | 实验成本 |
| --- | --- | --- | --- |
| A | 账号体系双轨（Postgres 与 MySQL V2 并存）无强制唯一性 | 启动校验：`PUBLIC_WEB_AUTH_ENABLED=true` 时必须且只能指定一个网页主库；文档写明边界 | 低（配置校验 + 文档） |
| B | 上下文窗口硬编码（8 条/80 字） | 提为配置项并写进 README/手册 | 低（常量 → Settings + 测试） |
| C | 登录限流只依赖 DB 表 | 加进程内 `RateLimitRepository` 回退实现；Redis 留接口，多实例再启用 | 低-中（小接口抽象） |
| D | 过期行无清理任务（web_sessions/验证码/重置码/限流计数） | 增加定期清理脚本并文档化保留策略 | 低（1 个脚本） |
| E | 记忆过期策略与隐私硬删除流程缺失 | 按 `docs/memory-and-storage-design.md` "下一步"清单实施 | 中（涉及 API 与状态机） |
| F | argon2 参数无迁移路径 | 参数集中到一处；verify 成功但参数落后时自动 rehash | 低 |

**迁移顺序：A → B → C → D → E（F 并入 A 一起做）。** 前四步都是低成本的"校验/配置/脚本"类改动，不触碰存储 schema 与核心链路，可在一个迭代内完成并回归（现有 814 passed 基线）。

## 10. 推荐的最小改动清单（3-5 条）

1. **单一网页主库校验（A）**：在 `app/core/config.py` 的 Settings 校验（或 `app/auth/runtime.py` 装配处）增加：`PUBLIC_WEB_AUTH_ENABLED=true` 时，`STORAGE_BACKEND`/V2/Postgres 组合必须明确指向一个主库，禁止"半开"组合；同步更新 `docs/POSTGRES_WEB_RUNTIME.md` 与 README 的选型边界说明。
2. **上下文窗口配置化（B）**：`RECENT_CONTEXT_MAX_MESSAGES`（默认 8）与 `RECENT_CONTEXT_MAX_CHARS`（默认 80）进 Settings，替换 `chat_service.py` 与 `chat_repository.py` 中的硬编码，并补一条契约测试。
3. **限流回退实现（C）**：新增进程内 `InMemoryRateLimitRepository`（带 TTL 清理）作为无 DB 时的回退与测试替身；Redis 版只留 Protocol 接口与文档触发条件。
4. **过期数据清理脚本（D）**：新增 `scripts/auth_expiry_cleanup.py`（清理过期 `web_sessions`、已用/过期验证码与重置码、超窗 `registration_attempts`），dry-run 模式，加入 README 运维一节。
5. **（可选）argon2 参数集中与 verify-and-rehash（F）**：把哈希参数抽为常量/配置，登录时检测参数落后自动重哈希，为未来升级留迁移路径。

---

*报告生成方式：只读代码与文档审计 + 外部公开资料调研；未修改任何源码，未执行 git 操作。*
