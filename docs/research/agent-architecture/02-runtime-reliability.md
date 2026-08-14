# T2：运行时稳定性与生成质量失败模式分析

> 分析对象：HutaoChatCore（2026-08-14 项目清理后的代码基线，本地全资产环境实测 814 passed / 2 skipped；导出仓库干净环境 810 passed / 6 skipped）。
> 分析范围：文本聊天（流式/非流式/修复路由）、语音识别、语音合成、世界工具、数据库、认证与 SMTP。
> 方法：逐文件精读 + 行号定位 + 行业实践对照（web 检索，文末附来源链接）。本报告只描述现状与建议，未修改任何文件。

## 1. 摘要

整体判断：本项目已具备相当完整的"失败不崩、失败可查"骨架——Provider 路由（超时/重试/熔断/脱敏 trace）、本地规则评估器（30+ 条规则）、本地降级回复、世界工具的证据门与冲突检测、TTS 的短时票据闭环，在同类毕设/个人项目中属于上游水平。但存在一条结构性主线：所有质量门禁在"非流式"路径上完整，而 Desk 主入口走流式且默认不做实时评估；同时"慢"（首字延迟、修复重生成、每查询新建 MySQL 连接、ASR 首次加载）是最普遍的可感知问题，而不是"崩"。

### 最严重的 5 个失败模式（一句话）

1. 流式中断无标记：文本流式回复中途断流时，已发出的半截文本直接结束，客户端无法区分"说完了"与"断了"，且不补发降级文本（app/services/chat_service.py 的 stream_reply 部分输出分支）。
2. 流式主路径绕过评估门：Desk 默认走 /api/v1/chat/stream，未启用世界工具时不做实时 evaluator 门禁，失败回复只被记录不被替换（chat_service.py:381 起 stream_reply 的 buffer_for_world_grounding 分支 + _write_records 的 replace_failed_response=False）。
3. 静默截断：model_client._extract_stream_delta 把非 JSON/错误行直接丢弃，模型流中段返回错误对象时表现为"正常结束"，被当成完整回复持久化（app/services/model_client.py:95-113）。
4. 单请求最坏延迟 = 超时 × 重试 × 修复：默认 API_TIMEOUT_SECONDS=90、修复路由再跑一整次非流式生成，最坏一条回复可耗 3 分钟以上，且 90s 超时对"首字延迟"这一真实痛点完全无效（app/core/config.py 默认值 + chat_service.py:1034 修复路由）。
5. MySQL 每查询新建连接 + JSONL 全量读改写：Database V2 每个 SQL 操作 asyncmy.connect 一次（无连接池、无 connect_timeout），JSONL 每次读改写整文件且锁是进程内的——量大或并发时首字延迟与写入竞争线性恶化（app/storage/mysql_repository.py:716-731、app/storage/chat_repository.py:33-42/672-688）。

## 2. 代码基线速览（引用位置）

