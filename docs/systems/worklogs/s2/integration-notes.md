# S2 集成说明

本文件供集成人员连接共享入口时使用。S2 开发不直接修改冻结文件。

## QQ 入口

在 `integrations/qq_bot/bot.py` 收到 OneBot 消息或撤回通知后，可调用：

```python
from app.channels.adapters import OneBotEventAdapter

channel_event = OneBotEventAdapter().adapt(event)
```

适配器支持 NoneBot 事件对象和等价 mapping，但自身不导入 NoneBot。集成前应保留现有 `event_to_incoming()` 行为，先以旁路方式比较统一事件与旧映射，再决定切换下游消费者。

## Core API 入口

在 `/api/v1/chat` 或 `/api/v1/chat/stream` 收到 `ChatRequest` 后，可调用：

```python
from app.channels.adapters import CoreApiEventAdapter

channel_event = CoreApiEventAdapter().adapt(request)
```

没有 `platform_user_id` 时使用 `user_id`；群 ID 存在时建立 group thread，否则使用 `session_id` 建立 private thread。

集成状态：已接入 `/api/v1/chat` 和 `/api/v1/chat/stream`。当前只使用统一事件中的规范化消息文本，原有 session、平台身份、Database V2、ChatService、S7 文本渲染和响应行为保持不变。

## Hermes / Weixin

当前不要创建 `HermesEventAdapter`。应先在项目内确定 Hermes 原始入站消息的稳定入口和真实字段，再在 `app/channels/adapters/` 中实现。现有能力矩阵明确表示 Weixin 不支持原生语音、撤回、typing、profile update 和 voice call。

## 响应投递

平台发送前调用：

```python
from app.channels import capabilities_for, evaluate_delivery

result = evaluate_delivery(response, capabilities_for("qq"))
```

只有 `result.delivered_parts` 可以交给平台发送器。`omitted_parts` 应进入可观察性记录，不应模拟发送成功。

## 冻结文件待更新项

集成人员合并时在 `README.md` 和 `AGENTS.md` 记录：

- S2 契约和 OneBot/Core API 适配器已经实现，但尚未接入共享运行时入口。
- Weixin 原生语音、撤回、typing、profile update 和 voice call 明确为不可用。
- S2 聚焦测试 12 passed，QQ 回归 81 passed，项目标准全量回归 429 passed。
