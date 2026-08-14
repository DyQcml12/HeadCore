# HutaoChatCore 项目功能与外部调用验收报告

> 验收日期：2026-07-19  
> Python 环境：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`  
> 项目状态：`DEGRADED`（核心聊天和部分真实模型可用，外部配置/平台能力仍有边界）  
> 安全说明：本报告不包含 API Key、Token、二维码、完整账号 ID 或聊天正文。

## 1. 结果摘要

| 分类 | 结果 |
| --- | --- |
| Core 健康与控制中心 | PASS |
| 全量自动化回归 | PASS：725 passed, 2 skipped |
| HeadCore 人格与世界工具编排 | PASS；世界工具审计可见 |
| 高德地区解析与天气 | PASS：真实线上请求成功 |
| SenseVoice ASR | PASS：真实样本 CER 0.0 |
| emotion2vec | PASS/DEGRADED：5/5 命中，但加载有缺失键警告 |
| QQ/NapCat 进程 | ONLINE；当前端到端新消息仍需用户在 QQ 中复核 |
| 新闻 | NOT_CONFIGURED：候选源存在，启用数为 0 |
| 国内官网渲染采集 | BLOCKED/NOT_CONFIGURED：开关关闭，且需逐站法律审核 |
| Ollama/VLM 图片识别 | BLOCKED：Ollama 在线但模型列表为空；当前只能 OCR 读字 |
| Database V2 正式链路 | BLOCKED：数据库和迁移门禁未满足 |
| Hermes/微信普通好友添加 | UNSUPPORTED：当前公开链路没有普通微信好友 API |

## 2. 测试证据

| 项目 | 测试方式 | 结果 | 证据/解释 | 当前边界 |
| --- | --- | --- | --- | --- |
| Python runtime | `scripts/python_runtime_preflight.py` | PASS | Python 3.11.15、FastAPI、Pydantic、pytest 均 ready | 只证明运行时导入，不证明每个原生模型 |
| Python 编译 | `python -m compileall app integrations scripts tests -q` | PASS | compileall 无错误 | 不等于线上服务已连通 |
| 全量测试 | `python -m pytest tests -q -p no:cacheprovider` | PASS | `725 passed, 2 skipped` | 2 个 skip 为外部/可选环境测试 |
| Core `/health` | HTTP GET `127.0.0.1:8000/health` | PASS | HTTP 200，provider/model 已配置状态可见 | 不暴露密钥 |
| 控制中心页面 | `/control`、`/control/qq`、`/control/weixin`、`/control/diagnostics` | PASS | 全部 HTTP 200 | 浏览器视觉回归需另行执行 |
| 控制 API | `/api/control/status`、`/v1/models` | PASS | HTTP 200 | 管理写操作仍需管理员身份 |
| 架构 HTML 发布稿 | `scripts/build_architecture_publication.py` | PASS | `output/html/hutaochatcore-architecture.html` 已按本轮文档生成 | PDF 刷新脚本缺 Node `playwright`，旧 PDF 不代表本轮内容 |
| HeadCore 普通聊天 | Core `/api/v1/chat` | PASS | DeepSeek live response，审计记录写入 | 依赖外部模型额度和网络 |
| 人格路由 | 自动化人格/平台测试 | PASS | QQ 使用 `hutao_v1`，微信使用 `xiaohe_v1`，共享 HeadCore | 真实长对话人格质量需实时评测 |
| 人格连续性 | `scripts/persona_continuity_eval.py` | PASS | 离线连续性场景通过 | 离线不代表模型每轮都稳定 |
| 世界工具显式调用 | Core 聊天 + 审计字段 | PASS | `ready / weather_current / 1` | QQ/微信只在用户明确询问时调用 |
| 世界工具拒绝编造 | 缺位置模拟 provider 回归 | PASS | 本地回复“告诉我城市或区县名” | 未来新增世界状态需继续接入 guard |
| Amap 地区解析 | `world_amap_smoke.py --district 长沙` | PASS | 返回唯一城市级 adcode `430100` | 同名区县仍需用户确认 |
| Amap 当前天气 | `world_amap_smoke.py --adcode 430100` | PASS | 返回天气、温度、湿度、风向、报告时间 | 真实值有 15 分钟缓存，不承诺秒级 |
| Amap IP 定位 | 代码/同意门禁检查 | NOT_RUN | 需要用户明确同意公网 IP 粗略定位 | 不自动读取或推断用户 IP |
| Amap 路线 | 适配器与自动化测试 | PASS/DEGRADED | 路线代码和缓存存在 | 真实路线额度/坐标仍需专门账号测试 |
| 新闻源清单 | `world_source_manifest_check.py` | PASS | 8 个候选源，API/RSS/官方页面策略合法门禁存在 | 目录不代表已启用 |
| 新闻运行状态 | `world_news_smoke.py` | NOT_CONFIGURED | catalog=8、registered=3、enabled=0 | 需要逐源写入启用/授权配置 |
| GDELT | 适配器存在 | NOT_CONFIGURED | discovery-only，默认关闭 | 不抓取链接文章正文 |
| 国际 RSS | UN/WHO RSS 适配器存在 | NOT_CONFIGURED | 默认关闭 | 需确认条款和访问频率 |
| 国内官方页面 | gov.cn 等清单存在 | NOT_CONFIGURED | 当前未执行渲染采集 | robots/条款不允许的站点必须保持关闭 |
| 三天缓存 | 自动化缓存/TTL 测试 | PASS | TTL 上限和跨请求共享已实现 | 当前天气自身 TTL 为 15 分钟 |
| 渲染爬虫 | 配置状态 | BLOCKED | `WORLD_RENDERED_FETCH_ENABLED=false` | 开启前需要浏览器运行时和逐站法律批准 |
| DeepSeek | `/health` 与线上聊天 | PASS | live API response，fallback=false | 受 API Key、额度、网络影响 |
| FFmpeg | QQ 语音相关自动化测试 | PASS | WAV/MP3 转换路径通过 | 需在 NapCat 中验证实际 record 展示 |
| SenseVoice ASR | `scripts/asr_file_smoke.py --limit 1` | PASS | `iic/SenseVoiceSmall`，设备 `cuda:0`，CER=0.0 | 单样本不代表所有口音/噪声 |
| emotion2vec | `scripts/audio_emotion2vec_smoke.py` | PASS/DEGRADED | 5/5 已知情绪命中 | 权重缺失键警告，需复核模型包版本 |
| 图片缓存/路由 | 本轮 QQ 图片缓存 + RapidOCR | PASS/DEGRADED | 图片可下载，OCR 可读文字；已禁止 OCR 文本驱动模型猜测物体 | 没有 VLM 时不能可靠识别场景和物体 |
| Ollama 图片模型 | `scripts/qq_vision_ollama_smoke.py` | BLOCKED | `ollama_http_404` | `/api/tags` 无目标模型或服务路由不匹配 |
| Database V2 schema | `database_v2_readiness_check.py` | BLOCKED | 数据库名不是目标库、开关 false、V2 表缺失 | 不得直接对用户正式库迁移 |
| 关系系统虚假账号 | 自动化 QQ/Weixin identity 测试 | PASS | 虚假平台身份合并/权限规则通过 | 正式 MySQL V2 仍需隔离库验收 |
| QQ Bridge | 8080 监听、NapCat WS 日志 | ONLINE | OneBot11 reverse WS 已启动，NapCat 有收发日志 | 新修复后的天气需用户发一条消息复核 |
| QQ 文本收发 | NapCat 日志历史证据 | PASS/HISTORICAL | 有私聊收发记录 | 本报告未代替当前账号新一轮人工验收 |
| QQ 语音入站 | 代码/离线测试 | BLOCKED | ASR 能力已可用，真实 QQ record 尚未本轮发送 | 需要在 QQ 发真实语音并核对 transcript/emotion |
| Weixin 文本 | Hermes 历史日志/适配器 | HISTORICAL | Hermes 连接逻辑和小何投影存在 | 当前未重新执行 pairing 与私信闭环 |
| Weixin 语音附件 | 通道契约/代码 | BLOCKED | 取决于 Hermes 是否提供可读附件字段 | 平台不提供时不能由 Core 伪造 |
| Weixin 好友申请 | 平台能力审计 | UNSUPPORTED | Hermes/iLink 公开接口没有普通微信好友添加 API | 只能使用 pairing/白名单申请模式 |
| Hermes tools/tool_calls | OpenAI schema 检查 | UNSUPPORTED | `/v1/chat/completions` 没有 `tools/tool_choice/tool_calls` 字段 | 世界工具只能由 Core 内部编排 |
| Windows 拦截 | runtime/model smoke | DEGRADED | 核心 Python 和模型已运行；部分原生 provider 仍可能被 WDAC 拦截 | 按 Code Integrity 事件逐项审核，不能绕过策略 |

## 3. 天气问题的最终使用方式

在 QQ 中直接发送：

```text
告诉我长沙天气怎么样
```

现在的处理顺序是：解析“长沙” -> Amap 地区解析 -> 获取 `430100` 当前天气 -> 将带来源和时间的事实交给模型组织 -> 返回 QQ 文本。若只发送“天气怎么样”，Core 会询问城市，不会猜测 IP，也不会输出“我看不了天气”这类模型臆测。

如果仍看到旧回复，按以下顺序排查：

1. 确认 `127.0.0.1:8000/health` 返回 200。
2. 查看 `logs/storage/model_invocations.jsonl` 中该时间之后的 `world_context_status`。
3. `ready/weather_current/1` 表示 Amap 已成功，问题在 QQ Bridge 发出或回复展示；`needs_location` 表示输入没有包含可解析的城市；`disabled/unavailable` 表示配置或外部来源问题。
4. 不要把 NapCat 的 WebUI Token 当成 Amap Key，也不要为了天气关闭 QQ/微信服务。

## 4. 仍需用户准备或决定的项目

| 项目 | 用户需要提供/操作 |
| --- | --- |
| Amap | 在 `.env` 填 Web 服务 Key，并确认条款允许项目用途；当前 Key 已能完成天气 smoke |
| 新闻 | 逐个选择合法源，填写 `WORLD_SOURCE_ENABLED_IDS` 与 `WORLD_SOURCE_LEGAL_APPROVED_IDS`；没有合法批准就保持为空 |
| VLM | 安装并启动 Ollama，下载一个许可允许的视觉模型，确认 `/api/tags` 返回模型 |
| Database V2 | 准备隔离测试库，先迁移再 readiness，再开启 `DATABASE_V2_ENABLED`；不要直接改正式库 |
| QQ | 在已登录 NapCat 的 QQ 中发送天气、语音和图片样本，记录结果而不是 Token |
| Weixin | 使用 Hermes 支持的 pairing 申请/批准流程；不能要求 Core 自动加普通微信好友 |
| 音频 | 提供有参考文本的中文语音样本，评估 ASR CER 和情绪置信度 |

## 5. 结论

当前项目不是“所有外部能力都已上线”，而是 HeadCore 主体、平台事件、人格路由、Amap 天气、ASR、TTS 和情绪识别已具备可运行证据；新闻、VLM、Database V2、微信好友添加和 QQ 真实语音闭环仍分别受配置、模型、数据库或平台 API 限制。后续开发应按本报告的 `BLOCKED/NOT_CONFIGURED/UNSUPPORTED` 项逐项解除，不应通过伪造接口或放宽安全门禁来制造“已完成”。