| 模块 | 职责与关键位置 |
| --- | --- |
| app/services/chat_service.py (1314 行) | 主链路编排。非流式 reply L216；流式 stream_reply L381；准备阶段 _prepare_chat L564；路由策略 _text_routing_policy L367；降级 _fallback_response L892；统一落库+二次评估 _write_records L908；本地兜底 _local_reply L994、_evaluation_fallback_reply L1006；修复路由 _repair_live_response_decision L1034 |
| app/services/model_client.py (116 行) | DeepSeek HTTP 客户端。chat L17、stream_chat L48（httpx 超时=request_timeout_seconds）、_extract_stream_delta L95（静默丢弃非 JSON 行） |
| app/services/response_evaluator.py (510 行) | 本地规则门 evaluate L37：30+ 条规则（身份泄漏/现实经历编造/敌意/低信任亲密/死亡话题/世界数值接地/繁体/波浪号等），打分 1-0.2×原因数。纯规则，无 LLM-as-judge |
| app/providers/router.py (401 行) | route L102（整调用 wait_for 超时+按错误码重试+熔断）；stream/_route_stream L179/189（逐 chunk 超时；已发过 chunk 后失败直接抛 partial_output，不再换 provider）；熔断 L323/332 |
| app/providers/contracts.py | ProviderCapability(TEXT/ASR/TTS)、ProviderErrorCode（not_configured/unavailable/model_missing/timeout/invalid_response/rate_limited/authentication_failed）、可重试集合默认={UNAVAILABLE,TIMEOUT,RATE_LIMITED} |
| app/core/config.py (475 行) | 默认值：API_TIMEOUT_SECONDS=90、API_TEMPERATURE=0.8、TEXT_PROVIDER_RETRIES=0、熔断 3 次/恢复 60s、ASR_PROVIDER_TIMEOUT_SECONDS=180、VOICE_CHAT_REPLY_TIMEOUT_SECONDS=25、WORLD_FETCH_TIMEOUT_SECONDS=12、TTS 票据 300s/间隔 8s/800 字 |
| app/audio/funasr_engine.py | FunAsrFileEngine L56：懒加载模型 _load_model L121（进程内缓存，首次全量加载）；transcribe_file L106 同步推理 |
| app/audio/file_service.py | transcribe_audio_file L88（主候选+修复候选+情绪增强）；save_upload_to_temp L77（无显式大小上限）；情绪失败静默降级 L118 |
| app/voice_chat/tts_service.py | synthesize_voice_reply L55（分段规划→逐段合成→append_wav_files→ffmpeg mp3）；convert_audio_for_delivery L124（ffmpeg 子进程） |
| app/voice_chat/gpt_sovits_tts.py | synthesize_gpt_sovits L9：urllib 同步调用本地 9880 服务，timeout=180，RIFF 魔数校验；check_gpt_sovits_ready L74 |
| app/voice_chat/web_tts.py | WebVoiceReplyStore L31：reply_id 票据（TTL 300s）、单账号并发 1、最小间隔 8s、纯内存（重启即失效） |
| app/voice_chat/planner.py | load_reference_library L126（本地注释库缺失时报带指引的 FileNotFoundError）；plan_voice_chat L154；infer_reply_emotion L188 |
| app/world/brain.py | decide_world_tools L130（显式意图才触发）；build_context_with_evidence L219（区划解析→天气/新闻，串行 await） |
| app/world/cache.py | AsyncTTLCache L26：TTL + 单飞（inflight 去重）+ 过期驱逐；纯内存、无持久化 |
| app/storage/chat_repository.py | JsonlChatRepository L287：_jsonl_lock L33（threading.RLock，进程内）、每次读写全文件 _read_jsonl L672/_append L682 |
| app/storage/mysql_repository.py | _connect L716：asyncmy 每查询新建连接、无池、无 connect_timeout |
| app/main.py | chat_stream L490；音频流总预算 25s 超时补"请重试" limit_audio_stream_to_realtime_budget L551；TTS 票据随流签发 _remember_completed_web_voice_reply L578 |
| app/auth/smtp_delivery.py | send_verification L48 → _send L54：smtplib 无任何超时；app/auth/registration.py L55 验证码 30 分钟 |

## 3. 分功能失败模式明细

### 3.1 文本聊天（流式/非流式/修复路由）

