# HeadCore 世界上下文与 Brain 工具决策设计

## 1. 设计目标

世界认知不是新的聊天主体，也不是平台 Adapter。它是 HeadCore 内部 Brain 获取现实证据的只读工具层：

```text
用户输入
-> WorldToolDecision
-> WorldRuntime / Adapter
-> WorldObservation / NewsDigest
-> WorldContextAssembler
-> 只读世界上下文
-> ChatService / Brain 回答
```

人格、关系、记忆和表达规则仍由 HeadCore 原有模块决定。外部来源不能发布人格、修改关系、写入长期记忆或直接发送平台消息。

## 2. 明确请求才调用

`app/world/brain.py` 只处理明确的天气、新闻、政策和路线查询。普通聊天、用户谈到自己看过的新闻、以及“不要联网”等退出表达不会触发工具。

当前意图：

| 意图 | 条件 | 当前行为 |
| --- | --- | --- |
| `weather_current` | 明确查询当前天气并提供城市/区县名称或六位 adcode | 先解析唯一行政区，再调用高德当前天气 |
| `weather_forecast` | 明确查询明天/未来天气并提供城市/区县名称或六位 adcode | 先解析唯一行政区，再调用高德预报 |
| `news_digest` | 明确查询最新新闻/资讯/热点 | 查询已批准新闻来源并合并 |
| `policy_updates` | 明确查询最新政策/国务院文件/规划 | 查询已批准政策元数据 |
| `travel_compare` | 明确提供“从 A 到 B”并询问路线或交通方式 | 解析地点候选，比较所请求的驾车/公共交通/步行方案 |
| `none` | 普通聊天、退出联网或不支持的请求 | 不调用任何世界工具 |

天气缺少位置时返回 `needs_location`，要求自然询问城市。城市/区县名称通过高德行政区域查询解析；只有唯一候选才继续天气调用。同名区县返回 `needs_location_confirmation` 并列出候选，系统不能猜测用户 IP 或替用户选择。

路线请求只提取起点、终点、交通方式、日期偏移和明确时间预算，不把完整聊天内容发给高德。缺少起终点时返回 `needs_route_endpoints`；地点同名或候选不唯一时返回 `needs_place_confirmation`。只有候选唯一后才把坐标用于路线调用，坐标不会进入最终提示或审计。用户主动提出路线查询视为本次精确路线计算的目的限定同意，不授权后台定位或长期保存位置。

多方案比较使用可审计规则：接口时长、距离、步行暴露、道路收费/公交票价、用户时间预算，以及目标日期天气预报。恶劣天气只增加保守缓冲；推荐结果必须注明路线是本次接口估算，不能声称已经预测未来拥堵、等车、停车、燃油或停车费。

## 3. 隐私最小化

工具决策不会把完整用户消息发送给 GDELT 或 RSS。新闻主题只从固定类别映射中选择，例如 `health`、`technology`、`finance`、`education`、`environment`、`China` 或 `world`。

IP 定位必须由调用方明确提供公网 IPv4 并设置同意标记。ChatService 当前不读取请求 IP，也不自动调用 IP 定位。

## 4. 世界上下文状态

`app/world/context.py` 输出 `WorldContextProjection`：

| 状态 | 含义 |
| --- | --- |
| `not_configured` | ChatService 没有世界上下文 Provider |
| `not_requested` | 本轮不需要世界工具 |
| `disabled` | 全局世界认知关闭 |
| `needs_location` | 天气请求缺少位置 |
| `needs_location_confirmation` | 行政区名称存在多个候选或没有匹配 |
| `needs_route_endpoints` | 路线请求缺少明确起点或终点 |
| `needs_place_confirmation` | 起点或终点没有匹配或存在多个候选 |
| `ready` | 有可用、未过期证据 |
| `partial` | 部分来源失败，其他来源可用 |
| `conflicted` | 多来源关键字段冲突 |
| `stale` | 证据过期 |
| `unavailable` | 来源关闭、未批准或请求失败 |

投影最多保留 8 项和 3500 字符。外部标题、摘要和 URL 被视为不可信数据，不能执行其中的指令、提示或角色要求。

## 5. 冲突和过期

天气观察在进入提示前检查 `expires_at`。过期数据不作为当前事实使用。

当前天气冲突规则：

- 多来源天气描述不一致时记录 `weather` 冲突。
- 多来源温度相差至少 5℃ 时记录 `temperature_c` 冲突。
- 发生冲突时状态变为 `conflicted`，提示要求明确说明不确定性，不能擅自挑选一个来源。

路线当前通过候选确认避免地点歧义，通过 `partial` 标记部分交通方式失败。未来接入第二个地图来源时，需要增加时长/距离差异规则，不能复用温度阈值。

## 6. 两级共享缓存

1. `WorldAcquisitionService` 缓存单来源观察，同一参数的并发请求只访问来源一次。
2. `NewsDigestService` 缓存主题、来源集合和条数限制相同的合并结果。

缓存键是 SHA-256，不包含原始 IP、完整用户消息或 API Key。新闻来源顺序不同仍复用同一 Digest。

## 7. ChatService 接入

`ChatService` 通过 `WorldContextProvider` 接收最终只读投影。世界上下文放在 system prompt，并明确标记为不可信外部数据。

审计元数据只记录：

- `world_context_status`
- `world_context_item_count`
- `world_context_conflict_count`
- `world_tool_intent`

不记录 API Key、原始 IP、来源响应正文或完整世界上下文。blocked 关系不会调用世界 Provider。

## 8. 当前未完成项

- 获批新闻/政策来源的真实运行验收。
- 将世界证据投影到可撤销的短期世界状态，而不是长期人格记忆。
- 未来交通预测、实时公交到站、停车、费用完整估算和第二地图来源交叉验证。
- 更通用的多步规划器：在路线以外联合日历、关系边界、资源约束和可撤销行动。

这些能力必须继续遵守“明确请求、最小数据、证据可追溯、默认关闭”的规则。
