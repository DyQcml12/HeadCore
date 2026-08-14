# S3 多模态感知系统实施报告

日期：2026-07-14

## 实现范围

- 新增不可变 typed contract：输入、观察、provider trace、记忆资格。
- 新增本地附件与远程 URL 预检：MIME、大小、空音频、凭据 URL、localhost 和非全局字面 IP。
- 新增 ASR adapter：兼容 `str` 及结构化对象，保留 emotion、language、confidence。
- 新增视觉 adapter：兼容现有 `VisionObservation` 风格字段及包装结果。
- 新增感知管线：输入校验、provider 调用、fallback、归一化、质量门、脱敏与记忆资格。
- 新增 OCR/VLM 冲突策略：合并可见文字与场景观察，冲突时采用较低置信度并标记 `ocr_vlm_conflict`，记忆资格为 `review`。
- 新增可选真实 FunASR smoke；缺少输入时明确 `SKIP`，模型/provider 错误明确 `FAIL`。
- 新增 S2 `ChannelEvent`/`ChannelAttachment` 到 `PerceptionInput` 的安全映射。
- 新增 S6 routing trace 到感知 trace 的脱敏映射。
- 兼容当前 QQ 视觉入口的 `adapt_vision_result()`，只归一化已经成功的 provider 结果，不重复下载或调用模型。

## 安全边界

- 未执行或主动解析用户文件内容。
- 未增加网络调用；URL 校验不下载资源。
- S3 核心开发未修改 ChatService、长期记忆、现有 provider、模型、Ollama 或 `.env`。
- provider 失败不会生成观察文本，错误消息经过现有 secret redactor。

## 已知集成边界

- S2/S6 公开契约已存在，S3 通过 `integration.py` 只读依赖其公开 contract，不导入内部 repository 或 router 状态。
- 域名 DNS 解析、重定向和实际响应流的 SSRF/大小校验属于未来受控下载器，不能仅依赖当前 URL 预检。
- Ollama 当前没有注册视觉模型，视觉真实 smoke 按设计不运行。