| # | 失败模式 | 触发条件 | 现有防护（引用） | 剩余缺口 | 典型可感知延迟量级 |
| --- | --- | --- | --- | --- | --- |
| T1 | 首字延迟(TTFT)长 | 准备阶段串行 await 一串仓储操作 + 模型排队 | _prepare_chat L564 内：resolve_relationship→ensure_session→list_recent_messages→save_message→head events→memory→world context 串行 | 没有任何 TTFT 预算/预取；世界工具开启时最坏再叠 12s×N | JSONL 本机 10-50ms；V2 开启 50-200ms（见 D2）；模型 TTFT 1-3s；世界工具未命中缓存 +2-12s |
| T2 | 整请求超时后重试造成双倍耗时 | 90s 内未完成生成 | route L102-145：wait_for(timeout)+重试（默认 retries=0 故单次） | 90s 对长生成可能偏短、对 TTFT 偏长；超时后无"部分可用"策略；重试不区分 5xx/超时 | 最坏 90s；若开启重试 180s+ |
| T3 | 流式中途断流→静默截断 | 网络抖动、服务端 5xx、网关断连 | _route_stream L189-321：已发 chunk 后失败→StreamingRoutingFailed(partial_output)；stream_reply 保留部分文本并记录 error | 客户端只见文本戛然而止，无"[回复中断]"标记；未发完的语义不补 | 用户等到断点即止；无重试 |
| T4 | 流式错误帧被吞→截断被当成成功 | 模型流中段返回 error/非 JSON 行 | _extract_stream_delta L95-113：JSONDecodeError/无 content → 返回空串继续 | 错误对象被丢弃，流"正常"结束→trace 记为 success、回复完整落库 | 用户得到半截"完整"回复 |
| T5 | 首字前失败无流式降级 | 密钥错/401/429 且无 chunk | _route_stream：无 chunk 失败→按重试/熔断走；stream_reply L470-485 抛 RoutingFailed → yield 本地兜底 | 兜底文案对上下文较泛（见 _local_reply L994）；无"正在重试"状态帧 | 失败到兜底 1-90s |
| T6 | 流式路径绕过质量门 | 默认无世界工具 → 不缓冲不评估 | stream_reply L400-445：buffer_for_world_grounding 为假时直通；_write_records L908-985 仍会评估但 replace_failed_response=False | 身份泄漏/死亡玩笑等规则类问题在 Desk 流式回复上只记录不拦截 | 0（但质量风险高） |
| T7 | 修复路由耗时且可能二次失败 | 非流式评估不过 → 再生成一轮 | _repair_live_response_decision L1034-1099：完整第二次非流式生成；失败返回 None 后由 _write_records 的本地兜底替换 | 修复无流式、无与首轮并发、无预算上限（再次 90s） | 额外 +5-20s（修复成功）或 +90s（修复超时） |
| T8 | 幻觉/事实错误（非天气） | 模型自由发挥 | 规则门只覆盖：天气温度/湿度数值 world_fact_grounding_reasons、现实经历编造 claims_real_world_experience | 无通用事实校验、无 LLM-as-judge、无检索比对 | 0（质量缺口而非延迟） |
| T9 | 重复/语气漂移/过长 | 多轮同质回复、temperature=0.8 | 输入侧 build_repetition_signal（_prepare_chat）、轮次长度门、catchphrase_stuffing≥5 | 无回复侧逐轮重复检测（与历史回复的 n-gram 比对）；长生成无 max_tokens 上限 | 长回复消耗用户时间与 token |
| T10 | 熔断/健康状态仅进程内 | 单进程重启即清零 | _circuit_is_open L323、_record_failure L332、ProviderRuntimeMonitor 进程内 | 多 worker/重启后熔断失效；无跨进程共享 | 恢复期 60s 内降级 |

### 3.2 语音识别（ASR）

| # | 失败模式 | 触发条件 | 现有防护 | 剩余缺口 | 延迟量级 |
| --- | --- | --- | --- | --- | --- |
| A1 | 首次识别极慢（冷启动） | 进程首请求触发模型加载 | _load_model L121 懒加载+进程缓存；get_engine_for_preset 单例缓存 | 无预热钩子；无加载进度状态；多线程首请求可能重复加载（dict 检查非原子） | GPU 5-15s；CPU 30-120s（device 默认 cuda:0，无 GPU 机器行为未定义） |
| A2 | 大文件/长音频超时 | 长录音或低配机器 | ASR_PROVIDER_TIMEOUT_SECONDS=180；RoutedFileAsrEngine 超时包装 | 线程超时后无法中断正在进行的 GPU 推理（Python 线程限制，AGENTS 历史亦注明）；无文件时长/大小上限 | >180s 后报错但资源继续占用 |
| A3 | 低质量音频转写差 | 噪声/远讲/方言 | 质量门 evaluate_asr_text_quality + 修复候选 transcribe_with_repair_candidates（pipeline.py）+ 失败时聊天侧要求重说（input_quality_passed 机制） | 修复预设默认空（ASR_REPAIR_PRESETS=""）；无降噪前处理 | 修复额外 +1-5s |
| A4 | 情绪误判 | SenseVoice 标签误报/情绪模型缺失 | 情绪来自转录标签或 emotion2vec；enrich_with_audio_emotion L118 失败静默降级；聊天侧情绪仅作弱信号 | 情绪置信度未被利用（emotion_confidence 常为 None）；无阈值过滤 | 加载情绪模型 +2-10s 首次 |
| A5 | 上传无大小限制 | 超大文件 | save_upload_to_temp L77 流式写盘（1MB 块） | 无 Content-Length/大小上限、无时长上限（生产 TODO 已在手册列出） | 磁盘/内存风险 |

