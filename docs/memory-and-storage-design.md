# 记忆与聊天存储设计

## 核心原则

聊天内容和长期记忆不是一回事。

- `messages` 表保存对话流水，用来审计、回放、排查问题。
- `memories` 表只保存被判断为有长期价值的信息。
- 不能把每一句聊天都当作长期记忆。
- 用户撤销的内容必须停止注入 prompt。

## 聊天内容怎么存

每次用户发消息，会写入 `messages` 表：

- `role = user`
- `content = 用户原话`
- `content_hash = 内容哈希`
- `session_id`
- `user_id`

模型回复也会写入 `messages` 表：

- `role = assistant`
- `content = 最终给用户看到的回复`
- `model_invocation_id = 本次模型调用记录`

这意味着数据库里确实会有完整聊天流水，但它只是历史记录，不会全部塞回模型。

## 模型调用怎么存

每次回复会写入 `model_invocations` 表：

- 模型供应商和模型名
- 是否真实调用 API
- 是否使用兜底回复
- 延迟
- prompt hash
- response hash
- 错误信息

默认不存完整 prompt，只存哈希，避免把过多上下文和敏感内容长期保存。

## 长期记忆怎么存

`memories` 表只存结构化记忆，例如：

- `user_alias`: 用户希望被怎么称呼
- `user_preference`: 用户明确表达的偏好
- `project_context`: 用户长期项目相关信息
- `conversation_preference`: 用户希望怎么聊天，例如少说点、自然点、别一大段
- `revocation`: 用户撤销或要求不要记的内容

当前不会把普通情绪、临时吐槽、隐私推断直接写成长期记忆。

## 聊天途中怎么知道用户喜好

当前是规则型识别：

- 用户说“叫我阿明” -> 写入 `user_alias`
- 用户说“少说点”“别一大段”“自然点” -> 写入 `conversation_preference`
- 用户说“不要记”“忘掉” -> 写入 `revocation`

写入长期记忆时会先规范化，不直接把整句塞进 prompt：

- `我以后改称呼了，叫我阿明。` -> `user_alias`: `称呼=阿明`
- `少说点，别一大段，自然点。` -> `conversation_preference`: `回复风格=短句；自然口语`
- `别给健康建议。` -> `conversation_preference`: `回复风格=不主动给健康建议`

后续可以升级为模型辅助提取，但必须保留规则和用户同意边界。

## 记忆怎么注入 prompt

每次生成回复前，只读取少量可用记忆：

- 默认最多 8 条
- 只读允许类型
- 过滤被撤销的记忆
- 用短文本注入 prompt

不是把全部历史聊天塞进去，也不是把整个数据库塞进去。

## 撤销怎么处理

撤销和删除分两层。

用户在聊天里说“不要记”“忘掉”时：

- `memories` 写入一条 `revocation`
- 后续 prompt 过滤相关长期记忆
- 不直接删除历史聊天流水

原因：

- `messages` 是审计流水，删除会破坏对话记录和调试链路。
- `memories` 里写入 `revocation`，后续注入时过滤相关记忆。

也就是说：

- 历史聊天还在 `messages`
- 长期记忆不会再使用被撤销内容
- prompt 不再注入被撤销内容

用户也可以通过接口查看或删除长期记忆：

- `GET /api/v1/memories?user_id=...`
- `DELETE /api/v1/memories/{memory_id}?user_id=...`

这个删除只删除 `memories` 里的长期记忆，不删除 `messages` 聊天流水。后续如果要支持聊天流水硬删除，需要单独增加隐私删除流程。

## 当前限制

- 偏好提取还是规则型，只覆盖明确说出口的聊天偏好。
- 记忆冲突合并还比较简单。
- `memories` 表没有 `active` 字段，目前撤销靠 `revocation` 记录过滤，接口删除靠物理删除单条长期记忆。
- 长期摘要还没做，目前只取结构化记忆。

## 下一步

1. 增加 `memory_type` 的细分类。
2. 增加记忆冲突合并。
3. 增加记忆过期策略。
4. 增加用户可编辑记忆接口。
5. 增加隐私硬删除流程。
