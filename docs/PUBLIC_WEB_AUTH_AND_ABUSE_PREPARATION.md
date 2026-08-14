# 公开 Web 测试：账号、记忆隔离与反滥用实施设计

状态：实施中。`migrations/v2/004_public_web_auth.sql`、`app/auth/registration.py`、`app/auth/registration_router.py`、`app/auth/rate_limit.py`、`app/auth/audit.py` 与 `app/auth/smtp_delivery.py` 已实现待验证用户、令牌哈希、一次性激活、不回显令牌的 API 工厂、基于 MySQL 原子计数的可注入注册/登录限流边界、认证审计写入和 SMTP 验证码投递 Provider；生产数据库、HTTPS 域名和验证码尚未接入，且 SMTP 默认关闭，因此本文不是“已开放注册”的声明。

## 1. 目标与非目标

目标是让外部测试用户可以用邮箱注册、验证、登录、管理自己的资料和记忆，同时保证一个账号不能读取、修改或推断另一个账号的聊天与记忆。

本阶段不做：社交登录、付费订阅、邀请返利、永久 API Key、客户端保存访问令牌、绕过邮箱验证的开放注册。

## 2. 身份模型

```text
email -> web_user -> profile -> conversations / memories
                      |
                      +-> server-side sessions
```

- `web_user` 是公开网页登录身份，使用随机 UUID，不使用连续数字 ID。
- `profile` 是 HeadCore 的人物/关系实体；一个公开账号只绑定自己的普通用户 profile。
- 用户浏览器只持有 HttpOnly 的不透明会话 Cookie；会话详情只存服务端。
- 现有 `memories.profile_id` 已具备按 profile 隔离的基础。公开 API 必须从认证会话得到 profile，禁止接受前端传来的任意 `user_id` 作为授权依据。

## 3. 数据库迁移目标

在 MySQL V2 启用后新增以下表，均使用 UUID、UTC 时间和索引：

| 表 | 关键字段 | 作用 |
| --- | --- | --- |
| `web_users` | `id`, `profile_id`, `email_normalized`, `password_hash`, `status` | 账号与 profile 的一对一绑定；邮箱唯一。 |
| `email_verification_tokens` | `user_id`, `token_hash`, `expires_at`, `used_at` | 一次性验证令牌；数据库只保存哈希。 |
| `web_sessions` | `user_id`, `token_hash`, `expires_at`, `revoked_at`, `last_seen_at` | 可撤销的服务端会话；Cookie 只保存随机原文 token。 |
| `registration_attempts` | `subject_hash`, `window_start`, `count`, `blocked_until` | 邮箱/IP/设备信号的限流记录；不保存原始 IP。 |
| `auth_audit_events` | `user_id`, `event_type`, `outcome`, `metadata` | 登录、验证、注销、限流和会话撤销审计。 |

密码使用 Argon2id。当前实现见 `app/auth/passwords.py`；不允许明文、SHA-256 或可逆加密密码。

## 4. 注册流程

1. 用户提交邮箱、显示名、密码和人机验证结果。
2. 服务端规范化邮箱，拒绝空白、无效格式、过长字段和未允许的额外字段。
3. 按 IP 哈希、邮箱哈希和人机验证结果检查限流；超限时统一延迟并返回模糊错误。
4. 密码执行 Argon2id 策略校验和哈希。
5. 创建 `web_user`、普通 `profile` 和未验证状态；**不创建可用会话**。
6. 生成高熵、一次性、短有效期验证令牌，数据库只保存哈希，邮件只发送验证链接。
7. 用户点击链接后以 POST 提交令牌；验证成功后启用账号并创建服务器会话。

“该邮箱是否已注册”“邮件是否存在”等响应必须保持语义相近，避免账号枚举。验证邮件重发也遵守相同限流。

## 5. 登录、会话与个人中心

- 登录失败、账号不存在、未验证、被封禁应使用防枚举的公共提示；详细原因仅进入审计日志。
- 登录成功后创建随机会话，Cookie 设置 `HttpOnly`、`SameSite=Lax`；生产 HTTPS 时才设置 `Secure`。
- 所有写操作使用 CSRF 防护；Cookie 会话本身不是 CSRF 防护。
- 登录响应中的 CSRF 令牌只允许留在当前页面内存；浏览器对 `POST /api/v1/chat`、`POST /api/v1/chat/stream`、`POST /api/v1/audio/chat/file` 和 `DELETE /api/v1/memories/{memory_id}` 必须发送 `X-CSRF-Token`。令牌不得进入 URL、Cookie、localStorage 或日志。
- 公开认证启用时，上述聊天、流式聊天、音频聊天和记忆 API 一律从 `hutao_session` 的服务端记录取得 `profile_id` 与会话 ID，忽略请求中的 `user_id`、`session_id`；伪造的平台身份字段会被拒绝。
- 个人中心只能读取和修改当前账号允许的显示名、密码、会话列表、记忆偏好和数据导出/删除申请。
- 改邮箱、改密码、删除账号、导出记忆、撤销其他会话要求当前密码或近期再认证。

## 6. 记忆规则

1. 聊天 API 从服务端会话取得 profile，不接受浏览器自选的 profile/user ID。
2. `GET /memories` 只能查询当前 profile 的允许投影。
3. 单条记忆删除必须同时按 `memory_id + profile_id` 条件删除，防止 IDOR。
4. 默认不把敏感原始输入、外部网页全文、精确路线、令牌或密码写入长期记忆。
5. 用户可以查看、删除自己的记忆；管理员查看必须走独立审计与授权流程。

## 7. 反白嫖与反机械注册

技术防护不能单独解决成本问题，必须叠加策略：

- 邮箱验证后才允许模型调用。
- 注册、登录、验证邮件重发、密码重置、对话和音频上传分别限流。
- 公开测试采用邀请码/审核队列/每日名额，而不是无限注册。
- 在注册和高成本动作处接入 CAPTCHA 或 Turnstile；服务端验证，不信任前端结果。
- 对每账号设置每日消息、音频时长、并发会话和世界工具预算；达到上限返回明确的等待信息。
- 异常设备、批量相似邮箱、频繁失败、代理滥用进入人工审核或短期封禁，不自动永久封号。
- 生产限流必须用 Redis 或数据库原子计数，不使用单进程内存计数。

## 8. 开放测试前置条件

| 条件 | 当前状态 |
| --- | --- |
| MySQL V2 和账户迁移已应用 | 未完成 |
| 真实邮件服务与已验证发信域 | 未完成 |
| HTTPS 域名与 Cookie Secure 配置 | 未完成 |
| CAPTCHA/Turnstile 服务端校验 | 未完成 |
| Redis/共享限流 | 未完成 |
| 隐私政策、服务条款、删除与导出流程 | 未完成 |
| 账号、邮箱、会话、记忆隔离自动化测试 | 认证、CSRF、聊天/音频身份覆盖和记忆删除边界已覆盖；完整生产验收未完成 |
| 小规模邀请码测试 | 未开始 |

## 9. 实施顺序

1. 新增 MySQL 账户、会话、验证、审计迁移与 repository。
2. 实现服务器端认证依赖、Argon2id、会话 Cookie、CSRF 和统一限流接口。
3. 实现注册、验证、登录、注销、密码重置；邮件仅通过可替换 Provider 发送。
4. 修改聊天和记忆 API，强制由会话确定 profile。
5. 构建登录、注册、验证结果、个人中心和记忆管理网页。
6. 配置生产外部服务后做邀请码小规模验收，再收集问题扩大范围。