### 3.3 语音合成（GPT-SoVITS 网页 TTS）

| # | 失败模式 | 触发条件 | 现有防护 | 剩余缺口 | 延迟量级 |
| --- | --- | --- | --- | --- | --- |
| V1 | 分段拼接瑕疵 | 多段语音 pause 拼接 | plan_voice_chat L154 分段 + append_wav_files（tts_service L55 起）pause_ms 按情绪 260/380ms | 拼接处听感（电流声/口齿）历史上多次被用户反馈（见归档）；无自动质检（静音/响度/时长） | 分段越多合成越久（每段 2-10s） |
| V2 | TTS 服务不可用 | 9880 未启动 | check_gpt_sovits_ready L74（openapi 探测）；控制中心健康项 | 无自动拉起（控制中心可手动 start）；无熔断（失败每次照打） | 失败即文字降级（正确行为） |
| V3 | ffmpeg 失败 | 未安装/损坏 | convert_audio_for_delivery L124 子进程+错误信息 | 无内置兜底格式（wav 直发）；错误无分类 | +0.2-1s |
| V4 | 音色不稳定 | 同文本多次合成差异 | 固定 seed=1856666206（gpt_sovits_tts L35） | 无听感回归基线（真实验收仍未做，手册已声明） | — |
| V5 | 票据/限流边界 | 并发、过期 | WebVoiceReplyStore L31：TTL 300s、单账号并发 1、间隔 8s、800 字上限（config 默认） | 纯内存（重启丢票据，需重新请求，可接受）；多实例部署不共享（当前单实例无碍） | 8s 最小间隔 |
| V6 | 数字读音 | "42"→"四二" | normalize_text_for_tts（naturalness.py）逐数字替换 | 多位数/年份/日期读法错误（质量瑕疵） | — |

### 3.4 世界工具（高德/新闻/政策）

| # | 失败模式 | 触发条件 | 现有防护 | 剩余缺口 | 延迟量级 |
| --- | --- | --- | --- | --- | --- |
| W1 | 来源超时拖慢回复 | 外部 API 慢 | WORLD_FETCH_TIMEOUT_SECONDS=12（config 默认）逐请求 | 区划解析+天气串行，最坏 24s；新闻 digest 多源并发但全部完成后才返回 | +12-24s 叠入 TTFT |
| W2 | 无证据时的空回复/编造 | 来源禁用/失败 | _world_guard_reply（chat_service）对 needs_location/conflicted/stale/disabled/unavailable 给出确定性话术；prompt 注入"不要编造实时信息" | guard 只覆盖 weather/route/news/policy 意图；意图外（如"帮我查股价"）走普通模型回复，存在编造空间 | 0-1s（本地 guard 直回） |
| W3 | 冲突/过期数据 | 多源矛盾、缓存过期 | world_context_conflict_count 渲染冲突、stale 状态（guard）；缓存 TTL 分源（900s 天气/300s 路线） | 冲突时只"告知不确定"，未自动重取；单飞缓存无持久化，重启全冷 | 缓存命中 <1ms；冷取 12s |
| W4 | 意图误触发 | "今天天气不错"等 | decide_world_tools L130 显式意图规则 | 规则误判仍可能（普通感慨触发工具或反之） | — |
| W5 | 缓存淘汰抖动 | >512 条 | AsyncTTLCache L26 过期驱逐+单飞 | 无精确 LRU（按 expires_at 最老淘汰，热键可能被挤）；无命中率观测 | — |

### 3.5 数据库与存储

