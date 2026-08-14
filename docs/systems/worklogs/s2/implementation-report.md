# S2 统一平台事件系统实现报告

日期：2026-07-14

## 实现范围

- 在 `app/channels/contracts.py` 定义平台身份、会话、消息、附件、事件、能力、响应和投递结果契约。
- 在 `app/channels/adapters/onebot.py` 实现不依赖 NoneBot 类型的 OneBot v11 消息与撤回事件适配器。
- 在 `app/channels/adapters/core_api.py` 实现 Core API 请求适配器。
- 在 `app/channels/capabilities.py` 显式声明 QQ、Weixin 和 Core API 能力，并提供确定性的投递能力检查。
- Hermes 事件适配器未实现，因为当前项目内没有稳定的 Hermes 原始事件入口；没有虚构私有字段或模拟能力。

## 契约决策

- 平台 ID 和消息 ID 在进入契约时统一转为字符串，避免大整数精度丢失。
- 时间戳统一转为带 UTC 时区的 `datetime`，拒绝无时区契约数据。
- 消息事件必须携带 `message`，撤回事件必须携带 `recalled_message_id`。
- 附件不下载正文。安全契约只保留清洗后的文件名、大小、媒体尺寸、时长和不透明平台引用。
- OneBot 的 URL、token、任意 segment data 不进入统一契约；未知 segment 只保留清洗后的类型和固定摘要。
- Adapter 只做平台字段映射，不判断管理员、关系、权限、人格或记忆策略。

## Capability Matrix

| 能力 | QQ | Weixin | Core API |
| --- | --- | --- | --- |
| text | 是 | 是 | 是 |
| image | 是 | 是 | 否 |
| file | 是 | 是 | 否 |
| audio attachment | 是 | 是 | 否 |
| native voice | 是 | 否 | 否 |
| recall | 是 | 否 | 否 |
| typing | 否 | 否 | 否 |
| profile update | 否 | 否 | 否 |
| voice call | 否 | 否 | 否 |

Weixin 当前音频能力按文件附件声明，不把它模拟为原生语音气泡。调用方必须在投递前调用 `evaluate_delivery()`；缺失能力会返回 `degraded` 或 `unsupported`，不会返回伪成功。

## 边界

- 未修改 QQ Bot、HermesRuntime、ChatService、数据库、控制中心或运行时配置。
- 未发送真实平台消息。
- 未增加依赖、网络请求、登录、pairing 或 token 管理代码。