| # | 失败模式 | 触发条件 | 现有防护 | 剩余缺口 | 延迟量级 |
| --- | --- | --- | --- | --- | --- |
| D1 | JSONL 全量读改写 | 每次读列整个文件解析 | _read_jsonl L672/_append L682；进程内 RLock L33 | 文件增长→线性变慢；多进程/多实例写互相覆盖；无压缩与归档 | 目前 <10MB 级别：10-50ms/次；长期恶化 |
| D2 | MySQL 每查询建连 | V2 开启后的每次 _execute | _connect L716 asyncmy.connect（无池） | 单次聊天 10+ 次建连；无 connect_timeout（库默认可能较长）；无重连 | 本机 5-15ms/连 → 一轮 +50-200ms；远程 ×5 |
| D3 | 迁移未就绪 | 直接开 V2 | readiness 检查脚本 + 手册强约束 + database_control readiness 上报 | 运行时不强制（DATABASE_V2_ENABLED=true 但表缺失→首查报错） | 启动后首请求失败 |
| D4 | 写入失败中断回复 | 落库异常 | _write_records L908 无 try；reply() 成功路径中落库异常会被外层 except 捕获→再走兜底再落库（可能二次失败→500） | 落库失败应"回复已发、审计异步补偿"而非回滚用户体验 | 偶发 500 |
| D5 | 锁/并发写竞争 | 多 worker 同时 append | 仅进程内 RLock | 跨进程无锁（Windows 下未用文件锁） | 数据丢失风险 |

### 3.6 认证与 SMTP

| # | 失败模式 | 触发条件 | 现有防护 | 剩余缺口 | 延迟量级 |
| --- | --- | --- | --- | --- | --- |
| S1 | SMTP 无超时挂死 | SMTP 服务器慢/不可达 | _send L54 smtplib.SMTP 默认无超时（仅 asyncio.to_thread 隔离主循环） | 线程永久占用；注册/重置请求挂起；无重试策略 | 可无限挂起（数分钟级别常见） |
| S2 | 验证码过期 | 30 分钟 TTL | registration.py L55 timedelta(minutes=30) | 过期提示友好度需前端配合；无重发体验优化 | 用户侧 30 分钟 |
| S3 | 邮件进垃圾箱 | 发件域无 SPF/DKIM | 无 | 生产 TODO | — |
| S4 | 会话/CSRF 状态在库 | DB 不可用 | 认证 fail-closed（条件挂载） | 依赖 D2 的建连开销 | +5-15ms/请求 |

## 4. 行业实践对照

- 首字延迟（TTFT）：生产级 LLM API 服务把 TTFT 作为独立 SLO，优化手段包括流式首包即发、提示词/上下文预取与缓存、连续批处理（continuous batching）、推测解码（speculative decoding）。参考 [Baseten: Building High-Performance Production APIs for LLMs](https://www.zenml.io/llmops-database/building-high-performance-production-apis-for-large-language-models#1)、[Baseten 生产级推测解码实践](https://www.baseten.co/blog/how-we-built-production-ready-speculative-decoding-with-tensorrt-llm/)、[LLM Serving Architecture（handbook-academy）](https://github.com/handbook-academy/engineering-handbook/blob/main/content/hld/part-9-ai-ml-system-design/00-llm-serving-architecture.md#2)。对本项目的映射：T1 的修复点是"把准备阶段与模型调用解耦/并行/预取"，而不是改模型。
- 超时、重试、熔断、降级：业界共识是"按错误类型分层处理"——4xx 不重试、429 指数退避+抖动、超时用预算而非单次硬超时、熔断半开试探、最终兜底返回可解释的降级话术。参考 [Portkey: Retries, fallbacks, and circuit breakers in LLM apps](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/#1)、[ai-fallback 生产级降级模式库](https://github.com/ModernMustardSeed/ai-fallback)。本项目已有骨架（router.py），缺口在 T2/T5/T7 的预算语义与流式降级标记。
- 语义缓存：GPTCache 类方案以嵌入相似度命中缓存，显著降低重复类问题（"你是谁""你是谁？"）的延迟与成本；工程上需处理相似度阈值、失效与命中率监控。参考 [zilliztech/GPTCache](https://github.com/zilliztech/GPTCache#1)、[IEEE: A New Performance Analysis Method for Semantic Caching for LLMs](https://ieeexplore.ieee.org/abstract/document/11111802/similar)。本项目已有 bge-m3/Qdrant 条件能力（SEMANTIC_MEMORY_*），可低成本试点"高频短问句缓存"。
- 评估门禁（LLM-as-judge）：规则门快而稳但盲区明显；LLM-as-judge 能查语义问题（幻觉/语气），但有成本、偏差与漏报（如 [The 30% Blind Spot: Why LLM Safety Judges Fail](https://snailsploit.com/ai-security/rai-judge-blind-spots/)），生产上通常"规则先行、judge 抽样/兜底、失败走修复或人工"。参考 [G-Eval 生产指南](https://futureagi.com/blog/g-eval-definitive-guide-2026/#related-reading)、[LLM-as-Judge in Production（Zylos）](https://zylos.ai/zh/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)、[LLM-as-Judge Fails for Agent Security](https://www.supra-wall.com/dashboard/blog/llm-as-judge-fails-agent-security)。对本项目的映射：T6/T8 的补法是"流式也过规则门（缓冲或事后）+ 抽样式 judge"。
- ASR/TTS 队列化与异步化：语音助手的通行做法是把 ASR→LLM→TTS 全链路异步/队列化、ASR 预热常驻、TTS 流式合成首包优先、多段拼接用交叉淡化（crossfade）替代硬拼接。参考 [NVIDIA nemotron-voice-agent best practices](https://github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent/blob/main/docs/05-best-practices.md#1)、[ai-engineering-from-scratch real-time audio](https://github.com/BrunoScaglione/ai-engineering-from-scratch/blob/main/phases/06-speech-and-audio/11-real-time-audio-processing/docs/en.md#1)。对本项目映射：A1/A2/V1。
- 流式断流 UX：SSE 生产实践强调显式结束帧（done）与失败帧（error），客户端据此区分完成/中断并支持续传；流不可恢复时可显示"已中断"。参考 [OpenHelm: Streaming LLM Responses](https://www.openhelm.ai/blog/streaming-llm-responses-real-time-ux)、[Ably: AI chat stream resumption](https://ably.com/blog/ai-chat-stream-resumption)、[腾讯云：ChatGPT 流式回答如何收尾](https://cloud.tencent.com.cn/developer/article/2630553)。对本项目映射：T3/T4/T6（text/plain 流没有结束帧语义，靠连接关闭区分）。

## 5. 实验清单（每条：改什么 → 怎么测 → 成功标准 → 回滚）

> 标注：★ = 可在当前框架内低成本完成（不引新依赖/新服务，改动局限于 1-2 个文件+测试）；☆☆ = 中等成本。

| # | 实验 | 改动 | 怎么测 | 成功标准 | 回滚 |
| --- | --- | --- | --- | --- | --- |
| E1 ★ | 流式失败帧 + 中断标记 | 在 stream_core_api_text 或 main.chat_stream 包装层捕获异常时 yield 中断提示文本，部分输出分支同样标记；客户端 studio app.js 检测标记展示提示 | 单测：mock stream 中途抛异常，断言输出尾含标记；浏览器测试复跑 | 中断可辨识且不覆盖已发文本；测试全绿 | 删除标记行即回滚 |
| E2 ★ | 流式直通也过规则门（事后拦截） | stream_reply 在无世界事实分支结束后同步跑一次 evaluator.evaluate（O(ms) 级），失败则 yield 本地兜底（与现有 buffered 分支对齐） | 单测：让模型回"我是AI语言模型"，断言 Desk 收到兜底或修复文本；全量回归 | 规则类泄漏在流式主路径被拦截；TTFT 不变 | 恢复旧分支一行 |
| E3 ★ | 修复路由预算 | _repair_live_response_decision 增加 repair 专用超时（如 20s，新配置 REPAIR_TIMEOUT_SECONDS 默认 20）；超时即返回 None 走本地兜底 | 单测：fake client 挂起，断言修复在 20s 内放弃并返回兜底 | 最坏回复延迟有界（从约 180s 降至约 110s） | 删配置键即回滚 |
| E4 ★ | MySQL 连接池 + connect_timeout | mysql_repository 改为进程内复用连接（单连接+asyncio.Lock 或 asyncmy pool），加 connect_timeout=5 | 现有 RecordingMySQLRepository 测试全绿；加一个"两次查询仅一次 connect"单测（monkeypatch _connect 计数） | 每轮 10 次建连降到 1 次；无回归 | 恢复原 _connect 实现 |
| E5 ★ | JSONL 写路径批量化 | 一轮内多次 append 合并写（或 asyncio.to_thread 写盘） | tests/test_jsonl_repository_concurrency.py 回归 + 100 并发写一致性测试 | 写延迟不随消息数线性增长 | 恢复逐次 append |
| E6 ★ | 常见问题语义缓存试点 | 仅对"身份类/问候类"短问句（is_identity_question 等既有分类器）做精确/归一化键缓存，TTL 60s，命中直接返回缓存回复（跳过模型），记录 cache_hit 审计 | 单测：同问题两次调用，第二次 0 次模型调用；命中率统计入 build_request_metadata | 身份类 TTFT 降至 <50ms；失败时行为不变 | 关闭开关 |
| E7 ★ | ASR 启动预热 + 加载状态 | uvicorn lifespan 或首请求前显式预热 get_engine_for_preset；/health 增加 asr_loaded 字段 | 启动后立即转写，首请求延迟对比；health 断言 | 首请求 ASR 延迟从 10s+ 降到 <3s；无 GPU 机器降级为不预热 | 移除 lifespan 钩子 |
| E8 ★ | ASR 文件大小/时长上限 | save_upload_to_temp 增加累计字节上限（如 20MB，配置键）并 413 拒绝 | 单测：上传超限文件被拒 | 明确 413 + 用户提示 | 移除上限 |
| E9 ★ | SMTP 超时 | smtp_delivery 的 SMTP 工厂传 timeout=10（smtplib 支持） | 单测：fake SMTP 睡眠，断言 to_thread 任务 10s 内异常 | 注册接口最坏延迟有界 | 去掉 timeout 参数 |
| E10 ★ | 数字读音修正 | naturalness.normalize_text_for_tts 对多位数字（年份/金额/小数）规则化 | 单测覆盖 42/2026/3.5/18:30 | 常见数字读法正确 | 恢复逐位替换 |
| E11 ☆☆ | 流式逐 chunk 规则门（增量） | 对已流出的累积文本每 N chunk 跑轻量规则（长度/标记类），触发即中断并换修复文本 | 单测 + 浏览器测试 | 违规回复在流中被截停 | 移除增量检查 |
| E12 ☆☆ | LLM-as-judge 抽样复核 | 仅对 world_grounding_facts 存在或 debug 场景的回复，用同模型异步复核事实/语气（独立超时 15s，失败不影响主流程），结果入审计 | 离线：构造 20 条含错误天气数值/编造回复，统计拦截率；记录成本 | 拦截率≥90% 且误伤<5% | 关配置 |
| E13 ☆☆ | 世界工具并行化与预算 | build_context_with_evidence 把区划解析与后续调用改为 asyncio.gather 或有依赖时预取；整个世界阶段加总预算（如 8s）超时即 unavailable | 单测：fake runtime 慢 5s×2，断言总预算生效 | 世界工具最坏叠加从 24s 降到 8s | 恢复串行 |
| E14 ☆☆ | 拼接质检 | 合成后对每段 wav 做时长/静音比/响度检查（复用 audio_utils 能力），异常段重试 1 次或剔除 | 单测：注入坏段，断言质检拦截 | 明显电噪/静音段不再交付 | 移除质检调用 |
| E15 ☆☆ | 流式断点续传（长回复） | 客户端断线时服务端把已生成文本按 reply 会话暂存，重连后补发余下部分（参考 Ably 方案） | 集成测试：断连重连后文本完整 | 断流不丢长回复 | 关掉暂存即回滚 |

优先级建议：E1、E2、E3、E4 为 P0（对应 Top5 中的 4 条）；E9、E8 为安全/体验快赢；其余按产品节奏。

## 6. 引用文件索引

- app/services/chat_service.py：reply L216 / stream_reply L381 / _prepare_chat L564 / _text_routing_policy L367 / _fallback_response L892 / _write_records L908 / _local_reply L994 / _evaluation_fallback_reply L1006 / _repair_live_response_decision L1034
- app/services/model_client.py：chat L17 / stream_chat L48 / _extract_stream_delta L95
- app/services/response_evaluator.py：evaluate L37
- app/providers/router.py：route L102 / stream L179 / _route_stream L189 / _circuit_is_open L323 / _record_failure L332
- app/core/config.py：Settings 默认值（API_TIMEOUT_SECONDS=90 等）
- app/main.py：chat_stream L490 / limit_audio_stream_to_realtime_budget L551 / _remember_completed_web_voice_reply L578
- app/audio/funasr_engine.py：FunAsrFileEngine L56 / transcribe_file L106 / _load_model L121
- app/audio/file_service.py：save_upload_to_temp L77 / transcribe_audio_file L88 / enrich_with_audio_emotion L118
- app/voice_chat/tts_service.py：synthesize_voice_reply L55 / convert_audio_for_delivery L124
- app/voice_chat/gpt_sovits_tts.py：synthesize_gpt_sovits L9 / check_gpt_sovits_ready L74
- app/voice_chat/web_tts.py：WebVoiceReplyStore L31 / acquire L80
- app/voice_chat/planner.py：load_reference_library L126 / plan_voice_chat L154
- app/world/brain.py：decide_world_tools L130 / build_context_with_evidence L219
- app/world/cache.py：AsyncTTLCache L26 / get_or_load L41
- app/storage/chat_repository.py：_jsonl_lock L33 / JsonlChatRepository L287 / _read_jsonl L672 / _append L682
- app/storage/mysql_repository.py：_connect L716
- app/auth/smtp_delivery.py：_send L54
- app/auth/registration.py：verification_lifetime L55

## 7. 外部来源链接

- [Baseten: Building High-Performance Production APIs for LLMs](https://www.zenml.io/llmops-database/building-high-performance-production-apis-for-large-language-models#1)
- [Baseten: production-ready speculative decoding](https://www.baseten.co/blog/how-we-built-production-ready-speculative-decoding-with-tensorrt-llm/)
- [LLM Serving Architecture（handbook-academy）](https://github.com/handbook-academy/engineering-handbook/blob/main/content/hld/part-9-ai-ml-system-design/00-llm-serving-architecture.md#2)
- [Portkey: Retries, fallbacks, and circuit breakers in LLM apps](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/#1)
- [ModernMustardSeed/ai-fallback](https://github.com/ModernMustardSeed/ai-fallback)
- [zilliztech/GPTCache](https://github.com/zilliztech/GPTCache#1)
- [IEEE: A New Performance Analysis Method for Semantic Caching for LLMs](https://ieeexplore.ieee.org/abstract/document/11111802/similar)
- [G-Eval (2026): The Definitive Guide for Production LLM Teams](https://futureagi.com/blog/g-eval-definitive-guide-2026/#related-reading)
- [LLM-as-Judge in Production（Zylos Research）](https://zylos.ai/zh/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)
- [LLM-as-Judge Fails for Agent Security](https://www.supra-wall.com/dashboard/blog/llm-as-judge-fails-agent-security)
- [The 30% Blind Spot: Why LLM Safety Judges Fail](https://snailsploit.com/ai-security/rai-judge-blind-spots/)
- [NVIDIA nemotron-voice-agent best practices](https://github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent/blob/main/docs/05-best-practices.md#1)
- [ai-engineering-from-scratch: real-time audio processing](https://github.com/BrunoScaglione/ai-engineering-from-scratch/blob/main/phases/06-speech-and-audio/11-real-time-audio-processing/docs/en.md#1)
- [OpenHelm: Streaming LLM Responses — Real-Time UX](https://www.openhelm.ai/blog/streaming-llm-responses-real-time-ux)
- [Ably: AI chat stream resumption](https://ably.com/blog/ai-chat-stream-resumption)
- [腾讯云：关闭浏览器标签页时 ChatGPT 的流式回答会如何收尾？](https://cloud.tencent.com.cn/developer/article/2630553)
