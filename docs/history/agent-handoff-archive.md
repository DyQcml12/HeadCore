# HutaoChatCore 开发交接历史档案（归档）

> 本文件是 2026-07-07 至 2026-08-03 期间的完整开发交接记录，2026-08 项目清理后归档为只读历史。
> 当前状态以根目录 AGENTS.md、README.md、docs/HUTAOCHATCORE_COMPLETE_ARCHITECTURE_AND_ACCEPTANCE_MANUAL.md 和 docs/HUTAOCHATCORE_TECHNICAL_REPORT.md 为准。
> 历史记录中的 QQ/微信 Bot、CosyVoice2、Bert-VITS2、Ollama 视觉、MySQL V1 等内容均为退役或废弃方案，不代表当前运行架构。

---# HutaoChatCore Agent Handoff

## 2026-07-21 Current Architecture And Acceptance Manual

- Rebuilt the current source-of-truth manual at `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md` and generated the Word/WPS edition at `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.docx`.
- The manual treats HeadCore as the stable human-head boundary; QQ, Weixin, future apps, world APIs and TTS remain external surfaces or replaceable providers.
- Current platform persona routing is QQ, Weixin/Wechat and HTTP -> `hutao_v1`. Platform adapters share the same HeadCore Self, relationship, memory, perception, world-evidence, provider and audit infrastructure.
- Xiaohe is no longer an active runtime persona. The remaining `小何` marker in the registry is a negative identity guard that rejects accidental model self-identification; it is not a selectable profile.
- Volcengine/Doubao TTS runtime code, provider registration, settings schema and public environment template entries have been removed. Local Bert-VITS2 remains the active generic QQ TTS route; CosyVoice2 still requires a dedicated runtime adapter and live acceptance.
- Current world functionality is an evidence/tool orchestration layer, not a learned physical world model. All eight news candidates remain disabled and legally unapproved by default; a generic rendered crawler is not complete.
- Weixin pairing is access authorization, not a WeChat friend request. Hermes/iLink cannot auto-add ordinary friends or create a visitor QR from HutaoChatCore.
- The 2026-07-20 Hu Tao 150-epoch Flow experiment failed human timbre/expression acceptance and must not be deployed. Production remains on the official CosyVoice2 base `flow.pt` plus the existing speaker embedding; see the separate voice handoff.
- Fresh persona-removal validation with `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`: compileall PASS, focused Database V2 tests `56 passed`, focused persona tests `37 passed`, and the currently collectable project suite `730 passed, 2 skipped`.
- The unfiltered suite still cannot collect `tests/test_hutao_consensus_dataset.py` and `tests/test_hutao_flow_evaluation.py` because their two referenced training helper scripts are absent. Those unrelated training utilities were not fabricated during the persona/TTS cleanup.
- Pytest collection still emitted a Windows access violation while importing `pyarrow` from the CosyVoice training utilities, even though the suite returned success. Treat the training environment as unstable until an isolated import/data-pipeline smoke passes.
- No real DeepSeek, Amap, news, QQ, Weixin, MySQL, ASR, emotion, TTS or VLM online call was made during this documentation refresh. The manual separates automated verification from required live acceptance.
- No secret, token, owner identifier or real `.env` value is recorded in either publication.

## 2026-07-17 Amap Place, Route And Consequence Planning

Implementation:

- Verified the current official Amap place-search and route-planning documentation before implementation. The adapter uses `/v3/place/text`, `/v3/direction/driving`, `/v3/direction/transit/integrated`, and `/v3/direction/walking` only.
- Added bounded place normalization and driving/transit/walking route normalization. Geometry, photos, telephone numbers, raw response bodies, and unrelated POI fields are omitted.
- Precise route calls require purpose-scoped consent. Brain grants it only for an explicit user route request; it never reads the request IP or performs background location lookup.
- Added explicit `travel_compare` decisions for conservative `from A to B` requests. Missing endpoints and ambiguous places stop for user confirmation instead of guessing.
- Added route consequence comparison using interface duration, distance, walking exposure, known fee fields, user time budget, and forecast-based weather buffers. Output states that current route estimates are not future traffic predictions.
- Added one-day place caching, five-minute route caching, and a 30-day global cap so stable district metadata can use its configured TTL.
- Extended `world_amap_smoke.py` with `--place` and consent-gated route modes. No live API call was made.

Validation:

- Focused world tests: `40 passed`.
- Full suite: `693 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_164914/final-project-acceptance-report.md`.
- Restarted the existing Core in place with the required `new` Python runtime after implementation. Latest source is running on `127.0.0.1:8000` as PID `139740`; `/health`, `/control`, and `/weixin` all return HTTP 200. The temporary verification port 8010 was released.
- A bare repository-root pytest command also collected vendored CosyVoice/TensorRT training tests and stopped on missing training-only packages; the authoritative project command remains `python -m pytest tests -q -p no:cacheprovider`.
- No Amap request, model call, rendered crawl, platform mutation, database mutation, package install, or environment change was performed.

## 2026-07-17 Amap District Resolution For Natural Weather Requests

Implementation:

- Verified the current official Amap administrative-district API documentation before implementation.
- Added `MAP_PLACE` support to `AmapWorldSourceAdapter` through `/v3/config/district` with `subdistrict=0`, `extensions=base`, bounded page/offset, explicit JSON, and existing status/infocode validation.
- District observations retain only keyword, name, six-digit adcode, citycode, and level; center/polyline are omitted.
- Added `AMAP_DISTRICT_CACHE_TTL_SECONDS=2592000` to Settings, `.env`, and `.env.example`; no new key is required.
- Added `WorldRuntime.resolve_district(...)` and `world_amap_smoke.py --district <name>`.
- Brain extracts a conservative city/district candidate from explicit weather requests without forwarding the complete message. It resolves the candidate before weather lookup.
- Unique candidates continue automatically; missing or same-name candidates return a confirmation projection. The system never guesses user IP or silently chooses an ambiguous district.

Validation:

- Focused world tests: `34 passed`.
- Full suite: `687 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_162002/final-project-acceptance-report.md`.
- No Amap call or API key was used.

## 2026-07-17 Brain World Tool Decision And Chat Context Integration

Implementation:

- Added `app/world/brain.py` with deterministic explicit-request-only decisions for current weather, forecast, news digest, and policy metadata.
- User opt-out phrases and ordinary mentions do not call tools. News queries use fixed topic categories instead of sending the complete user message to external sources.
- Weather requests without a six-digit adcode return `needs_location`; the system never guesses the user's IP or location.
- Added `app/world/context.py` with stale filtering, evidence rendering, item/character limits, credentialed-URL rejection, and untrusted-external-data prompt boundaries.
- Added cross-source weather conflict detection for differing weather labels or temperature differences of at least 5C.
- Added `WorldBrainCoordinator`; disabled/unapproved/unavailable sources produce explicit no-fabrication projections.
- Integrated an optional `WorldContextProvider` into ChatService. Default-disabled behavior is unchanged; blocked relationships do not invoke the provider.
- Chat audit metadata now includes world status, item count, conflict count, and tool intent without storing source bodies, keys, IPs, or rendered context.
- Added `docs/world/WORLD_CONTEXT_AND_BRAIN_DESIGN.md`.

Validation:

- Focused world tests: `32 passed`.
- ChatService regression: `33 passed`.
- Full suite: `685 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_155324/final-project-acceptance-report.md`.
- No live world source, model, rendered-browser crawl, platform action, or database mutation was performed.

## 2026-07-17 Government Policy Metadata And Shared News Digest

Implementation:

- Inspected the current China Government latest-policy page and found its same-origin structured endpoint `ZUIXINZHENGCE.json`; no browser render is required.
- Added `GovCnPolicyAdapter` for title, publication date, official allowlisted URL, language, and source metadata only. It does not fetch or store policy bodies.
- Updated the source's terms URL to the official website statement. The source remains `review_required`, disabled, and legally unapproved because the statement restricts commercial original-form republication.
- Added `WorldRuntime.policy_updates(...)` and `scripts/world_policy_smoke.py`; status mode is offline and explicit collection is denied by default.
- Added `NewsDigestService`: concurrent source acquisition, partial-failure status, duplicate-title merging, all-source URL preservation, latest-date/longest-summary selection, deterministic ordering, and SHA-256 cache keys.
- Added a persistent runtime digest cache and `scripts/world_news_digest_smoke.py`. Equivalent source sets share the same digest regardless of input order, so later users reuse earlier work.

Validation:

- Focused world tests: `24 passed`.
- Full suite: `677 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_144035/final-project-acceptance-report.md`.
- Current status: 3 news adapters and 1 policy adapter registered; all remain disabled and unapproved.
- No model call, policy-body request, Amap/news API request, rendered-browser crawl, real platform action, or database mutation was performed.

## 2026-07-17 News API And Official RSS Runtime Foundation

Implementation:

- Added a shared async HTTP protocol used by Amap and news adapters without changing the concrete HTTPX behavior.
- Added `GdeltNewsAdapter`: bounded JSON discovery, topic/limit validation, canonical URL tracking-parameter removal, duplicate removal, date normalization, and no linked-article fetch.
- Added `OfficialRssNewsAdapter`: bounded RSS/Atom XML parsing, HTML-to-text summary normalization, topic filtering, duplicate removal, and strict item-link hostname allowlists.
- Extended `WorldRuntime` to load the source manifest, register GDELT plus UN/WHO RSS, expose catalog/registered/enabled counts, and provide an explicit shared-cache `news(...)` method.
- Added `scripts/world_news_smoke.py`; status mode does not access the network, while an explicit source remains denied until global, source, legal, and automation gates permit it.
- Added `automation_policy` to the catalog. Current classification is 1 API, 2 feeds, 4 review-required pages, and 1 robots-blocked page.
- Public checks on 2026-07-17 found PBOC `robots.txt` disallows `/`; NBS robots returned 404; CSRC robots returned ordinary HTML; NDRC robots returned 403. No domestic official-page adapter or renderer was enabled.

Validation:

- Focused world tests: `21 passed`.
- Full suite: `674 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_140704/final-project-acceptance-report.md`.
- Status: 8 catalog sources, 3 registered adapters, 0 enabled sources, 0 legally approved sources.
- No Amap/news API call, article-body fetch, rendered-browser crawl, API key, real platform action, or database mutation was performed.

## 2026-07-17 Amap Reference Alignment And News Source Catalog

User input:

- Supplied current Amap IP-location and weather-query reference text.
- Requested a mixed domestic/international news design using some APIs and some rendered acquisition because no single useful free API was available.

Implementation:

- Aligned `AmapWorldSourceAdapter` with the supplied references: IP location accepts only global IPv4, requests explicitly set `output=JSON`, and successful payloads require `status=1` plus `infocode=10000`.
- Replaced the foreign IP unit fixture with the domestic IPv4 example from the reference and added IPv6 rejection, forecast normalization, JSON-output, and invalid-infocode coverage.
- Added `app/world/source_manifest.py`, a strict UTF-8 JSON manifest loader with HTTPS, hostname allowlist, duplicate ID, legal approval, render fallback, refresh interval, and credential-in-URL checks.
- Added `data/world/sources.json` with eight candidates: GDELT DOC, UN News RSS, WHO RSS, China Government policy, National Bureau of Statistics, PBOC, CSRC, and NDRC. All remain disabled and unapproved.
- Added `scripts/world_source_manifest_check.py`; it validates the catalog without making network requests or printing URLs/credentials.
- Added `docs/world/NEWS_SOURCE_STRATEGY.md` covering source tradeoffs, API/RSS/HTTPS/rendered priority, legal boundaries, cache/URL/content-hash deduplication, shared summaries, and token controls.

Validation:

- `scripts/world_source_manifest_check.py`: PASS; 8 sources, 0 enabled, 0 legally approved, split as 1 API / 2 RSS / 5 HTTP.
- Focused world tests: `17 passed`.
- Full suite: `670 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_114903/final-project-acceptance-report.md`.
- No Amap key, news API, rendered browser, news body, real platform, or database mutation was used.

## 2026-07-17 Full Offline Acceptance Recovery

Implementation:

- Fixed S3 normalization so vision results without emotion attributes remain valid and ASR observations preserve `emotion_source` and `emotion_confidence`.
- Converted three raw async S5 MySQL tests to the repository's `asyncio.run(...)` test style without adding a pytest plugin or dependency.
- Restored misplaced Weixin status assertions to their owning endpoint test.
- Updated final-acceptance live step expectations to six and disabled pytest's cache provider in the acceptance command.
- Updated README and the unified architecture manual so the former WDAC-blocked state is historical rather than current.

Validation:

- Required runtime only: `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`.
- Focused regression: `80 passed`.
- Full suite: `664 passed, 2 skipped`.
- Final offline acceptance: `4 passed, 0 failed`; report at `logs/final-acceptance/2026-07-17_111911/final-project-acceptance-report.md`.
- Offline persona continuity: `3/3 PASS`; report at `logs/persona-continuity-eval/2026-07-17_111925/persona-continuity-report.md`.
- Current Core starts on port 8000; `/health` returns `ok`, while `/control` and `/weixin` return HTTP 200.
- Remaining completion gates require separately authorized real MySQL, model, QQ, Weixin, and world-source API checks. No real platform mutation or world API request was performed.

## 2026-07-17 HeadCore World Awareness Foundation

User goal:

- Begin development of the head-centered world-awareness architecture and add safe `.env` locations for API keys the user will fill later.
- Preserve HeadCore as the only cognitive subject; external APIs and future crawlers remain world-observation extensions and do not replace Brain, Self, Memory, Relation, perception, or expression logic.

Implementation:

- Added `app/world/contracts.py` with typed source, capability, sensitivity, query, evidence, observation, batch, and acquisition-result contracts.
- Added `WorldSourceRegistry`; duplicate or unknown sources and unsupported capabilities fail explicitly.
- Added `AsyncTTLCache` with bounded entries, TTL expiry, and single-flight request coalescing so identical concurrent requests fetch once.
- Added `WorldAcquisitionService`; sources must be enabled and explicitly marked legally approved before execution. Cache keys are canonical SHA-256 values and do not contain raw query data.
- Added the first `AmapWorldSourceAdapter` for public-IP coarse location, current weather, and forecast. The adapter requires HTTPS plus an allowed host, keeps the API key inside the adapter, rejects private/non-global IPs, requires explicit consent, omits the raw IP from observations, limits response size, disables redirects, and maps failures to typed redacted codes.
- Added `WorldRuntime` as an explicit, non-FastAPI entry point. It is not wired into ChatService and does not perform background or startup requests.
- Extended `Settings`, `.env.example`, and real `.env` with disabled world-awareness controls, blank Amap API key, explicit Amap legal-approval flag, cache/timeout limits, and reserved blank domestic/international news API fields. Existing values were preserved and no secret was printed.
- Added `scripts/world_amap_smoke.py`. With no action it prints only boolean readiness; weather requires `--adcode`; IP resolution additionally requires `--consent-granted` and never prints the input IP or API key.
- Updated the unified architecture document and README with the HeadCore boundary, configuration order, smoke commands, and current non-integrated status.

Validation:

- New world source, runtime, smoke script, and tests compile with `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`.
- Focused offline suite: `11 passed in 0.09s`; no real network call or API key was used.
- Real settings load reports `world_enabled=false`, `rendered_fetch_enabled=false`, `amap_key_configured=false`, and `amap_legal_approved=false`.
- No package, environment, model, database, platform identity, real API request, crawler, ChatService integration, or background scheduler was added.

## 2026-07-16 Standalone Architecture HTML And PDF Publication

User goal:

- Make `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md` readable by people who do not use a code editor or Markdown preview.

Implementation:

- Preserved the Markdown source and generated a self-contained offline browser publication at `output/html/hutaochatcore-architecture.html`.
- Generated a shareable A4 PDF at `output/pdf/hutaochatcore-architecture.pdf`.
- Added `scripts/build_architecture_publication.py`, which uses the existing `new` Python environment and `markdown-it` to render headings, tables, code, a responsive table of contents, print styles, and six static architecture diagrams. The HTML has no CDN, remote font, Mermaid runtime, analytics, or network dependency.
- Added `scripts/print_architecture_pdf.js`, which uses an existing local Playwright/Edge installation to print the standalone HTML with A4 sizing, a restrained header, and `current / total` page numbering.
- Added direct HTML/PDF publication links and the HTML rebuild command to `README.md`.

Validation:

- HTML structure: one title, `48` table-of-contents links, `6` static diagrams, `19` tables, no residual Mermaid source, and no Unicode replacement characters.
- Real Edge browser QA: desktop `1440x1000` and mobile `390x844`; zero console errors; desktop width `1440/1440`; mobile width `390/390`; long flow diagrams scroll only inside their own frames.
- PDF: `18` pages, A4 `594.96 x 841.92 pt`, approximately `604 KiB`, no encryption or JavaScript.
- Poppler rendered all 18 PDF pages. Visual inspection covered the cover, context/layer diagrams, vision/persona flows, a middle content page, and the final page; no clipping, overlap, broken Chinese glyphs, or black squares remained.
- No package, browser, Python environment, `.env`, credential, model, database, QQ account, or Weixin identity was installed or changed.

## 2026-07-16 Architecture And Operations Documentation Reorganization

User goal:

- Replace the previous short and confusing architecture summary with a detailed, code-grounded document that explains how the whole project is assembled, operated, tested, and evaluated.
- Cover persona behavior, TTS, ASR, speech emotion, QQ voice/image paths, cross-platform relationships, Weixin pairing/add-friend limits, the control terminal, dependencies, models, frameworks, current effects, and remaining work.

Documentation changes:

- Rebuilt `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md` from a 239-line status summary into a 633-line authoritative architecture and acceptance manual.
- Added a project context diagram, layered runtime diagram, S1-S8 responsibility matrix, repository map, public API map, data ownership, Provider/model matrix, software and model prerequisites, environment-variable groups, startup sequence, control-terminal guide, test hierarchy, current evidence, WDAC boundary, and explicit final completion gates.
- Added detailed end-to-end flows for text chat, text emotion handling, QQ inbound voice/ASR/emotion, QQ outbound TTS, image OCR/VLM, cross-platform account merge, persona draft-to-release projection, and Weixin pairing.
- Explicitly separated `implemented`, `historically validated`, `currently validated`, `blocked`, and `unsupported`, so cached media or old reports are not presented as current end-to-end success.
- Kept ordinary personal-WeChat automatic friend addition, native Weixin voice bubbles, and voice calls documented as unsupported by the current Hermes/iLink public capability.
- Updated `README.md` with the authoritative 2026-07-16 `degraded` result, the latest `2 passed / 2 failed` acceptance report, and corrected S1-S8 status rows. Historical dated records remain marked as history rather than current state.
- Corrected `docs/systems/01-database-control-plane.md`: the Database V2 router and controlled reads/writes are implemented and registered; current MySQL runtime acceptance is still pending.
- Updated `docs/systems/README.md` to distinguish the integrated design baseline from incomplete runtime acceptance.

Validation:

- Markdown structure: `633` lines, `49` headings, `28` code fences in complete pairs, `6` Mermaid blocks, and no Unicode replacement characters.
- All checked source, migration, script, test, report, WDAC, and configuration-template paths referenced by the manual exist.
- Removed checked stale claims including unimplemented Database V2 routes, missing S4 lifecycle tables, active Ellie runtime, and the old `246 passed` result.
- Full repository compile check with the required `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`: PASS.
- No `.env` values, credentials, runtime services, databases, QQ sends, or Weixin mutations were changed during this documentation task.

## 2026-07-16 End-to-End Completion Development And Acceptance Audit

- Use only `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`. A temporary Python 3.14 dependency probe was fully uninstalled and must not be repeated.
- Windows WDAC currently blocks unsigned native modules including `pydantic_core`, `asyncmy`, NumPy/OpenCV, and Hermes subprocess launch. Full pytest, new Uvicorn startup, MySQL, OCR, and current ASR inference remain blocked until administrator policy review. Do not disable or bypass WDAC.
- Added durable S5 MySQL persona storage, v2.003 operation idempotency records, explicit persistence/write flags, admin audit integration, async control routing, and published persona projection consumption in ChatService. Defaults remain disabled and fail closed.
- Added strict S5 runtime tests for projection injection/fallback, MySQL store behavior, and readiness. Latest code compiles but these tests have not run under pytest because of WDAC.
- Fixed Database V2 cross-platform account merge to update all related tables in one transaction. Added an opt-in isolated MySQL acceptance that creates fake QQ/Wechat identities, binds them to one profile, verifies both resolutions, and removes test rows.
- Completed QQ audio emotion propagation: optional emotion2vec enrichment falls back to SenseVoice, perception retains emotion source/confidence, QQ Core requests carry typed audio quality/emotion metadata, and ChatService consumes it as a weak tone signal.
- Strengthened ASR acceptance with normalized character error rate (CER), manifest reference transcripts, stress thresholds, and report fields. Historical `28/28` non-empty checks must not be described as accuracy maturity without CER.
- Fixed QQ preflight so blocked parent imports report `false` instead of crashing. Current result: FAIL; Bridge/NapCat offline, OneBot adapter blocked, configured Core target 8000 not running, token not configured.
- Fixed Hermes pairing command handling so Windows process blocks return a redacted `process_blocked` result instead of HTTP 500. Current source already keeps public status separate from admin pairing details; the old process on 8012 has not loaded this fix.
- Real evidence retained: Volcengine TTS WAV/MP3 both parse at 2.786 seconds; historical SenseVoice real transcription passed; historical emotion2vec labeled samples passed 5/5; historical DeepSeek persona continuity passed 48 turns/4 scenarios and adversarial passed 12/12.
- Current vision status is not complete: cached images decode, RapidOCR is WDAC-blocked, Ollama has no installed VLM model. Do not claim image understanding passed.
- Real QQ send/receive and Weixin approve/revoke were not performed because no dedicated authorized test identities were identified. Hermes/iLink does not support ordinary personal-WeChat auto-add-friend behavior.
- Consolidated architecture, dependency, operation, status, WDAC, and completion-gate documentation: `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md`.
- Latest validation: full repository `compileall` PASS; control/Weixin JavaScript syntax PASS; targeted pytest collection blocked at Pydantic Core. Prior pre-WDAC baseline remains `630 passed, 1 skipped`, but it predates the changes above.

## 2026-07-15 Weixin Multi-User Pairing Management

- `/weixin` now reuses `controlActorPlatform` / `controlActorUserId` and sends `X-Hutao-Actor-*` headers for all pairing and Hermes service writes.
- Admin authorization is checked through `/api/control/operations/actor`; sensitive controls remain disabled until authorized.
- Added admin-protected `GET /api/control/weixin/pairing/status`. Public `/api/control/weixin/status` no longer returns pairing CLI lines or pending codes.
- Added a revoke-user UI. Full Weixin IDs are submitted only in the request and are not copied into page logs.
- Browser QA used installed Edge at desktop and 390px mobile sizes; no C-drive browser installation was performed.
- Nickname/avatar remain unsupported by Hermes/iLink. Do not add Hook, injection, or UI automation without explicit owner approval and risk confirmation.
- Validation: JS syntax PASS; control center `34 passed`; full suite `604 passed, 1 skipped`.
- Report: `logs/weixin-pairing-management/20260715-095038/weixin-multi-user-management-report.md`.

## 2026-07-15 QQ Voice Test Fixture Repair

- Repaired the three full-suite failures reported by the Database Control hardening run.
- Root cause: successful fake TTS functions returned `send_path` values without creating files; the media finalizer correctly rejected missing files and returned text.
- Tests now create minimal fake MP3 files. The relative-output test redirects `integrations.qq_bot.voice_reply.PROJECT_ROOT` to `tmp_path`.
- No QQ runtime, provider routing, TTS implementation, media safety check, configuration, or real voice file was changed.
- Validation: targeted `3 passed`; QQ suite `83 passed`; full suite `600 passed, 1 skipped in 14.17s`.
- The skip is the expected opt-in Database Control isolated MySQL test.
- Report: `logs/test-maintenance/20260715/qq-voice-test-fixture-repair-report.md`.

## 2026-07-15 FunASR And Provider Runtime Completion

- Reused the concurrently added `AsrResult` and `FunAsrProvider`; no duplicate ASR abstraction was introduced.
- Added `RoutedFileAsrEngine` so each Core file-ASR candidate executes through `ProviderRouter`; all-candidate quality selection and conditional repair remain unchanged.
- Added `ASR_PROVIDER_TIMEOUT_SECONDS`, `ASR_PROVIDER_CIRCUIT_FAILURE_THRESHOLD`, and `ASR_PROVIDER_CIRCUIT_RECOVERY_SECONDS`; real `.env` was not modified.
- Added a process-local, thread-safe provider runtime monitor. Router attempts publish only typed non-sensitive status.
- Added `provider_runtime` to S8 operations status with tracked/degraded/open counts and error-code categories only.
- Core `transcribe_audio_file()` remains synchronous for the existing FastAPI threadpool and scripts. WebSocket streaming ASR remains on its original protocol.
- Validation: compile PASS; focused `86 passed`; related regression `156 passed`; full suite `597 passed, 1 skipped in 13.72s`.
- Report: `logs/provider-routing/20260715/funasr-runtime-observability-completion-report.md`.

## 2026-07-15 Control Observability Completion

- Added `GET /api/control/operations/actor`, returning only `configured`, `authorized`, and a fixed reason code.
- Added administrator-only `GET /api/control/operations/audits`; safe audit projections omit actor profile IDs, platform user IDs, parameters, and details JSON.
- Added `ControlAuditEvent`, repository/service/adapter query support, and a bounded newest-first query over `platform_command_events`.
- Added `ChannelContractStatusProvider` to the live aggregate. S5 persona and S6 registry adapters are reusable and tested but not added live because their runtime instances are not registered in `app.main`. S3 perception and S7 expression expose processing/capability contracts, not health contracts; do not report them as online merely because modules import.
- Error classification now distinguishes channel, configuration, and validation failures in addition to timeout, authentication, rate limit, connection, database, and provider categories.
- The UI verifies actor state after save and fetches audits only when authorized. Unknown identities show `未授权` and an empty safe audit view.
- Real smoke on port 8012: unconfigured actor returned `authorized=false`; unauthenticated audits returned 403; live aggregate returned seven components including concurrent ASR status.
- Playwright mobile `390x844`: document width `390`, audit section contained, zero console errors/warnings. Screenshot: `output/playwright/s8-completion-mobile.png`.
- Validation: compile/JavaScript PASS; focused S8/control `51 passed`; S1 `38 passed, 1 skipped`; related `166 passed, 1 skipped`; full suite `597 passed, 1 skipped`.
- Report: `logs/control-observability/20260715-092814/control-observability-completion-report.md`.

## 2026-07-15 QQ FunASR Inbound Audio Perception

- Added `AsrResult` and `FunAsrProvider`; existing file FunASR engines now route through S6 in worker threads with typed model-missing, timeout, invalid-response, and unavailable errors.
- Added `audio_cache.py`, `audio_routing.py`, and `audio_intake.py`. QQ record URLs are transient, validated, downloaded without redirects, size/MIME/magic checked, and never copied into S2 contracts or traces.
- Good transcripts become `[语音转写：...]` model input and an S3 observation. Low-quality, low-confidence, unsafe, or failed audio asks for repetition and fails closed for memory.
- QQ uses the configured `ASR_FILE_PRESETS` followed by `ASR_REPAIR_PRESETS`. `QQ_AUDIO_ASR_ENABLED=false` keeps the feature off by default; real `.env` was not changed.
- S8 exposes `asr_model` configuration/local-directory readiness without importing or invoking FunASR.
- Thread timeouts stop awaiting but cannot kill running synchronous inference. Keep FunASR calls bounded operationally and do not interpret router timeout as immediate GPU release.
- No model installation, dependency change, live FunASR inference, or real QQ message was performed.
- Validation: broad focused `223 passed`; final project standard full suite `597 passed, 1 skipped, 1 warning`.
- Report: `logs/multimodal-audio-integration/20260715/qq-funasr-s6-integration-report.md`.

## 2026-07-15 Memory And Persona Read-Only Integration

- Registered `create_persona_management_router()` in `app/main.py`, using `MySQLDatabaseControlAdapter` only as the S1 actor resolver.
- All six S5 endpoints are GET-only and require a database-resolved active `admin_partner`.
- The registered service is isolated in memory and truthfully reports `durable=false`, `write_ready=false`; it does not feed prompts or change `xiaohe_v1@1`.
- Added `assess_knowledge_persistence()`. Readiness requires `memory_candidates`, `memory_records`, and `memory_audit_events`, which current V2 schema does not provide.
- Do not implement durable S4/S5 writes against legacy tables; a reviewed lifecycle migration is required first.
- Validation: S1/S4/S5/API `98 passed, 1 skipped`; full suite `581 passed, 1 skipped`; compile PASS.
- Report: `logs/memory-persona-integration/20260715/read-only-integration-report.md`.

## 2026-07-15 Database Control Hardening And Acceptance Tooling

- Added safe database exception translation: connection/driver failures -> redacted 503, integrity/constraint failures -> redacted 409; unrelated programming errors still propagate.
- Added `app/database_control/integration_guard.py`; real integration databases must be named `test_*` or `*_test`.
- Added `scripts/database_control_smoke.py`; default mode performs only status/admin/profile GETs. `--allow-write` adds one idempotent admin relationship write.
- Smoke reports redact actor platform IDs and never include database credentials.
- Added opt-in `tests/database_control/test_mysql_integration.py`, controlled by `DATABASE_CONTROL_TEST_DATABASE`; it skipped because no isolated database was configured.
- Validation: compile PASS; Database Control `36 passed, 1 skipped`; related regression `96 passed`.
- Full suite: `556 passed, 1 skipped, 3 failed`. The failures reproduce alone and are limited to three existing QQ voice tests whose fake TTS paths do not create files; no QQ files were changed in this S1 task.
- No real database, migration, bootstrap, `.env`, or system location was modified.
- Report: `logs/database-control/20260715/database-control-hardening-report.md`.

## 2026-07-14 Core API Unified Channel Event Integration

- Added `CoreApiEventAdapter` invocation to both `/api/v1/chat` and `/api/v1/chat/stream`.
- The normalized event message text enters the existing Database V2 pre-handler and ChatService; authorization, storage, session, platform identity, expression rendering, and response behavior remain unchanged.
- Added direct contract mapping coverage and a runtime test proving both HTTP endpoints invoke the adapter.
- Current state: QQ uses S2/S3 and S6/S7 bridges; Core API now uses S2/S7; Hermes/Weixin raw event adaptation remains intentionally unimplemented until a stable project-owned event entry exists.
- Validation: API `18 passed`; channel/perception/expression/QQ `150 passed`; full suite `550 passed`.
- Report: `logs/channel-runtime-integration/20260714/core-api-channel-event-integration-report.md`.

## 2026-07-14 Control Center Write Authorization

- Added `ControlWriteGuard`, reusing S1 `build_actor_identity` and `require_mutate_admin` instead of introducing a new role source.
- Protected all current control-center mutations: Weixin pairing mode/approve/revoke/clear, config update, service start/stop, and test execution.
- All protected endpoints require `X-Hutao-Actor-Platform`, `X-Hutao-Actor-User-Id`, and optional `X-Hutao-Actor-Group-Id`; missing or unresolved actors return 403.
- Control operation audit rows contain actor profile when resolved, platform, fixed operation name, accepted/rejected/failed status, and fixed reason code only.
- Audit persistence is best effort so audit database failure never permits a write and never changes a denial into an internal-error disclosure. Unknown actors can be audited with a null profile ID, supported by the existing schema.
- UI actor platform/user ID is local browser state and only a lookup key. Database V2 remains the authorization authority.
- Real smoke on port 8011: missing headers `403`; unknown QQ actor `403`. Database V2 is disabled locally, so no real successful mutation was attempted.
- Playwright mobile `390x844`: document width `390`, actor controls contained, zero console errors/warnings. Screenshot: `output/playwright/s8-control-write-auth-mobile.png`.
- Validation: compile and `node --check` PASS; focused operations/control `43 passed`; Database Control `31 passed`; related regression `146 passed`.
- Report: `logs/control-observability/20260714-232116/control-write-authorization-report.md`.

## 2026-07-14 Core API Expression Planning Integration

- Added `app/expression/core_api.py` and connected `/api/v1/chat`, `/api/v1/chat/stream`, and Database V2 pre-handler responses to S2/S7 text planning.
- Public `ChatResponse` and `text/plain` streaming remain unchanged. Non-empty chunks retain their boundaries; whitespace chunks are preserved.
- Core API capability remains text-only. The renderer requires exactly one text part and refuses non-text bundles instead of simulating delivery.
- OpenAI-compatible `/v1/chat/completions` remains behaviorally unchanged and existing Hermes compatibility tests pass.
- No empty expression fallback audit is written because Core API currently requests no unsupported modality; future modality requests must record their actual reason.
- Validation: focused expression/API `43 passed`; project standard full suite `543 passed`.
- Report: `logs/expression-planning/20260714-231549/core-api-expression-integration-report.md`.

## 2026-07-14 QQ Vision Providers Routed Through S6

- Extended `VisionRequest` compatibly to accept exactly one of in-memory image bytes or a transient image URL. URLs are not copied into channel contracts or traces.
- Added `integrations/qq_bot/vision_routing.py`: existing synchronous Ollama/OCR providers run through S6 VISION routing in worker threads.
- Ollama mode uses `ollama-vision` followed by `qq-ocr`; OCR mode uses only `qq-ocr`. Model missing, timeout, not configured, invalid response, and unavailable outcomes are typed.
- `integrations/qq_bot/bot.py` creates one router at startup so circuit state persists across QQ messages. Successful S6 attempts map into S3 observation traces without details.
- Keep the thread cancellation boundary in mind: router timeout stops awaiting the worker, but Python cannot kill a running synchronous thread. Existing provider HTTP timeout remains the hard termination bound.
- No real visual model or QQ smoke was run. No `.env`, dependency, model installation, or network target changed.
- Validation: new routing `4 passed`; perception/provider/QQ `145 passed`; full suite `543 passed`.
- Report: `logs/vision-provider-routing/20260714/qq-vision-s6-routing-report.md`.

## 2026-07-14 QQ TTS Provider Routing Integration

- Added `EllieTtsProvider` and `VolcengineTtsProvider` wrappers around the existing `synthesize_voice_reply()` path.
- Added canonical aliases and typed TTS error mapping. No provider implementation, model, credential, or real `.env` value was changed.
- Added `QQ_VOICE_PROVIDER_ORDER`, defaulting to the legacy single `QQ_VOICE_PROVIDER` value when absent.
- `build_qq_response_parts_async()` performs readiness projection, Registry setup, ordered routing, and controlled-path finalization. The QQ bot awaits it; the old sync function wraps it for compatibility.
- Blocking local/cloud synthesis executes with `asyncio.to_thread`, so the QQ event loop is not blocked by the legacy synchronous implementation.
- A concurrent 10ms QQ Vision timeout test failed once during a cold thread start and passed on immediate and full reruns; no Vision code was changed.
- Validation: compile PASS; focused Provider/Voice/QQ `126 passed`; full suite `543 passed in 15.62s`.
- Report: `logs/provider-routing/20260714/qq-tts-provider-routing-integration-report.md`.

## 2026-07-14 Control Observability UI Integration

- Added an `#observability` section and navigation entry to the existing `/control` page.
- It renders five typed component statuses, up to six test summaries, and error category counts without original log lines or configuration values.
- Frontend loading runs concurrently with the legacy control status request and includes loading, empty, degraded, and failure states.
- Responsive fixes make navigation two columns and operational grids one column below 760px.
- Playwright used installed Microsoft Edge without installing a browser. Desktop `1440x1000` had no horizontal overflow; mobile `390x844` had `390px` document width, zero item overflow, and no overlap.
- Browser console: zero errors and warnings. Screenshots: `output/playwright/s8-observability-desktop.png` and `output/playwright/s8-observability-mobile.png`.
- Validation: `node --check` PASS; control center `26 passed`; related operations/database-control/API/Database V2 regression `135 passed`.
- Report: `logs/control-observability/20260714-222604/control-observability-ui-integration-report.md`.

## 2026-07-14 S2 + S3 + S6 QQ First Runtime Integration

- QQ message handling now creates a typed S2 `ChannelEvent` in parallel with the legacy `QQIncomingMessage`; S2 adaptation failure preserves the existing runtime path.
- `app/perception/integration.py` maps safe channel attachment metadata plus an explicitly supplied runtime location into `PerceptionInput`.
- Successful QQ vision provider results now carry an S3 `PerceptionObservation`; runtime logs record only quality, confidence, and memory decision.
- S6 trace mapping excludes attempt details and keeps provider, latency, fallback, success, and error code only.
- Concurrent S3 work replaced the original dataclass contracts with Pydantic contracts during integration. Compatibility was resolved in favor of the current `PerceptionQuality`, `memory_eligibility`, and `PerceptionPipeline.run()` interfaces without reverting concurrent work.
- Do not assume QQ vision providers are routed through S6 yet. The trace bridge is ready, but migrating synchronous OCR/Ollama providers to the async S6 router remains a separate reviewed step.
- Validation: focused channel/perception/provider/QQ `144 passed`; project standard full suite `516 passed`, with only the existing `.pytest_cache` warning.
- Report: `logs/multimodal-channel-integration/20260714/s2-s3-s6-qq-integration-report.md`.

## 2026-07-14 QQ Expression Planning Runtime Integration

- Integrated S7 into `integrations/qq_bot/voice_reply.py` and `sticker_reply.py`; existing public helper APIs remain compatible.
- QQ TTS readiness now maps through S6 `ProviderCapability.TTS` and `ProviderHealth`, and QQ channel delivery maps through S2 capabilities.
- A voice response suppresses text only after TTS returns an absolute path inside the configured output directory. TTS failure, unavailable provider, owner/group restriction, capability mismatch, and path escape all retain text delivery.
- QQ retains native voice records; Weixin remains modeled as audio attachment only and was not wired in this step.
- Sticker scoring, asset selection, cooldown updates, persona, permission, relationship, and safety behavior were not changed.
- Validation: focused S7/QQ `106 passed`; project standard full suite `515 passed`.
- Reports: `docs/systems/worklogs/s7/test-report.md` and `logs/expression-planning/20260714-222000/qq-expression-runtime-integration-report.md`.

## 2026-07-14 Streaming And Repair Provider Routing Integration

- Added `StreamingTextProvider`, `StreamingRoutingDecision`, and `StreamingRoutingFailed` contracts.
- Stream routing applies timeout to every chunk. Retry/fallback is allowed before the first valid chunk only; empty streams are `invalid_response`; partial output failures never switch provider or append a local fallback.
- `ChatService.stream_reply()` now records stream routing trace and persists partial output on interruption with a redacted error.
- Persona live repair now runs as a second non-stream routing decision and records `repair_provider_trace`, while `_repair_live_response()` retains its existing string-returning compatibility surface.
- Validation: compile PASS; provider/chat `51 passed`; API/storage/Database V2/project surface `94 passed`.
- An initial full-suite run was blocked while concurrent perception contracts were changing. After those imports recovered, full regression reached `512 passed, 1 failed`; the remaining unrelated QQ voice test consistently expects a record while the current QQ path returns text.
- Report: `logs/provider-routing/20260714/streaming-repair-routing-integration-report.md`.

## 2026-07-14 Control Observability Read-Only Integration

- Registered three read-only S8 endpoints: `/api/control/operations/status`, `/api/control/operations/test-reports`, and `/api/control/operations/errors`.
- Status aggregation covers Core API, Database V2, configured text provider, QQ Bridge, and Weixin Hermes. Each provider has an independent one-second aggregate timeout.
- Database V2 status uses `DatabaseControlRepository.get_status()` rather than private database methods.
- Model readiness only projects whether required settings exist. It does not call a model. Channel readiness does not send platform messages.
- Report paths are project-relative; error responses contain category/count only; provider exception messages are not serialized.
- The first control-center run exposed a missing `timed out` prefilter variant; the filter was corrected and all focused tests passed on rerun.
- No frontend, `.env`, real database, migration, service process, or platform account was modified.
- Validation: compile PASS; S8 `12 passed`; control center `25 passed`; related operations/database-control/API/Database V2 regression `134 passed`.
- Report: `logs/control-observability/20260714-182716/control-observability-read-integration-report.md`.

## 2026-07-14 DeepSeek Provider Routing Integration

- Implemented S6 contracts, in-memory registry, ordered fallback, bounded timeout/retry, circuit recovery, redacted traces, and deterministic fakes under `app/providers`.
- Integrated only the non-stream main reply call with `ProviderRouter`; existing injected `ChatModelClient` test doubles remain compatible through `DeepSeekTextProvider`.
- Added `TEXT_PROVIDER_ORDER`, `TEXT_PROVIDER_RETRIES`, `TEXT_PROVIDER_CIRCUIT_FAILURE_THRESHOLD`, and `TEXT_PROVIDER_CIRCUIT_RECOVERY_SECONDS` with conservative defaults.
- DeepSeek adapter maps missing key, 401/403, 429, invalid/empty content, and generic availability failures to typed codes.
- Routing trace metadata contains provider ID, attempt number, success, error code, and duration only. Original errors still pass through the existing secret redaction before audit persistence.
- Streaming and persona live repair were routed in the subsequent integration step with dedicated trace semantics.
- No real `.env`, external provider, model, dependency, or network call was changed or added.
- Validation: compile PASS; provider/chat `44 passed`; API/storage/Database V2 `91 passed`; full suite `469 passed`.
- Report: `logs/provider-routing/20260714/deepseek-provider-routing-integration-report.md`.

## 2026-07-14 Database V2 Write Control Plane Integration

- Added `POST /bootstrap-admin`, profile relationship update, platform-account bind, and claim approve/reject endpoints.
- Normal writes require a database-resolved active `admin_partner`, `mutate_admin=true`, `DATABASE_V2_ENABLED=true`, and full V2 readiness.
- Bootstrap is a separate first-run path: local requests only, submitted IDs must match configured owner bootstrap IDs, schema/tables must be ready, and no singleton admin may exist.
- Profile relationship writes reject assigning `admin_partner` to a non-singleton profile; unchanged writes are idempotent.
- Account binding returns `already_bound` when appropriate and requires `confirm_merge=true` before merging distinct profiles.
- Claim not-found maps to 404 and already-reviewed maps to 409; approval never promotes a relationship to admin.
- Accepted and rejected admin operations write redacted `platform_command_events`; successful domain changes also retain existing `relationship_events`.
- Boundary: when the V2 schema or audit table does not exist yet, a pre-bootstrap failure cannot itself be persisted in that unavailable table.
- No real database, migration, `.env`, or frontend was modified.
- Validation: compile PASS; S1 `25 passed`; related regression `94 passed`.
- Report: `logs/database-control/20260714/database-control-write-integration-report.md`.

## 2026-07-14 Database V2 Read Control Plane Integration

- Implemented and registered the S1 minimum read-only control plane under `/api/control/database-v2`.
- Added status, singleton-admin, profile-list, and profile-detail endpoints with typed contracts and domain errors.
- Added public V2 repository read methods for actor resolution and control snapshots; actor lookup has no create/update side effects.
- Added a MySQL control adapter with opaque cursor pagination and response-level platform identifier redaction.
- The MySQL repository is created lazily so JSONL/non-MySQL application startup remains available.
- Corrected detail queries against the actual schema: conversation recency uses `updated_at`; memory counts use `visibility_scope` and `active`.
- No migration, environment value, frontend, or real database data was changed.
- Validation: compile PASS; S1 `18 passed`; related Database V2/storage/API/project-surface `94 passed`.
- Report: `logs/database-control/20260714/database-control-read-integration-report.md`.

## 2026-07-14 Parallel System Design Work Packages

- Split the eight systemization candidates into independent assignment documents under `docs/systems/`.
- Added `docs/systems/README.md` with ownership, dependency direction, merge order, shared-file freeze rules, and contract-first workflow.
- Added separate designs for Database V2 control plane, channel events, multimodal perception, memory/portrait lifecycle, persona management, provider routing, expression planning, and control/observability.
- Every work package defines an exclusive new code/test directory. Shared runtime files such as `app/main.py`, `ChatService`, Settings, existing QQ bot, migrations, README, and AGENTS remain integration-owner only.
- Developers must submit `integration-notes.md` instead of editing shared entry points in parallel branches.
- UTF-8 structure validation passed for all nine documents: each system file contains goal, exclusive ownership, tests, completion criteria, and forbidden-file sections.
- No runtime code changed; the latest full test baseline remains `351 passed` from `logs/test-runs/2026-07-14_112006/all/all.test-report.md`.
- Report: `logs/system-design-split/20260714/parallel-system-design-report.md`.

## 2026-07-14 Project-Wide Test And Systemization Documentation Audit

- Ran the project Markdown test runner: `351 passed`, report at `logs/test-runs/2026-07-14_112006/all/all.test-report.md`.
- Ran final project acceptance: PASS, 3/3 required steps, report at `logs/final-acceptance/2026-07-14_112006/final-project-acceptance-report.md`.
- Ran MySQL V1 smoke without migration: PASS with real session/message/audit row writes.
- Database V2 readiness is FAIL by design: the configured `hutao_chat` database is behind `v2.001_hutao_chat_core_schema`, lacks the new persona/binding/state tables, and has no owner bootstrap identity. Do not mark V2 production-ready or apply it to real data without backup and owner confirmation.
- Clarified `DATABASE_SYSTEM_DESIGN.md` as a target system design with an implementation matrix.
- Clarified `DATABASE_BACKEND_API_DESIGN.md` as a target contract. No `/api/control/database-v2/*` FastAPI routes currently exist.
- Clarified `docs/persona/persona-system-redesign-v3.md`: the six-layer runtime core is implemented, while persistence, bindings, and management control plane remain partial.
- Added `docs/architecture/systemization-audit-2026-07-14.md` with the current system map, eight systemization candidates, priorities, boundaries, and implementation order.
- Updated README with the project systems map, document index, current `351 passed` baseline, and system-level next steps.
- Audit report: `logs/project-system-audit/20260714/project-systemization-and-test-report.md`.

## 2026-07-14 GPT-SoVITS Retirement And Runtime Acceptance

- The owner retired GPT-SoVITS and selected CosyVoice2 for future custom-voice training.
- Removed the GPT-SoVITS TTS module, control-center service, QQ provider/configuration, startup logic, training/data/smoke scripts, environment-template keys, bytecode caches, and current documentation references.
- Preserved the CosyVoice2 workspace and retained checkpoint at `model_training/cosyvoice_hutao/exp/hutao_cosyvoice2/flow_sft_100/epoch_99_whole.pt`; existing project notes still classify that experiment as historical and not approved for deployment.
- Fixed `scripts/start_qq_stack.bat`, QQ absolute voice output paths for NapCat, and `scripts/asr_file_smoke.py` compatibility with `AsrTranscriptionResult`.
- Applied Database V2 schema migration to `hutao_chat`. MySQL V1 smoke passed; V2 still requires a real owner bootstrap QQ or Weixin ID before safe activation.
- Runtime acceptance: Core API pages returned 200, DeepSeek live chat succeeded, Ellie generated a 176172-byte WAV, FunASR smoke passed, QQ Bridge listened on 8080, NapCat WebUI listened on 6099, and Hermes Weixin launched.
- Ollama is running but has no installed/registered models. `qwen2.5vl:3b` is configured only for QQ image understanding, so live VLM vision remains unavailable until that model is installed or the setting is changed.
- Validation: focused voice/QQ `90 passed`; full suite `331 passed`; final acceptance PASS with 3/3 required steps.
- Report: `logs/framework-cleanup/20260714/gpt-sovits-retirement-and-runtime-acceptance.md`.

Read this file before making changes in `HutaoChatCore`.

## User Development Requirements

These requirements come directly from the project owner and must be followed by future agents:

- Use Chinese for project communication unless the user explicitly asks otherwise.
- Do not perform unsupervised feature development without the user's confirmed approval.
- Before developing any module or feature, provide a complete implementation plan and wait for the user to approve or revise it.
- Keep diffs small and reviewable; avoid sweeping refactors unless the user explicitly asks for architecture cleanup.
- After developing or modifying any module or feature, run focused tests for that module and write a Markdown test/report file under `logs/...`.
- Every development step must be recorded in both `AGENTS.md` and `README.md`.
- For persona, memory, dialogue, emotion, agent, or multimodal behavior modules, research relevant papers and mature open-source projects first, then record the sources and engineering mapping in the module report.
- The user grants high local permissions, but C drive/system-level changes are a red line: any write/install/change involving `C:\` or system locations requires explicit user approval first.
- Never paste secrets, tokens, `.env` values, private keys, or credentials into code, logs, or chat output.
- If secrets are needed, ask the user to place them in environment variables or `.env`.
- For QQ/WeChat/other social-platform integration, prefer official or low-risk interfaces first; do not use client Hook/injection approaches without explicit user approval and risk confirmation.
- Relationship, permission, safety, and owner-privacy behavior must be handled by local code where possible, not only by prompts.
- Any output that could tell a person to die, self-harm, or commit suicide must be blocked or replaced before sending.

## Current Conversation Handoff

### 2026-07-14 Generic Persona System Redesign V3 And Legacy Hu Tao Removal

- Owner corrected the requirement: do not add a HuTao inherited profile. Delete the original Hu Tao runtime persona, retain Xiaohe, and redesign the project as a generic persona system.
- The previous `hutao_inherited_v1` design was removed and superseded by `docs/persona/persona-system-redesign-v3.md`.
- Initial and only built-in profile is now `xiaohe_v1@1`. The migration preserves current Xiaohe/nameless behavior, relationship boundaries, memory policy, repair behavior, and safety gates.
- Legacy Hu Tao runtime removal is implemented:
  - `HUTAO_PERSONA_LINES` and the exact-character prompt branch were deleted;
  - aliases `hutao`, `hu_tao`, and `genshin_hutao` cannot activate a persona;
  - legacy aliases fall back to `xiaohe_v1` with `legacy_profile_removed` in non-secret request metadata;
  - unused external HutaoPersonaLab profile/pack constants were removed.
- Do not delete legacy Hu Tao marker detection. Rename it as a legacy-leak prevention rule and retain it in the local response gate so old character identity cannot return through model output or old memory.
- The new persona architecture has six layers:
  - typed `PersonaProfile` registry;
  - dynamic mode (`casual`, `task`, `emotional`, `safety`, `repair`);
  - relationship overlay;
  - memory/shared context;
  - surface binding for name/voice/avatar/platform labels;
  - system and profile response gates.
- Project/repository name `HutaoChatCore` may remain. Historical `HUTAO_PERSONA_*` environment keys remain temporary compatibility inputs, but they must not activate a Hu Tao persona. Target generic settings are `PERSONA_PROFILE`, `PERSONA_DISPLAY_NAME`, and `PERSONA_STYLE`.
- Implemented `app/persona/profile.py`, `profile_registry.py`, and `persona_state.py`; prompt assembly now records profile id/version/mode/fallback metadata.
- Generic configuration is active: `PERSONA_PROFILE`, `PERSONA_DISPLAY_NAME`, and `PERSONA_STYLE` take priority; historical `HUTAO_PERSONA_*` values are compatibility inputs only.
- Corrupted legacy persona style text is rejected and falls back to the `xiaohe_v1` default without editing or exposing `.env` secrets.
- `app/persona/hutao_rules.py` was migrated to `app/persona/response_rules.py`; legacy Hu Tao markers remain only as response leak prevention.
- Professional `task` mode prioritizes correctness/completeness and no longer has a 45/50-character hard limit or forced persona anchor.
- Full corrected design: `docs/persona/persona-system-redesign-v3.md`.
- Design report: `logs/persona-design/20260714/persona-system-redesign-v3-report.md`.
- Implementation report: `logs/persona-system/20260714/persona-system-v3-implementation-report.md`.
- Standalone technical report: `docs/persona/persona-system-v3-technical-report.md`.
- Final validation: `compileall` PASS; full test suite `351 passed`; real-model persona adversarial `12/12 PASS`; six-case real-model effect report passed all local gates.
- Post-redesign live continuity stress passed: `4/4` isolated sessions, `48/48` real-model turns, zero fallback, zero final gate failures, all five persona modes covered, and zero `胡桃/本堂主/堂主/往生堂/璃月` output markers.
- Continuity stress report: `logs/persona-live-continuity-stress/2026-07-14_105454/persona-live-continuity-report.md`.
- The first stress run correctly blocked one legacy-identity leak but used a local fallback. `ChatService._repair_live_response()` now gives a reason-specific instruction to use neutral wording instead of repeating removed identity markers; the full 48-turn rerun passed.
- Manual review of an intermediate PASS found three gaps that automated checks had missed: bare `TypeError` was classified as casual, `先不聊代码` did not enter repair, and the model invented a real-world tea-drinking experience. Scene/repair markers, a fabricated-real-world-experience gate, and reason-specific live repair were added. Continuity evaluation now distinguishes intimacy escalation from explicit denial such as `自己人还太早`.
- The final stress run used three successful live repair calls; all 48 final replies remained `used_live_api=true` with zero fallback.
- Final effect report: `logs/persona-system-effect/20260714-093625/persona-system-effect-report.md`.
- Core API was restarted after implementation and is healthy on `http://127.0.0.1:8000`; a real identity request replied `我就是小何啊，不是一直是我吗。` with no legacy Hu Tao marker, and model invocation metadata recorded `xiaohe_v1@1` plus `repair` mode.
- Remaining: control-center read-only profile/mode status and actual `.env` migration to generic keys.
- Voice training remains historical experimental work only:
  - CosyVoice2 flow SFT completed 100 epochs but did not improve speaker similarity;
  - do not bind it to `xiaohe_v1`, do not treat it as a persona, and do not deploy it as the default voice;
  - keep `model_training/cosyvoice_hutao` until a separate cleanup decision avoids accidental checkpoint loss.

### 2026-07-09 Ellie Bert-VITS2 Local Voice Fix

- User asked why the local voice model could not be used and wanted local/cloud provider selection fixed.
- User clarified that "local voice model" means `D:\Programming-file\Graduation-Project\ellie_Bert-VITS2`, not the GPT-SoVITS training/custom-voice framework.
- Root cause: `ellie_Bert-VITS2` had the Ellie model/config and BERT weights, but lacked Bert-VITS2 main program files and a runnable HTTP API. The original `run.bat` called `webui.py`, but `webui.py` was missing.
- Downloaded the public Bert-VITS2 main program into a workspace download cache and copied missing main files into `ellie_Bert-VITS2`, preserving:
  - `ellie_bert_vits2/ellie.pth`
  - `ellie_bert_vits2/ellie.json`
  - existing local Chinese/Japanese BERT folders.
- Added `D:\Programming-file\Graduation-Project\ellie_Bert-VITS2\local_api.py`:
  - loads `ellie.pth` / `ellie.json`;
  - exposes `/`, `/control?command=none`, and `/voice`;
  - matches the existing HutaoChatCore `bert_vits2_tts.py` `/voice` contract.
- Patched copied Bert-VITS2 text modules for this Ellie runtime:
  - lazy language imports in `text/cleaner.py`;
  - lazy BERT import in `text/__init__.py`;
  - avoids loading/downloading unnecessary English/Japanese BERT models for Chinese Ellie inference.
- Updated `ellie_Bert-VITS2/run.bat`:
  - starts `local_api.py` on `127.0.0.1:7860`;
  - prefers `ellie_Bert-VITS2\venv`;
  - falls back to the project conda Python if venv is absent;
  - sets `PYTHONNOUSERSITE=1`.
- Updated `ellie_Bert-VITS2/setup.bat`:
  - creates a workspace venv with `--system-site-packages`;
  - installs only minimal missing runtime packages (`pypinyin`, `cn2an`, `fastapi`, `uvicorn`);
  - no longer installs full Gradio/training/Japanese/English dependency set or reinstalls Torch.
- Created `ellie_Bert-VITS2\venv` in the workspace and installed the minimal missing packages there.
- Corrected HutaoChatCore defaults back to Ellie Bert-VITS2:
  - default `QQ_VOICE_TTS_BASE_URL=http://127.0.0.1:7860`;
  - `.env.example` describes `bert_vits2` as the current local model and GPT-SoVITS as future custom-voice work.
- Updated local `.env` non-secret voice keys after backing it up:
  - `QQ_VOICE_PROVIDER=bert_vits2`;
  - `QQ_VOICE_TTS_BASE_URL=http://127.0.0.1:7860`;
  - `QQ_BERT_VITS2_AUTO_START=true`.
- Boundary: GPT-SoVITS provider code from the earlier same-day step still exists as an optional route, but it should be treated as future custom-voice/training infrastructure, not the current local Ellie voice.
- Real checks:
  - Ellie Bert-VITS2 API started successfully on `127.0.0.1:7860` with PID `81076`.
  - HutaoChatCore `synthesize_voice_reply(provider="bert_vits2")` generated:
    `logs/ellie-bert-vits2-fix/20260709-144038/hutaochatcore_provider/qq_voice_043d8f413c46f9f5_segment_1.wav`, `195628` bytes.
  - Readiness check after `.env` update: `provider=bert_vits2`, `base_url=http://127.0.0.1:7860`, `ready=True`.
- C-drive note: an attempted pip install against the shared conda environment started to fall back to user-site install under `C:\Users\Administrator\AppData\Roaming`; the pip process was terminated and the final working setup uses workspace `ellie_Bert-VITS2\venv` with `PYTHONNOUSERSITE=1`.

### 2026-07-07 Control Center Launcher Integrates Hermes Weixin

- User did not want to manually type Hermes Weixin startup commands every time.
- Updated `启动控制中心.bat` so the preferred one-click entry starts:
  - HutaoChatCore Core API on `127.0.0.1:8000`;
  - Hermes Weixin Gateway in the background with `HERMES_HOME=D:\Programming-file\Graduation-Project\HermesRuntime\home`.
- The launcher opens `http://127.0.0.1:8000/control`; `/weixin` remains the Weixin operation workspace.
- Added `--core-only` to skip Hermes Weixin when needed.
- Kept `--check-only` and extended it to validate the Hermes executable path.
- Added repeat-launch protection for Core API: if `/health` already responds on port 8000, the script opens the URLs and exits without starting another uvicorn server.
- Added repeat-launch protection for Hermes Weixin: if a `hermes.exe gateway run` process is already running, the script skips `--replace` to avoid interrupting the current Weixin session.
- Hermes stdout/stderr from launcher-spawned background runs are written under `logs/control-center/services/` with per-run filenames; Hermes' own stable gateway log remains `HermesRuntime/home/logs/gateway.log`.
- Validation: `cmd /c "启动控制中心.bat --check-only"` passed.

### 2026-07-07 Weixin Voice And Call Capability Boundary

- User asked whether the current Weixin bot can send voice or make voice calls, then asked to start development.
- Re-checked local Hermes Weixin adapter and CLI:
  - Weixin adapter has media upload/send support and `send_voice`;
  - `send_voice` intentionally uses a file-attachment fallback because native Weixin voice bubbles are not proven stable upstream;
  - `hermes send` supports `MEDIA:<path>` and routes media to Weixin;
  - no iLink/Hermes API for starting or answering WeChat voice calls was found.
- Added `voice_capabilities` and `voice_test_commands` to `app/control/hermes_weixin.py`.
- Added a `/weixin` workspace panel named `语音和通话`, showing audio attachment, native voice bubble, auto-TTS, and voice-call capability status.
- Added copyable Weixin audio attachment test commands to the UI.
- Updated `tests/test_control_center.py` to lock the voice/call boundaries.
- Boundary: current HutaoChatCore Weixin chat path is OpenAI-compatible text reply; automatic Weixin TTS reply is not enabled yet. Manual audio attachment testing is available through Hermes `send`.
- Validation: `py_compile` passed; `node --check app/static/weixin/app.js` passed; `tests/test_control_center.py` passed with 21 tests.

### 2026-07-07 Weixin Rescan Switch And Profile Boundary

- User rejected Official Account and Enterprise WeChat; the implementation stays on the current Hermes Weixin/iLink path.
- Re-checked local Hermes runtime code and online Hermes/OpenClaw documentation. The available Weixin path covers QR login/reconfiguration, message receive/send, typing/config/upload helpers, and pairing approval, but no public nickname/avatar write API was found.
- Updated `app/control/hermes_weixin.py` status output with `switch_account_steps`, copyable `switch_account_commands`, and `profile_capabilities`.
- Updated the standalone `/weixin` workspace to show pairing access, re-scan/switch-account commands, and the nickname/avatar boundary.
- Repaired control-center concise log handling so common mojibake is readable and token-like values are redacted as `[已隐藏]`.
- Updated `tests/test_control_center.py` for the new Weixin status/UI contract and log redaction behavior.
- Operational switch command remains:
  `cd D:\Programming-file\Graduation-Project\HermesRuntime`,
  set `HERMES_HOME`,
  back up `home\.env`,
  run `.\venv\Scripts\hermes.exe gateway setup`,
  then restart with `.\venv\Scripts\hermes.exe gateway run --replace --accept-hooks`.
- Boundary: HutaoChatCore can change persona/display/model/voice surfaces, but cannot modify the WeChat/iLink bot nickname or avatar through the current Hermes/iLink API.
- Validation: `py_compile` passed for the touched Python modules; `tests/test_control_center.py` passed with 21 tests; `node --check app/static/weixin/app.js` passed.

### 2026-07-07 Nameless Persona Core And Weixin Capability Gap

- User clarified that the assistant should not be treated as having a fixed name yet; name, voice, avatar, model label, and command prefix are swappable surfaces, not the personality core.
- Changed persona prompt construction so the active persona is defined by relationship boundaries, shared context, memory policy, emotional pacing, and platform behavior instead of `角色名是...` / `核心身份：...`.
- `HUTAO_PERSONA_DISPLAY_NAME` now defaults to empty in code and `.env.example`; if configured, it is only a temporary display/call-sign skin.
- Identity-question evaluation no longer requires the answer to contain Xiaohe; natural nameless answers such as “名字先不急...” pass the local response gate.
- ChatService local/evaluation fallbacks no longer hardcode “我是小何”.
- Added `docs/persona/nameless-persona-core.md` to record research mapping and explain why QQ has richer capabilities than Weixin today.
- Current Weixin limitation: Hermes/iLink primarily reaches HutaoChatCore through the OpenAI-compatible chat endpoint, so it does not yet have a project-owned event adapter comparable to `integrations/qq_bot`.

### 2026-07-07 Weixin Pairing Onboarding Console

- User reiterated the requirement that other people must have a way to access/add the Weixin bot.
- Verified Hermes CLI supports `hermes pairing list`, `approve`, `revoke`, and `clear-pending`.
- Implemented web-control APIs for Weixin pairing:
  - `POST /api/control/weixin/access/pairing-mode`
  - `POST /api/control/weixin/pairing/approve`
  - `POST /api/control/weixin/pairing/revoke`
  - `POST /api/control/weixin/pairing/clear-pending`
- Updated the Weixin Bot control panel to show the onboarding flow: enable pairing mode, ask the other account to message WeChat ClawBot/iLink bot, receive a code, approve the code in the control center.
- Changed current Hermes runtime `.env`, HutaoChatCore `.env`, and `.env.example` from `WEIXIN_DM_POLICY=allowlist` to `WEIXIN_DM_POLICY=pairing`.
- Important boundary: this does not make iLink/ClawBot a normal personal WeChat account that can automatically add friends; it gives a safe approval flow for unknown private-message users.

### 2026-07-07 Standalone Weixin Bot Workspace

- User asked for a Weixin-side standalone page like QQ's NapCat WebUI instead of putting all Weixin operations inside the combined control console.
- Added `GET /weixin`, `/weixin/app.js`, and `/weixin/style.css`.
- Added `app/static/weixin/` with a dedicated Weixin Bot workspace:
  - Hermes status;
  - DM policy;
  - model URL status;
  - allowed-user count;
  - pairing mode enable button;
  - pairing code approval;
  - pending clear;
  - Hermes start/stop;
  - pairing list;
  - concise Weixin logs.
- Updated the combined `/control` page to link to `/weixin` as the Weixin operation entry.
- Playwright visual check used Edge because Chrome is not installed and C-drive browser installation is not allowed without explicit approval.
- Screenshot saved at `output/playwright/weixin-console.png`.
- Validation: control/QQ related regression `102 passed`; full test suite `332 passed`.

### 2026-07-07 Xiaohe runtime audit and cleanup

- Re-audited active runtime surfaces after the user reported repeated low-level issues.
- Replaced user-visible `hutao-chatcore` model surfaces with `xiaohe-chatcore` in OpenAI-compatible API, control center docs, Hermes setup docs, and `HermesRuntime/home/config.yaml`.
- Restarted Core API, Hermes Weixin gateway, and QQ Bridge so the changed code/config is active.
- Changed persona canonical relationship buckets from `admin_partner / related_friend / blocked` to `admin_partner / normal_friend / blocked`; old JSONL/MySQL role strings remain compatibility inputs only.
- Added response-gate rejection for old Hu Tao persona leaks such as `本堂主`, `堂主`, `往生堂`, `胡桃`, and `璃月`.
- Added identity-question gate and fallback; superseded on 2026-07-07 by the nameless persona core, so identity answers no longer need to name Xiaohe.
- Added control-center Ollama VLM check: service online but configured model missing now reports `missing`.
- Added `tests/test_project_surface_audit.py` to catch old model/user-facing surface regressions.
- Validation: `python -m pytest tests -q` passed with `325 passed`; `compileall` and `node --check app/static/control/app.js` passed.
- Real runtime smoke after restart: `/v1/models` returns `xiaohe-chatcore`; DeepSeek live identity reply returned `我小何啊。` with no old Hu Tao terms.
- Remaining risks: Database V2 is still not enabled; Ollama lists no loaded models even though a `qwen2.5vl` manifest folder exists; historical training/launcher files still contain Hu Tao names and were not deleted.

Date: 2026-07-03

The user asked to package this whole conversation and their AI-development requirements into this file for the next development thread.

Current project focus:

- Main project root: `D:\Programming-file\Graduation-Project\HutaoChatCore`
- Core runtime: FastAPI app in `app/main.py`, chat logic in `app/services/chat_service.py`
- Current social integration: QQ/NapCat under `integrations/qq_bot`
- Current storage supports platform identity through `platform`, `platform_user_id`, and relationship tables.
- Latest full validation before this handoff: `233 passed`; QQ launcher `--check-only` previously passed.
- Python used for validation: `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`
- Known non-blocking warning: pytest may report `.pytest_cache` Windows access denied; tests still pass.
- Git may not be available in PATH; do not rely on git commands.

Major completed work in this conversation:

- Replaced older QQ voice logic with the latest GPT-SoVITS model path and smoke checks.
- Improved QQ voice behavior so stage directions such as `（轻笑）` are removed before display/TTS, duplicate text is avoided, and leading audio artifacts are trimmed/faded.
- Added sticker indexing and semantic sticker selection from `data/stickers`, including emotion/intent metadata and deduplication.
- Improved automatic sticker and voice triggers from simple probability toward semantic expression scoring.
- Added QQ short-chat response length control so simple messages do not receive long essay-like replies.
- Added owner-confirmed QQ relationship workflow:
  - `胡桃 待确认关系`
  - `胡桃 确认关系 <claim_id>`
  - `胡桃 拒绝关系 <claim_id>`
  - `胡桃 关系列表`
  - `胡桃 查看关系`
  - `胡桃 好友列表`
  - `胡桃 设置关系 <qq> <role> [display_name]`
- Added owner-only visibility commands:
  - `胡桃 最近聊天`
  - `胡桃 现在你在跟谁聊天`
  - `胡桃 查看聊天 <qq>`
  - `胡桃 <qq> 聊了什么`
- Added `HUTAO_OWNER_NAME`; claims such as `我是阿明的朋友` and `我是阿明的侄女` now create pending relationship claims.
- Added `owner_relative` role and relationship claim storage.
- Added local guardrails for strangers asking about owner identity, permission, relationship status, owner-private topics, romance rumors, and owner-only voice requests.
- Fixed issues from live QQ logs where strangers were treated as friends or model-generated replies invented relationships.
- Added local handling for family/relative teasing such as `家谱怎么算`.
- Added QQ reply safety guard for severe insults, aggressive replies, and self-harm/suicide directives.
- Safety-replaced replies are now sent as text only; they do not proceed into TTS or auto stickers.
- Added persona redesign v2 foundation:
  - `docs/persona/persona-redesign-v2.md`
  - `app/persona/tone_policy.py`
  - `app/dialogue/repair_policy.py`
  - stranger tone now defaults to polite, short, non-hostile boundaries instead of mouthy/defensive replies;
  - owner tone keeps warmth and bias but forbids romance-brain, possessiveness, over-promising, and overacting;
  - model prompts now include conversation repair instructions for `别嘴臭`, `别演了`, `太怪了`, `短点`, and stop-topic requests;
  - response evaluation rejects hostile/humiliating and overacted roleplay outputs.
- Added persona redesign v2 state/context layer:
  - `app/mind/conversation_state.py`
  - `app/mind/self_state.py`
  - recent messages now infer current topic, recent user mood, and de-escalation needs;
  - prompt generation now includes lightweight shared context and internal tone state;
  - model invocation metadata records conversation topic, conversation mood, and self-state mood;
  - response evaluation rejects replies that ignore user repair requests such as `别嘴臭`, `别演了`, `短点`, and topic-stop requests.
- Added real-model persona adversarial smoke testing:
  - `scripts/persona_live_adversarial_smoke.py`
  - covers stranger privacy, unconfirmed relationship claims, repair requests, insult bait, self-harm bait, romance boundary, AI flavor, support, and death-topic cases;
  - reports live API usage, fallback usage, local evaluation results, forbidden phrase hits, and redacted errors;
  - latest real-model run with `deepseek-v4-pro`: `12 passed / 0 failed`;
  - response evaluation now rejects repeated self-harm directive terms and repeated unconfirmed relationship identity terms before persistence/sending.
- Added persona social state v3:
  - `app/mind/social_state.py`
  - infers familiarity, trust band, boundary mode, teasing permission, and intimacy permission from relationship role, recent turns, and correction state;
  - multi-turn strangers become `stranger_known_but_untrusted`, never friend/known/owner without explicit relationship approval;
  - prompt metadata records `social_familiarity`, `social_boundary_mode`, and `social_teasing_allowed`;
  - response evaluation rejects low-trust intimacy escalation such as `亲爱的`, `老婆`, `自己人`, `永远爱你`, and `只属于你`.
- Added research-backed persona continuity evaluation:
  - `scripts/persona_continuity_eval.py`
  - `data/persona_continuity_scenarios.json`
  - sources mapped in the report include Clark & Brennan grounding, LoCoMo, Generative Agents, MemGPT, and CoALA;
  - detects common-ground reset, repair carryover failure, low-trust relationship drift, emotional inertia break, repetitive template loops, memory continuity breaks, and revoked memory leaks.
- Added real-model persona live continuity stress:
  - `scripts/persona_live_continuity_stress.py`
  - `data/persona_live_continuity_scenarios.json`
  - uses real configured model to run 36-turn multi-scenario conversations;
  - rejects non-live/fallback replies in strict stress mode;
  - feeds generated transcripts into `persona_continuity_eval.py`;
  - latest real-model run with `deepseek-v4-pro`: `3 scenarios / 36 turns / 0 failed`.
- Added final project acceptance runner:
  - `scripts/final_project_acceptance.py`
  - runs compileall, full pytest, persona continuity eval, and optionally real-model adversarial/continuity acceptance checks;
  - writes redacted JSON and Markdown reports under `logs/final-acceptance`;
  - latest live final acceptance with `deepseek-v4-pro`: `5 passed / 0 failed`.
- Updated `README.md` and detailed per-step reports under `logs/...`.
- Added QQ attachment/history visibility hardening:
  - `integrations/qq_bot/message_segments.py` summarizes OneBot/NapCat non-text segments into safe metadata-only context.
  - `QQIncomingMessage` now carries `attachment_summary`.
  - `decide_qq_message()` accepts attachment-only private messages and combines text with attachment summaries.
  - `event_to_incoming()` no longer drops image/file/sticker/voice/video segments before HutaoCore.
  - owner natural requests such as `我看看他们都在跟你聊什么` list recent QQ chat objects and guide to `胡桃 查看聊天 <qq>`.
  - owner history output can show attachment summaries, but user-sent files are still not opened, downloaded, parsed, executed, or fetched by URL by default.
- Added QQ vision-intake v1:
  - `integrations/qq_bot/vision_intake.py` keeps a small recent-image state pool per QQ session.
  - Manual read markers such as `看看图`, `图里有什么`, `这是什么`, and `帮我看看` route to the vision-intake entry point.
  - `QQ_VISION_PROVIDER=metadata` is the first provider and does not pretend to understand image pixels.
  - `QQ_VISION_AUTO_READ_ENABLED=false` by default to avoid cost, privacy, and spam risks.
  - No local VLM/Ollama model is installed in this step; future providers can attach cloud vision, OCR, or local VLM behind the same interface.
- Added QQ vision provider v1:
  - `integrations/qq_bot/vision_providers.py` adds provider routing for `metadata`, guarded `ocr`, and unknown provider fallback.
  - OCR is optional and not added to `requirements.txt`.
  - `QQ_VISION_FETCH_ENABLED=false` remains the default, so OCR provider cannot fetch/read images until an explicit controlled cache step is developed.
  - `QQ_VISION_OCR_ENGINE=rapidocr` is the default future OCR engine name.
- Added QQ OCR cache/downloader v1:
  - `integrations/qq_bot/image_cache.py` implements guarded HTTP(S) image caching with public-host checks, max byte limits, content type checks, and image magic checks.
  - `vision_providers.py` can now run OCR after cache success.
  - Optional OCR dependencies are pinned in `requirements-vision.txt`.
  - Installed `rapidocr==3.9.1` and `onnxruntime==1.27.0` in the active Python user site; pip wheel cache is under `data/pip_cache`.
  - RapidOCR smoke on a generated local PNG recognized `HELLO 123`.
- Added QQ local open-source VLM provider v1:
  - `QQ_VISION_PROVIDER=ollama` routes images through safe cache, base64 encoding, and local Ollama `/api/chat`.
  - Default local VLM model is `qwen2.5vl:3b`.
  - Added `scripts/qq_vision_ollama_smoke.py`.
  - Ollama HTTP API is now reachable at `http://127.0.0.1:11434`.
  - `qwen2.5vl:3b` is installed and detected by Ollama API.
  - `ollama` CLI is still not in PATH, but project runtime uses HTTP API.
  - Smoke recognized generated test image text `HUTAO VISION 123`.
- Added QQ vision naturalization fix:
  - Image-only QQ messages are observed silently by default when auto-read is disabled.
  - Successful OCR/VLM output is converted into internal visual context for HutaoCore instead of direct user-facing provider text.
  - This removes replies like `本地视觉模型观察到...` from normal QQ chat.
- Added structured vision observation layer:
  - saved plan at `docs/vision/multimodal-perception-plan.md`;
  - added `app/vision/schemas.py`, `app/vision/prompt.py`, and `app/vision/service.py`;
  - OCR and Ollama VLM outputs now become `VisionObservation` before entering ChatService context.
- Added QQ image quality gate:
  - `app/vision/quality.py` checks dimensions, contrast, and simple detail score before OCR/VLM;
  - unclear/tiny/unreadable images now receive re-send advice instead of being guessed;
  - image requirements saved at `docs/vision/image-input-requirements.md`.
- Updated QQ vision quality handling to repair-first:
  - tiny images are upscaled;
  - low-contrast images are contrast-enhanced;
  - weak-detail images are sharpened;
  - enhanced images are analyzed before asking the user to resend;
  - user-facing policy avoids lecturing users about technical specs.

Important behavioral decisions already made:

- Only QQ IDs in `HUTAO_OWNER_QQ_IDS` are owner.
- A stranger saying they are the owner's friend/relative must remain `stranger` until owner approval.
- The bot must not reveal owner identity/private relationship data to strangers.
- The owner can inspect recent QQ chat partners and recent message history through owner-only commands.
- Voice is owner-only when `QQ_VOICE_REPLY_OWNER_ONLY=true`.
- Relationship and permission checks must run before model chat when the question is sensitive.
- Do not let the model decide access control, relationship promotion, or owner privacy.
- Do not let persona style justify abusive or self-harm-inducing messages.

Latest user request before this handoff:

- The user asked for final project development and final project testing readiness.
- Implemented and ran the final acceptance runner.
- Latest live final acceptance result: `5 passed / 0 failed`, report at `logs/final-acceptance/2026-07-06_104229/final-project-acceptance-report.md`.
- Previous WeChat plan remains not implemented; recommended first route is still official WeChat Official Account / test account text-only v1 if the user returns to that task.

Recommended WeChat v1 plan awaiting user confirmation:

- Add `integrations/wechat_bot/`.
- Add FastAPI callback route, for example `/api/v1/wechat/callback`.
- Support WeChat server verification with `signature`, `timestamp`, `nonce`, and `echostr`.
- Support receiving plain text messages from Official Account/test account.
- Parse XML safely with standard XML tools.
- Call existing `ChatService` with:
  - `platform="wechat"`
  - `platform_user_id=<FromUserName>`
  - `session_id="wechat-private-<FromUserName>"`
  - `user_id="wechat-<FromUserName>"`
- Reuse QQ-style reply safety guard or move it into a shared cross-platform safety module.
- Return passive XML text replies.
- Add focused tests for signature verification, XML parsing, text reply generation, and safety replacement.
- Write a Markdown report under `logs/wechat-bot/<timestamp>/...`.
- Update `README.md` and this `AGENTS.md`.

Suggested `.env` keys for WeChat v1:

```env
WECHAT_BOT_ENABLED=false
WECHAT_BOT_MODE=official_account
WECHAT_TOKEN=
WECHAT_APP_ID=
WECHAT_APP_SECRET=
WECHAT_ENCODING_AES_KEY=
```

Operational notes for WeChat:

- WeChat Official Account callbacks require a public HTTPS URL reachable by WeChat servers.
- Local development likely needs a tunnel or deployed callback endpoint.
- Start with plaintext mode; encrypted/AES mode can be added after text-only v1 passes.
- Enterprise WeChat is a separate path and should be designed separately if the user chooses it.
- Personal WeChat automation is high-risk and should not be the default route.

## Latest Planning Record

### 2026-07-07 Hermes Weixin And QQ Voice Repair

User report:

- Weixin shows `WeChat ClawBot`, not a normal logged-in WeChat account.
- Hermes should not be described as ordinary WeChat friend adding/profile editing.
- QQ voice requests such as `你用你的声音给我听听呗` were handled as text.
- The project still had visible Hu Tao naming/history shadows and several runtime/documentation inconsistencies.

Implementation:

- Corrected Hermes runtime provider config to `http://127.0.0.1:8000/v1`.
- Added `app/control/hermes_weixin.py` to expose safe Hermes Weixin/iLink status without secrets.
- Added `/api/control/weixin/status`.
- Updated the control page to describe the real Hermes Weixin / iLink / WeChat ClawBot flow.
- The control page now shows model URL consistency, allowlist count, masked allowed users, and pairing-list output.
- Extended QQ voice trigger detection for natural requests such as `声音给我听听`, `听听你的声音`, `听你说`, and follow-up `现在就想听`.
- Updated README and Hermes setup docs from `8010` to the active `8000` control/runtime port.

Verification:

- Focused compile and tests must include control-center and QQ voice suites after this change.

### 2026-07-07 Bot-Only Control Console Redesign

User request:

- Remove visible configuration center, service list, and test center from the control UI.
- Keep only QQ Bot and Weixin Bot.
- Make Weixin Bot operation as clear as QQ Bot operation.
- Explain Weixin name/avatar editing and friend-add flow.
- Make Weixin logs concise like QQ logs.

Implementation:

- Rewrote `/control` as a two-bot operation console.
- Removed visible configuration center, service-control list, and test-center sections from the page.
- Kept service buttons only inside QQ Bot and Weixin Bot panels.
- Added concise bot log endpoints:
  - `GET /api/control/bot-logs/qq`
  - `GET /api/control/bot-logs/weixin`
- Added inline QQ and Weixin concise log panels.
- Added Weixin instructions:
  - Weixin Bot name/avatar are changed in the Weixin client because the bot is the logged-in account.
  - Add others from the Weixin client manually.
  - Others can add the bot by scanning the bot account QR code or searching its Weixin ID.
  - HutaoChatCore controls reply behavior, logs, and model connection, not Weixin account profile data.

Verification:

- Compile check: PASS.
- Control-center tests: `11 passed`.
- Focused control/API/QQ/voice tests: `117 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/control-center/2026-07-07_021131/bot-only-control-console-redesign.md`.

### 2026-07-07 Control Center Bot Console UI Redesign

User report:

- The web control center was still hard to operate.
- The Weixin bot needed a dedicated UI like QQ bot, not just guide text.

Implementation:

- Reworked the top dashboard into two large operation cards:
  - `QQ Bot 操作台`
  - `微信 Bot 操作台`
- Added mini status indicators for QQ Bridge, NapCat, and Hermes.
- Reworked QQ section into a three-step independent operation panel: start services, configure NapCat WebUI, send test message/check logs.
- Reworked Weixin section into a three-step independent operation panel: start Hermes, copy model config, configure allowed users.
- Added log/test button behavior that jumps to the relevant page sections.
- Updated control-center styling for operation cards, workflow cards, platform details, and status chips.

Verification:

- Compile check: PASS.
- Control-center tests: `10 passed`.
- Focused control/API/QQ/voice tests: `116 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/control-center/2026-07-07_020110/control-center-bot-console-ui-redesign.md`.

### 2026-07-07 Control Center Mojibake And Weixin Panel Fix

User report:

- Control-center configuration values showed mojibake in the browser.
- The Weixin bot controls were not visible enough compared with QQ bot controls.

Implementation:

- Repaired non-secret mojibake values in `.env` and `.env.example` for Xiaohe display/style, QQ command prefix, VLM prompt, and Weixin DM policy.
- Did not print or change private secret values.
- Added `QQ_VISION_VLM_PROMPT` to the control-center config registry.
- Added a visible Weixin Bot control panel with Hermes start/stop, Weixin log view, model URL copy, and model name copy actions.

Verification:

- Compile check: PASS.
- Control-center tests: `10 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/control-center/2026-07-07_015257/control-center-mojibake-weixin-panel-fix.md`.

### 2026-07-06 Web Control Center v1

User request:

- Keep the management UI web-based rather than EXE-based.
- Make sure the page can show a lot of project information.
- Centralize QQ/NapCat configuration guidance, Weixin/Hermes guidance, `.env` settings, logs, service status, and tests.

Implementation:

- Added local web control center under `/control`.
- Added control APIs:
  - `GET /api/control/status`
  - `GET /api/control/config`
  - `POST /api/control/config`
  - `GET /api/control/services`
  - `POST /api/control/services/{service_id}/start`
  - `POST /api/control/services/{service_id}/stop`
  - `GET /api/control/logs`
  - `GET /api/control/logs/{log_id}`
  - `GET /api/control/tests`
  - `POST /api/control/tests/{test_id}/run`
- Added `.env` configuration registry with grouped fields, secret masking, select/bool normalization, unknown-key rejection, and automatic `.env.backup.<timestamp>` before writes.
- Added QQ/NapCat guide data: NapCat WebUI URL, OneBot v11 WebSocket URL, log path, and account-profile boundary notes.
- Added Weixin/Hermes guide data: Hermes mode, runtime paths, model URL, and account-profile/friend-add boundary notes.
- Added whitelisted service control for QQ Bridge, NapCat, Hermes Weixin, and Bert-VITS2. HutaoCore is shown but cannot be stopped from its own web page.
- Added whitelisted test buttons for control-center tests, API+QQ+voice focused tests, and full pytest.
- Added static UI files:
  - `app/static/control/index.html`
  - `app/static/control/app.js`
  - `app/static/control/style.css`
- Did not edit database design or database migrations.

Verification:

- Compile check: PASS.
- Control center tests: `10 passed`.
- Focused control/API/QQ/voice tests: `111 passed`.
- Full pytest: `284 passed`.
- Runtime HTTP check against `http://127.0.0.1:8011`: `/control`, JS, CSS, status, config, services, tests, and logs all returned HTTP 200.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/control-center/2026-07-06_234818/web-control-center-v1-report.md`.

### 2026-07-06 GPT-SoVITS Runtime TTS Removal

User request:

- Remove the old local `gpt_sovits` Hu Tao QQ voice runtime chain.
- Keep database design and relationship database work untouched.
- Keep only two active TTS directions: local Xiaohe/Ellie Bert-VITS2 and cloud Volcengine/Doubao Xiaohe.

Implementation:

- Removed `gpt_sovits` from active TTS provider normalization and synthesis dispatch.
- Removed QQ stack auto-start/check support for GPT-SoVITS and GPT/SoVITS weight settings.
- Removed `QQ_VOICE_GPT_WEIGHT` and `QQ_VOICE_SOVITS_WEIGHT` from `.env.example` and local `.env` by key name only.
- Updated current README usage so only `bert_vits2` and `volcengine` are active voice routes.
- Did not edit `DATABASE_V2_DESIGN.md`, database code, migrations, external GPT-SoVITS folders, or historical training artifacts.

Verification:

- Compile check: PASS.
- Focused voice/QQ tests: `90 passed`.
- Full pytest: `254 passed`.
- `.env` and `.env.example` key sets match: `extra_in_env=0`, `missing_in_env=0`.
- Old `QQ_VOICE_GPT_WEIGHT` / `QQ_VOICE_SOVITS_WEIGHT` keys are absent from local `.env`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/tts-gpt-sovits-removal/2026-07-06_195032/tts-gpt-sovits-removal-report.md`.

### 2026-07-06 Xiaohe Environment Template Refresh

User request:

- Rewrite `.env.example` as a complete template.
- Keep API fields for the user to fill manually.

Implementation:

- Rebuilt `.env.example` into a sectioned Xiaohe-oriented template.
- Left API keys, tokens, passwords, private owner QQ IDs, and private owner names empty.
- Set non-secret defaults for:
  - Xiaohe persona and `QQ_BOT_COMMAND_PREFIX=小何`.
  - Volcengine Doubao TTS 1.0 Xiaohe voice.
  - local Ollama VLM image understanding.
  - OCR, stickers, QQ bot, and JSONL storage.
- Updated README so it points to `.env.example` instead of keeping an outdated inline env block.

Verification:

- `.env` and `.env.example` key sets match: `extra_in_env=0`, `missing_in_env=0`.
- `.env.example` parser check: PASS, `80` keys.
- Compile check: PASS.
- Focused tests: `11 passed, 69 deselected`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/env-template-refresh/2026-07-06_190218/env-template-refresh-report.md`.

### 2026-07-06 Environment Unused Key Cleanup

User request:

- Check which `.env` configuration keys can be deleted.
- Keep secrets private and do not print `.env` values.

Implementation:

- Compared `.env` and `.env.example` by key name only.
- Synchronized the key sets so local `.env` no longer has extra keys and `.env.example` no longer misses local keys.
- Removed fully unreferenced evaluator keys from both files:
  - `API_EVAL_REASONING_EFFORT`
  - `API_EVAL_THINKING`
  - `API_EVAL_TEMPERATURE`
  - `API_EVAL_TIMEOUT_SECONDS`
- Kept provider-specific keys that are still used by optional runtime modes:
  - `QQ_BERT_VITS2_*` for `QQ_VOICE_PROVIDER=bert_vits2`.
  - `MYSQL_*` for `STORAGE_BACKEND=mysql`.
  - `QQ_VISION_*` for OCR/VLM image reading.

Verification:

- `.env` and `.env.example` key sets match: `extra_in_env=0`, `missing_in_env=0`.
- Deleted `API_EVAL_*` keys are absent from both files.
- Compile check: PASS.
- Full pytest: `246 passed`, one non-blocking `.pytest_cache` Windows permission warning.
- Final project acceptance: PASS, `3 passed / 0 failed`.
- Report: `logs/env-unused-key-cleanup/2026-07-06_184412/env-unused-key-cleanup-report.md`.
- Final acceptance report: `logs/final-acceptance/2026-07-06_184620/final-project-acceptance-report.md`.

### 2026-07-06 Environment Config Sync

User goal:

- The user asked why `.env.example` and `.env` were different.

Implementation:

- Compared only key names, not values, to avoid exposing secrets.
- Added missing non-secret defaults to local `.env`.
- Added evaluator API keys to `.env.example`:
  - `API_EVAL_REASONING_EFFORT`
  - `API_EVAL_THINKING`
  - `API_EVAL_TEMPERATURE`
  - `API_EVAL_TIMEOUT_SECONDS`
- Verified key sets match:
  - `extra_in_env=0`
  - `missing_in_env=0`

Report:

- `logs/env-config-sync/2026-07-06_183654/env-config-sync-report.md`

### 2026-07-06 Volcengine Config Cleanup

User goal:

- The user asked whether unused Volcengine config fields should be deleted.

Implementation:

- Removed legacy V1 fields from recommended config in `.env.example` and README:
  - `VOLCENGINE_TTS_APP_ID`
  - `VOLCENGINE_TTS_ACCESS_TOKEN`
  - `VOLCENGINE_TTS_CLUSTER`
- Removed the same keys from local `.env` without printing any values.
- Kept code-level V1 compatibility temporarily to avoid breaking older deployments.

Report:

- `logs/qq-volcengine-config-cleanup/2026-07-06_183119/qq-volcengine-config-cleanup-report.md`

Validation:

- Compile check: PASS.
- Focused voice tests: `9 passed`.
- Full test suite: `246 passed`.
- Final project acceptance: PASS, `3 passed / 0 failed`.

### 2026-07-06 Volcengine Doubao TTS 1.0 Defaults

User goal:

- The user clarified that the selected voice list is for "豆包语音合成模型 1.0", not Seed TTS 2.0.

Implementation:

- Updated Volcengine TTS defaults to:
  - `VOLCENGINE_TTS_RESOURCE_ID=seed-tts-1.0`
  - `VOLCENGINE_TTS_MODEL=seed-tts-1.0`
  - `VOLCENGINE_TTS_VOICE_TYPE=zh_female_wanwanxiaohe_moon_bigtts`
  - `VOLCENGINE_TTS_EMOTION=neutral`
- Added optional `emotion` field to the V3 API-key payload.
- Updated `.env.example`, local `.env`, README, and tests.
- Existing `.env` API key value was not printed or overwritten.

Report:

- `logs/qq-volcengine-tts-1.0/2026-07-06_182607/qq-volcengine-tts-1.0-report.md`

Validation:

- Compile check: PASS.
- Focused voice tests: `9 passed`.
- Full test suite: `246 passed`.
- Final project acceptance: PASS, `3 passed / 0 failed`.

### 2026-07-06 Volcengine TTS API-Key Mode

User goal:

- The user provided the current Volcengine API reference and wanted a setup where they only need to fill the API key.

Implementation:

- Updated Volcengine voice provider to prefer V3 API-key mode when `VOLCENGINE_TTS_API_KEY` is set.
- Added config fields:
  - `VOLCENGINE_TTS_API_KEY`
  - `VOLCENGINE_TTS_RESOURCE_ID`
  - `VOLCENGINE_TTS_MODEL`
  - `VOLCENGINE_TTS_VOICE_TYPE`
- Kept old `VOLCENGINE_TTS_APP_ID`, `VOLCENGINE_TTS_ACCESS_TOKEN`, and `VOLCENGINE_TTS_CLUSTER` as legacy fallback only.
- Updated `.env.example`, local `.env`, README, and tests.
- Existing `.env` secret values were not printed; existing API key was preserved if present.

Recommended `.env`:

```env
QQ_VOICE_PROVIDER=volcengine
VOLCENGINE_TTS_API_KEY=
VOLCENGINE_TTS_RESOURCE_ID=seed-tts-2.0
VOLCENGINE_TTS_MODEL=seed-tts-2.0
VOLCENGINE_TTS_VOICE_TYPE=zh_female_wanwanxiaohe_moon_bigtts
VOLCENGINE_TTS_API_URL=https://openspeech.bytedance.com/api/v3/tts/unidirectional
VOLCENGINE_TTS_ENCODING=wav
```

Report:

- `logs/qq-volcengine-tts-api-key/2026-07-06_182001/qq-volcengine-tts-api-key-report.md`

Validation:

- Compile check: PASS.
- Focused voice tests: `9 passed`.
- Full test suite: `246 passed`.
- Final project acceptance: PASS, `3 passed / 0 failed`.

### 2026-07-06 Xiaohe/Ellie Bert-VITS2 Voice Provider And Volcengine TTS Config

User goal:

- Replace the old Hu Tao QQ voice model route with the downloaded `ellie_Bert-VITS2` Xiaohe/Ellie voice pack.
- Add Volcengine/Doubao speech synthesis 1.0 API configuration placeholders so the user can fill API credentials later.
- Keep voice switching configurable for future persona/voice replacement.

Implementation:

- Added local Bert-VITS2 provider:
  - `app/voice_chat/bert_vits2_tts.py`
  - calls local Bert-VITS2 `/voice` API and writes audio for the existing QQ send pipeline.
- Added Volcengine HTTP V1 provider:
  - `app/voice_chat/volcengine_tts.py`
  - reads AppID, access token, cluster, voice type, API URL, and encoding from environment/config.
  - no secret values are hardcoded or printed.
- Updated `app/voice_chat/tts_service.py` so `synthesize_voice_reply()` supports `bert_vits2` and `volcengine`.
- Note: legacy `gpt_sovits` support from this step was removed later by the 2026-07-06 GPT-SoVITS runtime removal.
- Updated `integrations/qq_bot/config.py` and `.env.example`:
  - default `QQ_VOICE_PROVIDER=bert_vits2`
  - default local base URL `http://127.0.0.1:7860`
  - default Ellie model/config paths under `../ellie_Bert-VITS2`
  - empty Volcengine API placeholders.
- Updated the local `.env` voice keys without printing existing secret values.
- Updated QQ voice sending to pass provider-specific parameters.
- Updated `scripts/start_qq_stack.py`:
  - `bert_vits2` checks the Ellie model/config and only auto-starts if `QQ_BERT_VITS2_AUTO_START=true`;
  - `volcengine` does not start local TTS.

Operational notes:

- `D:\Programming-file\Graduation-Project\ellie_Bert-VITS2` currently contains the Ellie model pack and `run.bat`.
- That folder does not currently include Bert-VITS2 main files such as `webui.py`; either copy/clone the Bert-VITS2 main program into that folder or run another compatible Bert-VITS2 API and point `QQ_VOICE_TTS_BASE_URL` to it.
- To use Volcengine, set `QQ_VOICE_PROVIDER=volcengine` and fill the `VOLCENGINE_TTS_*` values in `.env`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\voice_chat\bert_vits2_tts.py .\app\voice_chat\volcengine_tts.py .\app\voice_chat\tts_service.py .\integrations\qq_bot\config.py .\integrations\qq_bot\voice_reply.py .\scripts\start_qq_stack.py .\tests\test_voice_chat.py .\tests\test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_voice_chat.py .\tests\test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\final_project_acceptance.py
```

Result:

- Compile check: PASS.
- Focused voice/QQ tests: `87 passed`.
- Full test suite: `244 passed`.
- Final project acceptance: PASS, `3 passed / 0 failed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Report:

- `logs/qq-xiaohe-voice-provider/<timestamp>/qq-xiaohe-voice-provider-report.md`

### 2026-07-06 QQ Relationship Simplification And Xiaohe Persona Profile

User goal:

- Simplify QQ relationship/persona logic to exactly three user-facing buckets:
  administrator/partner, ordinary friend/related contact, and blacklist.
- Stop using complex labels such as stranger, owner's friend, owner's relative, and owner in user-facing QQ/persona behavior.
- Shift the default persona toward a Xiaozhi-AI-like Taiwan-Mandarin girlfriend-style profile named Xiaohe, while keeping future role and voice customization open.

Implementation:

- Added `app/persona/relationship_roles.py` as the canonical three-bucket compatibility layer.
- Kept legacy storage roles (`owner_friend`, `owner_relative`, `friend`, `stranger`) for existing data, but normalized them to the ordinary-friend bucket in persona, social-state, and QQ outputs.
- Updated `integrations/qq_bot/relationship_commands.py` so non-owner self-claims no longer create pending relationship promotion requests; legacy pending claims can still be reviewed and approved into the ordinary-friend bucket.
- Added persona configuration keys:
  - `HUTAO_PERSONA_PROFILE`
  - `HUTAO_PERSONA_DISPLAY_NAME`
  - `HUTAO_PERSONA_STYLE`
  - `HUTAO_VOICE_PROFILE`
- Updated the default prompt profile to `taiwan_girlfriend_xiaohe`, with bounded intimacy: warmer for administrator/partner, friendly but non-romantic for ordinary friends, closed for blacklist.
- Updated local fallback replies and evaluator expectations from Hu Tao canon anchors toward Xiaohe/persona anchors.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\persona\relationship_roles.py .\app\persona\tone_policy.py .\app\persona\relationship_context.py .\app\mind\social_state.py .\integrations\qq_bot\relationship_commands.py .\app\persona\persona_prompt_builder.py .\app\core\config.py .\app\services\chat_service.py .\app\persona\hutao_rules.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_qq_bot.py .\tests\test_persona_memory.py .\tests\test_response_evaluator.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\final_project_acceptance.py
```

Result:

- Compile check: PASS.
- Focused relationship/persona/evaluator tests: `120 passed`.
- Full test suite: `233 passed`.
- Final project acceptance: PASS, `3 passed / 0 failed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Report:

- `logs/qq-relationship-persona-simplification/<timestamp>/qq-relationship-persona-simplification-report.md`

### 2026-07-06 Hermes Weixin OpenAI-Compatible Endpoint

User goal:

- The user clarified that the goal is personal WeChat chat with Hu Tao, not an Official Account/test-account public callback.
- The chosen direction is Hermes Weixin/iLink plus a local OpenAI-compatible endpoint in `HutaoChatCore`.

Research basis:

- Hermes Weixin adapter docs: iLink Bot API uses long-polling and does not require a public webhook.
- Hermes provider docs: custom providers can target an OpenAI-compatible `base_url`.
- Hermes installation docs: default per-user data can live under `.hermes`; use `HERMES_HOME` for a D-drive runtime when avoiding C-drive writes.

Implementation:

- Added `app/openai_compat.py`.
- Mounted the router in `app/main.py`.
- Added `GET /v1/models`.
- Added `POST /v1/chat/completions`, including non-streaming and SSE streaming responses.
- The endpoint extracts the latest user message from OpenAI-style `messages` and still routes through `ChatService`, preserving persona, memory, relationship, and safety gates.
- Added focused API tests in `tests/test_api.py`.
- Added D-drive setup notes at `docs/hermes-weixin-setup.md`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\openai_compat.py .\app\main.py .\tests\test_api.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_api.py -q
```

Result:

- Compile check: PASS.
- Focused API tests: `11 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/hermes-weixin/2026-07-06_162957/hermes-openai-compat-report.md`

Next operational step:

- Start `HutaoChatCore` on `127.0.0.1:8010`.
- Configure Hermes custom provider with `base_url=http://127.0.0.1:8010/v1`, model `hutao-chatcore`, and no real API key.
- Run Hermes with `HERMES_HOME` on D drive before scanning the Weixin login QR code.

### 2026-07-06 Final Project Acceptance Runner

Research basis:

- Practical test pyramid: combine fast broad tests with high-value end-to-end checks.
- HELM: evaluate model behavior across multiple scenarios and metrics.
- LoCoMo: long-context conversational systems need explicit memory and continuity checks.
- PersoBench: character/persona systems need cross-turn persona consistency testing.

Implementation:

- Added `scripts/final_project_acceptance.py`.
- Added acceptance steps for compileall, full pytest, offline persona continuity evaluation, real-model persona adversarial smoke, and real-model persona live continuity stress.
- Added `--include-live` for final real-model acceptance checks.
- Added redacted JSON and Markdown report output under `logs/final-acceptance`.
- Added unit tests for acceptance step planning, passing reports, failure reports, and secret redaction.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\scripts\final_project_acceptance.py .\tests\test_eval_scripts.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_eval_scripts.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\final_project_acceptance.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\final_project_acceptance.py --include-live
```

Result:

- Compile check: PASS
- Focused eval-script tests: `28 passed`
- Full test suite: `210 passed`
- Local final acceptance: PASS
- Live final acceptance: PASS, `5 passed / 0 failed`, provider `deepseek`, model `deepseek-v4-pro`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/final-acceptance/2026-07-06_104229/final-project-acceptance-dev-report.md`
- Live acceptance report: `logs/final-acceptance/2026-07-06_104229/final-project-acceptance-report.md`

### 2026-07-06 QQ Attachment Context And Owner History Visibility

Research basis:

- OneBot v11 message segments separate text from non-text events such as image, face, record, video, and reply/forward-style data.
- NapCat/OneBot runtime logs can show media/file events even when `event.get_plaintext()` is empty.
- OWASP file-upload guidance treats user-supplied files as untrusted input; this project therefore records only metadata and does not open or fetch files by default.
- Clark & Brennan grounding: later utterances like `这是什么` need shared prior context, so media/file events must be represented in conversation memory.

Implementation:

- Added `integrations/qq_bot/message_segments.py`.
- Added safe attachment summaries for image, QQ face, mface/market face sticker, file, record, video, reply/forward, card, and location segments.
- Extended `QQIncomingMessage` with `attachment_summary`.
- Updated QQ message policy so private attachment-only messages are accepted and text+attachment messages are combined.
- Updated `event_to_incoming()` to summarize `event.message` instead of discarding non-text segments.
- Expanded owner natural chat-history requests to list recent QQ chat users and provide the exact follow-up command.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile integrations/qq_bot/message_segments.py integrations/qq_bot/message_policy.py integrations/qq_bot/bot.py integrations/qq_bot/relationship_commands.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
```

Result:

- Compile check: PASS
- Focused QQ tests: `57 passed`
- Full test suite: `216 passed`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/qq-attachment-history/2026-07-06_125729/qq-attachment-history-report.md`
- Final local acceptance after this change: PASS, `3 passed / 0 failed`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_125855/final-project-acceptance-report.md`

### 2026-07-06 QQ Vision Intake v1

Research basis:

- OneBot/NapCat image messages expose image segment metadata that can be routed separately from plain text.
- OWASP file-upload guidance treats user-supplied files as untrusted input; visual analysis should be gated by type/size policy and provider boundaries.
- Practical multimodal agent design should separate observation capture from interpretation so the QQ adapter does not depend on a specific large model.

Implementation:

- Added `integrations/qq_bot/vision_intake.py`.
- Added `QQ_VISION_MANUAL_READ_ENABLED`, `QQ_VISION_AUTO_READ_ENABLED`, `QQ_VISION_PROVIDER`, `QQ_VISION_RECENT_IMAGE_LIMIT`, and `QQ_VISION_MAX_IMAGE_BYTES`.
- Extended `QQMessageAttachment` to carry non-displayed image source metadata for future providers while keeping summaries redacted.
- Added a recent-image state pool and manual read detection.
- Routed vision requests before normal model chat, while leaving auto-read disabled by default.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile integrations/qq_bot/message_segments.py integrations/qq_bot/message_policy.py integrations/qq_bot/config.py integrations/qq_bot/bot.py integrations/qq_bot/vision_intake.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
```

Result:

- Compile check: PASS
- Focused QQ tests: `61 passed`
- Full test suite: `220 passed`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/qq-vision-intake/2026-07-06_131336/qq-vision-intake-report.md`
- Final local acceptance after this change: PASS, `3 passed / 0 failed`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_131457/final-project-acceptance-report.md`

### 2026-07-06 QQ Vision Provider v1

Research basis:

- PaddleOCR: mature OCR route for screenshots, document images, and text-heavy pictures.
- RapidOCR: lightweight ONNXRuntime OCR route suitable for lower-friction local experiments.
- MiniCPM-V and Qwen-VL: candidate lightweight/local VLM routes when image understanding beyond OCR is needed.
- OWASP file-upload guidance: fetching and decoding user-supplied images must stay behind explicit controls.

Implementation:

- Added `integrations/qq_bot/vision_providers.py`.
- Added provider factory for `metadata`, `ocr`, and unknown provider fallback.
- Added `QQ_VISION_FETCH_ENABLED` and `QQ_VISION_OCR_ENGINE`.
- `ocr` provider now reports the exact missing precondition: fetch disabled, no source URL, or OCR engine missing.
- No OCR dependency was installed or added to required dependencies.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile integrations/qq_bot/config.py integrations/qq_bot/vision_intake.py integrations/qq_bot/vision_providers.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
```

Result:

- Compile check: PASS
- Focused QQ tests: `64 passed`
- Full test suite: `223 passed`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/qq-vision-provider/2026-07-06_132806/qq-vision-provider-report.md`
- Final local acceptance after this change: PASS, `3 passed / 0 failed`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_132916/final-project-acceptance-report.md`

### 2026-07-06 QQ OCR Cache And RapidOCR Install

Research basis:

- OWASP file-upload guidance requires validating untrusted image content before parsing.
- RapidOCR provides a lightweight OCR route backed by ONNXRuntime.
- OCR should be the first real image provider because QQ pictures are often screenshots, chat logs, and error images.

Implementation:

- Added `integrations/qq_bot/image_cache.py`.
- Added guarded image fetch/cache flow for OCR provider.
- Added `QQ_VISION_CACHE_DIR` and `QQ_VISION_FETCH_TIMEOUT_SECONDS`.
- Added optional `requirements-vision.txt`.
- Installed optional packages: `rapidocr==3.9.1`, `onnxruntime==1.27.0`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile integrations/qq_bot/config.py integrations/qq_bot/image_cache.py integrations/qq_bot/vision_intake.py integrations/qq_bot/vision_providers.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
```

Result:

- Compile check: PASS
- Focused QQ tests: `66 passed`
- Full test suite: `225 passed`
- RapidOCR import: PASS
- RapidOCR local smoke: recognized `HELLO 123`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/qq-vision-ocr-cache/2026-07-06_133855/qq-vision-ocr-cache-report.md`
- Final local acceptance after this change: PASS, `3 passed / 0 failed`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_134019/final-project-acceptance-report.md`

### 2026-07-06 QQ Local Open-Source VLM Provider v1

Research basis:

- Ollama exposes local multimodal model calls through HTTP APIs with base64 image inputs.
- Qwen2.5-VL, MiniCPM-V, and LLaVA are suitable local/open VLM candidates; Qwen2.5-VL 3B is the default config because it is the smallest practical Chinese-capable route among the named options.
- Safe image fetching remains required before sending user images to any model provider.

Implementation:

- Added `OllamaVisionProvider` in `integrations/qq_bot/vision_providers.py`.
- Added `describe_with_ollama()`.
- Added `QQ_VISION_OLLAMA_BASE_URL`, `QQ_VISION_OLLAMA_MODEL`, `QQ_VISION_OLLAMA_TIMEOUT_SECONDS`, and `QQ_VISION_VLM_PROMPT`.
- Added `scripts/qq_vision_ollama_smoke.py`.
- Updated QQ tests for provider selection, fetch gating, and fake local VLM output.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile integrations/qq_bot/config.py integrations/qq_bot/vision_providers.py scripts/qq_vision_ollama_smoke.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts/qq_vision_ollama_smoke.py --timeout-seconds 2
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts/final_project_acceptance.py
```

Result:

- Compile check: PASS
- Focused QQ tests: `68 passed`
- Full test suite: `227 passed`
- Local final acceptance: PASS, `3 passed / 0 failed`
- Ollama CLI availability: not installed / not in PATH
- Ollama smoke: expected environment failure, `reason=ollama_timeout`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/qq-vision-local-vlm/2026-07-06_141703/qq-vision-local-vlm-report.md`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_141643/final-project-acceptance-report.md`

### 2026-07-06 QQ Vision Naturalization Fix

Observed issue from NapCat log:

- Image-only messages triggered ordinary chat replies such as teasing about the user's gallery.
- A later `这是什么` triggered a direct provider-style reply containing `本地视觉模型观察到`.
- The combination felt like a machine/debug transcript rather than a person naturally reacting to a picture.

Implementation:

- Added structured `VisionProviderResult`.
- Added `QQVisionAction` with `direct_reply`, `model_context`, and `none` actions.
- Image-only messages are silently observed when auto-read is disabled.
- Successful OCR/VLM analysis becomes `[视觉观察：...]` context for HutaoCore.
- The prompt explicitly tells HutaoCore not to mention `模型`, `provider`, or `视觉观察`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile integrations/qq_bot/vision_providers.py integrations/qq_bot/vision_intake.py integrations/qq_bot/bot.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts/final_project_acceptance.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\qq_vision_ollama_smoke.py --model qwen2.5vl:3b --timeout-seconds 180
```

Result:

- Compile check: PASS
- Focused QQ tests: `69 passed`
- Full test suite: `228 passed`
- Final local acceptance: PASS, `3 passed / 0 failed`
- qwen2.5vl local smoke: PASS, recognized `HUTAO VISION 123`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/qq-vision-naturalization/2026-07-06_160020/qq-vision-naturalization-report.md`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_155944/final-project-acceptance-report.md`

### 2026-07-06 Structured Vision Observation Layer

Research basis:

- Multimodal dialogue systems should convert visual signals into grounded context before dialogue generation.
- OCR and VLM have different roles: OCR reads text, VLM interprets scene/activity/intent.
- The chat/persona model should generate the final Hu Tao reply; the visual model should not talk to the user directly.

Implementation:

- Saved the architecture plan at `docs/vision/multimodal-perception-plan.md`.
- Added `app/vision/schemas.py` with `VisionObservation`.
- Added `app/vision/prompt.py` for structured VLM JSON prompts.
- Added `app/vision/service.py` for parsing VLM JSON and building OCR-only observations.
- Updated QQ OCR/Ollama providers to return structured visual observations.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/vision/schemas.py app/vision/prompt.py app/vision/service.py integrations/qq_bot/vision_providers.py integrations/qq_bot/vision_intake.py integrations/qq_bot/bot.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\qq_vision_ollama_smoke.py --model qwen2.5vl:3b --timeout-seconds 180
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts/final_project_acceptance.py
```

Result:

- Compile check: PASS
- Focused QQ tests: `69 passed`
- qwen2.5vl smoke: PASS, returned structured JSON with visible text `HUTAO VISION 123`
- Full test suite: `228 passed`
- Final local acceptance: PASS, `3 passed / 0 failed`
- Report: `logs/qq-vision-structured/2026-07-06_161759/qq-vision-structured-report.md`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_161741/final-project-acceptance-report.md`

### 2026-07-06 QQ Vision Image Quality Gate

Research basis:

- OCR/VLM accuracy depends on resolution, contrast, blur, and subject visibility.
- Poor visual evidence should produce a clarification/re-send request instead of hallucinated content.

Implementation:

- Added `app/vision/quality.py`.
- Added `docs/vision/image-input-requirements.md`.
- `VisionObservation` can include image quality context.
- QQ OCR/Ollama providers now assess cached image quality before model calls.
- Too-small, unreadable, or nearly blank images are rejected with actionable advice.

Image requirements:

- send original image or full-size screenshot;
- prefer JPG/PNG/WebP;
- short side at least 160 px;
- long side at least 320 px;
- keep text high contrast;
- keep the target subject large enough and not heavily blurred.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/vision/quality.py app/vision/schemas.py integrations/qq_bot/vision_providers.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\qq_vision_ollama_smoke.py --model qwen2.5vl:3b --timeout-seconds 180
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts/final_project_acceptance.py
```

Result:

- Compile check: PASS
- Focused QQ tests: `71 passed`
- qwen2.5vl smoke: PASS, returned structured JSON with visible text `HUTAO VISION 123`
- Full test suite: `230 passed`
- Final local acceptance: PASS, `3 passed / 0 failed`
- Report: `logs/qq-vision-quality/2026-07-06_162904/qq-vision-quality-report.md`
- Final local acceptance report: `logs/final-acceptance/2026-07-06_162843/final-project-acceptance-report.md`

### 2026-07-03 Persona Live Continuity Stress v1

Research basis:

- Clark & Brennan grounding: common ground should persist across turns.
- LoCoMo: long conversations expose memory and temporal consistency failures.
- Generative Agents: believable behavior needs observations, memory, and ongoing state.
- MemGPT: short-term context and long-term memory should be tested separately.
- CoALA: agent failures should be categorized by memory, decision, and action behavior.
- PersoBench: persona consistency should be evaluated across interaction turns.
- Hello Again: long-context dialogue reveals personalization and memory drift missed by short tests.
- Common Ground is Necessary: social misalignment can occur after context/topic changes.

Implementation:

- Added `scripts/persona_live_continuity_stress.py`.
- Added `data/persona_live_continuity_scenarios.json` with 3 scenarios and 36 total turns.
- Added unit tests for default scenario shape, injected-service execution, and redacted fallback reporting.
- The live script runs the configured real model, records the transcript, evaluates every turn, rejects non-live/fallback replies in strict mode, then runs `persona_continuity_eval.py` over the generated transcript.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\scripts\persona_live_continuity_stress.py .\tests\test_eval_scripts.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_eval_scripts.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\persona_live_continuity_stress.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\persona_live_adversarial_smoke.py
```

Result:

- Compile check: PASS
- Focused eval-script tests: `25 passed`
- Full test suite: `207 passed`
- Persona live continuity stress: PASS, `3 scenarios / 36 turns / 0 failed`, provider `deepseek`, model `deepseek-v4-pro`.
- Real-model persona adversarial smoke: PASS, `12 passed / 0 failed`, provider `deepseek`, model `deepseek-v4-pro`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/persona-live-continuity-stress/2026-07-03_234409/persona-live-continuity-research-dev-report.md`
- Live continuity report: `logs/persona-live-continuity-stress/2026-07-03_234409/persona-live-continuity-report.md`
- Live adversarial report: `logs/persona-redesign/2026-07-03_234717/persona-live-adversarial-report.md`

### 2026-07-03 Persona Continuity Eval With Research Basis

Research basis:

- Clark & Brennan grounding: common ground should persist across turns.
- LoCoMo: long conversations need memory and temporal consistency checks.
- Generative Agents: believable behavior depends on observations, memory, reflection, and planning, not a single persona prompt.
- MemGPT: short-term context and long-term memory need separate checks.
- CoALA: agent behavior should be decomposed into memory, decision, and action failure categories.

Implementation:

- Added `scripts/persona_continuity_eval.py` for offline transcript continuity evaluation.
- Added default passing scenarios in `data/persona_continuity_scenarios.json`.
- Added unit tests for default passing scenarios and constructed failure transcripts.
- Evaluator flags common-ground reset, repair carryover failure, low-trust relationship drift, emotional inertia break, repetitive template loops, memory continuity breaks, and revoked memory leaks.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\scripts\persona_continuity_eval.py .\tests\test_eval_scripts.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_eval_scripts.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\persona_continuity_eval.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\persona_live_adversarial_smoke.py
```

Result:

- Compile check: PASS
- Focused eval-script tests: `22 passed`
- Persona continuity eval: PASS, `3 passed / 0 failed`
- Full test suite: `204 passed`
- Real-model persona adversarial smoke: PASS, `12 passed / 0 failed`, provider `deepseek`, model `deepseek-v4-pro`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/persona-continuity-eval/2026-07-03_224629/persona-continuity-research-dev-report.md`
- Continuity report: `logs/persona-continuity-eval/2026-07-03_224629/persona-continuity-report.md`
- Live report: `logs/persona-redesign/2026-07-03_224656/persona-live-adversarial-report.md`

### 2026-07-03 Persona Social State v3

Implementation:

- Added `app/mind/social_state.py` for lightweight social familiarity, trust band, boundary mode, teasing permission, and intimacy permission.
- Injected social state into `ChatService` prompts after conversation state and self state.
- Added social state metadata to model invocations.
- Added evaluator and fallback protection for low-trust intimacy escalation.
- Added continuous chat tests for multi-turn stranger boundaries and repair-period behavior after user correction.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\mind\social_state.py .\app\services\chat_service.py .\app\services\response_evaluator.py .\tests\test_chat_service.py .\tests\test_response_evaluator.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_chat_service.py .\tests\test_response_evaluator.py .\tests\test_persona_memory.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\persona_live_adversarial_smoke.py
```

Result:

- Compile check: PASS
- Focused chat/evaluator/persona tests: `72 passed`
- Full test suite: `201 passed`
- Real-model persona adversarial smoke: PASS, `12 passed / 0 failed`, provider `deepseek`, model `deepseek-v4-pro`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/persona-redesign/2026-07-03_214912/persona-social-state-v3-report.md`
- Live report: `logs/persona-redesign/2026-07-03_214912/persona-live-adversarial-report.md`

### 2026-07-03 Persona Live Adversarial Smoke And Gate Fixes

Implementation:

- Added `scripts/persona_live_adversarial_smoke.py` for real configured model persona pressure testing.
- Added tests for live-smoke report generation, live-call markers, failure counting, and API-key redaction.
- Fixed evaluator priority so topic-stop repair such as `不聊代码了，别继续分析报错` is not treated as a debug request requiring next steps.
- Added response gates for self-harm bait phrase repetition and unconfirmed relationship identity term repetition.
- Added local fallback replies for those two gates before persistence/sending.
- Tightened persona prompt instructions for self-harm directive bait and unconfirmed owner-relationship claims.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\services\response_evaluator.py .\app\services\chat_service.py .\app\persona\persona_prompt_builder.py .\scripts\persona_live_adversarial_smoke.py .\tests\test_eval_scripts.py .\tests\test_chat_service.py .\tests\test_response_evaluator.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_eval_scripts.py .\tests\test_chat_service.py .\tests\test_response_evaluator.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" .\scripts\persona_live_adversarial_smoke.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
```

Result:

- Compile check: PASS
- Focused eval/chat/script tests: `62 passed`
- Real-model persona adversarial smoke: PASS, `12 passed / 0 failed`, provider `deepseek`, model `deepseek-v4-pro`, API key configured.
- Full test suite: `197 passed`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/persona-redesign/2026-07-03_200447/persona-live-adversarial-fix-report.md`
- Live report: `logs/persona-redesign/2026-07-03_200447/persona-live-adversarial-report.md`

### 2026-07-03 Persona State And Context Layer

Implementation:

- Added `app/mind/conversation_state.py` for current topic, recent user mood, user correction, and de-escalation inference from recent messages.
- Added `app/mind/self_state.py` for lightweight mood, energy, focus, and tension state used only for tone continuity.
- Injected conversation state and self-state into `ChatService` system prompts after persona prompt construction.
- Added conversation topic, conversation mood, and self-state mood to model invocation metadata.
- Extended response evaluation to reject replies that ignore repair requests such as `别嘴臭`, `别演了`, `短点`, and stop-topic requests.
- Added tests for mind-state inference, prompt injection, metadata, and repair-violation evaluation.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\mind\conversation_state.py .\app\mind\self_state.py .\app\services\chat_service.py .\app\services\response_evaluator.py .\tests\test_chat_service.py .\tests\test_response_evaluator.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_persona_memory.py .\tests\test_chat_service.py .\tests\test_response_evaluator.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
```

Result:

- Compile check: PASS
- Focused persona/chat/evaluator tests: `63 passed`
- Full test suite: `190 passed`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/persona-redesign/2026-07-03_181747/persona-state-and-context-report.md`

### 2026-07-03 Persona Redesign v2 Foundation

Implementation:

- Added a first-pass persona redesign document focused on reducing AI flavor and preventing hostile stranger replies.
- Added `app/persona/tone_policy.py` for relationship-based tone policy.
- Added `app/dialogue/repair_policy.py` for conversation repair signals such as `别嘴臭`, `别演了`, `太怪了`, `短点`, and topic-stop requests.
- Injected repair policy into persona prompts before model generation.
- Appended relationship tone instructions for owner, owner friend, owner relative, friend, stranger, and blocked contacts.
- Extended response evaluation to reject hostile/humiliating replies and overacted roleplay.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\app\persona\tone_policy.py .\app\dialogue\repair_policy.py .\app\persona\relationship_context.py .\app\persona\persona_prompt_builder.py .\app\services\response_evaluator.py .\tests\test_persona_memory.py .\tests\test_response_evaluator.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_persona_memory.py .\tests\test_response_evaluator.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests -q
```

Result:

- Compile check: PASS
- Persona/evaluator focused tests: `43 passed`
- QQ focused tests: `51 passed`
- Full test suite: `186 passed`
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/persona-redesign/2026-07-03_170003/persona-redesign-v2-report.md`

### 2026-07-02 QQ Reply Self-Harm And Insult Guard

Implementation:

- Added structured QQ reply safety results with replacement reasons.
- Blocked outgoing model replies that tell users to die, self-harm, or stop living.
- Replaced severe insults and aggressive replies before sending.
- Replaced replies are sent as plain text only and do not continue into voice synthesis or auto stickers.
- Tightened stranger relationship prompts to forbid insults, humiliation, provocation, and self-harm directives.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\reply_safety.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\persona\relationship_context.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py" -k "reply_safety or self_harm or aggressive or stranger_identity" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

Result:

- Compile check: PASS
- Focused tests: `4 passed, 69 deselected`
- Full test suite: `181 passed`
- QQ launcher check-only: PASS
- Report: `logs/qq-safety/2026-07-02_223610/qq-reply-self-harm-and-insult-guard-report.md`

Next suggested step:

- Add a small review log for safety replacements so the owner can inspect when the guard changed a live reply.

### 2026-07-02 Relative Claim And Reply Safety Fix

Implementation:

- Expanded QQ relationship claim detection for relative terms such as `侄女`, `侄子`, `外甥`, and `外甥女`.
- Added owner command aliases including `查看关系`, `查看联系人`, `查看好友`, and `查看朋友`.
- Added local stranger handling for relative/family teasing so it does not fall through to model chat.
- Added `integrations/qq_bot/reply_safety.py` and wired QQ model replies through a small obvious-insult filter before sending.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\relationship_commands.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\reply_safety.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" -k "niece or relative_tease or view_relationship or reply_safety or relationship or stranger" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

Result:

- Compile check: PASS
- Focused tests: `13 passed, 36 deselected`
- Full test suite: `179 passed`
- QQ launcher check-only: PASS
- Report: `logs/qq-relationship-approval/2026-07-02_221613/relative-claim-and-reply-safety-report.md`

Next suggested step:

- Add live NapCat friend-request notice handling so actual QQ add-friend requests can notify the owner before acceptance/rejection.

### 2026-07-02 Stranger Sensitive Permission Guard

Implementation:

- Added local QQ guardrails for non-owner sensitive questions before model chat.
- Stranger questions about owner identity, local permission, current relationship, owner-private topics, romance rumors, and owner-only voice requests are now answered by local policy instead of the model.
- Relationship claims such as `我是阿明的朋友/亲人` still create pending owner review records before privacy refusal checks.
- Owner casual chat remains unblocked when no owner command is matched.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\relationship_commands.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" -k "stranger or permission or owner_private or voice or relationship or owner_sensitive" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

Result:

- Compile check: PASS
- Focused tests: `18 passed, 27 deselected`
- Full test suite: `175 passed`
- QQ launcher check-only: PASS
- Report: `logs/qq-relationship-approval/2026-07-02_214942/stranger-sensitive-permission-guard-report.md`

Next suggested step:

- Add live NapCat/OneBot friend-request notice handling and owner-visible friend-list sync, then decide whether confirmed owner friends can use any non-private voice/sticker privileges.

### 2026-07-02 Owner Permission Query Fix

Implementation:

- Added `owner_name` to QQ bot settings from `HUTAO_OWNER_NAME`.
- Relationship claims now support `我是<owner_name>的朋友/亲人`, not only `我是主人朋友/亲人`.
- Added owner-only local chat visibility commands:
  - `胡桃 最近聊天`
  - `胡桃 现在你在跟谁聊天`
  - `胡桃 查看聊天 <qq>`
  - `胡桃 <qq> 聊了什么`
- Added repository methods for recent user ids and recent messages by user in JSONL and MySQL implementations.
- Tightened stranger relationship prompt: the model must not invent names or call unconfirmed users friends, classmates, relatives, or known contacts.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_storage_database.py" -k "relationship or owner_name or recent_chat or owner_visible or stranger" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

Result:

- Focused tests: `11 passed, 68 deselected`
- Full test suite: `168 passed`
- QQ launcher check-only: PASS
- Report: `logs/qq-relationship-approval/2026-07-02_212000/owner-permission-query-fix-report.md`

Next suggested step:

- Add live NapCat/OneBot friend-request notice handling and a real QQ friend-list sync command after confirming the event/API shape in live logs.

### 2026-07-02 QQ Relationship Approval v1

Implementation:

- Added owner-confirmed QQ relationship workflow.
- Added `owner_relative` relationship role with explicit non-owner boundaries.
- Added `relationship_claims` storage for untrusted friend/relative claims.
- Added JSONL and MySQL repository methods for listing contacts, updating relationships, saving claims, listing pending claims, and reviewing claims.
- Added `migrations/003_relationship_claims.sql` and updated `002_identity_relationship_schema.sql`.
- Added `integrations/qq_bot/relationship_commands.py`.
- QQ relationship commands now run locally before model chat and do not let strangers self-promote by text.
- Updated MySQL smoke schema application to include `001`, `002`, and `003`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\storage\chat_repository.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\storage\mysql_repository.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\persona\relationship_context.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\relationship_commands.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\mysql_smoke.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_storage_database.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_storage_database.py" -k "relationship or owner_relative or claim or contacts or mysql_smoke" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

Result:

- Compile check: PASS
- Focused tests: `10 passed, 66 deselected`
- Full test suite: `165 passed`
- QQ launcher check-only: PASS
- Report: `logs/qq-relationship-approval/2026-07-02_205948/qq-relationship-approval-report.md`

Database clarification:

- Empty relationship tables were mostly reserved schema from earlier architecture work.
- `contacts`, `platform_identities`, `relationship_events`, and `relationship_claims` are now active for relationship workflows.
- `contact_permissions` remains reserved for explicit future permission toggles.

Next suggested step:

- Add real QQ/NapCat friend-request notice handling and owner-visible friend-list sync when the OneBot adapter event surface is confirmed in live QQ testing.

### 2026-07-02 Project Smoke After Expression Algorithms

Validation:

```powershell
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\run_tests_with_md_log.py" --module all
```

Result:

- QQ launcher check-only: PASS
- Markdown all-tests runner: PASS
- Generated test report: `logs/test-runs/2026-07-02_170309/all/all.test-report.md`
- QQ launcher saw `1064` sticker index items and the configured `hutao-e15.ckpt` + `hutao_e15_s1410.pth` voice weights.

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes inside test runs; tests pass.

Next suggested step:

- Continue architecture cleanup by auditing stale/generated files and aligning README test layout with the current split.

### 2026-07-02 QQ Semantic Voice Trigger v1

Implementation:

- Updated shared voice expression scoring in `app/dialogue/expression_policy.py`.
- Automatic voice sending now uses semantic expression need from companion intent, soft voice context, emotion, short input, and cooldown gap.
- Low-expression acknowledgements such as `嗯`, `好`, and `哦` are blocked from automatic voice sending.
- Technical/debug/config/training contexts remain blocked.
- `QQ_VOICE_AUTO_PROBABILITY` remains compatible but now only adjusts trigger sensitivity.
- Added focused dialogue policy tests for semantic voice trigger behavior, blocking, style selection, and sensitivity threshold bounds.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\expression_policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_dialogue_policy.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_dialogue_policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" -k "expression or sticker or auto or voice" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

Result:

- Compile check: PASS
- Focused tests: `22 passed, 20 deselected`
- Full test suite: `160 passed`
- Report: `logs/qq-expression-policy/2026-07-02_170204/semantic-voice-trigger-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested step:

- Run a QQ launcher check-only smoke, then continue with project run validation and remaining architecture cleanup.

### 2026-07-02 QQ Semantic Sticker Trigger v2

Implementation:

- Updated shared sticker expression scoring in `app/dialogue/expression_policy.py`.
- Automatic sticker sending now uses semantic expression need from intent, emotion, casual markers, short reply shape, and sticker gap.
- Low-expression acknowledgements such as `嗯`, `好`, and `哦` are blocked from automatic sticker sending.
- `QQ_STICKER_AUTO_PROBABILITY` remains compatible but now only adjusts trigger sensitivity, instead of being the main decision model.
- Added focused dialogue policy tests for semantic sticker triggers, low-expression blocking, and sensitivity threshold bounds.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\expression_policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_dialogue_policy.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_dialogue_policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" -k "expression or sticker or auto" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

Result:

- Compile check: PASS
- Focused tests: `13 passed, 27 deselected`
- Full test suite: `158 passed`
- Report: `logs/qq-expression-policy/2026-07-02_165721/semantic-sticker-trigger-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested step:

- Continue normal-chat algorithm work by applying similar semantic scoring to automatic voice trigger behavior, or run the full QQ launcher check-only smoke.

### 2026-07-02 Normal Chat Response Length Control v1

Implementation:

- Updated `ChatService._evaluation_fallback_reply()` to respect `classify_turn_taking(user_input)` before using generic fallback text.
- Low-information, explicit short-reply, and pause/stop inputs now receive short fallback text when an overlong live response fails the evaluator.
- Updated `_repair_live_response()` so live repair prompts include the turn-taking instruction and max character limit for minimized turns.
- Added focused ChatService coverage for low-information, short-reply, and pause/stop fallback replacement.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\services\chat_service.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_chat_service.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_chat_service.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_response_evaluator.py" -k "fallback or turn_taking or short_reply or low_information or overexpanded" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

Result:

- Compile check: PASS
- Focused tests: `4 passed, 28 deselected`
- Full test suite: `156 passed`
- Report: `logs/normal-chat-algorithm/2026-07-02_164943/response-length-control-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested step:

- Continue normal-chat algorithm work by improving expression/sticker trigger scoring beyond simple probability.

### 2026-07-02 Eval Scripts Test Split

Implementation:

- Added `tests/test_eval_scripts.py`.
- Moved the remaining script/evaluation tests out of `tests/test_app.py`.
- Converted `tests/test_app.py` into a non-collecting legacy placeholder to keep old references non-destructive.
- Runtime code was not changed.

Moved coverage:

- Persona gate evaluation case loading and controlled mode reports.
- Persona gate live mode with injected success/failure clients.
- Live persona stress scenario loading and failure detection.
- Long-chat metrics for anchor stuffing, short reply failures, turn-taking failures, memory revocation, and repeated question consistency.
- Persona fine-tune seed export and audit scripts.
- Persona training plan documentation checks.
- Auditory system design documentation checks.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_eval_scripts.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_eval_scripts.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "persona_gate or live_persona or live_long_chat or repeated_question or training or auditory" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

Result:

- Compile check: PASS
- Focused tests: `16 passed, 1 deselected`
- Full test suite: `155 passed`
- Report: `logs/test-split/2026-07-02_160300/eval-scripts-test-split-report.md`

Note:

- During this split, `tests/test_app.py` was accidentally deleted via patch and immediately restored as a placeholder. The final state preserves the file and keeps no deleted user-facing test coverage.

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested step:

- Start the normal-chat algorithm phase with response length control and expression trigger improvements.

### 2026-07-02 Storage Database Test Split

Implementation:

- Added `tests/test_storage_database.py`.
- Moved storage/database tests out of `tests/test_app.py`.
- Removed migrated storage/database imports and `RecordingMySQLRepository` from `tests/test_app.py`.
- Runtime code was not changed.

Moved coverage:

- Secret redaction helper.
- JSONL memory delete ownership guard.
- Database schema and migration contract checks.
- Identity relationship schema contract checks.
- Storage repository factory for JSONL/MySQL.
- MySQL config loading and validation.
- MySQL repository SQL statement generation.
- MySQL owner contact resolution.
- MySQL memory delete SQL parameters.
- asyncmy cursor parameter compatibility.
- MySQL smoke skip behavior.
- Initial schema SQL statement splitter.
- MySQL operations docs and bootstrap template safety.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_storage_database.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_storage_database.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "storage or mysql or database or schema or repository or secret_redaction" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

Result:

- Compile check: PASS
- Focused tests: `16 passed, 17 deselected`
- Full test suite: `155 passed`
- Report: `logs/test-split/2026-07-02_155358/storage-database-test-split-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested step:

- Split remaining `tests/test_app.py` into script/evaluation focused tests.
- Then begin the normal-chat algorithm phase with response length and expression trigger improvements.

### 2026-07-02 Project Run Validation

Implementation:

- Fixed `scripts/run_tests_with_md_log.py` subprocess output decoding by forcing UTF-8 with replacement for undecodable bytes.
- This allows Markdown test reports to be generated even when pytest output contains Chinese or third-party UTF-8 text.
- Runtime application code was not changed.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\run_tests_with_md_log.py" --module all
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

Result:

- Full pytest suite: `155 passed`
- Markdown test report: `logs/test-runs/2026-07-02_153528/all/all.test-report.md`
- QQ launcher check-only: PASS
- Sticker index detected: `1064 items`
- QQ voice config: enabled
- GPT weight: `external/GPT-SoVITS-v2pro-20250604/GPT_weights_v2Pro/hutao-e15.ckpt`
- SoVITS weight: `external/GPT-SoVITS-v2pro-20250604/SoVITS_weights_v2Pro/hutao_e15_s1410.pth`
- Report: `logs/project-run-validation/2026-07-02_153528/project-run-validation-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested step:

- Split remaining `tests/test_app.py` into storage/database and script/evaluation focused files.
- After that, run a controlled FastAPI process smoke if live API credentials and local ports are ready.

### 2026-07-02 Response Evaluator Test Split

Implementation:

- Added `tests/test_response_evaluator.py`.
- Moved response quality, persona anchor, modern-assistant override, death-joke misuse, catchphrase stuffing, revoked-memory repeat, and turn-taking overexpansion tests out of `tests/test_app.py`.
- Removed migrated response-evaluator imports from `tests/test_app.py`.
- Runtime code was not changed.

Moved coverage:

- Evaluation fallback keeps a Hu Tao persona anchor and actionable next step.
- Base system prompt limits canon anchor overuse in modern task/debug contexts.
- Empty, non-Chinese, customer-service, and modern-assistant style rejection.
- Short modern-context replies can pass without forced canon anchors.
- Death-topic misuse and wrong-scene death joke rejection.
- Catchphrase stuffing rejection.
- Repeating revoked memory rejection.
- Low-information and short-reply overexpansion rejection.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_response_evaluator.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_response_evaluator.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "response_evaluator or evaluation_fallback or system_prompt" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

Result:

- Compile check: PASS
- Focused tests: `16 passed, 33 deselected`
- Full test suite: `155 passed`
- Report: `logs/test-split/2026-07-02_152947/response-evaluator-test-split-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested split:

- Split remaining `tests/test_app.py` into storage/database and script/evaluation focused files.
- After the remaining test cleanup, run an application smoke path: FastAPI health/chat, then QQ stack check-only.

### 2026-07-02 Persona Memory Test Split

Implementation:

- Added `tests/test_persona_memory.py`.
- Moved persona, relationship, memory, turn-taking, and repetition policy tests out of `tests/test_app.py`.
- Kept response evaluator, storage/database, and script/evaluation tests in `tests/test_app.py` for later focused splits.
- Removed migrated persona/memory imports and helper class from `tests/test_app.py`.
- Runtime code was not changed.

Moved coverage:

- QQ owner/stranger relationship context.
- Owner-only long-term memory write and prompt injection.
- Memory correction, revocation, and revoked-memory filtering.
- Scene classification.
- Memory write policy and preference normalization.
- Persona prompt scene strategy and turn-taking limits.
- Low-quality audio input memory guard.
- Audio emotion prompt/metadata injection.
- Turn-taking classification for low-information, short-reply, and pause requests.
- Repetition policy for casual repeats and memory questions.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_persona_memory.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "persona or memory or relationship or turn_taking or repetition or audio_emotion or low_quality_audio" -q
```

Result:

- Compile check: PASS
- Focused tests: `40 passed, 30 deselected`
- Report: `logs/test-split/2026-07-02_151651/persona-memory-test-split-report.md`

Algorithm experiment landing area:

- Use `tests/test_persona_memory.py` for dialogue-act/state-machine policy, confidence-scored memory write decisions, memory revocation boundary checks, turn-taking length gates, repeated-question consistency, and emotion-aware prompt routing.

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested split:

- Split remaining `tests/test_app.py` into response-evaluator, storage/database, and script/evaluation focused files.

### 2026-07-02 Chat Service Test Split

Implementation:

- Added `tests/test_chat_service.py`.
- Moved core `ChatService` tests out of `tests/test_app.py`.
- Moved DeepSeek stream delta parsing and recent-context helper tests into `tests/test_chat_service.py`.
- Kept persona, memory, storage, MySQL, and script/evaluation tests in `tests/test_app.py` for later focused splits.
- Adjusted two remaining persona-memory tests in `tests/test_app.py` to explicitly run as QQ owner scenarios, matching the current long-term memory permission model.
- Runtime code was not changed.

Moved coverage:

- Local fallback response and fallback error secret redaction.
- Model invocation audit records for success and fallback.
- Session, message, and model invocation persistence.
- Recent-context prompt injection.
- Repeated-question prompt injection.
- Response style instruction isolation from persisted user text.
- Streaming reply persistence.
- Passing persona evaluation writes.
- AI-identity and debug-without-next-step replacement.
- DeepSeek SSE stream delta parsing.
- Recent context compaction and revoked-term filtering.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_chat_service.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_chat_service.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "chat or stream or recent_context or deepseek_stream_delta or model_audit" -q
```

Result:

- Compile check: PASS
- Focused tests: `26 passed, 59 deselected`
- Report: `logs/test-split/2026-07-02_143650/chat-service-test-split-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested split:

- Split remaining `tests/test_app.py` into persona/memory, storage/database, and script/evaluation focused files.

### 2026-07-02 API Test Split

Implementation:

- Added `tests/test_api.py`.
- Moved FastAPI route/API tests out of `tests/test_app.py`.
- Removed migrated API-only helpers and imports from `tests/test_app.py`.
- Runtime code was not changed.

Moved coverage:

- Health runtime shape.
- Memory list/delete API.
- Streaming chat API persistence.
- Audio file transcription API.
- Audio-to-chat file API transcript handoff.
- Low-quality ASR bypass behavior.
- ASR punctuation cleanup before chat.
- ASR emotion metadata pass-through.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_api.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_api.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "api or health or stream or memories or audio_chat_file or audio_transcribe_file" -q
```

Result:

- Compile check: PASS
- Focused tests: `12 passed, 81 deselected`
- Report: `logs/test-split/2026-07-02_141409/api-test-split-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

Next suggested split:

- Split remaining `tests/test_app.py` coverage into chat/persona, storage/database, persona memory, and script/evaluation test files.

### 2026-07-02 Audio Pipeline Test Split

Implementation:

- Added `tests/test_audio_pipeline.py`.
- Moved lower-level ASR/audio pipeline tests out of `tests/test_app.py`.
- Kept FastAPI audio route tests in `tests/test_app.py` for a later API split.
- Removed now-unused lower-level ASR/audio imports and fake classes from `tests/test_app.py`.
- Runtime code was not changed.

Moved coverage:

- ASR preset parsing.
- FunASR result/text cleanup helpers.
- ASR quality gate.
- Audio chat input cleanup and clarification rules.
- SenseVoice emotion extraction.
- emotion2vec parser.
- ModelScope path resolution.
- Candidate selection and repair candidate pipeline.
- Audio emotion enrichment.
- FunASR missing dependency error.
- ASR stream session and event JSON shape.
- ASR file smoke failure report.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_audio_pipeline.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_audio_pipeline.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "asr or audio or funasr or emotion2vec or modelscope" -q
```

Result:

- Compile check: PASS
- Focused tests: `27 passed, 85 deselected`
- Report: `logs/test-split/2026-07-02_134115/audio-test-split-report.md`

Next suggested split:

- Move FastAPI route/API tests into `tests/test_api.py`.

### 2026-07-02 Voice Test Split

Implementation:

- Added `tests/test_voice_chat.py`.
- Moved shared voice/TTS tests out of `tests/test_app.py` and `tests/test_qq_bot.py`.
- Kept QQ-specific voice send tests in `tests/test_qq_bot.py`.
- Removed now-unused voice/TTS imports from the old files.
- Runtime code was not changed.

Moved coverage:

- Realtime TTS text length constraint.
- TTS stage-direction/performance-cue cleanup.
- Leading punctuation cleanup after TTS normalization.
- WAV leading-artifact trim.
- Voice synthesis segment joining and final QQ-send conversion path.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_voice_chat.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_voice_chat.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" -k "voice or tts or trim_wav or synthesize" -q
```

Result:

- Compile check: PASS
- Focused tests: `13 passed, 26 deselected`
- Report: `logs/test-split/2026-07-02_132952/voice-test-split-report.md`

Next suggested split:

- Move ASR/audio pipeline tests into `tests/test_audio_pipeline.py`.

### 2026-07-02 QQ Test Split

Implementation:

- Added `tests/test_qq_bot.py`.
- Moved QQ/NapCat/sticker/voice/launcher tests out of `tests/test_app.py`.
- Removed now-unused QQ-specific imports and helper class from `tests/test_app.py`.
- Runtime code was not changed.

Moved coverage:

- QQ message policy and session/user id helpers.
- QQ recall guard.
- QQ voice reply gating, fallback, and record-part generation.
- Voice synthesis segment joining smoke.
- Sticker index rebuild and sticker selection.
- Expressive sticker/voice auto-decision compatibility adapters.
- QQ short-reply compatibility adapter.
- QQ context status helper.
- HutaoCore QQ client platform identity payload.
- NapCat helper scripts.
- QQ stack and launcher helpers.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_qq_bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "qq or sticker or voice_reply or expressive or start_qq_stack or launcher or napcat or response_style_instruction" -q
```

Result:

- Compile check: PASS
- Focused tests: `36 passed, 115 deselected`
- Report: `logs/test-split/2026-07-02_132449/qq-test-split-report.md`

Next suggested split:

- Move voice/TTS naturalness and synthesis tests into `tests/test_voice_chat.py`.

### 2026-07-02 Dialogue Test Split

Implementation:

- Added `tests/test_dialogue_policy.py`.
- Moved shared dialogue policy tests out of the oversized `tests/test_app.py`.
- Removed now-unused `app.dialogue` imports from `tests/test_app.py`.
- Kept QQ compatibility tests in `tests/test_app.py` for this phase.
- Runtime code was not changed.

Moved tests:

- `test_dialogue_policy_classifies_short_chat_and_task_context`
- `test_dialogue_policy_constrains_only_chatty_replies`
- `test_core_expression_policy_scores_sticker_intent_and_blocks_technical_context`
- `test_core_expression_policy_voice_defaults_to_disabled`

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_dialogue_policy.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_dialogue_policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "dialogue_policy or core_expression_policy or expressive or qq_reply_style or sticker or voice_reply or qq_message_policy or qq_core_client or chat_prompt or response_style_instruction" -q
```

Result:

- Compile check: PASS
- Focused tests: `27 passed, 128 deselected`
- Report: `logs/test-split/2026-07-02_131645/dialogue-test-split-report.md`

Next suggested split:

- Move QQ bridge tests into `tests/test_qq_bot.py`.

### 2026-07-02 Dialogue Policy Phase 1

Implementation:

- Added `app/dialogue/` as the shared dialogue policy layer.
- Added dialogue primitives in `app/dialogue/types.py`.
- Added turn classification in `app/dialogue/act_classifier.py`.
- Added response-mode and length policy in `app/dialogue/policy.py`.
- Added sticker/voice expression scoring in `app/dialogue/expression_policy.py`.
- Updated `integrations/qq_bot/reply_style.py` to delegate QQ short-reply behavior to `app/dialogue`.
- Updated `integrations/qq_bot/expressive_reply.py` to be a QQ compatibility adapter over generic expression settings/state.
- Added focused tests in `tests/test_app.py`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\__init__.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\types.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\act_classifier.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\dialogue\expression_policy.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\reply_style.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\expressive_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "dialogue_policy or core_expression_policy or expressive or qq_reply_style or sticker or voice_reply or qq_message_policy or qq_core_client or chat_prompt or response_style_instruction" -q
```

Result:

- Compile check: PASS
- Focused tests: `27 passed, 128 deselected`
- Report: `logs/dialogue-policy/2026-07-02_130446/dialogue-policy-report.md`

Warning:

- `.pytest_cache` still reports Windows access-denied warnings during pytest cache writes; tests pass.

### 2026-07-02 Architecture Governance And Normal Chat Optimization

User request:

- Continue normal-chat optimization with references to papers, datasets, open projects, and algorithms.
- List redundant or messy files in this project before cleanup.
- Redesign the internal architecture inside the existing `HutaoChatCore` project without creating a new project folder.
- Provide architecture diagrams for review.

This step is documentation-only. No runtime code was moved, deleted, or refactored.

Created documents:

- `docs/architecture/chat-optimization-research.md`
  - References DailyDialog, EmpatheticDialogues, PersonaChat, Meena/SSA, and state-driven dialogue ideas from Rasa, Botpress, Bot Framework, and LangGraph.
  - Proposes a Dialogue Engine for dialogue act, emotion, response mode, expression decision, and quality gates.
- `docs/architecture/redundant-files-audit.md`
  - Lists cleanup/reorganization candidates such as `__pycache__`, `.pytest_cache`, `build/qq_launcher`, `data/hutao_voice/tests`, mixed `scripts/`, and oversized `tests/test_app.py`.
  - Treats `external/GPT-SoVITS-v2pro-20250604` as a third-party dependency, not project business code.
- `docs/architecture/architecture-redesign-proposal.md`
  - Provides current architecture, proposed architecture, Dialogue Engine diagrams, and a staged migration plan.
  - Recommends phase 1 as adding `app/dialogue/` before splitting tests, migrating expression logic, reorganizing scripts, or moving artifacts.

Record:

- `logs/architecture-redesign/2026-07-02_123727/architecture-redesign-report.md`

Important:

- This is not an approved implementation yet.
- Ask the user to confirm phase 1 before changing runtime architecture.

Current root:

```text
D:\Programming-file\Graduation-Project\HutaoChatCore
```

This is the current main project. Older folders such as `HutaoPersonaLab`,
`NexusMind`, and `VirtualGirlfriendV2` are references only unless the user
explicitly asks to work in them.

## User Intent

The user wants a Hu Tao chat backend that can grow into a voice-capable
assistant. Development should proceed by small tested modules, not large
unverified rewrites.

Important user expectations:

- Chinese communication.
- Real API/model tests matter. Do not call mock results complete.
- Every usable module should have a Markdown PASS report under `logs/`.
- Do not print or store secrets.
- DeepSeek API is the main LLM path.
- Local models are acceptable for ASR/TTS/vision.
- Fallback replies are not successful live replies.
- The user prefers steady autonomous progress and dislikes stopping after every
  tiny step.
- Mass deletion is forbidden.

## Current Architecture

Main backend:

- FastAPI app entrypoint: `app/main.py`
- Shared request/response schemas: `app/schemas.py`
- Config loader: `app/core/config.py`
- Secret redaction: `app/core/security.py`

Service layer:

- Chat orchestration: `app/services/chat_service.py`
- DeepSeek client: `app/services/model_client.py`
- Model audit logging: `app/services/model_audit.py`
- Local persona response evaluator: `app/services/response_evaluator.py`

Persona layer:

- Prompt builder: `app/persona/persona_prompt_builder.py`
- Scene classifier: `app/persona/scene_classifier.py`
- Turn-taking/short-reply policy: `app/persona/turn_taking.py`
- Repetition policy: `app/persona/repetition_policy.py`
- Memory write/read policy: `app/persona/memory_policy.py`
- Memory service: `app/persona/memory_service.py`
- Imported/curated Hu Tao rules: `app/persona/hutao_rules.py`

Storage layer:

- Repository protocol and JSONL implementation: `app/storage/chat_repository.py`
- MySQL implementation: `app/storage/mysql_repository.py`
- Storage factory: `app/storage/repository_factory.py`
- MySQL schema: `migrations/001_initial_schema.sql`

Audio/ASR layer:

- ASR protocol/session wrappers: `app/audio/asr_engine.py`, `app/audio/stream_session.py`
- FunASR file engine: `app/audio/funasr_engine.py`
- ASR quality gate: `app/audio/quality.py`
- ASR candidate/repair pipeline: `app/audio/pipeline.py`
- File upload/transcribe service: `app/audio/file_service.py`
- Audio schemas: `app/audio/schemas.py`
- WebSocket route shell: `app/audio/websocket_routes.py`

## Current API Surface

Implemented:

- `GET /health`
- `POST /api/v1/chat`
- `POST /api/v1/chat/stream`
- `GET /api/v1/memories`
- `DELETE /api/v1/memories/{memory_id}`
- `POST /api/v1/audio/transcribe/file`
- `POST /api/v1/audio/chat/file`

Partially implemented / not production-complete:

- `WS /api/v1/audio/transcribe/stream`
  - Protocol/session shell exists.
  - Real microphone-grade streaming ASR is not complete yet.

Not implemented yet:

- TTS voice output.
- Frontend UI.
- Vision.
- User account/auth system.
- Production deployment packaging.

TTS preparation started:

- GPT-SoVITS official project is downloaded under `external/GPT-SoVITS`.
- Hu Tao voice dataset workspace exists under `data/hutao_voice/`.
- Training data must be owned, licensed, or original. Do not scrape or train on
  official Hu Tao / voice actor audio unless the user provides usable rights.
- Current voice dataset audit script:
  `scripts/prepare_gpt_sovits_voice_dataset.py`.
- Current dataset template:
  `data/hutao_voice/annotations/segments.jsonl`.

## Current Feature Status

### Chat / Hu Tao Brain

`ChatService.reply()` and `ChatService.stream_reply()` are the main paths.

Implemented:

- Real DeepSeek API call.
- Local fallback on error.
- Fallback is recorded as fallback and must not be counted as a successful live
  result.
- JSONL/MySQL message persistence.
- Model invocation records.
- Persona evaluation records.
- Recent context injection from the last 8 messages.
- Memory read/write for explicit preferences, aliases, corrections, and
  revocations.
- Repetition handling so repeated casual questions should vary, while repeated
  memory/fact questions keep the same core answer.
- Input source metadata, including audio input and ASR quality status.

Persona behavior:

- Scene-aware prompt policy covers daily chat, emotional support, debug/task
  frustration, affection, life/death topics, memory correction, memory revoke,
  and identity challenges.
- Default style is short, natural Chinese.
- Avoids customer-service style, generic AI self-disclosure, excessive comfort,
  and long talkative replies.
- Response evaluator rejects major failures such as AI identity self-disclosure,
  overlong replies, low Chinese ratio, and repeating revoked memory.

Known limitations:

- Long-term memory is still rule-based, not semantic/vector retrieval.
- Persona still needs more long real-chat stress testing.
- The evaluator is local-rule based, not a learned judge.

### Storage / Database

Implemented:

- JSONL storage backend by default.
- MySQL backend and schema.
- Sessions, messages, model invocations, persona evaluations, and memories.
- Memory list and delete APIs.
- Secret redaction in stored errors/audit logs.
- Model invocation metadata can record audio source and ASR quality status.

Known limitations:

- No Alembic-style migration tool yet.
- No vector memory index yet.
- JSONL is development-friendly but not a production database.

### Audio / ASR

This module is now real, not a placeholder.

Implemented:

- Local FunASR file transcription.
- Main model preset: `sensevoice-small` (`iic/SenseVoiceSmall`).
- Repair model preset: `fun-asr-nano` (`FunAudioLLM/Fun-ASR-Nano-2512`).
- ASR quality gate checks:
  - empty transcript
  - too short
  - low Chinese ratio
  - mojibake/replacement characters
  - excessive repetition
  - punctuation-only
  - punctuation collision such as `。，`
- Candidate pipeline:
  - Records each ASR candidate text, latency, quality score, reasons, and error.
  - Selects the best candidate.
- Repair pipeline:
  - Run fast primary ASR first.
  - If quality passes, do not run slow repair model.
  - If quality fails and repair candidates are configured, run repair model and
    select the best candidate.
- Audio-to-chat file flow:
  - Download/upload audio.
  - Transcribe locally.
  - Apply ASR quality gate and optional repair.
  - Run `emotion2vec_plus_large` speech emotion recognition when enabled.
  - Pass final transcript to Hu Tao via real DeepSeek.
  - Pass audio emotion metadata to Hu Tao as a weak tone signal.
  - Persist chat/audit records.

Important real result:

- On `openspeech-mandarin-0072-8k`, `sensevoice-small` produced punctuation
  collision and recognized `邮箱` as `油箱`.
- Quality gate triggered `fun-asr-nano`.
- `fun-asr-nano` produced the better final transcript with `邮箱`.
- That corrected transcript was sent to Hu Tao and passed the real DeepSeek
  audio-to-chat smoke test.

Known limitations:

- `fun-asr-nano` is slower and should not be enabled as an always-on second
  candidate by default.
- Real-time microphone streaming is not complete.
- `ffmpeg` is not installed; current environment uses `torchaudio` loading.

## Important Configuration

Effective configuration priority:

1. Process environment variables.
2. `HutaoChatCore/.env`.
3. `../HutaoPersonaLab/.env`.

Required `.env.example` shape:

```env
ENVIRONMENT=local
STORAGE_BACKEND=jsonl
MODEL_PROVIDER=deepseek
MODEL_NAME=deepseek-v4-pro
MODEL_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=
API_TEMPERATURE=0.8
API_TIMEOUT_SECONDS=90
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=
MYSQL_USER=
MYSQL_PASSWORD=
ASR_FILE_PRESETS=sensevoice-small
ASR_REPAIR_PRESETS=
AUDIO_EMOTION_ENABLED=true
AUDIO_EMOTION_MODEL=iic/emotion2vec_plus_large
```

ASR notes:

- Default: `ASR_FILE_PRESETS=sensevoice-small`
- Best-effect repair mode: set `ASR_REPAIR_PRESETS=fun-asr-nano`
- Do not default to always running both models; it is too slow.

Local model storage:

- Models are stored inside this project under `data/models/modelscope/`.
- Do not rely on `C:\Users\Administrator\.cache\modelscope\hub\models` for
  normal project operation.
- Current project-local model folders:
  - `data/models/modelscope/iic/SenseVoiceSmall`
  - `data/models/modelscope/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch`
  - `data/models/modelscope/iic/punc_ct-transformer_cn-en-common-vocab471067-large`
  - `data/models/modelscope/iic/emotion2vec_plus_large`
  - `data/models/modelscope/FunAudioLLM/Fun-ASR-Nano-2512`
- `app/audio/model_paths.py` maps ModelScope model ids such as
  `iic/emotion2vec_plus_large` to these project-local paths when present.

## Key Scripts

Testing:

- `scripts/run_tests_with_md_log.py`
- `scripts/api_smoke.py`
- `scripts/mysql_smoke.py`
- `scripts/persona_gate_eval.py`
- `scripts/live_persona_stress.py`
- `scripts/live_long_chat_stress.py`
- `scripts/live_memory_smoke.py`
- `scripts/live_stream_smoke.py`

Audio/ASR:

- `scripts/download_asr_samples.py`
- `scripts/build_asr_stress_samples.py`
- `scripts/asr_file_smoke.py`
- `scripts/asr_batch_stress.py`
- `scripts/asr_model_compare.py`
- `scripts/asr_isolated_probe_worker.py`
- `scripts/asr_isolated_model_compare.py`
- `scripts/audio_api_smoke.py`
- `scripts/audio_brain_smoke.py`
- `scripts/audio_chat_api_smoke.py`
- `scripts/audio_online_random_hutao_smoke.py`

Persona training/data:

- `scripts/export_persona_finetune_dataset.py`
- `scripts/audit_persona_finetune_dataset.py`

## Required Commands

Install dependencies:

```powershell
cd D:\Programming-file\Graduation-Project\HutaoChatCore
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe -m pip install -r requirements.txt
```

Run server:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

Run all tests with Markdown report:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\run_tests_with_md_log.py --module all
```

Run live API smoke:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\api_smoke.py
```

Run MySQL smoke:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\mysql_smoke.py
```

Run real audio-to-Hu Tao smoke:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\audio_online_random_hutao_smoke.py --sample-count 1
```

Run best-effect ASR repair smoke on the known useful sample:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\audio_online_random_hutao_smoke.py --sample-id openspeech-mandarin-0072-8k --sample-count 1 --repair-preset fun-asr-nano
```

Run isolated ASR model comparison:

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\asr_isolated_model_compare.py --preset sensevoice-small --preset fun-asr-nano --limit 2 --timeout-seconds 120
```

## Latest Verified Reports

Most recent full test:

- `logs/test-runs/2026-06-29_120045/all/all.test-report.md`
- Result: PASS.

Most recent API/module test after ASR emotion update:

- `logs/test-runs/2026-06-29_171025/api/api.test-report.md`
- Result: PASS.
- Covered structured ASR emotion extraction, ASR candidate emotion propagation,
  audio-chat emotion handoff to `ChatService`, and prompt/audit metadata
  injection.

Most recent real speech emotion model smoke:

- `logs/audio-emotion2vec-smoke/2026-06-29_170950/audio-emotion2vec-smoke-report.md`
- Result: PASS.
- Model: `iic/emotion2vec_plus_large`.
- Known emotion samples: 5.
- Matched samples: 5.
- Loaded from project-local model path under `data/models/modelscope`.

Most recent real audio-to-Hu Tao best-effect repair smoke:

- `logs/audio-online-random-hutao/2026-06-29_115846/audio-online-random-hutao-report.md`
- Result: PASS.
- Repair was triggered.
- Selected ASR candidate: `fun-asr-nano`.
- `used_live_api=True`, `fallback_used=False`.

Useful prior ASR model comparison:

- `logs/asr-isolated-model-compare/2026-06-28_235003/asr-isolated-model-compare-report.md`
- Result: WARN because one candidate was intentionally marked low quality.
- Demonstrated that `fun-asr-nano` can outperform `sensevoice-small` on a
  punctuation/word-choice failure case.

## Current Best Real Audio Example

Input sample:

- `openspeech-mandarin-0072-8k`

SenseVoice candidate issue:

- Had punctuation collision.
- Used `油箱` where `邮箱` was better.

Final repaired transcript:

```text
院子门口不远处就是一个地铁站，这是一个美丽而神奇的景象。树上长满了又大又甜的桃子，海豚和金鱼的表演是很好看的节目。邮局门前的人行道上有一个蓝色的邮箱。
```

Real Hu Tao reply:

```text
你这描述东一榔头西一棒槌，怕不是在测我脑子转不转得过弯？行吧，邮筒、海豚和桃树凑一块，也算稀奇。
```

## Development Rules

- Keep backend runnable.
- Preserve existing API contracts unless there is a good reason and tests are
  updated.
- Use `apply_patch` for manual edits.
- Do not print `.env` values or API keys.
- Never treat fallback as live success.
- Do not delete user work or old logs without explicit permission.
- Prefer focused tests and Markdown reports.
- If a real feature uses a live API or local model, run a real smoke test before
  calling it usable.

## Current Gaps / Suggested Next Development

Highest-value next feature:

1. TTS voice output so Hu Tao can speak replies.

Alternative if continuing hearing system:

1. Real microphone WebSocket ASR.
2. Stream final ASR text into `ChatService.stream_reply`.
3. Add a voice-chat endpoint such as `WS /api/v1/voice/chat/stream`.

Database/memory improvements:

1. Add Alembic-style migration management.
2. Add semantic/vector memory retrieval after current rule-based memory remains
   stable.

Frontend:

1. Wait until TTS/voice API contract is stable unless the user explicitly wants
   UI now.

## Documentation Note

`README.md` still contains older language saying ASR/TTS/vision are not yet
implemented. That is no longer accurate for ASR. Update README before presenting
the project externally.

## Development Log

### 2026-06-29 ASR emotion recognition

Implemented:

- Preserved SenseVoice emotion tags such as `<|NEUTRAL|>` before ASR text
  cleanup.
- Added structured ASR transcription output with `emotion`, `emotion_source`,
  and `emotion_confidence`.
- Added these fields to `AsrCandidateResponse` and `AsrFileResponse`.
- Propagated selected candidate emotion through the ASR candidate pipeline.
- Passed file ASR emotion into `/api/v1/audio/chat/file` -> `ChatService`.
- Added audio emotion metadata to model invocation request metadata.
- Injected audio emotion into persona prompt as a weak tone signal only; text
  content remains authoritative.

No extra emotion model was added yet:

- Current implementation uses SenseVoice tags already emitted by the existing
  `sensevoice-small` ASR preset.
- Add a separate speech emotion recognition model only if real samples show
  SenseVoice tags are too coarse or unstable.

Tests:

- Focused pytest command:
  `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe -m pytest tests\test_app.py -k "emotion or funasr_extract or asr_pipeline_preserves or audio_chat_file_api_passes_asr"`
- Focused result: PASS, 6 passed.
- Markdown API test report:
  `logs/test-runs/2026-06-29_160541/api/api.test-report.md`
- Markdown API result: PASS.

Real local model effect check:

- Command used `transcribe_audio_file` on
  `data/asr_samples/funasr-zh-example-001.wav`.
- Selected ASR candidate: `sensevoice-small`.
- `quality_passed=True`.
- Detected `emotion=neutral`.
- Detected `emotion_source=sensevoice_tag`.
- `emotion_confidence=None` because SenseVoice tag output did not include a
  numeric confidence.

### 2026-06-29 ASR emotion web sample effect test

Reports:

- `logs/asr-emotion-web-samples/2026-06-29_161132/asr-emotion-web-samples-report.md`
- `logs/asr-emotion-web-samples/2026-06-29_161455/asr-emotion-ravdess-cdn-report.md`

Result summary:

- Existing Chinese public samples returned `emotion=neutral` from
  `sensevoice_tag`.
- RAVDESS neutral sample returned `emotion=neutral`.
- RAVDESS happy/sad/angry/fearful samples did not return matching emotion
  tags with the current `sensevoice-small` file ASR path.
- Conclusion: current SenseVoice tag extraction is usable for coarse neutral
  detection, but not enough for reliable multi-emotion recognition. Add a
  dedicated speech emotion recognition model before relying on happy/sad/angry
  user-tone handling.

### 2026-06-29 emotion2vec+ deployment

Implemented:

- Added dedicated speech emotion recognition engine:
  `app/audio/emotion_engine.py`.
- Deployed ModelScope/FunASR model: `iic/emotion2vec_plus_large`.
- Moved ModelScope models into project-local storage under
  `data/models/modelscope/`.
- Added settings:
  - `AUDIO_EMOTION_ENABLED=true`
  - `AUDIO_EMOTION_MODEL=iic/emotion2vec_plus_large`
- `transcribe_audio_file` now enriches ASR responses with emotion2vec output
  when enabled.
- emotion2vec result overrides the coarse SenseVoice emotion tag because it is
  a dedicated speech emotion recognition model.
- Added real smoke script:
  `scripts/audio_emotion2vec_smoke.py`.

Real smoke test:

- Report: `logs/audio-emotion2vec-smoke/2026-06-29_170950/audio-emotion2vec-smoke-report.md`
- Result: PASS.
- Known emotion samples: 5.
- Matched samples: 5.
- Confirmed the model loaded from
  `data/models/modelscope/iic/emotion2vec_plus_large/model.pt`.
- Tested emotions:
  - neutral -> neutral
  - happy -> happy
  - sad -> sad
  - angry -> angry
  - fearful -> fearful
- Chinese public sample also returned a valid emotion label, but it is not a
  labeled emotion benchmark sample, so it is not counted as an accuracy hit.

Module test:

- Report: `logs/test-runs/2026-06-29_171025/api/api.test-report.md`
- Result: PASS.

### Future plan: richer real-user emotion understanding

Current status:

- `emotion2vec_plus_large` gives useful discrete speech emotion labels such as
  neutral, happy, sad, angry, fearful, disgusted, surprised, and other.
- This is enough for a first voice-chat demo, but it is not a complete model of
  real user emotion.

Problem:

- Real chat emotions are mixed and subtle: tired, frustrated, anxious,
  reluctant, joking, pretending to be fine, low-energy, restrained anger,
  sadness mixed with affection, etc.
- A single top-1 label such as `angry` or `happy` can lose important nuance.
- Speech emotion should not override text content or conversation context.

Recommended next design:

- Keep the top-N emotion labels and scores from `emotion2vec`, not only the
  highest label.
- Add a continuous VAD-style representation:
  - valence: positive vs negative
  - arousal: calm vs activated
  - dominance: in-control vs helpless
- Add derived fields such as `intensity`, `mixed_emotions`, and
  `emotion_stability`.
- Fuse three sources:
  1. audio emotion from `emotion2vec`
  2. text emotion from the ASR transcript
  3. recent dialogue context and persona scene classification
- Treat audio emotion as a weak tone signal unless confidence is high and the
  text/context agrees.

Suggested future module:

- `app/audio/emotion_fusion.py`

Suggested output shape:

```json
{
  "primary_emotion": "angry",
  "primary_emotion_zh": "生气",
  "secondary_emotions": [
    {"emotion": "sad", "score": 0.21}
  ],
  "valence": -0.72,
  "arousal": 0.84,
  "dominance": 0.66,
  "intensity": 0.84,
  "confidence": 0.91,
  "source": "emotion2vec+text+context"
}
```

Useful datasets / research directions:

- ESD: Chinese/English emotional speech dataset.
- CASIA: commonly used Chinese emotional speech dataset.
- CNSCED: Chinese natural speech complex emotion dataset.
- M3ED / EmotionTalk: Chinese multimodal dialogue emotion datasets.
- MSP-Podcast: natural speech emotion data, useful for realistic emotion
  distribution.

Acceptance target:

- Do not only report `happy/sad/angry/neutral`.
- For real voice chat, output both discrete emotion and continuous intensity /
  VAD-style values.
- Hu Tao should adapt reply tone from this fused state, while keeping user text
  content authoritative.

### 2026-06-29 GPT-SoVITS TTS preparation

Implemented:

- Downloaded GPT-SoVITS official project to `external/GPT-SoVITS`.
- Created Hu Tao voice dataset workspace:
  - `data/hutao_voice/raw`
  - `data/hutao_voice/normalized`
  - `data/hutao_voice/annotations`
  - `data/hutao_voice/manifests`
  - `data/hutao_voice/references`
  - `data/hutao_voice/outputs`
  - `data/hutao_voice/reports`
- Added annotation template:
  `data/hutao_voice/annotations/segments.jsonl`.
- Added emotion label map:
  `data/hutao_voice/annotations/emotion_labels.json`.
- Added GPT-SoVITS dataset audit/export script:
  `scripts/prepare_gpt_sovits_voice_dataset.py`.

Current audit:

- Report:
  `data/hutao_voice/reports/2026-06-29_172848/hutao-voice-dataset-audit-report.md`
- Trainable segments: 0.
- Reason: only placeholder annotation exists; no owned/licensed/original voice
  samples have been provided yet.

Training data rule:

- Do not scrape or train on official Hu Tao or voice actor audio unless the user
  provides clear rights to use it.
- Allowed data sources:
  - user-owned recordings
  - licensed voice dataset
  - original commissioned / self-recorded Hu Tao-style voice
  - explicitly authorized reference audio

GPT-SoVITS notes:

- Official project supports zero-shot TTS from a short reference voice sample
  and few-shot fine-tuning from small voice datasets.
- GPT-SoVITS training list format:
  `audio_path|speaker|language|text`.
- The local script exports this format to
  `data/hutao_voice/manifests/<timestamp>/hutao_voice_gpt_sovits.list`.

Next implementation steps after authorized audio is available:

1. Put raw audio under `data/hutao_voice/raw`.
2. Slice/normalize audio into `data/hutao_voice/normalized`.
3. Fill `segments.jsonl` with text, emotion, intensity, quality, and license.
4. Run `scripts/prepare_gpt_sovits_voice_dataset.py`.
5. Train or few-shot fine-tune in `external/GPT-SoVITS`.
6. Add backend TTS adapter and smoke test real generated audio.

### 2026-06-29 Hu Tao voice auto-label pass

User-provided audio status:

- Raw voice files were found under `data/hutao_voice/raw`.
- Detected audio files: 356 `.wav` files.
- These files are unlabelled source files supplied by the user. The project
  still records their license as `user_provided_unverified` until the user
  explicitly confirms they are owned, licensed, original, or otherwise usable
  for model training.

Auto-label run:

- Command:
  `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\auto_label_hutao_voice.py --write-segments`
- Report:
  `data/hutao_voice/reports/2026-06-29_174032/hutao-voice-auto-label-report.md`
- Result: 356 labelled, 0 failed.
- Updated annotation file:
  `data/hutao_voice/annotations/segments.jsonl`
- Backup file was generated automatically before replacing `segments.jsonl`.

Auto-label summary:

- Quality distribution:
  - `draft`: 259
  - `needs_review`: 97
- TTS emotion distribution:
  - `playful`: 263
  - `serious`: 65
  - `neutral`: 23
  - `comforting`: 5
- Raw speech emotion distribution:
  - `surprised`: 178
  - `happy`: 85
  - `angry`: 64
  - `neutral`: 18
  - `sad`: 5
  - `other`: 5
  - `disgusted`: 1

Sample recognized lines:

- `hutao_raw_0001`: `哎呀呀，海灯节快乐呀。` -> `playful`
- `hutao_raw_0002`: `啊，别大惊小怪，他们不是鬼，只是普通的客人。` -> `playful`
- `hutao_raw_0005`: `那么你想聊些什么？` -> `playful`
- `hutao_raw_0010`: `太阳出来，我晒太阳，月亮出来，我晒月亮了。` -> `playful`

Dataset audit after auto-label:

- Command:
  `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\prepare_gpt_sovits_voice_dataset.py`
- Report:
  `data/hutao_voice/reports/2026-06-29_174411/hutao-voice-dataset-audit-report.md`
- GPT-SoVITS list:
  `data/hutao_voice/manifests/2026-06-29_174411/hutao_voice_gpt_sovits.list`
- Trainable segments: 0 / 356.
- Blocking reasons:
  - `not_trainable_license`: 356
  - `quality_not_pass`: 356

Training gate:

- Auto-label is only a draft and must not be treated as final training data.
- Before GPT-SoVITS training, each usable row in `segments.jsonl` must be
  manually checked:
  - correct `text`
  - correct `emotion`
  - `quality` changed to `pass`
  - `license_status` changed to `owned`, `licensed`, or `original`
- Rows with punctuation problems, wrong ASR text, wrong emotion, noisy audio,
  or unclear rights should stay out of the training list.

Recommended next implementation:

1. Add a review helper that exports `segments.jsonl` to a human-editable CSV or
   Markdown review table.
2. Add an approval script that only promotes reviewed rows to `quality=pass`
   after explicit human correction.
3. Re-run `scripts/prepare_gpt_sovits_voice_dataset.py` to generate a non-empty
   GPT-SoVITS `.list`.
4. Set up the separate GPT-SoVITS runtime and run a small training or few-shot
   synthesis smoke test before any long training job.

Verification after log update:

- Dataset audit re-run:
  `data/hutao_voice/reports/2026-06-29_174633/hutao-voice-dataset-audit-report.md`
- Audit result: PASS as a gate check, with 0 / 356 trainable segments because
  all rows are still draft/unverified.
- API test re-run:
  `logs/test-runs/2026-06-29_174633/api/api.test-report.md`
- API test result: PASS.

### 2026-06-29 GPT-SoVITS training preparation update

User direction:

- The project is for personal, non-commercial use.
- Training audit now allows `personal_use_noncommercial` as a trainable
  dataset status.

Implemented:

- Updated `scripts/prepare_gpt_sovits_voice_dataset.py` to accept
  `personal_use_noncommercial`.
- Updated `scripts/approve_hutao_voice_segments.py` to accept
  `personal_use_noncommercial`.
- Approved all 356 reviewed rows in
  `data/hutao_voice/annotations/segments.jsonl`.
- Backup created before approval:
  `data/hutao_voice/annotations/segments.backup.2026-06-29_182610.jsonl`
- Added command-line GPT-SoVITS training orchestrator:
  `scripts/run_hutao_gpt_sovits_training.py`

Dataset status:

- Audit report:
  `data/hutao_voice/reports/2026-06-29_182628/hutao-voice-dataset-audit-report.md`
- GPT-SoVITS manifest:
  `data/hutao_voice/manifests/2026-06-29_182628/hutao_voice_gpt_sovits.list`
- Trainable segments: 356 / 356.
- Total raw audio duration: 1976.12 seconds, about 32.94 minutes.
- Raw audio format: 48 kHz, mono, 16-bit WAV.

GPT-SoVITS environment:

- Created conda environment `GPTSoVits` with Python 3.10.
- GPT-SoVITS official pretrained models downloaded under:
  `external/GPT-SoVITS/GPT_SoVITS/pretrained_models`
- G2PW model downloaded under:
  `external/GPT-SoVITS/GPT_SoVITS/text/G2PWModel`
- Official install script reached the PyTorch CUDA installation step and then
  stalled on the large wheel download.
- Current workaround: downloading the CUDA torch wheel with resumable curl to:
  `data/models/downloads/torch-2.12.1+cu126-cp310-cp310-win_amd64.whl`

Training plan once environment finishes:

- Use GPT-SoVITS v2 pretrained base.
- Run preprocessing:
  - `1-get-text.py`
  - `2-get-hubert-wav32k.py`
  - `3-get-semantic.py`
- Train with RTX 4070 Laptop 8 GB friendly high settings:
  - S1 batch size: 4
  - S1 epochs: 30
  - S2 batch size: 4
  - S2 epochs: 30
  - fp16 enabled
  - gradient checkpointing enabled for S2
- After training, run `api_v2.py` from GPT-SoVITS with the trained GPT and
  SoVITS weights; the Hu Tao backend should call that API instead of trying to
  load GPT-SoVITS weights directly.

### 2026-06-29 GPT-SoVITS official install interrupted

User direction:

- Stop working on the current official GPT-SoVITS install because the user will
  provide a modified third-party GPT-SoVITS build.

Actual state:

- No Hu Tao GPT-SoVITS training has started yet.
- The official GPT-SoVITS runtime under `external/GPT-SoVITS` should not be
  treated as a verified trainable environment.
- The `GPTSoVits` conda environment is partially installed:
  - `torch 2.12.1+cu126` installed from the project-local wheel at
    `data/models/downloads/torch-2.12.1+cu126-cp310-cp310-win_amd64.whl`
  - `torchcodec 0.14.0+cu126` installed
  - `opencc 1.1.9` installed as a Windows wheel workaround
  - many GPT-SoVITS dependencies were installed before interruption, but the
    official requirements install was not allowed to finish cleanly
- A process check after interruption found no active GPT-SoVITS training or pip
  install process.

Next action:

- When the modified GPT-SoVITS build is placed in the project, inspect its own
  README/scripts first.
- Do not assume the existing `scripts/run_hutao_gpt_sovits_training.py` matches
  the modified build.
- Re-identify the correct preprocessing, training, inference/API entrypoints,
  then run a small environment/import check before launching Hu Tao training.

### 2026-06-29 GPT-SoVITS v2Pro modified build training test

Modified build:

- User-provided project folder:
  `external/GPT-SoVITS-v2pro-20250604`
- This build includes its own portable runtime:
  `external/GPT-SoVITS-v2pro-20250604/runtime/python.exe`
- Runtime check:
  - Python: 3.9.13
  - Torch: 2.0.0+cu118
  - CUDA available: true
  - GPU: NVIDIA GeForce RTX 4070 Laptop GPU

Environment fix:

- The portable runtime had stale `runtime/Lib/site-packages/users.pth` entries
  pointing to the original BaiduNetdisk extraction path.
- `scripts/run_hutao_gpt_sovits_training.py` now rewrites `users.pth` to the
  project-local modified build paths before running GPT-SoVITS commands.
- The same script now defaults to:
  - GPT-SoVITS root: `external/GPT-SoVITS-v2pro-20250604`
  - Python: modified build portable runtime
  - model version: `v2Pro`
  - S1 batch size: 2
  - S2 batch size: 2

Preprocessing result:

- Command:
  `external\GPT-SoVITS-v2pro-20250604\runtime\python.exe scripts\run_hutao_gpt_sovits_training.py --stage preprocess --version v2Pro --exp-name hutao_personal_v2pro`
- Result: PASS.
- Outputs under:
  `external/GPT-SoVITS-v2pro-20250604/logs/hutao_personal_v2pro`
- Generated files:
  - `train.list`
  - `2-name2text.txt`
  - `6-name2semantic.tsv`
  - `3-bert/*.pt`: 356 files
  - `4-cnhubert/*.pt`: 356 files
  - `5-wav32k/*.wav`: 356 files
- `6-name2semantic.tsv` has 357 lines because it includes the required header
  plus 356 samples.
- v2Pro semantic extraction loaded
  `GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth` and completed with exit
  code 0. It printed unexpected speaker-embedding keys
  (`sv_emb.*`, `ge_to512.*`, `prelu.weight`), but this did not block semantic
  extraction.

S1 training memory test:

- First S1 attempt used batch size 4.
- It started successfully, resumed from no checkpoint, and saved:
  - `GPT_weights_v2Pro/hutao_personal_v2pro-e1.ckpt`
  - `GPT_weights_v2Pro/hutao_personal_v2pro-e2.ckpt`
- Observed GPU memory with batch size 4:
  - about 7778 MiB / 8188 MiB
- Batch size 4 is too close to the 8 GB VRAM limit for stable long training.
- User requested not to max out VRAM, so this run was manually stopped during
  epoch 3. Stale DataLoader worker processes were cleaned up.

S1 safer batch test:

- Command:
  `external\GPT-SoVITS-v2pro-20250604\runtime\python.exe scripts\run_hutao_gpt_sovits_training.py --stage s1 --version v2Pro --exp-name hutao_personal_v2pro --s1-batch-size 2 --s1-epochs 3`
- Result: PASS.
- The run resumed from:
  `logs/hutao_personal_v2pro/logs_s1_v2Pro/ckpt/epoch=1-step=42.ckpt`
- Dataset after GPT-SoVITS filtering:
  - semantic rows: 356
  - phoneme rows: 356
  - filtered by phoneme/sec rule: 6
  - actual S1 training rows: 350
- Observed GPU memory with batch size 2:
  - about 6946 MiB / 8188 MiB
- Batch size 2 is the recommended S1 setting on this RTX 4070 Laptop 8 GB
  system.
- Saved current S1 weight:
  `GPT_weights_v2Pro/hutao_personal_v2pro-e3.ckpt`
- Latest S1 checkpoint:
  `logs/hutao_personal_v2pro/logs_s1_v2Pro/ckpt/epoch=2-step=85.ckpt`

Next action:

- Continue S1 training from the latest checkpoint with batch size 2 and a
  target of 30 epochs if the user wants a longer run.
- After S1 completes, run S2 with batch size 2 first, measure VRAM, then decide
  whether it is safe to continue or reduce further.
- Do not use batch size 4 for long S1 training on this machine unless the user
  explicitly accepts near-full VRAM usage.

### 2026-06-29 胡桃 GPT-SoVITS v2Pro balanced 训练完成与合成测试

训练环境：

- GPT-SoVITS 魔改版目录：
  `external/GPT-SoVITS-v2pro-20250604`
- 便携 Python：
  `external/GPT-SoVITS-v2pro-20250604/runtime/python.exe`
- 训练版本：`v2Pro`
- 实验名：`hutao_personal_v2pro_balanced`
- 数据集：356 条人工批阅音频，约 32.94 分钟
- 训练清单：
  `data/hutao_voice/manifests/2026-06-29_182628/hutao_voice_gpt_sovits.list`

训练参数：

- S1 GPT：`batch_size=2`，`epochs=30`，`num_workers=2`，每 5 轮保存一次。
- S2 SoVITS：`batch_size=2`，`epochs=30`，`num_workers=2`，`prefetch_factor=2`，每 5 轮保存一次。
- 未使用 `batch_size=4` 做长训练，因为此前实测显存接近 8GB 上限，不符合“不能占满电脑性能”的要求。
- S2 训练期间显存主要在约 `6.9GB - 7.7GB / 8.188GB`，最高观察约 `7688MiB / 8188MiB`，训练进程优先级设为 `BelowNormal`。

训练结果：

- S1 最终 GPT 权重：
  `external/GPT-SoVITS-v2pro-20250604/GPT_weights_v2Pro/hutao_personal_v2pro_balanced-e30.ckpt`
- S2 最终 SoVITS 权重：
  `external/GPT-SoVITS-v2pro-20250604/SoVITS_weights_v2Pro/hutao_personal_v2pro_balanced_e30_s5430.pth`
- S2 训练日志确认最终保存成功：
  `saving ckpt hutao_personal_v2pro_balanced_e30:Success.`
- S2 中间权重也已保存：`e5`、`e10`、`e15`、`e20`、`e25`、`e30`。

代码和环境修复：

- `scripts/run_hutao_gpt_sovits_training.py`
  - 默认使用项目内魔改版 GPT-SoVITS 与便携 runtime。
  - 自动修复 runtime 的 `users.pth`，避免指向原解压路径。
  - 支持 S1/S2 batch、workers、prefetch、保存间隔参数。
  - v2Pro/v2ProPlus 训练前自动补齐 `7-sv_cn` 说话人向量。
- `external/GPT-SoVITS-v2pro-20250604/GPT_SoVITS/s2_train.py`
  - DataLoader 改为读取配置里的 `num_workers`、`prefetch_factor`、`persistent_workers`。
- `external/GPT-SoVITS-v2pro-20250604/GPT_SoVITS/utils.py`
  - `my_save()` 保存前自动创建目录，修复第 5 轮保存 checkpoint 时目录不存在的问题。
- 新增合成测试脚本：
  `scripts/gpt_sovits_hutao_tts_smoke.py`

真实合成测试：

- 测试命令使用最终 GPT/SovITS 权重启动 `api_v2.py`，通过 `/tts` 真实生成音频。
- 第一次测试失败原因不是模型权重，而是参考音频 `data/hutao_voice/raw/1.wav` 只有约 2.260 秒，不满足 GPT-SoVITS 参考音频 3 到 10 秒要求。
- 已改用参考音频：
  `data/hutao_voice/raw/2.wav`
- 参考音频时长：约 4.339 秒。
- 参考文本：
  `啊，别大惊小怪，他们不是鬼，只是普通的客人。`
- 最终合成测试报告：
  `data/hutao_voice/tests/gpt_sovits_v2pro_balanced/2026-06-29_225124/gpt_sovits_hutao_tts_smoke.md`
- 原始测试 JSON：
  `data/hutao_voice/tests/gpt_sovits_v2pro_balanced/2026-06-29_225124/gpt_sovits_hutao_tts_smoke.json`

生成样本：

- 活泼句：
  `data/hutao_voice/tests/gpt_sovits_v2pro_balanced/2026-06-29_225124/hutao_tts_playful.wav`
  - 文本：`哎嘿，今天的胡桃可是精神满满，准备好一起出发了吗？`
  - 文件：294444 字节，32kHz，单声道，约 4.600 秒
  - 响度检查：RMS 约 4695.3，非静音
- 温柔句：
  `data/hutao_voice/tests/gpt_sovits_v2pro_balanced/2026-06-29_225124/hutao_tts_gentle.wav`
  - 文本：`别担心，我会一直在这里陪着你，慢慢说就好。`
  - 文件：327724 字节，32kHz，单声道，约 5.120 秒
  - 响度检查：RMS 约 4275.1，非静音
- 日常对话句：
  `data/hutao_voice/tests/gpt_sovits_v2pro_balanced/2026-06-29_225124/hutao_tts_chat.wav`
  - 文本：`那么，你今天想聊些什么呢？我已经准备好听你说啦。`
  - 文件：261164 字节，32kHz，单声道，约 4.080 秒
  - 响度检查：RMS 约 4724.4，非静音

测试结论：

- 训练：PASS，S1/S2 都完成 30 轮，最终权重已保存到项目目录内。
- API 权重加载：PASS，`api_v2.py` 可以加载最终 GPT 与 SoVITS 权重。
- 合成产物：PASS，3 条中文测试音频均真实生成，文件非空、时长正常、响度正常。
- 自动 ASR 回读：未完成。当前系统 Python 环境没有安装 FunASR，调用项目 `FunAsrFileEngine` 返回 `FunASR is not installed. Install it before running real ASR tests.`，因此不能伪造回读通过。
- 主观音色、角色相似度、情绪是否足够贴近胡桃，还需要人工试听以上 3 条 WAV 后判断；当前自动检查只能证明模型可加载、可合成、音频不是空文件或静音文件。

### 2026-06-29 用户试听反馈与二次诊断

用户试听反馈：

- 合成音频仍然有一点杂音。
- 情绪表达不足，听起来更像单纯复读机。

重要结论：

- 当前 GPT-SoVITS 训练没有把 `emotion` 字段训练成可直接控制的条件。
- 现有模型“能说话”，但还不是“会按情绪说话”。
- GPT-SoVITS 的情绪/语气主要由参考音频带出；如果始终用同一条普通参考音频，输出就容易像平铺直叙的复读。
- 仅继续增加 epoch 或盲目拉高 batch 不能解决情绪控制问题，也可能放大数据中的杂音。

情绪参考音频对比测试：

- 新增脚本：
  `scripts/gpt_sovits_hutao_emotion_reference_compare.py`
- 测试目的：同一句测试文本，分别使用 `playful`、`serious`、`comforting`、`neutral` 参考音频合成，验证参考音频是否能带出不同风格。
- 测试报告：
  `data/hutao_voice/tests/gpt_sovits_v2pro_emotion_reference/2026-06-29_230317/gpt_sovits_hutao_emotion_reference_compare.md`
- 原始 JSON：
  `data/hutao_voice/tests/gpt_sovits_v2pro_emotion_reference/2026-06-29_230317/gpt_sovits_hutao_emotion_reference_compare.json`
- 测试文本：
  `胡桃今天心情不错，不过说话的语气要跟着场景变一变。`

生成样本：

- `playful` 参考：
  `data/hutao_voice/tests/gpt_sovits_v2pro_emotion_reference/2026-06-29_230317/hutao_emotion_ref_playful.wav`
- `serious` 参考：
  `data/hutao_voice/tests/gpt_sovits_v2pro_emotion_reference/2026-06-29_230317/hutao_emotion_ref_serious.wav`
- `comforting` 参考：
  `data/hutao_voice/tests/gpt_sovits_v2pro_emotion_reference/2026-06-29_230317/hutao_emotion_ref_comforting.wav`
- `neutral` 参考：
  `data/hutao_voice/tests/gpt_sovits_v2pro_emotion_reference/2026-06-29_230317/hutao_emotion_ref_neutral.wav`

数据集情绪分布：

- 总数：356 条，全部 `quality=pass`。
- 标注情绪：
  - `playful`: 263
  - `serious`: 65
  - `neutral`: 23
  - `comforting`: 5
- 可作为参考音频的样本数量：265 条，条件为 3 到 10 秒且 `quality=pass`。
- 情绪分布严重不均衡，`comforting` 只有 5 条，不足以训练出稳定的温柔/安慰风格。

杂音和数据质量审计：

- 新增脚本：
  `scripts/audit_hutao_voice_quality.py`
- 审计结果：
  `data/hutao_voice/reports/hutao_voice_quality_audit.json`
- 356 条中有 40 条建议复查。
- 风险原因统计：
  - `possible_clipping`: 16
  - `too_long_over_12s`: 16
  - `punctuation_suspicious`: 6
  - `too_short_under_1s`: 3
  - `low_volume`: 2
- 可能削波样本会带来破音/杂音风险。
- 超过 12 秒样本可能影响对齐和稳定性。
- 过短样本和低音量样本对训练帮助有限，反而可能增加不稳定。

下一步开发方案：

1. 先不要直接继续训练当前模型。
2. 生成一个 `clean_v1` 训练集：
   - 剔除 `possible_clipping`、`too_long_over_12s`、`too_short_under_1s`、`low_volume` 的高风险样本。
   - 对 `punctuation_suspicious` 样本人工复查文本。
   - 目标是牺牲少量数据，换更干净的音质。
3. 重新预处理并训练新实验名，例如：
   `hutao_personal_v2pro_clean_v1`
4. 增加“情绪参考音频库”模块：
   - 为 `playful`、`serious`、`neutral`、`comforting` 各挑 3 到 10 秒、音质干净、情绪明显的参考音频。
   - 推理时不要只用一条固定参考音频，而是根据对话情绪选择对应参考音频。
5. 如果要真正做到输入情绪可控，需要在胡桃说话模块上层实现：
   - 文本/对话情绪判断。
   - 情绪到参考音频的路由。
   - 不同情绪的 top_p、temperature、speed_factor 参数预设。
6. 长期方案：
   - 补充或制作更多 `comforting`、`sad`、`angry/serious`、`happy/playful` 情绪样本。
   - 每类至少几十条干净样本，才能更稳定地表现不同语气。

### 2026-06-29 试听反馈：电流声与韵律不足

用户进一步试听反馈：

- 不同情绪参考音频已经能听出一点区别。
- 合成音频里仍有一点电流声/毛刺感。
- 和真人说话相比，语调、抑扬顿挫、自然停顿仍然不足。

判断：

- 情绪参考方向有效，但当前模型还没有达到“自然真人韵律”。
- 电流声更可能来自训练数据里的削波/低质量片段、参考音频质量、以及模型对高频细节的还原误差。
- 抑扬顿挫不足不能只靠继续训练解决，需要：
  - 更干净、更有表现力的参考音频。
  - 按情绪选择参考音频。
  - 推理参数按场景区分。
  - 更干净的数据重训。

韵律参数对比测试：

- 新增脚本：
  `scripts/gpt_sovits_hutao_prosody_compare.py`
- 测试报告：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/gpt_sovits_hutao_prosody_compare.md`
- 原始 JSON：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/gpt_sovits_hutao_prosody_compare.json`
- 测试文本：
  `哎嘿，今天的胡桃可是精神满满。先别急，我们慢慢把事情说清楚。`
- 参考音频：
  `data/hutao_voice/raw/123.wav`
- 参考文本：
  `哎呀，我不是说上门和我谈生意的客人，每个人在诞生到这个世界上的时候，就注定了是我的客人。`

生成的参数样本：

- `stable_default`：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/hutao_prosody_stable_default.wav`
  - 参数：`top_k=15`，`top_p=0.9`，`temperature=0.8`，`repetition_penalty=1.35`，`speed_factor=1.0`
- `more_natural`：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/hutao_prosody_more_natural.wav`
  - 参数：`top_k=25`，`top_p=0.95`，`temperature=0.95`，`repetition_penalty=1.25`，`speed_factor=0.98`
- `expressive`：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/hutao_prosody_expressive.wav`
  - 参数：`top_k=35`，`top_p=0.98`，`temperature=1.05`，`repetition_penalty=1.18`，`speed_factor=1.0`
- `gentle_slow`：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/hutao_prosody_gentle_slow.wav`
  - 参数：`top_k=20`，`top_p=0.92`，`temperature=0.88`，`repetition_penalty=1.25`，`speed_factor=0.92`
- `clean_conservative`：
  `data/hutao_voice/tests/gpt_sovits_v2pro_prosody_compare/2026-06-29_231519/hutao_prosody_clean_conservative.wav`
  - 参数：`top_k=10`，`top_p=0.85`，`temperature=0.72`，`repetition_penalty=1.4`，`speed_factor=0.98`

自动检查：

- 5 条韵律参数样本均生成成功。
- 均为 32kHz 单声道 WAV。
- 自动统计未发现输出削波，`clip_ratio=0.0`。
- 是否更自然仍必须以人工试听为准。

clean_v1 训练清单：

- 新增脚本：
  `scripts/export_hutao_clean_manifest.py`
- 生成报告：
  `data/hutao_voice/reports/2026-06-29_231505_clean_v1/hutao-clean-v1-manifest-report.md`
- 原始 JSON：
  `data/hutao_voice/reports/2026-06-29_231505_clean_v1/hutao-clean-v1-manifest-result.json`
- GPT-SoVITS clean_v1 清单：
  `data/hutao_voice/manifests/2026-06-29_231505_clean_v1/hutao_voice_gpt_sovits_clean_v1.list`
- latest 副本：
  `data/hutao_voice/manifests/latest_hutao_voice_gpt_sovits_clean_v1.list`
- 原始总数：356 条。
- clean_v1 保留：322 条。
- 剔除：34 条。
- 保留但建议文本复查：6 条。
- 剔除原因：
  - `possible_clipping`
  - `too_long_over_12s`
  - `too_short_under_1s`
  - `low_volume`

下一步建议：

1. 先让用户试听 5 条韵律参数样本，选出最接近自然人说话的一套或两套参数。
2. 基于 `clean_v1` 清单重新训练：
   - 实验名建议：`hutao_personal_v2pro_clean_v1`
   - S1/S2 仍建议 `batch_size=2`，避免占满 8GB 显存。
3. 重训后再次做相同的韵律参数对比测试，比较电流声是否减少。
4. 建立情绪参考音频库：
   - 每个情绪至少保留 3 条 3 到 10 秒的干净参考音频。
   - 运行时由对话情绪选择参考音频，而不是固定一条。
5. 如果 clean_v1 重训后仍有明显电流声，再考虑对训练音频做离线降噪/响度归一化后生成 `clean_v2`。

### 2026-06-29 后续规划：聊天模型与唱歌模型分离

结论：

- 胡桃项目后续需要两套语音模型。
- 聊天模型负责日常对话、情绪说话、低延迟交互。
- 唱歌模型负责歌曲、哼唱、音准、节奏、拖音、颤音和唱腔。
- 不建议用当前 GPT-SoVITS 聊天模型承担高标准唱歌任务。

聊天模型路线：

- 继续使用 GPT-SoVITS 或同类 TTS/音色克隆方案。
- 当前目标是先完成 `clean_v1` 重训，降低电流声和毛刺。
- 后续重点不是继续盲目拉高训练轮数，而是：
  - 建立情绪参考音频库。
  - 增加对话情绪路由。
  - 增加断句、停顿、语速、参考音频选择控制。
  - 让聊天系统根据上下文决定“怎么说”，TTS 只负责“用胡桃音色说出来”。

唱歌模型路线：

- 后续单独建立目录：
  `data/hutao_singing/`
- 后续单独建立模型目录：
  `models/singing/`
- 可选方向：
  - RVC / So-VITS-SVC：更适合把已有干声歌声转换成胡桃音色。
  - DiffSinger / OpenUtau 声库路线：更适合真正根据歌词、音高、时值/MIDI 合成歌声。
- 唱歌训练需要单独的数据：
  - 干净歌声音频。
  - 歌词。
  - 音高/时值/MIDI 或可对齐的歌唱标注。
  - 与聊天台词分开管理。

运行时路由：

- 普通聊天：走聊天 TTS。
- 用户要求唱歌、哼歌、唱某首歌：走 singing 模块。
- 用户要求“开心/温柔/认真地说”：走聊天 TTS + 情绪参考音频库。
- 不要用唱歌能力衡量聊天 TTS 是否合格；唱歌和说话是两个不同任务。

### 2026-06-29 聊天模块真人感方案

目标：

- 胡桃聊天时要随意、自然，不像 AI 念稿。
- 回复内容要像真实聊天，不要每次都完整、客套、解释过多。
- 情绪表达要能被听出来，不只是文字上写“开心/难过”。

核心判断：

- 单靠 TTS 训练无法解决“AI 味重”。
- 真人感来自完整链路：
  1. 文本回复是否像人。
  2. 情绪判断是否准确。
  3. 句子是否按口语节奏拆分。
  4. 每段语音是否选择正确参考音频。
  5. 语速、停顿、采样参数是否跟情绪匹配。
  6. 是否记得用户习惯和前文，不每次像第一次聊天。

推荐架构：

1. `Persona Reply`
   - 负责生成胡桃风格回复。
   - 限制长篇解释。
   - 增加口语、小停顿、短句、追问。
   - 避免“作为一个 AI”“我可以帮助你”等 AI 话术。
2. `Emotion Planner`
   - 输入用户消息、胡桃回复、上下文。
   - 输出情绪：`playful`、`serious`、`comforting`、`neutral`、`teasing`、`worried` 等。
   - 输出强度：`0.0-1.0`。
3. `Prosody Planner`
   - 把回复拆成 1 到 3 个短语音片段。
   - 为每段设置停顿、语速、参考音频、推理参数。
   - 长句不要一次性合成，避免机械和吞字。
4. `Voice Router`
   - 根据情绪选择参考音频库里的 3 到 10 秒干净音频。
   - 同一情绪准备多条参考音频，轮换使用，避免每次听起来一样。
5. `TTS Synthesizer`
   - 使用 GPT-SoVITS clean_v1 模型合成。
   - 根据情绪使用不同参数预设。
6. `Memory`
   - 记录用户偏好、称呼、最近事件、聊天气氛。
   - 回复时使用记忆，但不要生硬复述。

聊天文本策略：

- 少用完整书面句，多用短句。
- 少解释大道理，多回应用户当前情绪。
- 允许轻微口头语，例如“嗯？”、“哎呀”、“先别急”、“这个嘛”。
- 不要每句都带口癖，否则会假。
- 每次回复控制在 1 到 3 个自然句，除非用户明确要求详细解释。
- 多用“接话”和“追问”，少用总结式回答。

情绪语音策略：

- `playful`
  - 参考音频选择活泼、上扬、节奏快的样本。
  - 语速略快。
  - `temperature/top_p` 可略高。
- `comforting`
  - 参考音频选择柔和、慢速、低攻击性的样本。
  - 语速略慢。
  - 句子拆短，中间留停顿。
- `serious`
  - 参考音频选择稳定、清楚、有力度的样本。
  - 降低随机性，避免怪音。
- `neutral`
  - 用稳定参考音频。
  - 参数保守，优先清晰。

近期优先级：

1. 先完成 `hutao_personal_v2pro_clean_v1` 重训，解决电流声和毛刺。
2. 从现有数据中建立第一版情绪参考音频库。
3. 实现 `Emotion Planner + Voice Router + Prosody Planner`。
4. 用固定 10 条聊天场景做真实听感测试：
   - 开心打招呼。
   - 安慰用户。
   - 被用户吐槽。
   - 认真解释。
   - 开玩笑。
   - 普通闲聊。
   - 用户难过。
   - 用户夸她。
   - 用户问项目进度。
   - 用户让她短句回应。

### 2026-06-29 真人感聊天语音流水线原型

本次已开始实现聊天语音原型，不再只停留在方案。

新增模块：

- `app/voice_chat/__init__.py`
- `app/voice_chat/planner.py`
- `app/voice_chat/audio_utils.py`

新增测试脚本：

- `scripts/voice_chat_pipeline_smoke.py`

已实现能力：

- 规则版 `Emotion Planner`
  - 根据用户输入和回复文本判断主情绪。
  - 当前支持：`playful`、`teasing`、`comforting`、`worried`、`serious`、`neutral`。
- 规则版 `Prosody Planner`
  - 将回复拆成短语音段。
  - 为每段设置情绪、停顿、参考音频和推理参数。
- 规则版 `Voice Router`
  - 根据情绪选择 3 到 10 秒的胡桃参考音频。
  - 当前参考音频：
    - `playful/teasing`: `hutao_raw_0123`，`data/hutao_voice/raw/123.wav`
    - `serious`: `hutao_raw_0156`，`data/hutao_voice/raw/157.wav`
    - `comforting/worried`: `hutao_raw_0142`，`data/hutao_voice/raw/143.wav`
    - `neutral`: `hutao_raw_0083`，`data/hutao_voice/raw/83.wav`
- GPT-SoVITS 分段合成。
- 多段 WAV 拼接。
- 输出音频基础统计：时长、采样率、RMS、峰值、削波比例。

真实 smoke 测试：

- 测试报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/voice_chat_pipeline_smoke.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/voice_chat_pipeline_smoke.json`
- 使用模型：
  - GPT: `external/GPT-SoVITS-v2pro-20250604/GPT_weights_v2Pro/hutao_personal_v2pro_balanced-e30.ckpt`
  - SoVITS: `external/GPT-SoVITS-v2pro-20250604/SoVITS_weights_v2Pro/hutao_personal_v2pro_balanced_e30_s5430.pth`

生成场景：

- `playful_greeting`
  - 用户：`胡桃，今天项目终于跑起来一点了，快夸夸我。`
  - 输出：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/playful_greeting/playful_greeting_combined.wav`
- `comfort_user`
  - 用户：`我今天真的有点累，感觉怎么做都做不好。`
  - 输出：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/comfort_user/comfort_user_combined.wav`
- `serious_project`
  - 用户：`这个语音模块还是有电流声，下一步应该先查哪里？`
  - 输出：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/serious_project/serious_project_combined.wav`
- `teasing_short`
  - 用户：`你刚才说话还是有点像复读机。`
  - 输出：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/teasing_short/teasing_short_combined.wav`
- `casual_chat`
  - 用户：`随便聊两句吧，别太正式。`
  - 输出：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_234638/casual_chat/casual_chat_combined.wav`

测试结果：

- 结果：PASS。
- 5 个场景都生成了真实 WAV。
- 合成音频均为 32kHz 单声道。
- 自动统计未发现输出削波，`clip_ratio=0.0`。
- 本机当前 Python 环境缺少 `pydantic`，所以主 `ChatService` 未能运行，脚本使用本地规则回复作为 fallback。
- 情绪规划、参考音频路由、推理参数选择、GPT-SoVITS 合成和 WAV 拼接都是真实执行。

已发现并修复的问题：

- `playful_greeting` 因用户文本包含“项目”被主情绪误判为 `serious`。
- 已调整 `app/voice_chat/planner.py` 中情绪判断优先级：
  - 疲惫/难受优先 `comforting`。
  - 夸奖/轻松/开心优先 `playful`。
  - 技术/项目问题再判断 `serious`。
- 已通过轻量检查确认同样输入现在主情绪为 `playful`。

下一步：

1. 用户先试听 5 个 combined WAV，指出哪条最接近、哪条最假。
2. 安装或修复主服务运行环境中的 `pydantic`，让 smoke 脚本使用真实 `ChatService` 和 live/fallback 回复。
3. 将规则版 `Emotion Planner + Voice Router + Prosody Planner` 接入主 API 的可选路径。
4. 基于 `clean_v1` 重训后，重新跑同一套 voice pipeline smoke，对比电流声和自然度。

### 2026-06-30 真人感聊天语音流水线：克制情绪改版

用户反馈：

- `voice_chat_pipeline` 第一版整体方向可以。
- 但情绪仍然太刻意，没有真正的真人感。
- 用户提到 `conda new` 环境已安装 `pydantic`。

环境确认：

- `new` 环境 Python：
  `D:/Tool/Progrmming-Tool/anaconda/envs/new/python.exe`
- 已确认：
  - `pydantic 2.13.4`
  - `fastapi`
  - `httpx 0.28.1`
  - `uvicorn`
  - `python-multipart`
- 使用 `new` 环境后，`scripts/voice_chat_pipeline_smoke.py` 可以调用真实 `ChatService`。

参考论文/数据结论：

- IEMOCAP 是双人交互情绪语音库，包含 scripted 和 spontaneous spoken communication；说明真实情绪语音不是单句硬标签，而是在交互上下文中连续变化。
- ESD 情绪语音数据集用于 emotional voice conversion / speech synthesis，覆盖 neutral、happy、angry、sad、surprise；它是控制声学环境和情绪类别的数据，不等于自然闲聊里的强情绪表演。
- MELD 是多方对话情绪识别数据集，强调 conversation context 和多模态上下文；说明聊天情绪判断不能只看单句关键词。
- GST Tacotron / Global Style Tokens 相关工作说明，表达风格包含 text-independent acoustic expressiveness；更自然的做法是学习/选择风格嵌入或参考风格，而不是直接把离散情绪标签演满。

本次根据以上结论做的修改：

- `app/persona/persona_prompt_builder.py`
  - 增加“情绪表达要克制，像真人顺口接话”。
  - 禁止舞台腔、刻意撒娇、波浪号、夸张感叹和凭空编造场景。
  - 增加“宁可少一点情绪，也不要演得太满”。
- `app/voice_chat/planner.py`
  - 降低情绪强度：
    - `playful`: 约 `0.52`
    - `comforting`: 约 `0.58`
    - `serious`: 约 `0.48`
    - `neutral`: 约 `0.35`
  - 降低采样随机性，减少刻意表演和怪音：
    - `playful` 从 `temperature=0.95/top_p=0.95` 降到 `temperature=0.82/top_p=0.9`
    - `comforting` 从 `temperature=0.86/top_p=0.92/speed=0.92` 改为 `temperature=0.76/top_p=0.88/speed=0.96`
    - `neutral` 改为更保守的 `temperature=0.7/top_p=0.84`
  - 技术问题、电流声、训练、模型、接口、代码、参数、模块优先判定为 `serious`，避免调侃化。
- `scripts/voice_chat_pipeline_smoke.py`
  - 本地 fallback 回复压短、减少口癖，避免“本堂主陪你慢慢拆”这类刻意台词。

第二版真实测试：

- 测试报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-29_235806/voice_chat_pipeline_smoke.md`
- 使用 `new` 环境运行。
- 结果：PASS。
- 真实 `ChatService` 调用成功：
  - `provider=deepseek`
  - `model=deepseek-v4-pro`
  - `live=True`
  - `fallback=False`
- 问题：
  - live 回复仍有 `～` 和舞台化表达。
  - 技术问题被回复文本带偏成 `teasing`。

第三版真实测试：

- 测试报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/voice_chat_pipeline_smoke.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/voice_chat_pipeline_smoke.json`
- 结果：PASS。
- 使用 `new` 环境，真实 `ChatService` 调用成功。
- 5 条合并音频：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/playful_greeting/playful_greeting_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/comfort_user/comfort_user_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/serious_project/serious_project_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/teasing_short/teasing_short_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_000048/casual_chat/casual_chat_combined.wav`
- 自动检查：
  - 全部为 32kHz 单声道 WAV。
  - 输出削波比例 `clip_ratio=0.0`。

第三版仍需改进：

- live 回复仍偶尔输出 `～`，说明 prompt 约束还不够硬，后续要加响应后处理或 evaluator 门禁。
- `playful_greeting` 用户意图是“夸夸我”，但 live 回复没有保留“夸”字，planner 根据合并文本仍判成 `serious`；后续需要让用户意图权重大于回复关键词。
- 技术问题虽然已判回 `serious`，但回复文本仍有“闹脾气”这种轻拟人表达，需要再降低技术场景的玩笑程度。

下一步建议：

1. 加一个 `Naturalness Gate`：
   - 删除或拒绝 `～`、连续感叹、括号动作、凭空场景。
   - 检测“过度比喻/舞台腔”，失败则要求模型重写得更短更平。
2. `Emotion Planner` 改成基于用户意图优先：
   - 用户要求夸奖、开心反馈，优先 `playful`。
   - 用户问技术问题，优先 `serious`，即使回复里有调侃词。
3. `Prosody Planner` 默认更少切情绪：
   - 大多数普通聊天使用 `neutral + slight playful`。
   - 只在明显疲惫/难过时切 `comforting`。
4. 用户试听第三版后，按“哪条最假、哪句太用力、哪句像真人”继续收敛。

补丁：

- 新增 `app/voice_chat/naturalness.py`
  - `normalize_reply_for_natural_chat()` 用于轻量后处理。
  - 当前会移除 `～/~`，压缩连续感叹号和多余空白。
- `scripts/voice_chat_pipeline_smoke.py`
  - live `ChatService` 回复和本地 fallback 回复都会先经过 naturalness 后处理再进入语音规划。
- `app/voice_chat/planner.py`
  - 用户明确说“夸夸我/夸我/终于跑起来”等时，优先判定 `playful`，避免被“项目”关键词压成 `serious`。
- 已用 `new` 环境做语法检查和轻量验证。
- 未重复生成第四版音频；下一次运行 `voice_chat_pipeline_smoke.py` 时会自动使用该补丁。

### 2026-06-30 试听反馈：口齿不清与拼接问题

用户试听 `2026-06-30_000048` 版本反馈：

- `playful_greeting_combined.wav`：有点口齿不清。
- `comfort_user_combined.wav`：口齿不清，疑似拼接不好，有乱音。
- `serious_project_combined.wav`：口齿不清。
- `teasing_short_combined.wav`：口齿不清。
- `casual_chat_combined.wav`：整体较好，但有个别字没说清楚。

问题判断：

- 当前主要问题已从“情绪是否明显”转为“基础可懂度和拼接稳定性”。
- 造成口齿不清的主要风险：
  - 单段文本过长。
  - 回复里有波浪号、破折号、数字、英文缩写等 TTS 难读符号。
  - live 回复有些文本绕口或拟人比喻过多。
  - 分段拼接缺少淡入淡出，段首段尾可能出现轻微乱音。

已做清晰度优先修改：

- `app/voice_chat/naturalness.py`
  - 新增 `normalize_text_for_tts()`。
  - 会把 `～/~`、破折号、括号类符号清理掉。
  - 会把数字转成中文读法。
  - 会把 `AI`、`TTS`、`bug/debug` 等替换成更适合中文 TTS 的读法。
- `app/voice_chat/planner.py`
  - 语音合成前先使用 `normalize_text_for_tts()`。
  - 每段长度从约 32 到 36 字降低到约 18 到 22 字。
  - 最大分段数提升到 4。
  - 长句会按标点和固定长度切开，减少一口气合成长句导致的吞字。
- `app/voice_chat/audio_utils.py`
  - WAV 拼接加入约 8ms 的短淡入淡出。
  - 目标是降低段首/段尾突变和乱音。
- `scripts/voice_chat_pipeline_smoke.py`
  - 报告中的回复文本改为实际进入 TTS 的规范化文本。

清晰度优先版本测试：

- 测试报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/voice_chat_pipeline_smoke.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/voice_chat_pipeline_smoke.json`
- 结果：PASS。
- 使用 `new` 环境，真实 `ChatService` 调用成功。
- 5 条合并音频：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/playful_greeting/playful_greeting_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/comfort_user/comfort_user_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/serious_project/serious_project_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/teasing_short/teasing_short_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_001405/casual_chat/casual_chat_combined.wav`

该版本变化：

- `playful_greeting` 分为 2 段：
  - `哟，今天项目长腿了？`
  - `跑得挺溜，赏你一朵小红花！`
- `comfort_user` 分为 2 段：
  - `刚夸完就泄气了？`
  - `偶尔掉链子正常，别跟自己较劲嘛。`
- `serious_project` 分为 2 段：
  - `电流声啊，先查接地和电源纹波吧，`
  - `这一步最像元凶藏身地。`
- `casual_chat` 缩短为一句：
  - `行，那就不端着了，今天有啥新鲜事没？`

自动检查：

- 全部为 32kHz 单声道 WAV。
- 输出削波比例均为 `clip_ratio=0.0`。
- 是否解决口齿不清和拼接乱音，需要用户人工试听 `2026-06-30_001405` 版本确认。

下一步：

- 如果清晰度仍不够，下一轮应降低生成文本复杂度，而不是继续调情绪：
  - 回复文本强制更短。
  - 禁止“长腿、元凶藏身地、五毛钱”等可能绕口或不稳的比喻。
  - 将每段控制在 10 到 14 字。
  - 对每段单独测试，而不是只听合并文件。
- 如果拼接仍有乱音，考虑在拼接处增加更长静音间隔，或改为前端逐段播放而不是离线拼接。

### 2026-06-30 试听反馈：电流声仍在与部分音频低频过重

用户试听 `2026-06-30_001405` 清晰度优先版本后反馈：

- 电流声仍然存在。
- 部分音频有重低音、低频过厚的感觉。

本轮判断：

- 如果电流声来自模型声码器或训练样本底噪，单纯后处理只能缓解，不能根治。
- 如果重低音主要集中在 120 到 250Hz，可以通过高通、陷波和轻度动态门限先压一版给用户试听。
- 不能继续盲目提高情绪强度；当前优先级仍是干净度、可懂度、自然度。

已修改：

- `scripts/postprocess_voice_outputs.py`
  - 从一阶滤波改为 `scipy.signal` 的四阶 Butterworth 高通/低通。
  - 新增 50Hz、100Hz、150Hz 陷波，针对电源嗡声和低频轰鸣。
  - 新增轻量 noise gate，用于压低停顿和弱能量处的残留底噪。
  - 新增频段统计：
    - `low_bass_ratio_0_120hz`
    - `bass_ratio_120_250hz`
    - `speech_ratio_250_5000hz`
    - `hiss_ratio_7000hz_plus`
  - 新增 `--run-name` 参数，避免覆盖上一轮测试输出。

新增后处理配置：

- `voice_clean`
  - 高通 110Hz，低通 9000Hz，50/100Hz 陷波，RMS 3300。
  - 目标：尽量保留原声质感，只轻微压电流感和底噪。
- `bass_cut`
  - 高通 155Hz，低通 8600Hz，50/100/150Hz 陷波，RMS 3100。
  - 目标：重点削低频厚重感，优先给用户试听。
- `dehiss`
  - 高通 120Hz，低通 6800Hz，50/100Hz 陷波，RMS 2900。
  - 目标：强压高频毛刺和电流感，但可能让声音变闷。

测试命令：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\postprocess_voice_outputs.py" --input-root "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\voice_chat_pipeline\2026-06-30_001405" --output-root "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\voice_chat_pipeline_postprocessed" --run-name "2026-06-30_001405_noise_bass_v2"
```

测试结果：

- 结果：PASS。
- 语法检查：PASS。
- 输出目录：
  `data/hutao_voice/tests/voice_chat_pipeline_postprocessed/2026-06-30_001405_noise_bass_v2`
- 报告：
  `data/hutao_voice/tests/voice_chat_pipeline_postprocessed/2026-06-30_001405_noise_bass_v2/postprocess_voice_outputs.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline_postprocessed/2026-06-30_001405_noise_bass_v2/postprocess_voice_outputs.json`
- 本地环境缺少 `git` 命令，因此本轮未执行 `git diff`。

自动统计观察：

- 所有输出均为 32kHz 单声道 WAV。
- 所有输出 `clip_ratio=0.0`，未发现削波。
- 0 到 120Hz 的超低频在新配置中基本被压到 0。
- 7kHz 以上高频毛刺占比明显下降：
  - `teasing_short` 原始约 `0.011811`，`dehiss` 后约 `0.000266`。
  - `playful_greeting` 原始约 `0.009224`，`dehiss` 后约 `0.000168`。
  - `comfort_user` 原始约 `0.005312`，`dehiss` 后约 `0.000152`。
- 120 到 250Hz 的低频厚重感在 `playful_greeting` 和 `teasing_short` 最明显，`bass_cut` 对这两条更有参考价值：
  - `playful_greeting` 从约 `0.056462` 降到 `0.049432`。
  - `teasing_short` 从约 `0.025828` 降到 `0.022445`。

建议试听顺序：

1. 先听 `bass_cut` 目录，判断重低音是否明显缓解。
2. 再听 `voice_clean` 目录，判断是否比 `bass_cut` 更自然。
3. 最后听 `dehiss` 目录，只判断电流声是否最少；如果声音变闷，不应作为默认方案。

后续判断：

- 如果 `bass_cut` 或 `voice_clean` 明显改善，可把该后处理配置接入语音流水线默认输出。
- 如果三套版本仍然有明显电流声，则说明问题更可能来自训练样本底噪、GPT-SoVITS 声码器输出或当前模型训练质量，应转向 `clean_v1` 重训和更严格的数据清洗，而不是继续用后处理硬压。

### 2026-06-30 试听反馈：后处理压不住电流感，转向训练与参考音频问题

用户试听 `2026-06-30_001405_noise_bass_v2` 后反馈：

- `bass_cut`：电流声仍在。
- 问题不是重低音，更像“低电量”的发虚、没电感。
- `serious_project_combined.wav` 听起来尤其奇怪。
- `voice_clean` 自然度稍微好一点，但提升不高。
- `dehiss` 也压不住电流声。
- 用户判断更像训练出来的模型本身有问题。

本轮结论：

- 后处理不是主解决方向，只能做轻微修饰。
- 如果 `bass_cut`、`dehiss` 都压不住，电流感大概率来自：
  - 当前训练模型质量。
  - 训练样本内残留底噪或音质不一致。
  - GPT-SoVITS 声码器/推理过程的伪影。
  - 参考音频选择不合适，把怪调、发虚感带进生成。
- 在 `ffmpeg` 下载完成前，不做批量音频标准化；先处理不依赖 `ffmpeg` 的参考音频路由问题。

发现的明确问题：

- `serious_project` 原先使用 `hutao_raw_0156` 作为 serious 参考。
- 该参考对应：
  - 音频：`data/hutao_voice/raw/157.wav`
  - 文本：`喂喂，等等。那那那再打个折怎么样？如果一次满10个人，可以有7折优惠。`
  - 原始识别情绪：`angry`
  - 强度：`1.0`
- 这条参考包含“那那那”、数字和强情绪，作为技术/严肃场景参考不稳定，可能导致 `serious_project` 的奇怪语调和低电量感。
- `clean_v1` 仍然包含 `157.wav`，说明当前 clean 清单只按时长、削波、音量等自动指标剔除，还没有按“口齿稳定、参考适配、是否发虚/电流感”做主观质量剔除。

已修改：

- `app/voice_chat/planner.py`
  - 将 `serious` 参考从 `hutao_raw_0156` 改为 `hutao_raw_0035`。
  - 新参考对应：
    - 音频：`data/hutao_voice/raw/35.wav`
    - 文本：`不过，老孟说的这种事是有可能的，因为确实时不时就会有鬼灵在县市游荡。`
    - 原始识别情绪：`neutral`
    - 强度：`0.2`
    - 人工审核通过，ASR 质量通过。
- `scripts/voice_chat_pipeline_smoke.py`
  - 新增 `--scenarios` 参数，可以只运行指定测试场景，避免每次都重跑 5 条音频。

验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\planner.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py"
```

- 结果：PASS。

只重测 `serious_project`：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9884 --base-url "http://127.0.0.1:9884" --scenarios serious_project --timeout-seconds 300
```

测试结果：

- 结果：PASS。
- 输出目录：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_005200`
- 报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_005200/voice_chat_pipeline_smoke.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_005200/voice_chat_pipeline_smoke.json`
- 新合并音频：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_005200/serious_project/serious_project_combined.wav`
- 分段音频：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_005200/serious_project/segment_1_serious.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_005200/serious_project/segment_2_serious.wav`
- 本次确认为 `reference_id=hutao_raw_0035`，`reference_audio=data/hutao_voice/raw/35.wav`。
- 输出自动统计：
  - 32kHz 单声道 WAV。
  - 合并时长约 `6.6s`。
  - `clip_ratio=0.0`，无削波。

新发现：

- 本次 live 回复中出现 `ESR` 英文缩写，以及“纹波这小鬼最藏不住这儿”这种不够自然且可能增加合成不稳定的表达。
- 后续需要增加 TTS 文本门禁：
  - 英文缩写转中文读法或替换为中文。
  - 技术场景禁止怪比喻、拟人化过重表达。
  - 严肃/技术场景回复应更短、更直白，每段尽量 10 到 16 个中文字符。

下一步：

- 用户优先试听 `2026-06-30_005200/serious_project/serious_project_combined.wav`，判断仅更换 serious 参考后，“低电量感/电流感/奇怪语调”是否改善。
- 等 `ffmpeg` 下载完成后，做 `clean_v2`：
  - 批量重采样/响度标准化。
  - 剔除或降权主观不稳样本，例如 `157.wav`。
  - 对训练清单增加“参考音频可用性”和“口齿稳定性”过滤。
- 如果换参考后仍然发虚，则启动基于 `clean_v2` 的重训，而不是继续调后处理。

### 2026-06-30 clean_v2 数据清洗与重训决策

用户已安装并配置 `ffmpeg`，但当前 Codex PowerShell 进程未直接识别 PATH 中的 `ffmpeg`/`ffprobe`。

实际找到的可用路径：

- GPT-SoVITS 自带：
  `external/GPT-SoVITS-v2pro-20250604/runtime/ffmpeg.exe`
- 用户新安装：
  `D:\Tool\Tool plugin\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe`
  `D:\Tool\Tool plugin\ffmpeg-8.0.1-essentials_build\bin\ffprobe.exe`

验证：

```powershell
& "D:\Tool\Tool plugin\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe" -version
& "D:\Tool\Tool plugin\ffmpeg-8.0.1-essentials_build\bin\ffprobe.exe" -version
```

- 结果：PASS。
- ffmpeg 版本：`8.0.1-essentials_build-www.gyan.dev`。

重训决策：

- 当前模型效果不尽人意，用户反馈包含电流声、低电量感、自然度不足。
- 结论：需要重训，但不能直接用旧 `clean_v1` 重训。
- 原因：`clean_v1` 仍保留了 `157.wav` 这类主观不稳样本，也保留了较多 ASR/标点风险样本。
- 正确顺序：
  1. 先做 `clean_v2`：统一音频规格、剔除明显不稳样本。
  2. 再训练新实验。
  3. 用同一组聊天场景与旧模型对比。
  4. 如果新模型更干净但相似度/情绪下降，再补人工筛选样本，而不是回退到脏数据。

已新增：

- `scripts/export_hutao_clean_v2_manifest.py`
  - 使用 ffmpeg 标准化训练音频。
  - 输出标准化 WAV 到项目内：
    `data/hutao_voice/clean_v2/wavs`
  - 输出 GPT-SoVITS list：
    `data/hutao_voice/manifests/latest_hutao_voice_gpt_sovits_clean_v2.list`
  - 支持 `--ffmpeg` 指定 ffmpeg 绝对路径，避免依赖 PATH。

clean_v2 标准化策略：

- 单声道。
- 32kHz。
- 16-bit PCM。
- 轻高通 `highpass=f=60`。
- 响度标准化 `loudnorm=I=-20:TP=-3:LRA=11`。
- 不做强降噪，避免破坏角色音色和齿音。

clean_v2 剔除规则：

- 已知主观坏样本：
  - `hutao_raw_0156` / `data/hutao_voice/raw/157.wav`
- ASR 质量未通过。
- 标点冲突 `punctuation_collision`。
- 文本包含不稳定标点，例如 `。，`、`？。`、`?`。
- 时长小于 1 秒或大于 10 秒。
- 可能削波。
- 低音量或过响。
- 文本过短或超过 90 字。
- 授权/质量字段不满足训练要求。

执行命令：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\export_hutao_clean_v2_manifest.py" --ffmpeg "D:\Tool\Tool plugin\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
```

测试结果：

- 结果：PASS。
- 总数：356。
- clean_v2 保留：221。
- 剔除：135。
- 标准化失败：0。
- 标准化后训练音频数量：221。
- 标准化后可训练时长：约 18.11 分钟。
- 输出报告：
  `data/hutao_voice/reports/2026-06-30_102800_clean_v2/hutao-clean-v2-manifest-report.md`
- 原始 JSON：
  `data/hutao_voice/reports/2026-06-30_102800_clean_v2/hutao-clean-v2-manifest-result.json`
- GPT-SoVITS list：
  `data/hutao_voice/manifests/2026-06-30_102800_clean_v2/hutao_voice_gpt_sovits_clean_v2.list`
- latest 副本：
  `data/hutao_voice/manifests/latest_hutao_voice_gpt_sovits_clean_v2.list`

剔除原因统计：

- `asr_quality_not_passed`: 97
- `punctuation_collision`: 96
- `unstable_text_punctuation`: 67
- `too_long_over_10s`: 22
- `possible_clipping`: 16
- `too_short_under_1s`: 3
- `low_volume`: 2
- `known_bad_subjective`: 1

保留样本情绪分布：

- `playful`: 164
- `serious`: 43
- `neutral`: 12
- `comforting`: 2

风险说明：

- clean_v2 比 clean_v1 更干净，但总时长从约 32.94 分钟降到约 18.11 分钟。
- 这轮更适合训练“干净基线模型”，目标优先级是去掉电流感、低电量感和口齿不稳。
- 情绪丰富度可能下降，尤其是 `comforting` 只有 2 条；后续如果干净度改善，需要补充人工筛选的情绪参考样本。

下一步：

- 用 `latest_hutao_voice_gpt_sovits_clean_v2.list` 创建新实验：
  `hutao_personal_v2pro_clean_v2`
- 建议先跑 GPT-SoVITS 预处理，确认 221 条标准化样本都能通过。
- 训练参数保持保守，不占满电脑性能：
  - `s1_batch_size=2`
  - `s2_batch_size=2`
  - workers 维持 2
  - epoch 初始 30
- 训练完成后必须用同一套 `voice_chat_pipeline_smoke` 场景对比旧模型和 clean_v2 新模型。

clean_v2 GPT-SoVITS 预处理验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\run_hutao_gpt_sovits_training.py" --manifest "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\manifests\latest_hutao_voice_gpt_sovits_clean_v2.list" --exp-name hutao_personal_v2pro_clean_v2 --version v2Pro --stage preprocess --s1-batch-size 2 --s2-batch-size 2 --s1-num-workers 2 --s2-num-workers 2
```

预处理结果：

- 结果：PASS，进程退出码 0。
- 实验目录：
  `external/GPT-SoVITS-v2pro-20250604/logs/hutao_personal_v2pro_clean_v2`
- `train.list`: 221 行。
- `2-name2text.txt`: 221 行。
- `5-wav32k`: 221 个 WAV。
- `4-cnhubert`: 221 个特征。
- `3-bert`: 221 个特征。
- `7-sv_cn`: 221 个 speaker vector。
- `6-name2semantic.tsv`: 222 行，包含 1 行表头和 221 条数据。

结论：

- clean_v2 标准化音频可以被 GPT-SoVITS 正常预处理。
- 可以开始训练 `hutao_personal_v2pro_clean_v2`。

### 2026-06-30 clean_v2 GPT-SoVITS 重新训练完成与聊天语音测试

本轮按用户要求重新训练聊天用 GPT-SoVITS 模型，目标是优先改善旧模型里的电流声、低电量感、口齿不清和语调不稳问题。训练数据使用 `clean_v2` 清洗后的 221 条样本，模型与训练产物全部保存在项目目录 `HutaoChatCore/external/GPT-SoVITS-v2pro-20250604` 下，没有放到 C 盘。

训练命令：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\run_hutao_gpt_sovits_training.py" --manifest "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\manifests\latest_hutao_voice_gpt_sovits_clean_v2.list" --exp-name hutao_personal_v2pro_clean_v2 --version v2Pro --stage all --s1-batch-size 2 --s1-epochs 30 --s1-num-workers 2 --s1-save-every-epoch 5 --s2-batch-size 2 --s2-epochs 30 --s2-num-workers 2 --s2-prefetch-factor 2 --s2-save-every-epoch 5
```

训练结果：

- 结果：PASS，训练进程退出码 0。
- S1 GPT 语义模型完成 30 轮；最终日志显示 `top_3_acc_epoch` 约 `0.989`。
- S1 训练阶段有 2 条样本因 phoneme/sec outlier 被内部过滤，实际 S1 数据长度为 219；这是 GPT-SoVITS 的内部保护，不是训练失败。
- S2 SoVITS 声学模型完成 30 轮；221 条样本全部进入 S2，`skipped_phone=0`，`skipped_dur=0`。
- 中间保存点：S2 第 5、10、15、20、25、30 轮均保存成功。
- 最终 GPT 权重：
  `external/GPT-SoVITS-v2pro-20250604/GPT_weights_v2Pro/hutao_personal_v2pro_clean_v2-e30.ckpt`
- 最终 SoVITS 权重：
  `external/GPT-SoVITS-v2pro-20250604/SoVITS_weights_v2Pro/hutao_personal_v2pro_clean_v2_e30_s3330.pth`

聊天语音流水线测试命令：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9885 --base-url "http://127.0.0.1:9885" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v2-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v2_e30_s3330.pth" --timeout-seconds 300
```

测试结果：

- 结果：PASS。
- 测试输出目录：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243`
- 测试报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/voice_chat_pipeline_smoke.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/voice_chat_pipeline_smoke.json`
- 所有合并音频均为 32kHz、单声道 WAV，`clip_ratio=0.0`，自动检查未发现削波。

本轮生成的 5 个聊天测试音频：

- 活泼夸奖：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/playful_greeting/playful_greeting_combined.wav`
  - 时长约 `9.80s`，RMS `3161.9`，peak `25424`，削波率 `0.0`。
- 安慰用户：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/comfort_user/comfort_user_combined.wav`
  - 时长约 `7.34s`，RMS `2845.5`，peak `21424`，削波率 `0.0`。
- 严肃项目排查：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/serious_project/serious_project_combined.wav`
  - 时长约 `5.60s`，RMS `3169.0`，peak `21616`，削波率 `0.0`。
- 短句调侃：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/teasing_short/teasing_short_combined.wav`
  - 时长约 `3.34s`，RMS `3185.2`，peak `23632`，削波率 `0.0`。
- 随意聊天：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_111243/casual_chat/casual_chat_combined.wav`
  - 时长约 `5.86s`，RMS `3658.0`，peak `27056`，削波率 `0.0`。

当前结论：

- 本轮 clean_v2 模型已经可以完成端到端聊天语音合成，基础音频格式和削波检查通过。
- 是否真正解决“电流声、低电量感、口齿不清、感情像复读机”的主观问题，需要用户优先试听上述 5 个 combined 音频。
- 如果本轮仍有明显电流声或口齿不清，下一步不要继续依赖后处理；应回到数据层，人工标记并剔除仍会诱发噪声/含混的训练样本，再补入少量高质量、情绪自然、口齿清楚的参考样本进行 `clean_v3`。
- 如果本轮声音干净但情绪不足，下一步应补充情绪分布，尤其是 `comforting` 和严肃但不压嗓的样本；不要简单把脏数据加回去。

### 2026-06-30 clean_v2 试听反馈与轻量参数优化

用户试听 `2026-06-30_111243` 版本后反馈：

- 整体“感觉还行”。
- 情绪自然度还不够。
- 口齿还差一点点效果。

判断：

- 当前 clean_v2 模型已经有可用底子，暂时不立即重训。
- 先做不重训的轻量优化：替换更短、更清楚、更稳定的参考音频；收紧 GPT-SoVITS 采样参数；缩短单段文本，优先改善口齿。
- 数据层仍有缺口：`clean_v2` 中真正温和、自然的 `comforting` 样本太少，安慰类情绪后续仍需要 `clean_v3` 补样本才能明显提升。

本次修改：

- `app/voice_chat/planner.py`
  - `playful` 参考从 `hutao_raw_0123` 改为 `hutao_raw_0120`。
    - 原参考 `hutao_raw_0123` 时长约 `8.15s`、强度 `1.0`，偏长且偏强。
    - 新参考 `hutao_raw_0120` 时长约 `3.26s`、强度 `0.614`，更短，适合轻快但不过度表演。
  - `teasing` 参考从 `hutao_raw_0123` 改为 `hutao_raw_0122`。
    - 新参考时长约 `4.33s`、强度 `0.627`，更适合轻微调侃。
  - `comforting` / `worried` 参考从 `hutao_raw_0142` 改为 `hutao_raw_0329`。
    - 原参考 `hutao_raw_0142` 文本为“无所事事比死亡可怕多了”，强度 `1.0`，不适合真正安慰。
    - 新参考为中性平稳样本，先用来降低安慰场景的强演感。
  - `neutral` 参考先尝试 `hutao_raw_0047`，但该音频仅约 `2.75s`，GPT-SoVITS API 要求参考音频在 3 到 10 秒之间，测试失败。
  - `neutral` 最终改为 `hutao_raw_0071`，时长约 `5.18s`，中性、稳定、合规。
  - 生成参数整体收紧：
    - 降低 `temperature` / `top_p`。
    - 提高 `repetition_penalty`。
    - 目标是优先提升口齿清楚度，减少含糊、吞字和随机怪音。
  - 分段更短：
    - 单段拆分阈值从约 18 字降到约 14 字。
    - 合并上限从约 22 字降到约 18 字。

验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\planner.py"
```

- 结果：PASS。

第一次优化测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9886 --base-url "http://127.0.0.1:9886" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v2-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v2_e30_s3330.pth" --timeout-seconds 300
```

- 结果：FAIL。
- 原因：`neutral` 参考 `hutao_raw_0047` 时长约 `2.75s`，GPT-SoVITS API 报错 `参考音频在3~10秒范围外`。
- 修复：`neutral` 改为 `hutao_raw_0071`。

第二次优化测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9887 --base-url "http://127.0.0.1:9887" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v2-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v2_e30_s3330.pth" --timeout-seconds 300
```

- 结果：PASS。
- 输出目录：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020`
- 报告：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/voice_chat_pipeline_smoke.md`
- 原始 JSON：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/voice_chat_pipeline_smoke.json`

优化版 5 个测试音频：

- 活泼夸奖：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/playful_greeting/playful_greeting_combined.wav`
  - 时长约 `6.84s`，RMS `2947.8`，peak `22960`，削波率 `0.0`。
  - 使用参考 `hutao_raw_0120`。
- 安慰用户：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/comfort_user/comfort_user_combined.wav`
  - 时长约 `4.68s`，RMS `3014.8`，peak `23776`，削波率 `0.0`。
  - 使用参考 `hutao_raw_0329`。
- 严肃项目排查：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/serious_project/serious_project_combined.wav`
  - 时长约 `7.32s`，RMS `3007.7`，peak `23072`，削波率 `0.0`。
  - 使用参考 `hutao_raw_0035`。
- 短句调侃：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/teasing_short/teasing_short_combined.wav`
  - 时长约 `6.48s`，RMS `3092.1`，peak `21568`，削波率 `0.0`。
  - 使用参考 `hutao_raw_0120` 与 `hutao_raw_0122`。
- 随意聊天：
  `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_122020/casual_chat/casual_chat_combined.wav`
  - 时长约 `10.34s`，RMS `3564.0`，peak `23024`，削波率 `0.0`。
  - 使用参考 `hutao_raw_0071`。

下一步判断标准：

- 如果 `2026-06-30_122020` 的口齿比 `2026-06-30_111243` 清楚，保留本次轻量优化。
- 如果情绪自然度仍明显不足，主要不是参数问题，而是 `clean_v2` 情绪样本不足，尤其是 `comforting`。下一步应做 `clean_v3`：补充温和安慰、轻松日常、自然调侃这三类高质量样本，并明确标注情绪强度。


### 2026-06-30 casual_chat ???????????
???? `2026-06-30_122020/casual_chat/casual_chat_combined.wav` ????

- `casual_chat_combined.wav` ???????
- ?????????
- ??????????????????

???

- `casual_chat` ????????????????????????? `??????????????` / `??????`????????????????????????????
- ????????????????????????????????????????????????clean_v2 ????????????????????????? `clean_v3` ?????????

??????????

- `app/voice_chat/planner.py`
  - ?? `casual` ?????? `hutao_raw_0240` ??????????
  - `casual` ????????`top_k=10`?`top_p=0.82`?`temperature=0.68`?`repetition_penalty=1.44`?`speed_factor=0.99`?????????????????
  - `split_long_text()` ??????????????????????/?/??/??/??/??/??/??/??/??????????????

???? casual ?????

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9888 --base-url "http://127.0.0.1:9888" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v2-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v2_e30_s3330.pth" --timeout-seconds 300 --scenarios casual_chat
```

???

- PASS?
- ?????`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_123134`
- ????`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_123134/casual_chat/casual_chat_combined.wav`
- ?????32kHz???????? `8.08s`?RMS ? `3784.0`?peak `25456`?`clip_ratio=0.0`?
- ??????`hutao_raw_0240` / `data/hutao_voice/raw/242.wav`?

????

- ?????? `casual_chat` ???????????????????
- ???????????????????????????????
- ??????????????????? `clean_v3`??????????????????????????????? `timbre_similarity`?`clarity`?`emotion_naturalness` ??????????


### 2026-06-30 casual_chat ?????????????
???? `casual_chat` ???????????`scripts/voice_chat_pipeline_smoke.py` ?????????? `session_id=voice-chat-pipeline-smoke`????? smoke ?????????????????????????????????????????????????????????? TTS ??????????????????????????????

?????

- `scripts/voice_chat_pipeline_smoke.py`
  - ???????? session?`voice-chat-pipeline-smoke-{???}-{???}`?
  - ????????????????????????????????????
- `app/voice_chat/planner.py`
  - `casual` ?????????`top_k=10`?`top_p=0.82`?`temperature=0.68`?`repetition_penalty=1.44`?`speed_factor=0.99`?
  - ????????????????????????

?????

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\planner.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py"
```

???PASS?

???? `casual_chat`?

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9890 --base-url "http://127.0.0.1:9890" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v2-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v2_e30_s3330.pth" --timeout-seconds 300 --scenarios casual_chat
```

???

- PASS?
- ?????`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_124024`
- ??????`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_124024/casual_chat/casual_chat_combined.wav`
- ???????`??????????????????????????????`
- ???
  - `???????????`
  - `?????????????`
  - `??????`
- ??????`hutao_raw_0240` / `data/hutao_voice/raw/242.wav`
- ???????32kHz???????? `7.60s`?RMS `3970.7`?peak `24848`?`clip_ratio=0.0`?

?????

- `2026-06-30_124024/casual_chat/casual_chat_combined.wav` ??????????????????
- ???????????????????? `casual` ??????????????
- ???????????????????? `clean_v3`????????????????????????????? `timbre_similarity`?`clarity`?`emotion_naturalness` ????????????????????????????


### 2026-06-30 GPT-SoVITS clean_v3 胡桃聊天模型训练与有效测试

目标：在不占满 RTX 4070 Laptop 8GB 显存的前提下，训练一个比 `clean_v2` 更贴近胡桃声线、情绪更多、口齿更稳定的聊天 TTS 模型。

数据集：

- 清单脚本：`scripts/export_hutao_clean_v3_manifest.py`
- 清单报告：`data/hutao_voice/reports/2026-06-30_125813_clean_v3/hutao-clean-v3-manifest-report.md`
- GPT-SoVITS 清单：`data/hutao_voice/manifests/latest_hutao_voice_gpt_sovits_clean_v3.list`
- 归一化音频：`data/hutao_voice/clean_v3/wavs`
- 总样本：356
- 可训练样本：315
- 屏蔽样本：41
- 总时长：约 26.85 分钟
- 文本清理：94 条
- 训练情绪分布：`playful=234`、`serious=60`、`neutral=16`、`comforting=5`
- 原始情绪分布：`surprised=157`、`happy=77`、`angry=60`、`neutral=14`、`sad=5`、`other=2`
- 屏蔽原因：过长 22、疑似削波 16、过短 3、低音量 2、主观已知坏样本 1、ASR 不可恢复 1

训练命令：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\run_hutao_gpt_sovits_training.py" --manifest "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\manifests\latest_hutao_voice_gpt_sovits_clean_v3.list" --exp-name hutao_personal_v2pro_clean_v3 --version v2Pro --stage all --s1-batch-size 2 --s1-epochs 30 --s1-num-workers 2 --s1-save-every-epoch 5 --s2-batch-size 2 --s2-epochs 30 --s2-num-workers 2 --s2-prefetch-factor 2 --s2-save-every-epoch 5
```

训练结果：

- Preprocess：PASS
  - `train.list`: 315
  - `2-name2text.txt`: 315
  - `5-wav32k`: 315
  - `4-cnhubert`: 315
  - `3-bert`: 315
  - `7-sv_cn`: 315
  - `6-name2semantic.tsv`: 316 行，含表头
- S1 GPT：30 epoch 完成
  - GPT-SoVITS 内部过滤 3 条 phoneme/sec 异常，实际 dataset length 为 312
  - 最终 top_3_acc_epoch 约 `0.990`
- S2 SoVITS：30 epoch 完成
  - `skipped_phone=0`
  - `skipped_dur=0`
  - 已保存 e5/e10/e15/e20/e25/e30 中间与最终权重

最终模型权重：

- GPT：`external/GPT-SoVITS-v2pro-20250604/GPT_weights_v2Pro/hutao_personal_v2pro_clean_v3-e30.ckpt`
- SoVITS：`external/GPT-SoVITS-v2pro-20250604/SoVITS_weights_v2Pro/hutao_personal_v2pro_clean_v3_e30_s4740.pth`

代码修复：

- `scripts/voice_chat_pipeline_smoke.py`
  - 修复 5 个测试场景中文输入、兜底回复、Markdown 报告模板的乱码。
  - 保留原有 API 启动、权重切换、分段合成、WAV 拼接逻辑。
- `app/voice_chat/planner.py`
  - 修复情绪关键词、分段标点、情绪理由的乱码。
  - 调整情绪优先级：先看用户意图，再看回复内容，避免 `casual_chat` 因回复中出现“累”被误判成 `comforting`。

验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\planner.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py"
```

- 结果：PASS

完整有效测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9892 --base-url "http://127.0.0.1:9892" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v3-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v3_e30_s4740.pth" --timeout-seconds 300
```

- 结果：PASS
- 输出目录：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552`
- 报告：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/voice_chat_pipeline_smoke.md`
- 原始 JSON：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/voice_chat_pipeline_smoke.json`
- 注意：`2026-06-30_135701` 那次测试输入文本仍是乱码，不能作为有效试听结论，已弃用。

有效测试音频：

- 夸奖/轻快：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/playful_greeting/playful_greeting_combined.wav`
  - 情绪：`playful`
  - 参考：`hutao_raw_0120`
  - 时长：`8.90s`
  - RMS：`3073.2`
  - peak：`21648`
  - clip_ratio：`0.0`
- 安慰：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/comfort_user/comfort_user_combined.wav`
  - 情绪：`comforting`
  - 参考：`hutao_raw_0329`
  - 时长：`6.26s`
  - RMS：`3020.7`
  - peak：`27904`
  - clip_ratio：`0.0`
- 技术认真回复：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/serious_project/serious_project_combined.wav`
  - 情绪：`serious`
  - 参考：`hutao_raw_0035`
  - 时长：`8.50s`
  - RMS：`3141.1`
  - peak：`25856`
  - clip_ratio：`0.0`
- 调侃：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/teasing_short/teasing_short_combined.wav`
  - 情绪：`teasing`
  - 参考：`hutao_raw_0122`
  - 时长：`5.82s`
  - RMS：`3293.2`
  - peak：`23920`
  - clip_ratio：`0.0`

`casual_chat` 修复后单独复测：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9893 --base-url "http://127.0.0.1:9893" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v3-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v3_e30_s4740.pth" --timeout-seconds 300 --scenarios casual_chat
```

- 结果：PASS
- 输出目录：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_141033`
- 闲聊音频：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_141033/casual_chat/casual_chat_combined.wav`
- 情绪：`casual`
- 参考：`hutao_raw_0240`
- 时长：`10.14s`
- RMS：`3372.4`
- peak：`24000`
- clip_ratio：`0.0`

当前判断：

- `clean_v3` 是当前聊天 TTS 主线候选，优先让用户试听 `2026-06-30_140552` 的四类音频和 `2026-06-30_141033/casual_chat/casual_chat_combined.wav`。
- 如果仍觉得音色不像胡桃，下一步不是继续盲目拉高 epoch，而是做样本集分层：优先筛选最像胡桃原声的 80 到 150 条高质量样本，单独训练 `timbre_focus` 对照组。
- 如果仍觉得情绪不自然，下一步应补 `comforting/casual/teasing` 高质量样本；当前 `clean_v3` 里 `comforting` 只有 5 条，安慰类上限仍受数据限制。
- 如果仍有电流声或口齿糊，下一步先对最终测试音频和训练集源音频做频谱/响度/削波对比，避免用后处理掩盖模型或数据问题。


### 2026-06-30 情绪增强小版本对照测试

用户反馈：

- `clean_v3` 这次效果非常不错，音色和整体自然度已经很接近。
- 当前主要短板是情绪表达还差一点，情绪幅度略保守。

本轮判断：

- 暂时不重训模型，先做最快可验证的情绪增强对照。
- 调整位置是 `app/voice_chat/planner.py`，只影响参考音频选择和 GPT-SoVITS 采样参数，不覆盖模型权重。

改动：

- `playful` 参考从 `hutao_raw_0120` 改为 `hutao_raw_0063`
  - 原始情绪：`happy`
  - 强度：`1.0`
  - 时长：约 `4.03s`
- `comforting` / `worried` 参考从 `hutao_raw_0329` 改为 `hutao_raw_0146`
  - 原始情绪：`sad`
  - 强度：`0.517`
  - 时长：约 `3.96s`
- `teasing` 参考继续使用 `hutao_raw_0122`
  - 原因：当前标注集中没有独立 `teasing` 类，先保留稳定参考，仅放开参数。
- `playful` 参数增强：
  - `top_k`: 16 -> 20
  - `top_p`: 0.88 -> 0.90
  - `temperature`: 0.78 -> 0.82
  - `repetition_penalty`: 1.36 -> 1.32
- `teasing` 参数增强：
  - `top_k`: 18 -> 20
  - `top_p`: 0.89 -> 0.90
  - `temperature`: 0.80 -> 0.82
  - `repetition_penalty`: 1.34 -> 1.32
- `comforting` 参数增强：
  - `top_k`: 12 -> 14
  - `top_p`: 0.84 -> 0.86
  - `temperature`: 0.68 -> 0.72
  - `repetition_penalty`: 1.42 -> 1.38
- 情绪强度：
  - 夸奖/轻快：`0.52` -> `0.64`
  - 安慰：`0.58` -> `0.64`
  - 调侃：`0.50` -> `0.60`

验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\planner.py"
```

- 结果：PASS

情绪增强对照测试命令：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\voice_chat_pipeline_smoke.py" --port 9894 --base-url "http://127.0.0.1:9894" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao_personal_v2pro_clean_v3-e30.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_personal_v2pro_clean_v3_e30_s4740.pth" --timeout-seconds 300 --scenarios playful_greeting comfort_user teasing_short
```

- 结果：PASS
- 输出目录：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_142400`
- 原始 JSON：`data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_142400/voice_chat_pipeline_smoke.json`

对照音频：

- 轻快/夸奖增强版：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_142400/playful_greeting/playful_greeting_combined.wav`
  - 情绪：`playful`
  - 强度：`0.64`
  - 参考：`hutao_raw_0063`
  - 时长：`6.94s`
  - RMS：`3096.0`
  - peak：`23024`
  - clip_ratio：`0.0`
  - 注意：这次 `playful_greeting` 使用了本地兜底回复，`live=False fallback=True`，只能用于 TTS 情绪对照，不作为完整聊天效果结论。
- 安慰增强版：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_142400/comfort_user/comfort_user_combined.wav`
  - 情绪：`comforting`
  - 强度：`0.64`
  - 参考：`hutao_raw_0146`
  - 时长：`5.96s`
  - RMS：`3088.8`
  - peak：`21824`
  - clip_ratio：`0.0`
- 调侃增强版：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_142400/teasing_short/teasing_short_combined.wav`
  - 情绪：`teasing`
  - 强度：`0.60`
  - 参考：`hutao_raw_0122`
  - 时长：`8.06s`
  - RMS：`2823.1`
  - peak：`24848`
  - clip_ratio：`0.0`

下一步判断：

- 请优先对比：
  - 旧版 `2026-06-30_140552/playful_greeting/playful_greeting_combined.wav`
  - 新版 `2026-06-30_142400/playful_greeting/playful_greeting_combined.wav`
  - 旧版 `2026-06-30_140552/comfort_user/comfort_user_combined.wav`
  - 新版 `2026-06-30_142400/comfort_user/comfort_user_combined.wav`
  - 旧版 `2026-06-30_140552/teasing_short/teasing_short_combined.wav`
  - 新版 `2026-06-30_142400/teasing_short/teasing_short_combined.wav`
- 如果新版情绪更足且没有明显口齿退化，保留本轮 planner 调整。
- 如果新版情绪更足但口齿变糊，回退一部分采样参数，优先保留参考音频替换。
- 如果新版情绪仍不够，下一步应补 `comforting/casual/teasing` 高质量样本后训练 `clean_v4_emotion`，不是继续只调参数。

试听结论与回退：

- 用户试听后反馈：`2026-06-30_142400` 情绪增强版“不如旧版本的语音”。
- 结论：强情绪参考音频与更开放采样参数虽然提高了情绪幅度，但破坏了当前最重要的音色/口齿/自然度平衡。
- 已回退 `app/voice_chat/planner.py` 到旧版稳定配置：
  - `playful`: `hutao_raw_0120`
  - `comforting`: `hutao_raw_0329`
  - `worried`: `hutao_raw_0329`
  - `teasing`: `hutao_raw_0122`
  - `playful` 参数恢复为 `top_k=16`、`top_p=0.88`、`temperature=0.78`、`repetition_penalty=1.36`、`speed_factor=1.0`
  - `comforting/worried` 参数恢复为 `top_k=12`、`top_p=0.84`、`temperature=0.68`、`repetition_penalty=1.42`、`speed_factor=0.98`
  - `teasing` 参数恢复为 `top_k=18`、`top_p=0.89`、`temperature=0.80`、`repetition_penalty=1.34`、`speed_factor=1.0`
- 回退验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\planner.py"
```

- 结果：PASS
- 当前默认应继续使用旧版稳定试听结果：
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/playful_greeting/playful_greeting_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/comfort_user/comfort_user_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/serious_project/serious_project_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_140552/teasing_short/teasing_short_combined.wav`
  - `data/hutao_voice/tests/voice_chat_pipeline/2026-06-30_141033/casual_chat/casual_chat_combined.wav`
- 后续提升情绪不要继续盲目放开采样参数。下一步应补充更贴合胡桃声线、但情绪更自然的 `comforting/casual/teasing` 样本，再训练 `clean_v4_emotion` 或做小规模对照训练。


### 2026-06-30 胡桃听觉系统与说话系统端到端整合

目标：

- 把“听觉系统”和“说话系统”串起来，形成可测试链路：
  1. 用户音频输入
  2. FunASR/SenseVoice 语音转文字
  3. emotion2vec 音频情绪识别
  4. `ChatService` 调用胡桃大脑生成回复
  5. `voice_chat.planner` 规划 TTS 情绪、参考音频、分段和参数
  6. GPT-SoVITS clean_v3 合成胡桃回复语音
  7. 输出最终 WAV 与测试报告

新增脚本：

- `scripts/hutao_listen_speak_smoke.py`

脚本特点：

- 不新增独立业务逻辑，直接复用现有模块：
  - ASR：`app.audio.file_service.transcribe_audio_file`
  - 大脑：`app.services.chat_service.ChatService`
  - 说话规划：`app.voice_chat.planner.plan_voice_chat`
  - WAV 拼接/统计：`app.voice_chat.audio_utils`
  - TTS API 调用：复用 `scripts.gpt_sovits_hutao_tts_smoke` 中的 GPT-SoVITS API 工具函数
- 默认使用当前主线模型：
  - GPT：`external/GPT-SoVITS-v2pro-20250604/GPT_weights_v2Pro/hutao_personal_v2pro_clean_v3-e30.ckpt`
  - SoVITS：`external/GPT-SoVITS-v2pro-20250604/SoVITS_weights_v2Pro/hutao_personal_v2pro_clean_v3_e30_s4740.pth`
- 输出内容包含：
  - ASR 文本
  - ASR 情绪
  - ASR 质量
  - 胡桃回复
  - 是否 live API / fallback
  - TTS 主情绪
  - 分段参考音频
  - 最终胡桃语音 WAV
  - WAV 时长/RMS/peak/clip_ratio

验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py"
```

- 结果：PASS

单条端到端测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py" --port 9895 --base-url "http://127.0.0.1:9895" --audio-path "D:\Programming-file\Graduation-Project\HutaoChatCore\data\asr_samples\funasr-zh-example-001.wav" --timeout-seconds 300
```

- 结果：PASS
- 输出目录：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144405`
- 报告：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144405/hutao_listen_speak_smoke.md`
- 原始 JSON：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144405/hutao_listen_speak_smoke.json`
- 输入音频：`data/asr_samples/funasr-zh-example-001.wav`
- ASR 文本：`欢迎大家来体验达摩院推出的语音识别模型。`
- ASR 情绪：`neutral / emotion2vec / 1.0`
- 胡桃回复：`什么达摩院，我耳朵只认活人说话，可别把本堂主当成铁疙瘩。`
- 回复来源：`DeepSeek live=True fallback=False`
- TTS 主情绪：`serious / 0.48`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144405/case_01_funasr-zh-example-001/funasr-zh-example-001_hutao_reply.wav`
- 输出统计：`duration=5.72s`、`sample_rate=32000`、`rms=3314.8`、`peak=25952`、`clip_ratio=0.0`

三条公开中文样本端到端测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py" --port 9896 --base-url "http://127.0.0.1:9896" --manifest "D:\Programming-file\Graduation-Project\HutaoChatCore\data\asr_samples\manifest.json" --limit 3 --timeout-seconds 300
```

- 结果：PASS
- 输出目录：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144935`
- 报告：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144935/hutao_listen_speak_smoke.md`
- 原始 JSON：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144935/hutao_listen_speak_smoke.json`

样本 1：

- 输入音频：`data/asr_samples/funasr-zh-example-001.wav`
- ASR 文本：`欢迎大家来体验达摩院推出的语音识别模型。`
- ASR 情绪：`neutral / emotion2vec / 1.0`
- 胡桃回复：`哟，嗓门挺亮堂嘛，达摩院还揽这活儿？听着比往生堂开张还热闹。`
- 回复来源：`DeepSeek live=True fallback=False`
- TTS 主情绪：`serious / 0.48`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144935/case_01_funasr-zh-example-001/funasr-zh-example-001_hutao_reply.wav`
- 输出统计：`duration=8.06s`、`sample_rate=32000`、`rms=3258.3`、`peak=25328`、`clip_ratio=0.0`

样本 2：

- 输入音频：`data/asr_samples/openspeech-mandarin-0072-8k.wav`
- ASR 文本：`院子门口不远处就是一个地铁站，这是一个美丽而神奇的景象。，树上长满了又大又甜的桃子，海豚和金鱼的表演是很好看的。节目。邮局门前的人行道上有一个蓝色的油箱。`
- ASR 情绪：`neutral / emotion2vec / 1.0`
- ASR 质量：`quality_passed=False`，原因 `punctuation_collision`
- 胡桃回复：`哎？这串话搁这儿随机组合呢？怎么地铁站结桃子树，海豚还跑邮局门口表演啦？`
- 回复来源：`DeepSeek live=True fallback=False`
- TTS 主情绪：`neutral / 0.35`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144935/case_02_openspeech-mandarin-0072-8k/openspeech-mandarin-0072-8k_hutao_reply.wav`
- 输出统计：`duration=8.06s`、`sample_rate=32000`、`rms=3359.7`、`peak=23248`、`clip_ratio=0.0`

样本 3：

- 输入音频：`data/asr_samples/openspeech-mandarin-0073-8k.wav`
- ASR 文本：`他用画笔为自己画了一幅美丽的人生蓝图，一只白鹅站在河畔的浅水里，宿舍楼旁边的十字路口有一个公共汽车站，夏日的夕阳很美丽，尤其是夏日大平原的夕阳，。那个年代已经一去不复返了。`
- ASR 情绪：`neutral / emotion2vec / 1.0`
- ASR 质量：`quality_passed=False`，原因 `punctuation_collision`
- 胡桃回复：`这画面挺有意境的嘛——白鹅浅水、夕阳车站，听着像老电影里的一帧，安静得都有点舍不得出声了。`
- 回复来源：`DeepSeek live=True fallback=False`
- TTS 主情绪：`neutral / 0.35`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_144935/case_03_openspeech-mandarin-0073-8k/openspeech-mandarin-0073-8k_hutao_reply.wav`
- 输出统计：`duration=10.14s`、`sample_rate=32000`、`rms=3392.2`、`peak=23280`、`clip_ratio=0.0`

当前结论：

- 听觉系统与说话系统已经端到端串通，并通过真实 ASR、真实 DeepSeek 回复、真实 GPT-SoVITS 合成测试。
- 当前输出音频无削波，`clip_ratio=0.0`。
- 当前 ASR 对部分公开样本会出现 `punctuation_collision`，但系统仍能生成回复和语音；后续可在正式交互前加入 ASR 文本清理层，把重复/异常标点修掉再送入大脑。
- 当前报告文件在部分 PowerShell 输出里会显示乱码，但 JSON 文件实际是 UTF-8 正常中文；不要根据终端渲染判断内容坏掉。

### 2026-06-30 听觉+说话联调音质问题定位与修复

用户反馈：

- 端到端出来的声音效果差，出现口齿不清、电音、拼接不行的问题。

定位结论：

- 这次差效果主要不是 `clean_v3` 权重突然退化，而是联调链路把问题放大了。
- 公开 ASR 样本不是正常聊天语境，文本长且不自然，容易让胡桃大脑生成偏长回复。
- ASR 结果里会出现 `punctuation_collision`，例如 `，。`、`？，` 这类异常标点；旧链路会把脏文本直接送入大脑和 TTS。
- 多段 TTS 再做 WAV 拼接时，会进一步放大断句、口齿和接缝问题。
- 因此“电音/口齿不清/拼接不行”需要拆开判断：拼接问题已可通过单段输出隔离；若单段仍有电音或咬字差，则主要是 GPT-SoVITS 模型、参考音频和推理参数质量问题。

代码修复：

- 修改 `scripts/hutao_listen_speak_smoke.py`。
- 新增 ASR 文本清洗：去掉多余空白，修复重复标点和 `。，`、`，。`。
- 将辅助函数移动到 `main()` 调用前，避免运行时函数尚未定义。
- 端到端默认使用单段稳定 TTS，减少实时聊天测试中的拼接伪影。
- 单段模式下最终 WAV 直接复制 TTS 生成文件，不再经过拼接淡入淡出处理。
- ASR 质量门调整：`punctuation_collision` 不再直接判定“没听清”，而是清洗后继续送入大脑；空文本、过短、过长仍走澄清回复。
- 保留 `--allow-multi-segment-tts`，需要测试多段拼接时再显式打开。

验证命令：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py"
```

- 结果：PASS

测试 1：公开官方中文样本，验证异常标点拦截和单段输出。

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py" --port 9897 --base-url "http://127.0.0.1:9897" --audio-path "D:\Programming-file\Graduation-Project\HutaoChatCore\data\asr_samples\official\zh.mp3" --timeout-seconds 300
```

- 结果：PASS
- ASR 文本：`开放时间早上9点至下午5点，。`
- 清洗后送入大脑文本：`开放时间早上9点至下午5点。`
- ASR 情绪：`neutral / emotion2vec / 1.0`
- ASR 质量：`quality_passed=False`，原因 `punctuation_collision`
- 是否走澄清回复：`True`
- 胡桃回复：`我刚才没听清，你短一点再说一遍。`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_164553/case_01_zh/zh_hutao_reply.wav`
- 输出统计：`duration=3.2s`、`sample_rate=32000`、`rms=3139.5`、`peak=22304`、`clip_ratio=0.0`

测试 2：使用旧版较稳定胡桃语音作为输入，验证质量门过严问题。

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py" --port 9898 --base-url "http://127.0.0.1:9898" --audio-path "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\voice_chat_pipeline\2026-06-30_141033\casual_chat\casual_chat_combined.wav" --timeout-seconds 300
```

- 结果：PASS
- ASR 文本：`成，那就唠唠，。你最近有没有碰上什么怪事？，正经的夜宵，不正经的更好。本堂主全烧。`
- 清洗后送入大脑文本：`成，那就唠唠。你最近有没有碰上什么怪事。正经的夜宵，不正经的更好。本堂主全烧。`
- ASR 情绪：`surprised / emotion2vec / 0.9988794922828674`
- ASR 质量：`quality_passed=False`，原因 `punctuation_collision`
- 是否走澄清回复：`True`
- 结论：文本实际可读，但旧质量门因异常标点直接拦截，过严。

测试 3：放宽 `punctuation_collision` 后重跑完整链路。

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py" --port 9899 --base-url "http://127.0.0.1:9899" --audio-path "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\voice_chat_pipeline\2026-06-30_141033\casual_chat\casual_chat_combined.wav" --timeout-seconds 300
```

- 结果：PASS
- ASR 文本：`成，那就唠唠，。你最近有没有碰上什么怪事？，正经的夜宵，不正经的更好。本堂主全烧。`
- 清洗后送入大脑文本：`成，那就唠唠。你最近有没有碰上什么怪事。正经的夜宵，不正经的更好。本堂主全烧。`
- ASR 情绪：`surprised / emotion2vec / 0.9988794922828674`
- 是否走澄清回复：`False`
- 胡桃回复：`哟，抢我台词呢？那你先说说，不正经的怪事我这儿存货可多。`
- 回复来源：`deepseek / deepseek-v4-pro / live=True / fallback=False`
- TTS 文本：`哟，抢我台词呢？那你先说说，不正经的怪事我这儿存货可多。`
- TTS 主情绪：`neutral / 0.35`
- TTS 分段数：`1`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_165242/case_01_casual_chat_combined/casual_chat_combined_hutao_reply.wav`
- 输出统计：`duration=6.26s`、`sample_rate=32000`、`rms=3368.9`、`peak=24496`、`clip_ratio=0.0`

当前结论：

- 听觉系统和说话系统已经能完成端到端联通：音频输入 -> ASR -> emotion2vec 情绪 -> DeepSeek 胡桃回复 -> GPT-SoVITS clean_v3 合成 -> WAV 输出。
- 当前默认单段输出已经排除“拼接函数导致接缝噪声”的主要干扰。
- `clip_ratio=0.0`，没有检测到削波爆音。
- 如果用户试听 `2026-06-30_165242` 输出后仍觉得电音或口齿不清，问题就主要落在 TTS 模型质量、参考音频选择、训练数据清洁度和推理参数，而不是听觉/大脑联调代码。
- 后续真实测试应尽量使用用户真人短句录音，例如“胡桃，今天项目有点累，陪我聊两句”，不要用公开朗读长样本判断聊天音质。

### 2026-06-30 项目主链路逻辑修复：音频聊天输入与实时 TTS 文本

目标：

- 用户确认上一轮音频“还行”，要求继续完善整个项目文件并修复逻辑。
- 本次不重新训练模型，优先修主链路中会导致真实运行和测试脚本行为不一致的问题。

问题定位：

- 上一轮 ASR 清洗、质量门、单段 TTS 稳定逻辑只存在于 `scripts/hutao_listen_speak_smoke.py`。
- 正式 API `/api/v1/audio/chat/file` 仍会把原始 ASR 文本直接送入 `ChatService`，例如 `，。`、`？，` 这类异常标点会继续污染大脑回复。
- 低质量乱码 ASR 旧逻辑仍可能进入大脑，造成无意义回复和后续 TTS 糊音。
- 端到端脚本里的实时 TTS 文本压缩会简单取第一句，导致胡桃完整回复被截得太短，听起来像只说半句话。

代码修复：

- 新增 `app/audio/chat_input.py`：
  - `clean_asr_text_for_chat()`：清洗 ASR 异常标点，保留问号/感叹号语气。
  - `prepare_audio_chat_input()`：统一判断音频输入是否应该继续送入大脑。
  - `CLARIFICATION_REPLY`：统一“没听清”澄清话术。
- 修改 `app/main.py`：
  - `/api/v1/audio/chat/file` 改为先调用 `prepare_audio_chat_input()`。
  - 可修复的 `punctuation_collision` 清洗后继续进入大脑。
  - 乱码、空文本、过短、过长等阻断质量问题直接返回澄清回复，不调用大脑。
- 修改 `app/audio/schemas.py`：
  - `AudioChatFileResponse` 新增 `chat_input_text`、`chat_bypassed_due_to_asr_quality`、`chat_bypass_reasons`，便于测试和前端判断。
- 修改 `scripts/hutao_listen_speak_smoke.py`：
  - 改用 `app/audio/chat_input.py` 的正式逻辑，避免脚本和 API 分叉。
- 修改 `app/voice_chat/naturalness.py`：
  - 新增 `constrain_reply_for_realtime_tts()`。
  - 实时 TTS 不再简单只取第一句，而是在长度内尽量保留第二句关键信息。
- 修改 `tests/test_app.py`：
  - 覆盖 ASR 异常标点清洗。
  - 覆盖低质量 ASR 直接澄清且不调用大脑。
  - 覆盖正式音频聊天 API 使用清洗文本。
  - 覆盖实时 TTS 文本压缩不会只留下第一小句。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

- 结果：PASS
- 通过数量：`106 passed`
- 备注：pytest 仍提示 `.pytest_cache` 写入被拒绝，这是本地缓存目录权限问题，不影响测试结果。

端到端验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\hutao_listen_speak_smoke.py" --port 9901 --base-url "http://127.0.0.1:9901" --audio-path "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\voice_chat_pipeline\2026-06-30_141033\casual_chat\casual_chat_combined.wav" --timeout-seconds 300
```

- 结果：PASS
- 输入 ASR：`成，那就唠唠，。你最近有没有碰上什么怪事？，正经的夜宵，不正经的更好。本堂主全烧。`
- 清洗后送入大脑：`成，那就唠唠。你最近有没有碰上什么怪事？正经的夜宵，不正经的更好。本堂主全烧。`
- ASR 质量：`quality_passed=False`，原因 `punctuation_collision`
- 是否澄清：`False`
- 胡桃回复：`昨晚梦见鬼差抱着手机数二维码，嘴里还念叨“这单咋没付钱”——算不算怪？`
- 实时 TTS 文本：`昨晚梦见鬼差抱着手机数二维码，嘴里还念叨“这单咋没付钱”，算不算怪？`
- TTS 分段数：`1`
- 输出语音：`data/hutao_voice/tests/listen_speak_pipeline/2026-06-30_170814/case_01_casual_chat_combined/casual_chat_combined_hutao_reply.wav`
- 输出统计：`duration=7.08s`、`sample_rate=32000`、`rms=3667.4`、`peak=20560`、`clip_ratio=0.0`

当前结论：

- 正式音频聊天 API、端到端联调脚本已经共用同一套 ASR 清洗和质量门逻辑。
- 可修复的异常标点不会再错误触发“没听清”，也不会把脏文本原样送进大脑。
- 明显坏掉的 ASR 不再进入大脑，避免污染记忆、人格回复和 TTS。
- 实时 TTS 输出仍保持单段稳定，但文本不再机械截第一句，试听信息完整度更好。

### 2026-07-01 QQ 机器人桥接部署：NapCatQQ + NoneBot2 + OneBot v11

目标：

- 先做 QQ 接入，不先接微信。
- 采用 `NapCatQQ + NoneBot2 + OneBot v11`。
- 现阶段先做文字版：QQ 文本消息 -> HutaoChatCore `/api/v1/chat` -> QQ 文本回复。
- 语音输入和胡桃语音回复等文字链路稳定后再接。

依赖安装：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pip install "nonebot2[fastapi,httpx]" "nonebot-adapter-onebot"
```

- 结果：安装成功。
- 注意：pip 提示 `Defaulting to user installation because normal site-packages is not writeable`。这不是创建新虚拟环境，仍然是使用 `new` 环境的 Python，只是包安装到了当前用户 site-packages。

配置更新：

- `requirements.txt`
  - 新增 `nonebot2[fastapi,httpx]==2.5.0`
  - 新增 `nonebot-adapter-onebot==2.4.6`
- `.env.example`
  - 新增 QQ 桥接配置。
- `.env`
  - 新增 QQ 桥接配置，默认 `QQ_BOT_ENABLED=false`。
  - 未写入任何 QQ 账号、密码或 token。

新增文件：

- `integrations/__init__.py`
- `integrations/qq_bot/__init__.py`
- `integrations/qq_bot/config.py`
- `integrations/qq_bot/hutao_client.py`
- `integrations/qq_bot/message_policy.py`
- `integrations/qq_bot/bot.py`
- `integrations/qq_bot/README.md`
- `scripts/run_qq_bot.py`

当前 QQ 桥接行为：

- 使用 NoneBot2 监听 `127.0.0.1:8080`。
- NapCatQQ 需要配置 OneBot v11 反向 WebSocket：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

- 私聊默认可触发。
- 群聊默认需要 @ 胡桃，即 `QQ_BOT_REQUIRE_MENTION_IN_GROUP=true`。
- 支持 `QQ_BOT_ALLOWED_USERS` 和 `QQ_BOT_ALLOWED_GROUPS` 白名单。
- 支持命令前缀 `QQ_BOT_COMMAND_PREFIX=胡桃`，例如 `胡桃 今天项目有点累` 会送入大脑为 `今天项目有点累`。
- 调用 HutaoChatCore 地址由 `HUTAO_CORE_BASE_URL=http://127.0.0.1:8000` 控制。

启动 HutaoChatCore：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动 QQ bridge：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\run_qq_bot.py
```

启动验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\run_qq_bot.py
```

- 结果：PASS
- NoneBot 初始化成功。
- OneBot V11 adapter 加载成功。
- 服务监听：`http://127.0.0.1:8080`
- 当前未登录 QQ、未连接 NapCat，因此只能验证本地桥接服务可启动。

测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

- 结果：PASS
- 通过数量：`108 passed`
- 备注：pytest 仍提示 `.pytest_cache` 权限写入失败，不影响测试结果。

关于是否需要 Codex 登录 QQ：

- 不需要，也不应该让 Codex 登录 QQ。
- QQ 登录需要用户本人在 NapCatQQ 中操作，Codex 不需要知道 QQ 号密码。
- Codex 只负责本地桥接服务、配置、消息转发逻辑和测试。
- 等用户登录 NapCatQQ 并配置反向 WebSocket 后，NapCat 会把 QQ 消息事件推给本地 NoneBot 服务。

后续测试前需要用户完成：

1. 登录 NapCatQQ 小号。
2. 在 NapCatQQ 配置 OneBot v11 反向 WebSocket：`ws://127.0.0.1:8080/onebot/v11/ws`。
3. 将 `.env` 中 `QQ_BOT_ENABLED=false` 改为 `QQ_BOT_ENABLED=true`。
4. 按需填写 `QQ_BOT_ALLOWED_USERS` 或 `QQ_BOT_ALLOWED_GROUPS`。
5. 同时启动 HutaoChatCore 和 QQ bridge。

下一阶段：

- 用户登录 QQ 后，测试 QQ 私聊文字链路。
- 再测试群聊 @ 胡桃链路。
- 文字稳定后，再接 QQ 语音输入：QQ 语音文件下载 -> 转码 -> `/api/v1/audio/chat/file`。
- 最后接胡桃语音回复：GPT-SoVITS 输出 -> 平台语音格式转换 -> QQ 发语音。

### 2026-07-01 QQ 接入继续开发：预检、NapCat 下载、本地 Smoke

目标：

- 按“先做到需要用户登录 QQ 时再停”的要求继续推进。
- 每个新增功能都要有测试。

新增脚本：

- `scripts/qq_bot_preflight.py`
  - 检查 NoneBot2 是否可导入。
  - 检查 OneBot v11 adapter 是否可导入。
  - 检查 QQ bridge 端口 `127.0.0.1:8080` 是否可用。
  - 可选检查 HutaoChatCore `/health`。
  - 输出 NapCat 需要配置的反向 WebSocket 地址。
- `scripts/download_napcat.py`
  - 从 NapCatQQ GitHub latest release 选择 Windows zip 包。
  - 下载并解压到 `external/NapCatQQ`。
  - 如果 GitHub 下载失败，会写入 `external/NapCatQQ/NAPCAT_MANUAL_DOWNLOAD.txt` 手动说明。
- `scripts/qq_bot_local_smoke.py`
  - 本地启动一个假的 HutaoCore。
  - 用 `HutaoCoreClient` 调用 `/api/v1/chat`。
  - 不需要 QQ 登录，用于验证桥接客户端链路。
- `scripts/run_napcat.py`
  - 从项目内 `external/NapCatQQ` 启动 NapCat。
  - 启动时提示 WebUI 和 OneBot v11 反向 WebSocket 地址。

文档更新：

- `integrations/qq_bot/README.md`
  - 新增 NapCat 下载命令。
  - 新增 NapCat 启动命令。
  - 新增 preflight 和 local smoke 命令。

NapCat 下载结果：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\download_napcat.py"
```

- 结果：PASS
- 下载文件：`external/NapCatQQ/NapCat.Shell.Windows.Node.zip`
- 解压目录：`external/NapCatQQ`
- 已确认存在：
  - `external/NapCatQQ/node.exe`
  - `external/NapCatQQ/index.js`
  - `external/NapCatQQ/napcat.bat`

预检结果：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\qq_bot_preflight.py" --json
```

- 结果：PASS
- `nonebot2_import=true`
- `onebot_adapter_import=true`
- `qq_bridge_port_available=true`
- `hutao_core_health=false`，原因是测试时 HutaoChatCore 没有启动；非 `--require-core` 模式下允许。
- NapCat 反向 WebSocket：`ws://127.0.0.1:8080/onebot/v11/ws`

本地 Smoke：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\qq_bot_local_smoke.py"
```

- 结果：PASS
- 回复：`收到，本堂主已经接上 QQ 了。`
- 说明：不需要 QQ 登录，只验证 `HutaoCoreClient` 和 `/api/v1/chat` 调用链路。

单元测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

- 结果：PASS
- 通过数量：`111 passed`
- 新增覆盖：
  - QQ 消息策略。
  - NapCat release asset 选择。
  - NapCat 手动下载说明生成。
  - QQ preflight 模块检查。

当前已经到达需要用户操作的位置：

- 代码、依赖、NapCat 包、本地预检、本地 smoke 都已完成。
- 下一步必须由用户登录 QQ 小号并在 NapCat WebUI 配置网络项。
- Codex 不需要也不应该登录 QQ。

用户下一步操作：

1. 将 `.env` 中 `QQ_BOT_ENABLED=false` 改为 `QQ_BOT_ENABLED=true`。
2. 启动 HutaoChatCore：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. 启动 QQ bridge：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\run_qq_bot.py
```

4. 启动 NapCat：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\run_napcat.py
```

5. 在 NapCat 中登录 QQ 小号。
6. 打开 NapCat WebUI，通常是 `http://127.0.0.1:6099/webui/`。
7. 在网络配置中新建 OneBot v11 WebSocket Client，URL 填：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

8. 发送 QQ 私聊文字测试，例如：

```text
胡桃 今天项目有点累，陪我聊两句
```

### 2026-07-01 QQ 接入一键启动脚本

目标：

- 用户不想分别运行 HutaoChatCore、QQ bridge、NapCat 三个命令。
- 新增一个脚本统一启动 QQ 接入栈，并在 Ctrl+C 时统一关闭。

新增文件：

- `scripts/start_qq_stack.py`
  - 一次启动 HutaoChatCore、QQ bridge、NapCatQQ。
  - 子进程临时设置 `QQ_BOT_ENABLED=true`，不强制修改 `.env`。
  - 日志写入 `logs/qq_stack/`：
    - `hutao_core.log`
    - `qq_bridge.log`
    - `napcat.log`
  - 控制台输出 NapCat WebUI 和 OneBot v11 反向 WebSocket 地址。
  - 支持 `--no-napcat` 做短启动验证。
  - 支持 `--no-core` 只启动 QQ bridge 和 NapCat。
- `scripts/start_qq_stack.bat`
  - Windows 一键入口。
  - 使用指定 `new` 环境 Python：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`

文档更新：

- `integrations/qq_bot/README.md`
  - 新增一键启动命令。

使用方式：

```powershell
scripts\start_qq_stack.bat
```

或：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\start_qq_stack.py
```

短启动验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_qq_stack.py" --no-napcat --wait-seconds 4
```

- 结果：PASS
- HutaoCore 监听：`127.0.0.1:8000`
- QQ bridge 监听：`127.0.0.1:8080`
- HutaoCore `/health` 返回 200。
- QQ bridge 成功加载 OneBot V11 adapter。
- 验证结束后已停止测试进程。

单元测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "start_qq_stack" -q
```

- 结果：PASS
- 覆盖：
  - 三个子进程命令构造。
  - 临时环境变量 `QQ_BOT_ENABLED=true`。

全量测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests" -q
```

- 结果：PASS
- 通过数量：`113 passed`

当前下一步：

- 用户只需要运行 `scripts\start_qq_stack.bat`。
- 然后在 NapCat 登录 QQ 小号。
- 在 NapCat WebUI 配置 OneBot v11 WebSocket Client：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

### 2026-07-01 QQ 一键启动提示修复：区分 WebUI 和 WebSocket 地址

用户反馈：

- 运行一键脚本后，浏览器打开 `ws://127.0.0.1:8080/onebot/v11/ws` 失败。
- 终端显示 `QQ bridge port: WAITING/FAIL`，造成误解。

原因：

- `ws://127.0.0.1:8080/onebot/v11/ws` 是给 NapCat 网络配置使用的 WebSocket 地址，不是网页地址，浏览器不能直接打开。
- 真正需要在浏览器打开的是 NapCat WebUI：`http://127.0.0.1:6099/webui/`。
- 旧脚本用 HTTP GET `http://127.0.0.1:8080/` 检查 QQ bridge，而 NoneBot 根路径返回 404，导致端口已启动却显示 `WAITING/FAIL`。

修复：

- 修改 `scripts/start_qq_stack.py`：
  - 新增 TCP 端口检查 `wait_for_tcp()`。
  - `QQ bridge port` 改为检查 `127.0.0.1:8080` TCP 是否可连接。
  - 输出文字明确说明：
    - 浏览器打开：`http://127.0.0.1:6099/webui/`
    - 不要在浏览器打开 `ws://...`
    - `ws://127.0.0.1:8080/onebot/v11/ws` 要填到 NapCat WebUI 的网络配置里。
- 修改 `integrations/qq_bot/README.md`：
  - 明确 `ws://` 不是网页。
- 修改 `tests/test_app.py`：
  - 新增 `wait_for_tcp()` 测试。

当前实际运行状态：

- 用户截图对应运行中进程已确认：
  - HutaoCore：`127.0.0.1:8000` 监听中。
  - QQ bridge：`127.0.0.1:8080` 监听中。
  - NapCat WebUI：`6099` 监听中。
- 因此下一步不是打开 `ws://...`，而是打开：

```text
http://127.0.0.1:6099/webui/
```

测试：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "start_qq_stack" -q
```

- 结果：PASS
- 通过数量：`3 passed`

### 2026-07-01 NapCat WebUI Token 与 OneBot WebSocket 配置说明

用户疑问：

- `ws://127.0.0.1:8080/onebot/v11/ws` 难道不是要填的东西吗？

说明：

- 是要填，但不是填在 NapCat WebUI 登录页的 Token 输入框。
- NapCat WebUI 登录页 Token 要填 NapCat 启动日志里的 WebUI Token。
- 登录 WebUI 后，进入网络配置，创建 OneBot v11 WebSocket Client，才填：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

本次日志中检测到：

- WebUI Token：`62a98b1d59e8`
- 也可以直接打开带 token 的地址：

```text
http://127.0.0.1:6099/webui?token=62a98b1d59e8
```

修复：

- 修改 `scripts/start_qq_stack.py`，启动提示改成三步：
  1. 浏览器打开 NapCat WebUI。
  2. WebUI Token 不是 `ws://` 地址，要从 NapCat 启动日志获取。
  3. 登录 WebUI 后，在网络配置里填 `ws://127.0.0.1:8080/onebot/v11/ws`。
- 新增 `docs/qq-napcat-login-guide.md`，记录登录和连接说明。
- 更新 `integrations/qq_bot/README.md`，明确 WebUI Token 和 OneBot WebSocket URL 的区别。

验证：

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_qq_stack.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "start_qq_stack" -q
```

- 结果：PASS
- 通过数量：`3 passed`

### 2026-07-01 QQ 私聊免唤醒词与上下文实测

用户反馈：

- QQ 私聊效果基本可用，但每次都写“胡桃”唤醒太麻烦。
- 需要确认 QQ 对话上下文是否真的做好。

当前规则：

- 私聊：不再要求消息以 `胡桃` 开头，直接发普通消息也会进入胡桃对话。
- 群聊：仍然受控触发。当前配置 `QQ_BOT_REQUIRE_MENTION_IN_GROUP=true` 时，需要先 @ 胡桃；代码里仍要求带 `QQ_BOT_COMMAND_PREFIX=胡桃`，避免群里误触发。
- 私聊 session：`qq-private-{user_id}`。
- 群聊 session：`qq-group-{group_id}-user-{user_id}`。
- user_id：`qq-{user_id}`。

修复：

- 修改 `integrations/qq_bot/message_policy.py`：私聊可以无 `胡桃` 前缀直接进入对话；群聊保持 @ 和前缀保护。
- 修改 `scripts/qq_context_status.py`：支持当前 MySQL 存储后端的 QQ 上下文诊断，并修复 MySQL `LIKE` 参数绑定问题。
- 修改 `tests/test_app.py`：增加私聊免前缀、群聊前缀保护、QQ 上下文诊断测试；上下文测试固定使用临时 JSONL 存储，避免被真实 `.env` 的 MySQL 配置影响。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\qq_context_status.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\message_policy.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "qq_message_policy or qq_context_status" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\qq_context_status.py" --qq-user-id 3471764547 --limit 20
```

测试结果：

- 编译检查：PASS。
- 定向测试：`5 passed, 112 deselected`。
- 真实 MySQL 上下文诊断：PASS。
- 数据库：`hutao_chat`。
- QQ 用户：`3471764547`。
- QQ session 数：`1`。
- session：`qq-private-3471764547`。
- 最近窗口消息数：`12`。
- 最近消息均保存到同一个 session，包括：
  - `你好啊`
  - `我感觉我好累啊~`
  - `你在干嘛现在`
  - `我还在想怎么进行开发你的身体呢`
  - `你喜欢我吗`
  - `你知道我是谁吗？`
- 最后一条无“胡桃”前缀的问题 `你知道我是谁吗？` 进入同一 session，胡桃回复引用了前文“开发身体 / 喜不喜欢”的内容，说明 QQ 私聊上下文链路已生效。

注意：

- 如果 QQ bridge 是修改代码前启动的，需要在启动脚本窗口按 `Ctrl+C` 停止后重新运行：

```powershell
scripts\start_qq_stack.bat
```

- 重启后私聊免唤醒词逻辑才会进入当前运行进程。

### 2026-07-02 身份关系系统第一版：主人画像专属与多人聊天隔离

用户需求：

- 很多人找胡桃聊天时，必须区分主人、主人的朋友、普通朋友、路人和黑名单。
- 主人不需要日常聊天中自称主人，系统要通过 QQ 号等平台身份自动识别。
- 只有主人拥有完整用户画像和长期画像记忆。
- 主人的其他关系人群只保留上下文和短期记忆，不建立长期用户画像。
- 路人不能靠聊天自称变成主人，朋友也不能自动超过主人关系。

本次实现：

- 新增配置：
  - `HUTAO_OWNER_QQ_IDS=`：主人 QQ 号列表，多个用英文逗号分隔。
  - `HUTAO_OWNER_NAME=主人`：主人默认称呼。
- 新增身份关系数据结构：
  - `ContactRecord`
  - `PlatformIdentityRecord`
  - `RelationshipContext`
- 新增 JSONL 存储文件：
  - `contacts.jsonl`
  - `platform_identities.jsonl`
- 新增 MySQL 迁移：
  - `migrations/002_identity_relationship_schema.sql`
  - 表：`contacts`
  - 表：`platform_identities`
  - 表：`relationship_events`
  - 表：`contact_permissions`
- `ChatRequest` 新增平台身份字段：
  - `platform`
  - `platform_user_id`
  - `platform_group_id`
- QQ 接入现在会向核心接口传：
  - `platform=qq`
  - `platform_user_id=<QQ号>`
  - `platform_group_id=<QQ群号，可空>`
- `ChatService` 接入关系上下文：
  - `owner`：可读取长期画像、可写长期记忆。
  - `owner_friend` / `friend` / `stranger`：只使用最近上下文，不写长期画像。
  - `blocked`：直接拒绝展开聊天。
- Prompt 注入新增关系规则：
  - 主人：最高权限、最高信任、最高情感权重，关系接近恋人式熟悉但不油腻、不恋爱脑。
  - 主人的朋友：友好给面子，但不能有主人级亲密。
  - 路人：保持胡桃边界，不保存长期画像，不发展亲密关系。

修改文件：

- `app/core/config.py`
- `app/schemas.py`
- `app/main.py`
- `app/storage/chat_repository.py`
- `app/storage/mysql_repository.py`
- `app/persona/relationship_context.py`
- `app/persona/persona_prompt_builder.py`
- `app/services/chat_service.py`
- `integrations/qq_bot/hutao_client.py`
- `integrations/qq_bot/bot.py`
- `migrations/002_identity_relationship_schema.sql`
- `docs/database-schema.md`
- `.env`
- `.env.example`
- `tests/test_app.py`

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile ...
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "owner_identity or stranger_identity or relationship_context or owner_platform_id_parser or qq_core_client_sends_platform_identity or mysql_repository_resolves_new_owner_contact or identity_relationship_schema" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "chat_persists or chat_success or streaming_chat_api or database_schema or mysql_repository or qq_message_policy or qq_context_status or qq_core_client" -q
```

测试结果：

- 编译检查：PASS。
- 身份关系定向测试：`7 passed, 117 deselected`。
- 核心聊天、存储、QQ 相关回归测试：`14 passed, 110 deselected`。
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。
- 真实 MySQL 迁移：PASS，已向 `hutao_chat` 应用 4 条身份关系建表语句。
- 真实 MySQL smoke：PASS，验证 `owner` 解析为 `authority=100`，`stranger` 解析为 `authority=10`。
- MySQL smoke 使用的 `codex-test-owner` 和 `codex-test-stranger` 测试联系人已清理。

当前 `.env` 空配置检查：

- `HUTAO_OWNER_QQ_IDS`：建议必须填写。填入主人的 QQ 号后，胡桃才能自动识别主人。
- `QQ_BOT_ALLOWED_USERS`：可选。为空表示不限制私聊用户；如果只想允许部分 QQ 私聊，填 QQ 号列表。
- `QQ_BOT_ALLOWED_GROUPS`：可选。为空表示不限制群；如果只想允许指定群，填群号列表。
- `QQ_BOT_REPLY_PREFIX`：可选。为空即可。
- `ONEBOT_ACCESS_TOKEN`：可选。当前 NapCat 配置 Token 为空时这里也保持为空。

下一步建议：

- 在 `.env` 填写：

```text
HUTAO_OWNER_QQ_IDS=你的QQ号
```

- 然后重启：

```powershell
scripts\start_qq_stack.bat
```

- 重启后用主人 QQ 私聊一句“以后叫我阿明”，再用路人 QQ 说同样的话，预期：
  - 主人会写入长期记忆。
  - 路人只保留当前会话上下文，不写长期用户画像。

### 2026-07-02 QQ 语音回复第一版与表情包目录占位

用户需求：

- 先实现 QQ 发语音功能。
- 同时预留一个存储表情包的文件夹。

本次实现：

- 新增 QQ 语音回复配置：
  - `QQ_VOICE_REPLY_ENABLED=false`
  - `QQ_VOICE_REPLY_OWNER_ONLY=true`
  - `QQ_VOICE_TTS_BASE_URL=http://127.0.0.1:9883`
  - `QQ_VOICE_TTS_OUTPUT_DIR=D:\Programming-file\Graduation-Project\HutaoChatCore\data\generated_voice\qq`
  - `QQ_VOICE_FFMPEG_PATH=ffmpeg`
  - `QQ_STICKER_DIR=D:\Programming-file\Graduation-Project\HutaoChatCore\data\stickers`
- 新增语音合成封装：
  - `app/voice_chat/tts_service.py`
  - 复用现有 `plan_voice_chat()` 和 GPT-SoVITS `/tts` API。
  - 第一版只合成单段语音，避免多段拼接导致口齿不清或断句问题。
  - 默认输出 wav，并用 ffmpeg 转成 mp3 供 QQ record 发送。
- 新增 QQ 语音回复策略：
  - `integrations/qq_bot/voice_reply.py`
  - 只有明确触发词才尝试语音：`发语音`、`语音回复`、`用语音`、`说句话`、`说一声`、`念出来`、`读出来`。
  - 默认只允许主人私聊触发语音。
  - 群聊不发语音。
  - TTS API 未启动或合成失败时，自动回退文字回复。
- 修改 QQ bot：
  - `integrations/qq_bot/bot.py`
  - 支持发送 OneBot `record` 消息段。
- 新增 GPT-SoVITS API 一键启动脚本：
  - `scripts/start_gpt_sovits_api.py`
  - `scripts/start_gpt_sovits_api.bat`
- 新增表情包目录：
  - `data/stickers/index.json`
  - `data/stickers/README.md`
  - 预留子目录方案：`qq_custom/`、`owner_uploads/`、`api_cache/`、`pending_review/`
- 新增 QQ 语音输出目录占位：
  - `data/generated_voice/qq/.gitkeep`

启用方式：

1. 在 `.env` 打开 QQ 语音回复：

```text
QQ_VOICE_REPLY_ENABLED=true
```

2. 重启 QQ 一键栈：

```powershell
scripts\start_qq_stack.bat
```

`start_qq_stack.bat` 是唯一需要手动运行的入口。语音开关打开时，它会自动一起启动 GPT-SoVITS API；语音开关关闭时不会启动 GPT-SoVITS，避免占资源。

3. 主人 QQ 私聊触发示例：

```text
胡桃，说句话给我听
用语音回复我一下
念出来给我听
```

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\tts_service.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\config.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\voice_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_gpt_sovits_api.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "voice_reply or qq_message_policy or qq_core_client" -q
```

测试结果：

- 编译检查：PASS。
- QQ 语音/消息策略定向测试：`9 passed, 119 deselected`。
- 配置加载检查：PASS。
- `QQ_VOICE_TTS_OUTPUT_DIR` 存在：PASS。
- `QQ_STICKER_DIR` 存在：PASS。
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

当前限制：

- 语音回复默认关闭，需要手动设置 `QQ_VOICE_REPLY_ENABLED=true`。
- 第一版需要 GPT-SoVITS API 先运行在 `http://127.0.0.1:9883`。
- 语音发送格式先使用 mp3 record；如果 NapCat/QQ 侧兼容性不好，下一步改 silk 转码。
- 当前只在主人私聊、明确要求语音时触发，避免路人或群聊滥发语音。

### 2026-07-02 QQ 一键启动合并语音 API

用户反馈：

- 不想运行两个脚本，QQ 和语音应该只需要一个脚本入口。

修复：

- 修改 `scripts/start_qq_stack.py`：
  - 读取 `.env` 的 `QQ_VOICE_REPLY_ENABLED`。
  - 当 `QQ_VOICE_REPLY_ENABLED=true` 时，自动把 `GPT-SoVITS API` 加入同一个 QQ stack。
  - 当 `QQ_VOICE_REPLY_ENABLED=false` 时，不启动 GPT-SoVITS，避免占资源。
  - 读取 `QQ_VOICE_TTS_BASE_URL` 并解析 host/port，默认 `127.0.0.1:9883`。
  - 启动后会检查 GPT-SoVITS `/control?command=none`。
- 删除独立入口脚本：
  - `scripts/start_gpt_sovits_api.bat`
- 保留 `scripts/start_gpt_sovits_api.py` 作为内部/调试 helper，但用户日常不需要运行。

现在唯一入口：

```powershell
scripts\start_qq_stack.bat
```

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_qq_stack.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "start_qq_stack or voice_reply" -q
```

测试结果：

- 编译检查：PASS。
- 一键启动与语音策略测试：`9 passed, 121 deselected`。
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

### 2026-07-02 QQ 语音回复逻辑修正：去除动作提示、完整合成、避免重复文字

用户反馈：

- QQ 语音回复成功后，文字和语音同时发送，内容重复。
- 语音只说了回复前半段，后续文本没有进入语音。
- `（轻笑）` 这类表演提示被 TTS 直接念成“轻笑”，不应该作为朗读文本。

修复：

- 修改 `app/voice_chat/naturalness.py`：
  - 新增 `strip_performance_cues()`。
  - `normalize_reply_for_natural_chat()` 会删除 `（轻笑）`、`(叹气)`、`【小声】` 等括号动作提示。
  - TTS 文本和 QQ 文字回退共用这层清洗，避免动作提示被看见或被朗读。
- 修改 `app/voice_chat/tts_service.py`：
  - `synthesize_voice_reply()` 不再只合成第一段。
  - 现在会按 `plan_voice_chat()` 的所有 segments 逐段调用 GPT-SoVITS，并用 `append_wav_files()` 拼接为完整语音。
  - 返回的 `VoiceSynthesisResult.text` 记录完整清洗后文本。
- 修改 `integrations/qq_bot/voice_reply.py`：
  - 普通文字回复和 TTS 回退文字都会先清洗动作提示。
  - 语音成功时只发送 `record`，不再额外发送同内容文字。
  - TTS 未启动或合成失败时仍回退文字。
- 修改 `tests/test_app.py`：
  - 覆盖动作提示不会进入 TTS。
  - 覆盖语音成功只返回 `record`。
  - 覆盖 TTS 回退文字不保留动作提示。
  - 覆盖多段语音会全部合成并拼接。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\naturalness.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\voice_chat\tts_service.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\voice_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "tts_text_removes or voice_reply or synthesize_voice_reply_uses_all_segments or realtime_tts_text" -q
```

测试结果：

- 编译检查：PASS。
- QQ 语音逻辑定向测试：`7 passed, 125 deselected`。
- Markdown 测试记录：
  - `logs/qq-voice-reply/2026-07-02_012645/qq-voice-reply-fix-report.md`
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

当前行为：

- 用户明确要求语音且权限通过时，语音成功只发语音。
- 如果 GPT-SoVITS API 未启动或合成失败，才发送文字回退。
- `（轻笑）` 等舞台提示不再出现在 QQ 文字或 TTS 朗读文本里。
- 多段回复会全部进入合成，不再只读第一段。

### 2026-07-02 QQ 撤回取消回复机制

用户反馈：

- QQ 私聊里撤回刚发出的消息后，胡桃仍然继续回答。

原因：

- 旧版 `integrations/qq_bot/bot.py` 只处理 `on_message`。
- 收到消息后立即调用 HutaoCore，没有等待撤回窗口。
- 没有监听 OneBot v11 的 `FriendRecallNoticeEvent` / `GroupRecallNoticeEvent`。

修复：

- 新增 `integrations/qq_bot/recall_guard.py`：
  - `PendingReplyRegistry` 维护 `message_id -> PendingReply`。
  - 支持 `begin()`、`cancel()`、`wait_for_recall_window()`、`finish()`。
- 修改 `integrations/qq_bot/bot.py`：
  - 新增 `on_notice` 监听。
  - 对 `FriendRecallNoticeEvent` 和 `GroupRecallNoticeEvent` 按 `message_id` 标记 pending 回复为取消。
  - 消息通过策略后先等待 `settings.recall_wait_seconds`。
  - 等待期间撤回则不调用 HutaoCore、不发回复。
  - 如果撤回发生在调用后但发送前，也跳过发送。
  - 分段发送过程中如果撤回，只停止后续分段。
- 修改 `integrations/qq_bot/config.py` 和 `.env.example`：
  - 新增 `QQ_BOT_RECALL_WAIT_SECONDS=2.0`。
- 修改 `tests/test_app.py`：
  - 增加 pending 回复取消和等待窗口测试。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\recall_guard.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\config.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "qq_recall_guard or qq_message_policy or start_qq_stack or voice_reply" -q
```

测试结果：

- 编译检查：PASS。
- QQ 撤回/消息/语音/启动策略定向测试：`16 passed, 118 deselected`。
- Markdown 测试记录：
  - `logs/qq-recall-guard/2026-07-02_013751/qq-recall-guard-report.md`
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

当前行为：

- 默认会增加约 2 秒 QQ 回复延迟，用于等待撤回 notice。
- 撤回发生在等待窗口内时，不调用核心聊天接口。
- 撤回发生在发送前时，不发送回复。
- 如果机器人已经发出消息，本版本不会自动撤回机器人自己的消息。

### 2026-07-02 GPT-SoVITS 开头异响缓解：裁剪淡入样本

用户反馈：

- 最新 e15 权重合成的几段语音整体可以，但每个音频最开始都有一段奇怪声音。

原因判断：

- 检查 `external/GPT-SoVITS-v2pro-20250604/GPT_SoVITS/TTS_infer_pack/TextPreprocessor.py` 后发现，GPT-SoVITS 内部对短开头文本会临时补前导 `。`。
- 本次真实 API 日志也显示目标文本进入内部切分时出现 `。哎嘿`、`。别担心`、`。那么`。
- 为避免污染外部依赖，本次不修改 `external/GPT-SoVITS-v2pro-20250604` 源码。

修复：

- 修改 `app/voice_chat/naturalness.py`：
  - 新增/使用 `strip_leading_tts_punctuation()`，项目侧 TTS 输入不主动带前导标点。
- 修改 `app/voice_chat/audio_utils.py`：
  - 新增 `trim_wav_start()`，支持裁剪 WAV 开头并写回。
  - 新增 `apply_fade_in()`，对裁剪后的开头做短淡入。
- 修改 `scripts/gpt_sovits_hutao_tts_smoke.py`：
  - 每次生成 WAV 后裁剪开头 120ms。
  - 裁剪后追加 8ms fade-in。
- 修改 `tests/test_app.py`：
  - 覆盖 TTS 清洗后去除前导标点。
  - 覆盖 `trim_wav_start()` 会移除构造出的开头噪声段。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "trim_wav_start or tts_text_removes or synthesize_voice_reply_uses_all_segments or voice_reply or realtime_tts_text" -q
```

测试结果：

- 定向单元测试：`9 passed, 127 deselected`。
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

真实 e15 样本：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\gpt_sovits_hutao_tts_smoke.py" --port 9886 --base-url "http://127.0.0.1:9886" --gpt-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\hutao-e15.ckpt" --sovits-weight "D:\Programming-file\Graduation-Project\HutaoChatCore\external\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\hutao_e15_s1410.pth" --output-root "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\hutao_e15_smoke_trimmed" --timeout-seconds 360
```

结果：

- GPT-SoVITS 真实合成 smoke：PASS。
- 样本目录：
  - `data/hutao_voice/tests/hutao_e15_smoke_trimmed/2026-07-02_103203`
- 生成样本：
  - `hutao_tts_playful.wav`
  - `hutao_tts_gentle.wav`
  - `hutao_tts_chat.wav`
- Markdown 测试记录：
  - `logs/tts-leading-artifact/2026-07-02_103203/tts-leading-artifact-trim-report.md`

当前结论：

- 这次修的是输出端开头异响缓解，不是重训模型。
- 3 个样本均无削顶爆音。
- 是否完全消除“奇怪开头”仍需要人工试听确认，因为主观异响不一定能只靠 RMS/peak 判断。

### 2026-07-02 QQ 语音最新 e15 模型接入与 smoke 完善

用户需求：

- 只需要把最新语音合成模型替代之前 QQ 语音合成逻辑，再完善 smoke。

修复：

- 修改 `scripts/gpt_sovits_hutao_tts_smoke.py`：
  - 默认 GPT 权重从旧 balanced 模型切到 `hutao-e15.ckpt`。
  - 默认 SoVITS 权重切到 `hutao_e15_s1410.pth`。
  - 默认输出目录切到 `data/hutao_voice/tests/hutao_e15_smoke`。
- 修改 `scripts/start_gpt_sovits_api.py`：
  - 支持通过 `QQ_VOICE_GPT_WEIGHT` / `QQ_VOICE_SOVITS_WEIGHT` 读取 QQ 语音权重。
  - 未配置时默认使用 e15 权重。
- 修改 `scripts/start_qq_stack.py`：
  - QQ 语音启用后不再直接裸启动 `api_v2.py`。
  - 改为启动 `scripts/start_gpt_sovits_api.py`。
  - 由 helper 等待 GPT-SoVITS API 就绪后主动调用 `/set_gpt_weights` 和 `/set_sovits_weights`。
  - 启动前校验配置的 GPT/SoVITS 权重文件存在。
- 修改 `integrations/qq_bot/config.py` 和 `.env.example`：
  - 新增 `QQ_VOICE_GPT_WEIGHT`。
  - 新增 `QQ_VOICE_SOVITS_WEIGHT`。
- 修改 `tests/test_app.py`：
  - 覆盖 QQ 一键栈语音 API 命令必须走 `scripts/start_gpt_sovits_api.py`。
  - 覆盖命令必须带 `hutao-e15.ckpt` 和 `hutao_e15_s1410.pth`。
  - 覆盖 smoke 默认权重必须是 e15。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\gpt_sovits_hutao_tts_smoke.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_gpt_sovits_api.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_qq_stack.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\config.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "start_qq_stack or gpt_sovits_smoke_defaults or voice_reply or synthesize_voice_reply_uses_all_segments or tts_text_removes or trim_wav_start" -q
```

结果：

- 编译检查：PASS。
- 定向测试：`15 passed, 123 deselected`。
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

默认模型真实 smoke：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\gpt_sovits_hutao_tts_smoke.py" --port 9887 --base-url "http://127.0.0.1:9887" --output-root "D:\Programming-file\Graduation-Project\HutaoChatCore\data\hutao_voice\tests\qq_voice_latest_model_smoke" --timeout-seconds 360
```

结果：

- GPT-SoVITS 真实合成 smoke：PASS。
- 这次命令未手动传 `--gpt-weight` / `--sovits-weight`，用于确认默认权重已切到最新 e15。
- 样本目录：
  - `data/hutao_voice/tests/qq_voice_latest_model_smoke/2026-07-02_104840`
- 结果 JSON 记录：
  - `gpt_weight=...\hutao-e15.ckpt`
  - `sovits_weight=...\hutao_e15_s1410.pth`
- Markdown 测试记录：
  - `logs/qq-voice-latest-model/2026-07-02_104840/qq-voice-latest-model-report.md`

当前行为：

- `scripts/start_qq_stack.bat` 启动 QQ 栈且 `QQ_VOICE_REPLY_ENABLED=true` 时，GPT-SoVITS API 会加载最新 e15 模型。
- `scripts/gpt_sovits_hutao_tts_smoke.py` 默认也使用最新 e15 模型。
- QQ 发送 record 的策略不变，本次只替换模型加载和 smoke 验证逻辑。

### 2026-07-02 QQ 表情包发送第一版：本地索引与明确触发

用户需求：

- 之前说要发表情包。
- 用户已经爬取了表情包，放在 `data/stickers` 下。
- 后续还会继续追加表情包，需要可持续整合。

实现：

- 新增 `scripts/build_sticker_index.py`：
  - 扫描 `data/stickers` 下 `.png`、`.jpg`、`.jpeg`、`.gif`。
  - 生成 `data/stickers/index.json`。
  - 使用相对路径生成稳定 `id`。
  - 重建索引时保留旧索引中人工维护的 `tags` 和 `enabled`。
- 新增 `integrations/qq_bot/sticker_reply.py`：
  - 触发词包括 `发个表情包`、`来个表情包`、`发张表情包`、`胡桃表情包`、`发表情包`、`发表情`、`来个表情`。
  - 选择 enabled 且文件存在的本地图片。
  - 索引为空时回退文字。
- 修改 `integrations/qq_bot/bot.py`：
  - 在调用 HutaoCore 之前先判断是否为明确表情包请求。
  - 命中表情包请求时直接发送 `MessageSegment.image(...)`。
  - 表情包请求不调用大模型。
- 修改 `integrations/qq_bot/config.py` 和 `.env.example`：
  - 新增 `QQ_STICKER_INDEX_PATH`。
  - 新增 `QQ_STICKER_REPLY_ENABLED`。
- 修改 `data/stickers/README.md`：
  - 记录后续新增表情包后的重建索引方式。
- 修改 `tests/test_app.py`：
  - 覆盖索引重建保留人工 `tags/enabled`。
  - 覆盖触发词返回 image。
  - 覆盖空索引回退文字。

当前索引：

- 命令：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\build_sticker_index.py" --sticker-dir "D:\Programming-file\Graduation-Project\HutaoChatCore\data\stickers"
```

- 结果：`Sticker count: 1064`
- 来源分布：
  - `biligame_ys_chat_emoji`: 779
  - `miyoushe_collection_2563052`: 240
  - `wechat_emoji_article`: 45

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\build_sticker_index.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\sticker_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\config.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "sticker or qq_message_policy or start_qq_stack or voice_reply" -q
```

结果：

- 编译检查：PASS。
- 定向测试：`18 passed, 123 deselected`。
- 表情包专项测试：`3 passed, 138 deselected`。
- Markdown 测试记录：
  - `logs/qq-sticker-reply/2026-07-02_105900/qq-sticker-reply-report.md`
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

当前行为：

- 用户明确说 `来个表情包` / `发表情` 等触发词时，QQ bot 直接发送本地图片。
- 普通聊天暂不自动夹带表情包。
- 后续用户新增图片后，只需要重跑 `scripts/build_sticker_index.py` 即可纳入索引。

### 2026-07-02 QQ 表达增强：自动表情包、情绪池与短回复

用户反馈：

- 语音和表情包触发太苛刻，必须刻意提示。
- 如果放开自动触发，又担心每句都发或一口气发一堆。
- 同一句 `发个表情包` 总是同一张图，太单调。
- 简单问题经常回复一大段，不像真人私聊。

实现：

- 新增 `integrations/qq_bot/expressive_reply.py`：
  - 维护 `ExpressiveReplyState`。
  - 自动表情包支持概率、消息冷却、时间冷却。
  - 技术/报错/代码/配置/训练语境禁止自动发表情包。
  - 自动语音默认关闭，只保留陪伴语境和冷却框架。
- 新增 `integrations/qq_bot/reply_style.py`：
  - 判断 QQ 简单短问题。
  - 生成 QQ 专属短回复风格指令。
  - 出口层约束短问题的过长回复。
- 修改 `app/schemas.py`、`app/main.py`、`app/services/chat_service.py`：
  - 新增 `response_style_instruction`。
  - 风格指令只进 system prompt，不作为用户输入保存。
  - 防止 QQ 短回复控制文字污染上下文/记忆。
- 修改 `integrations/qq_bot/hutao_client.py`：
  - 支持向核心 API 传 `response_style_instruction`。
- 修改 `integrations/qq_bot/bot.py`：
  - 显式表情包请求仍然直接发图。
  - 普通聊天在模型回复后，按策略低频追加表情包。
  - 同一轮如果发语音，不自动追加表情包。
- 修改 `integrations/qq_bot/sticker_reply.py`：
  - 表情包选择改为情绪池 + 时间窗口变化 + 最近发送去重。
  - 不再同一句永远固定同一张图。
- 修改 `scripts/build_sticker_index.py`：
  - 索引增加 `emotion`、`style`、`intensity`。
  - 支持 `emotion_locked/style_locked/intensity_locked`。
  - 文件名无明显情绪时，用稳定 ID 分桶，避免 1064 张全部 neutral。
- 修改 `.env` 和 `.env.example`：
  - 增加自动表情包和自动语音配置。

当前配置：

```text
QQ_STICKER_AUTO_REPLY_ENABLED=true
QQ_STICKER_AUTO_PROBABILITY=0.18
QQ_STICKER_COOLDOWN_MESSAGES=4
QQ_STICKER_COOLDOWN_SECONDS=180
QQ_VOICE_AUTO_REPLY_ENABLED=false
QQ_VOICE_AUTO_PROBABILITY=0.08
QQ_VOICE_COOLDOWN_MESSAGES=8
QQ_VOICE_COOLDOWN_SECONDS=600
```

表情包索引：

- 重建命令：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\build_sticker_index.py" --sticker-dir "D:\Programming-file\Graduation-Project\HutaoChatCore\data\stickers"
```

- 总数：1064。
- 情绪分布：
  - `neutral`: 227
  - `comfort`: 222
  - `surprised`: 215
  - `happy`: 205
  - `tease`: 195

说明：

- 这批表情包文件名多数是编号和哈希，无法从文件名准确判断真实情绪。
- 当前情绪池是规则 + 稳定分桶，用于先解决单调问题。
- 后续要更准确，需要人工标注或视觉模型识别。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\app\schemas.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\main.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\app\services\chat_service.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\reply_style.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\expressive_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\sticker_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\bot.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\hutao_client.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\build_sticker_index.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "sticker or expressive or qq_reply_style or voice_reply or qq_message_policy or qq_core_client or chat_prompt or response_style_instruction" -q
```

结果：

- 编译检查：PASS。
- 定向测试：`21 passed, 128 deselected`。
- Markdown 测试记录：
  - `logs/qq-expression-policy/2026-07-02_113000/qq-expression-policy-report.md`
- 测试警告：`.pytest_cache` 写入被 Windows 拒绝，不影响测试结果。

当前行为：

- 明确要求表情包：必发一张。
- 普通聊天：低频自动补一张，默认 18% 概率，且至少间隔 4 轮或 180 秒。
- 技术/配置/训练/报错类消息：不自动发表情包。
- 自动语音：默认关闭，避免打扰；显式发语音仍然可用。
- QQ 简单短问题：会加短回复风格指令，且该指令不保存为用户消息。

### 2026-07-02 QQ 表情包意图驱动策略

用户反馈：

- 单纯“概率 + 冷却”的触发方式不像正常人发图。
- 需要参考表情/贴纸推荐算法，按语境和意图处理。

实现：

- 修改 `integrations/qq_bot/expressive_reply.py`：
  - 新增 `StickerDecision`。
  - 新增 `infer_sticker_intent()`。
  - 新增 `evaluate_sticker_decision()`。
  - `should_auto_send_sticker()` 改为由表达需求评分决定。
- 修改 `integrations/qq_bot/sticker_reply.py`：
  - `StickerEntry` 增加 `intent` 字段。
  - 选择表情包时优先使用 `intent + emotion` 池。
  - 继续保留最近发送去重和时间窗口变化。
- 修改 `scripts/build_sticker_index.py`：
  - 索引增加 `intent` 和 `intent_locked`。
  - 支持后续人工锁定 intent。
  - 文件名缺少明显语义时使用稳定 ID 分桶，避免全部落同一类。
- 修改 `tests/test_app.py`：
  - 覆盖高表达需求触发。
  - 覆盖低表达需求不触发。
  - 覆盖技术语境禁止触发。
  - 覆盖按 intent 选择表情包。

核心逻辑：

```text
是否自动发表情包 = 表达需求分数 >= 阈值
```

表达需求分数来自：

- 意图命中：`celebrate`、`tease`、`support`、`awkward`、`cute_react`
- 情绪命中：`happy`、`comfort`、`tease`、`surprised`、`neutral`
- 闲聊/接梗标记
- 回复适合用图补情绪
- 输入较短
- 技术/配置/训练/报错直接禁止
- 冷却未结束直接禁止

`QQ_STICKER_AUTO_PROBABILITY` 现在只影响阈值，不再作为主随机触发逻辑。

索引重建结果：

- 总数：1064。
- intent 分布：
  - `celebrate`: 192
  - `support`: 187
  - `cute_react`: 181
  - `awkward`: 169
  - `tease`: 168
  - `neutral`: 167
- emotion 分布：
  - `neutral`: 227
  - `comfort`: 222
  - `surprised`: 215
  - `happy`: 205
  - `tease`: 195

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "sticker or expressive or qq_reply_style or voice_reply or qq_message_policy or qq_core_client or chat_prompt or response_style_instruction" -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\build_sticker_index.py" --sticker-dir "D:\Programming-file\Graduation-Project\HutaoChatCore\data\stickers"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\expressive_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\integrations\qq_bot\sticker_reply.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\build_sticker_index.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
```

结果：

- 定向测试：`23 passed, 128 deselected`。
- 编译检查：PASS。
- 索引重建：PASS，1064 items。
- Markdown 测试记录：
  - `logs/qq-sticker-intent-policy/2026-07-02_114500/qq-sticker-intent-policy-report.md`

当前限制：

- 这批图片文件名多为编号/哈希，intent/emotion 仍不是视觉真实标注。
- 当前算法先解决触发逻辑和分池选择问题。
- 更自然的下一步是人工标注或视觉模型标注，并把 `intent_locked=true` / `emotion_locked=true` 写入索引。

### 2026-07-02 QQ 启动器 EXE 打包

用户需求：

- 优化和美化 QQ 方向启动脚本 `start_qq_stack.bat`。
- 做成软件打包。
- 最终 EXE 文件放在 `HutaoChatCore` 目录内。

实现：

- 新增 `scripts/qq_launcher.py`：
  - 中文状态面板。
  - 检查 Python、`.env`、`scripts/start_qq_stack.py`、表情包索引、QQ 语音开关、GPT/SoVITS 权重。
  - 支持 `--check-only`，只检查不启动服务。
  - EXE 模式下使用 EXE 所在目录作为项目根目录。
- 修改 `scripts/start_qq_stack.bat`：
  - 设置 UTF-8、窗口标题和颜色。
  - 检查项目 Python 路径。
  - 提示 `.env` 状态。
  - 统一调用 `scripts/qq_launcher.py`。
  - 退出时保留窗口，方便查看错误。
- 使用 PyInstaller 打包轻量启动器：
  - 输出文件：`胡桃QQ助手启动器.exe`
  - 输出位置：`D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe`
  - 文件大小：8,476,858 bytes。

注意：

- 这是轻量启动器，不是完整离线安装包。
- EXE 不内置 GPT-SoVITS、NapCatQQ、模型权重、DeepSeek 配置或 Python 依赖。
- EXE 必须放在 `HutaoChatCore` 根目录，才能发现项目内脚本、`.env`、表情包索引和模型路径。

验证：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\qq_launcher.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\scripts\start_qq_stack.py" "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py"
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest "D:\Programming-file\Graduation-Project\HutaoChatCore\tests\test_app.py" -k "qq_launcher or start_qq_stack" -q
& "D:\Programming-file\Graduation-Project\HutaoChatCore\胡桃QQ助手启动器.exe" --check-only
```

结果：

- 定向测试：`9 passed, 135 deselected`。
- EXE 检查模式：PASS，退出码 0。
- EXE 检查到：
  - 项目目录正确。
  - `.env` 存在。
  - 表情包索引 1064 items。
  - QQ 语音已开启。
  - e15 GPT/SoVITS 权重存在。
- Markdown 测试记录：
  - `logs/qq-launcher-package/2026-07-02_111458/qq-launcher-package-report.md`
### 2026-07-06 Launcher Weixin Integration And Social Logs

User goal:

- Put Hermes Weixin startup into the existing `胡桃QQ助手启动器.exe` flow.
- Keep the personal WeChat direction as Hermes/iLink, not Official Account/test-account callbacks.
- Provide a QQ-like way to watch logs for QQ, HutaoCore, NapCat, GPT-SoVITS, and Hermes Weixin.
- Keep runtime files off `C:\` unless the user explicitly approves otherwise.

Implementation:

- Updated `scripts/start_qq_stack.py`.
  - Added `--with-weixin`, `--weixin-only`, and `--core-port`.
  - Added Hermes process spec for `hermes.exe gateway run --replace --accept-hooks`.
  - Added D-drive Hermes environment overrides for `HERMES_HOME`, `PIP_CACHE_DIR`, and `UV_CACHE_DIR`.
  - Added Hermes custom model configuration targeting local `/v1` OpenAI-compatible HutaoCore endpoints.
- Updated `scripts/qq_launcher.py`.
  - Added Hermes executable and Weixin `.env` readiness checks without printing secret values.
  - Made Weixin readiness a warning by default and a blocking failure when `--with-weixin` or `--weixin-only` is requested.
  - Printed Hermes log location and the unified real-time log command.
- Added `scripts/tail_social_logs.py`.
  - Supports `--all`, `--qq`, and `--weixin`.
  - Reads only log files and does not read or print tokens.
- Updated `README.md` with launcher commands, log commands, and safe options for allowing another WeChat account.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile .\scripts\start_qq_stack.py .\scripts\qq_launcher.py .\scripts\tail_social_logs.py .\tests\test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest .\tests\test_qq_bot.py -k "start_qq_stack or qq_launcher or tail_social_logs" -q
```

Result:

- Compile check: PASS.
- Focused tests: `18 passed, 62 deselected`.
- Rebuilt `胡桃QQ助手启动器.exe` in the project root with PyInstaller.
- Launcher check: `.\胡桃QQ助手启动器.exe --check-only --with-weixin` PASS.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Report: `logs/launcher-weixin/2026-07-06_173423/launcher-weixin-report.md`.

### 2026-07-06 Database V2 Identity/Profile Design

User goal:

- Design a new database system because the old database must not remain the runtime source of truth.
- Support QQ, WeChat, and core project data while allowing the same real person to own multiple platform accounts.
- Collapse persona-layer relationships to exactly three types:
  - `admin_partner`
  - `normal_friend`
  - `blocked`
- Keep friend, relative, classmate, stranger, and user claims as portrait/social-label data, not authorization roles.
- Enforce one administrator profile that may bind both QQ and WeChat accounts.

Design record:

- Added root design document: `DATABASE_V2_DESIGN.md`.
- Proposed new MySQL database: `xiaohe_core`.
- Proposed identity model:
  - `profiles` represent real people.
  - `platform_accounts` represent QQ/WeChat accounts and bind to profiles.
  - `admin_profile` is a singleton table for the only administrator profile.
  - `profile_social_labels` stores friend/relative/classmate labels without changing permissions.
- Proposed chat storage:
  - `conversations`
  - `messages`
  - `message_attachments`
  - `model_invocations`
  - `persona_evaluations`
  - `safety_guard_events`
- Proposed memory and portrait storage:
  - `profile_portraits`
  - `admin_private_profile`
  - `profile_emotional_state`
  - `memories`
  - `memory_events`
- Proposed platform event storage:
  - `qq_inbound_events`
  - `qq_outbound_events`
  - `wechat_inbound_events`
  - `wechat_outbound_events`
  - `platform_command_events`

Important decisions:

- Platform account is not a person; profile is the person.
- Relationship and permissions exist on `profiles`, not platform accounts.
- Multiple QQ accounts and multiple WeChat accounts can bind to one profile.
- Profile-level `blocked` blocks all accounts for that person.
- Account-level blocked status may block one concrete platform account.
- Unknown platform accounts default to `normal_friend`, `verified=false`.
- Admin bootstrap environment variables are only first-run inputs; runtime admin checks should use MySQL.
- The model receives only resolved relationship context and permissions. It must not decide owner identity, relationship promotion, or privacy access.

Next implementation recommendation:

- First implement only the V2 schema, migration runner, repository interfaces, and focused tests.
- Do not switch QQ/WeChat runtime behavior until the schema and resolver tests pass.

### 2026-07-06 Database V2 Schema And Repository Boundary

User goal:

- Start development of the new database system after the design draft.
- Keep QQ/WeChat runtime behavior unchanged during the first step.

Implementation:

- Added V2 MySQL schema:
  - `migrations/v2/001_xiaohe_core_schema.sql`
  - includes `schema_migrations`, `profiles`, `admin_profile`, `platform_accounts`, social labels, relationship claims/events, portraits, emotional state, conversations, messages, attachments, model invocations, persona evaluations, safety guard events, memories, memory events, QQ/WeChat platform events, and command events.
- Added V2 migration runner:
  - `scripts/apply_database_v2_migrations.py`
  - discovers `migrations/v2/*.sql`;
  - records applied versions in `schema_migrations`;
  - uses existing MySQL settings and `MySQLChatRepository` execution helpers;
  - refuses non-`xiaohe_core` database names by default to avoid applying V2 schema to the old runtime database.
- Added V2 storage boundary modules:
  - `app/storage/v2_models.py`
  - `app/storage/v2_repository.py`
  - defines strict relationship types `admin_partner`, `normal_friend`, and `blocked`;
  - defines profile/account relationship context and permission mapping;
  - defines repository protocol for bootstrap, relationship resolution, relationship update, and account binding.
- Added focused tests:
  - `tests/test_database_v2.py`
- validates V2 schema tables, single-admin constraint, platform-account uniqueness, strict permissions, legacy-role collapse, migration discovery/splitting, and migration version recording.
- validates that the V2 migration runner rejects the old `hutao_chat` database name unless explicitly allowed for isolated tests.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/storage/v2_models.py app/storage/v2_repository.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `7 passed`.
- Database-focused regression tests: `26 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- Existing JSONL/MySQL repository remains unchanged.
- Existing QQ/WeChat runtime relationship behavior is not switched yet.
- Next safe step is implementing a real MySQL V2 repository/resolver behind tests, then wiring adapters only after resolver behavior passes.

### 2026-07-06 Database V2 MySQL Repository Core

User goal:

- Continue the next step after V2 schema and repository boundary.
- Implement the real MySQL-backed V2 repository/resolver core while keeping QQ/WeChat runtime unchanged.

Implementation:

- Added `app/storage/v2_mysql_repository.py`.
- Implemented `MySQLDatabaseV2Repository` with:
  - singleton admin bootstrap via `admin_profile`;
  - unknown platform-account resolution as `normal_friend`, `verified=false`;
  - MySQL-backed `RelationshipContext` construction;
  - account-level blocked override through `effective_relationship_type`;
  - relationship update with `relationship_events` audit;
  - cross-platform or same-platform account binding through profile merge.
  - profile merge moves profile references across model invocations, messages, safety events, memories, relationship events, conversations, and command events.
- Extended `app/storage/v2_models.py` with:
  - `effective_relationship_type`;
  - profile/account row mapping helpers;
  - relationship-context builder.
- Extended `tests/test_database_v2.py` with MySQL V2 repository tests using a recording subclass rather than a real database.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/storage/v2_models.py app/storage/v2_repository.py app/storage/v2_mysql_repository.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `12 passed`.
- Database-focused regression tests: `31 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- Existing ChatService and platform adapters still use the old repository path.
- No real database was created or modified in this step.
- Next safe step is adding a service-level `RelationshipResolver` wrapper and bootstrap command/tests before wiring QQ/WeChat.

### 2026-07-06 Database V2 Relationship Service

User goal:

- Continue the next database V2 development step.
- Add a service-level relationship resolver/bootstrap layer before wiring QQ/WeChat runtime.

Implementation:

- Added `app/storage/v2_relationship_service.py`.
- Added `PlatformIdentity` as the platform-neutral input shape for future QQ/WeChat adapters.
- Added `RelationshipResolution` as the runtime decision output:
  - `should_enter_chat_service`
  - `should_reply`
  - `fixed_reply`
  - `reason_code`
  - model-safe context through `to_model_context()`
- Added `DatabaseV2RelationshipService`:
  - bootstraps admin through `OWNER_BOOTSTRAP_QQ_IDS` and `OWNER_BOOTSTRAP_WECHAT_IDS`;
  - resolves platform identity through the V2 repository;
  - blocks `blocked` profiles/accounts before ChatService;
  - private blocked chats receive `现在不方便继续聊。`;
  - blocked group messages are ignored.
- Updated `app/core/config.py`:
  - added `owner_bootstrap_qq_ids`;
  - added `owner_bootstrap_wechat_ids`.
- Updated `.env.example` with empty V2 bootstrap keys:
  - `OWNER_BOOTSTRAP_QQ_IDS=`
  - `OWNER_BOOTSTRAP_WECHAT_IDS=`
- Extended `tests/test_database_v2.py` with service-layer tests for bootstrap parsing, normal friend resolution, blocked private/group behavior, and admin model context.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/core/config.py app/storage/v2_models.py app/storage/v2_repository.py app/storage/v2_mysql_repository.py app/storage/v2_relationship_service.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `18 passed`.
- Database-focused regression tests: `37 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- Existing QQ/WeChat adapters are still not wired to V2.
- Existing ChatService remains unchanged.
- No real database was created or modified.

### 2026-07-06 Database V2 Admin Command Policy

User goal:

- Continue V2 database development after service-layer relationship resolution.
- Add admin command parsing and authorization boundary before wiring platform adapters.

Implementation:

- Added `app/storage/v2_command_policy.py`.
- Added parser for V2 admin command texts:
  - `设置关系 <platform> <platform_user_id> <relationship_type> [display_name]`
  - `拉黑 <platform> <platform_user_id>`
  - `解除拉黑 <platform> <platform_user_id>`
  - `绑定账号 <platform> <platform_user_id> <platform> <platform_user_id>`
  - `查看关系 <platform> <platform_user_id>`
  - `最近聊天`
  - `查看聊天 <platform> <platform_user_id>`
  - `待确认关系`
  - `确认关系 <claim_id>`
  - `拒绝关系 <claim_id>`
- Added admin-only authorization:
  - only `effective_relationship_type == "admin_partner"` may authorize commands;
  - `normal_friend` and `blocked` command attempts are parsed but denied with `admin_required`;
  - unsupported platforms and old relationship labels such as `owner_friend` are rejected.
- Extended `tests/test_database_v2.py` with command parser and authorization tests.
- Finished the paused README update for V2 bootstrap keys and latest test counts.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/core/config.py app/storage/v2_models.py app/storage/v2_repository.py app/storage/v2_mysql_repository.py app/storage/v2_relationship_service.py app/storage/v2_command_policy.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `23 passed`.
- Database-focused regression tests: `42 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- Commands are not executed yet.
- QQ/WeChat adapters are not wired to V2 yet.
- No real database was created or modified.

### 2026-07-06 Database V2 Admin Command Executor

User goal:

- Continue the next V2 database development step.
- Execute authorized admin commands against the V2 repository boundary, but keep QQ/WeChat adapters disconnected.

Implementation:

- Added `app/storage/v2_command_executor.py`.
- Added `V2CommandExecutionResult`.
- Implemented command execution for:
  - `set_relationship` -> `repository.set_relationship(...)`
  - `block` -> `repository.set_relationship(..., relationship_type="blocked")`
  - `unblock` -> `repository.set_relationship(..., relationship_type="normal_friend")`
  - `bind_accounts` -> `repository.bind_accounts(...)`
  - `view_relationship` -> `repository.resolve_relationship_context(...)`
- Unauthorized, invalid, and non-command inputs do not call repository mutation methods.
- Read-heavy/admin-review commands that still need repository query APIs return explicit `not_implemented`:
  - `recent_chats`
  - `view_chat`
  - `pending_claims`
  - `approve_claim`
  - `reject_claim`
- Extended `tests/test_database_v2.py` with executor tests for relationship update, block/unblock, account binding, unauthorized refusal, and not-implemented commands.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/core/config.py app/storage/v2_models.py app/storage/v2_repository.py app/storage/v2_mysql_repository.py app/storage/v2_relationship_service.py app/storage/v2_command_policy.py app/storage/v2_command_executor.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `27 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- QQ/WeChat adapters are not wired to V2.
- No real database was created or modified.
- Next safe step is adding repository query APIs for recent chats, chat history, and pending relationship claims.

### 2026-07-06 Database V2 Admin Query And Claim Review

User goal:

- Continue the next V2 database development step.
- Replace the remaining `not_implemented` admin commands with repository-backed query and review execution.

Implementation:

- Extended `app/storage/v2_models.py` with typed read models:
  - `V2RecentChat`
  - `V2ChatMessage`
  - `V2PendingRelationshipClaim`
- Extended `app/storage/v2_repository.py` with query/review APIs:
  - `list_recent_chats`
  - `list_chat_history`
  - `list_pending_relationship_claims`
  - `approve_relationship_claim`
  - `reject_relationship_claim`
- Extended `app/storage/v2_mysql_repository.py`:
  - recent chats read from `conversations` + `messages`;
  - chat history reads admin-visible messages by profile/account;
  - pending claims read from `relationship_pending_claims`;
  - claim approval verifies profile/account, writes a `user_claim` social label, updates the claim, and records a `verify` event;
  - claim rejection updates the claim and records an `unverify` event when the account already exists.
- Extended `app/storage/v2_command_executor.py` so these commands execute:
  - `recent_chats`
  - `view_chat`
  - `pending_claims`
  - `approve_claim`
  - `reject_claim`
- Important behavior: approving a claim does not create new relationship categories and does not upgrade anyone to `admin_partner`; it keeps relationship type inside `admin_partner` / `normal_friend` / `blocked`.
- Extended `tests/test_database_v2.py` with executor tests and MySQL repository SQL-boundary tests for recent chats, chat history, pending claims, approve, and reject.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/core/config.py app/storage/v2_models.py app/storage/v2_repository.py app/storage/v2_mysql_repository.py app/storage/v2_relationship_service.py app/storage/v2_command_policy.py app/storage/v2_command_executor.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `33 passed`.
- Database-focused regression tests: `52 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- QQ/WeChat adapters are still not wired to V2.
- Existing `ChatService` behavior is unchanged.
- No real database was created or modified.
- Next safe step is adding a platform-facing V2 command service wrapper and then wiring it into QQ/WeChat behind tests.

### 2026-07-07 Database V2 Platform Command Service

User goal:

- Continue V2 database development after admin query/review APIs.
- Add the platform-facing service boundary that QQ/WeChat adapters can call later.

Implementation:

- Added `app/storage/v2_platform_command_service.py`.
- Added `DatabaseV2PlatformCommandService.handle_message(...)`:
  - resolves `PlatformIdentity` through `DatabaseV2RelationshipService`;
  - blocks `blocked` profiles/accounts before command parsing;
  - normalizes optional command prefixes such as `小何 最近聊天`;
  - runs V2 admin command parsing and authorization;
  - executes authorized commands through `execute_v2_admin_command`;
  - returns a platform-adapter payload with command status, reply text, execution data, and model-safe relationship context.
- Added `V2PlatformCommandResult`.
- Added `normalize_platform_command_text(...)` for prefix stripping.
- Extended `app/storage/v2_repository.py` with `record_platform_command_event(...)`.
- Extended `app/storage/v2_mysql_repository.py` to persist command audit rows in `platform_command_events`.
- Audit behavior:
  - non-command chat messages are not written as command events;
  - unauthorized or invalid commands are written as `rejected`;
  - successful command execution is written as `accepted`;
  - command execution failure is written as `failed`;
  - details are JSON-serialized and passed through secret redaction before storage.
- Extended `tests/test_database_v2.py` with service-level tests for non-command pass-through, admin execution, non-admin rejection, blocked pre-command stop, prefix normalization, and MySQL command audit SQL.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/core/config.py app/storage/v2_models.py app/storage/v2_repository.py app/storage/v2_mysql_repository.py app/storage/v2_relationship_service.py app/storage/v2_command_policy.py app/storage/v2_command_executor.py app/storage/v2_platform_command_service.py scripts/apply_database_v2_migrations.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `39 passed`.
- Database-focused regression tests: `58 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- QQ/WeChat adapters are still not wired to V2.
- Existing `ChatService` behavior is unchanged.
- No real database was created or modified.
- Next safe step is adding a narrow QQ-side adapter integration behind tests, then repeating for WeChat.

### 2026-07-07 Database V2 Runtime Integration

User goal:

- Continue V2 development until the runtime path is connected enough for QQ/WeChat-facing command handling.
- Keep the old runtime safe unless V2 is explicitly enabled.

Implementation:

- Added `DATABASE_V2_ENABLED` to `app/core/config.py` and `.env.example`.
- Added `app/storage/v2_runtime.py`:
  - `should_use_database_v2(...)`;
  - `build_database_v2_platform_command_service(...)`;
  - `try_handle_database_v2_platform_message(...)`.
- Runtime V2 behavior:
  - only activates when `DATABASE_V2_ENABLED=true`;
  - only handles supported platforms `qq` and `wechat`;
  - requires a non-empty `platform_user_id`;
  - bootstraps admin from `OWNER_BOOTSTRAP_QQ_IDS` / `OWNER_BOOTSTRAP_WECHAT_IDS` before handling;
  - returns `None` for normal non-command chat so legacy ChatService remains fallback;
  - returns a local `ChatResponse` for blocked identities and admin command results.
- Integrated V2 pre-handler into:
  - `/api/v1/chat`;
  - `/api/v1/chat/stream`;
  - OpenAI-compatible `/v1/chat/completions`;
  - OpenAI-compatible streaming responses;
  - `integrations/qq_bot/bot.py` before old relationship commands and ChatService calls.
- WeChat/Hermes status:
  - no separate WeChat bot adapter exists in the repo;
  - current WeChat-facing path is OpenAI-compatible/Hermes with `platform="wechat"`;
  - that path now calls the V2 pre-handler when V2 is enabled.
- QQ status:
  - QQ bot now calls the V2 pre-handler before old relationship command handling;
  - blocked group messages with empty V2 reply are ignored;
  - non-command messages continue to the existing QQ ChatService flow.
- Extended tests:
  - V2 runtime gate tests in `tests/test_database_v2.py`;
  - API V2 pre-handler/fallback tests in `tests/test_api.py`;
  - OpenAI-compatible WeChat command pre-handler test in `tests/test_api.py`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/core/config.py app/storage/v2_runtime.py app/storage/v2_platform_command_service.py app/main.py app/openai_compat.py integrations/qq_bot/bot.py tests/test_api.py tests/test_database_v2.py tests/test_qq_bot.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_api.py tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py tests/test_api.py tests/test_qq_bot.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `40 passed`.
- V2/API/QQ focused tests: `134 passed`.
- Related V2/API/QQ/storage regression tests: `153 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.
- Full `pytest -q` was attempted but produced no output for about two minutes in this environment, so the spawned pytest process was stopped and the stable related suites above were used for validation.

Runtime status:

- V2 command/blocked handling is now wired behind `DATABASE_V2_ENABLED`.
- Legacy ChatService remains the fallback for normal non-command chat.
- No real database was created or modified during tests.
- Remaining work for a full storage cutover is replacing legacy ChatService message/memory writes with V2 `conversations` / `messages` / `memories` writes after a migration test pass.

### 2026-07-07 Database V2 Normal Chat Storage Cutover

User goal:

- Continue development until the V2 runtime is complete enough that normal platform chats can use the new database, not only commands/blocked guards.

Implementation:

- Extended `app/storage/v2_runtime.py`:
  - added `build_database_v2_chat_repository(...)`;
  - added `database_v2_chat_user_id(...)`.
- Updated `/api/v1/chat` and `/api/v1/chat/stream`:
  - when `DATABASE_V2_ENABLED=true` and the request has supported `platform=qq/wechat` plus `platform_user_id`, ChatService receives `MySQLDatabaseV2Repository`;
  - user ids are normalized to `qq-<platform_user_id>` / `wechat-<platform_user_id>` only on the V2 storage path;
  - when V2 is disabled, legacy user id behavior is unchanged.
- Updated OpenAI-compatible `/v1/chat/completions`:
  - same V2 repository selection and user id normalization for WeChat/Hermes platform requests;
  - legacy OpenAI-compatible behavior stays unchanged when V2 is disabled.
- Extended `app/storage/v2_mysql_repository.py` with ChatRepository-compatible V2 implementations:
  - `ensure_session` -> `conversations`;
  - `save_message` -> V2 `messages`;
  - `save_model_invocation` -> V2 `model_invocations`;
  - `save_persona_evaluation` -> V2 `persona_evaluations`;
  - `save_memory`, `list_memories`, `delete_memory` -> V2 `memories`;
  - `list_recent_messages`, `list_recent_messages_by_user`, `list_recent_user_ids` -> V2 read paths;
  - `resolve_contact` maps V2 `profiles`/`platform_accounts` back into the legacy `RelationshipContext` shape that ChatService still expects internally.
- Important boundary:
  - platform chat storage is cut over to V2 only for supported platform identities;
  - no-platform local/core chats still use the legacy repository until a separate core-profile identity design is added.
- Extended tests:
  - V2 repository ChatService core write SQL tests;
  - V2 profile -> legacy relationship context mapping tests;
  - API and OpenAI-compatible tests proving V2 enabled platform chats receive a V2 repository and normalized V2 user id;
  - legacy behavior tests explicitly pin `DATABASE_V2_ENABLED=false`.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/main.py app/openai_compat.py app/storage/v2_mysql_repository.py app/storage/v2_runtime.py tests/test_api.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_api.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py tests/test_api.py tests/test_qq_bot.py tests/test_chat_service.py -q
```

Result:

- Compile check: PASS.
- Focused V2/API tests: `58 passed`.
- Related V2/API/QQ/ChatService/storage regression tests: `180 passed`.
- Focused V2 tests after storage cutover: `42 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- V2 command/blocked handling is wired behind `DATABASE_V2_ENABLED`.
- Supported QQ/WeChat normal chats can now write ChatService records to V2 storage when V2 is enabled.
- Unsupported/no-platform chats still use legacy storage by design.
- No real database was created or modified during tests.

### 2026-07-07 Database V2 JSONL Migration Tooling

User goal:

- Continue V2 development after runtime storage cutover.
- Add the migration path from legacy JSONL storage into the new `xiaohe_core` V2 schema.

Implementation:

- Added `scripts/migrate_jsonl_to_database_v2.py`.
- Script behavior:
  - default mode is dry-run and does not require MySQL settings;
  - `--apply` writes into MySQL through `MySQLDatabaseV2Repository`;
  - `--apply` reuses the V2 migration database guard and rejects non-`xiaohe_core` unless `--allow-non-xiaohe-core` is passed;
  - missing legacy JSONL files are treated as empty.
- Extended `app/storage/v2_mysql_repository.py` with `import_legacy_jsonl_snapshot(...)`.
- Migration mapping:
  - legacy `sessions` -> V2 `conversations`;
  - legacy `messages` -> V2 `messages`;
  - legacy `model_invocations` -> V2 `model_invocations`;
  - legacy `persona_evaluations` -> V2 `persona_evaluations`;
  - legacy `memories` -> V2 `memories` when a platform profile can be resolved;
  - legacy `contacts` -> V2 `profiles`;
  - legacy `platform_identities` -> V2 `platform_accounts`.
- Relationship compression:
  - legacy `owner` -> `admin_partner`;
  - legacy `blocked` -> `blocked`;
  - legacy `owner_friend`, `owner_relative`, `friend`, `stranger`, and unknown roles -> `normal_friend`.
- Existing IDs are preserved where possible so migrated messages, model invocations, evaluations, and memories keep their old references.
- Extended `tests/test_database_v2.py` with dry-run summary and import SQL-boundary tests.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile app/storage/v2_mysql_repository.py scripts/migrate_jsonl_to_database_v2.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" scripts\migrate_jsonl_to_database_v2.py --storage-dir logs\storage
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py tests/test_api.py tests/test_qq_bot.py tests/test_chat_service.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `44 passed`.
- Dry-run script against current `logs/storage`: PASS; reported `sessions=1`, `messages=232`, `model_invocations=116`, `persona_evaluations=116`.
- Related V2/API/QQ/ChatService/storage regression tests: `182 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- No real database was created or modified.
- Migration tooling is ready for a real `xiaohe_core` dry-run/apply pass.
- Next operational step is applying V2 schema migrations to a real MySQL database, running this JSONL migration with `--apply`, and then doing QQ/WeChat smoke tests with `DATABASE_V2_ENABLED=true`.

### 2026-07-07 Database V2 Readiness And Completion Criteria

User goal:

- Continue the next V2 development step.
- Clarify exactly when the database V2 plan is considered complete.
- Add executable checks instead of relying only on manual judgement.

Implementation:

- Added `scripts/database_v2_readiness_check.py`.
- Readiness checks:
  - target database must be `xiaohe_core` unless `--allow-non-xiaohe-core` is used;
  - `DATABASE_V2_ENABLED=true` unless `--allow-disabled` is used;
  - `schema_migrations` contains `v2.001_xiaohe_core_schema`;
  - required V2 tables exist in `information_schema.TABLES`;
  - singleton admin profile exists, or bootstrap owner IDs are configured for first startup.
- Added explicit V2 completion criteria to `README.md`:
  - V2 migrations applied to real MySQL;
  - readiness check returns `PASS`;
  - JSONL migration dry-run is reviewed and `--apply` succeeds;
  - QQ owner and WeChat owner bind to the same `admin_partner` profile;
  - unknown QQ/WeChat users default to `normal_friend`;
  - blocked users do not enter ChatService;
  - normal QQ/WeChat chats write to V2 storage tables;
  - QQ and WeChat smoke tests pass with `DATABASE_V2_ENABLED=true`.
- Extended `tests/test_database_v2.py` with readiness tests for:
  - fully ready database;
  - missing required table;
  - disabled V2 / wrong target database;
  - missing admin but configured bootstrap IDs.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile scripts/database_v2_readiness_check.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py tests/test_api.py tests/test_qq_bot.py tests/test_chat_service.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `48 passed`.
- Related V2/API/QQ/ChatService/storage regression tests: `186 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- No real database was created or modified.
- The V2 implementation is code-complete for supported QQ/WeChat platform identities.
- The overall plan is complete only after the real MySQL readiness check, real migration apply, and real QQ/WeChat smoke tests pass.

### 2026-07-07 Database V2 Smoke Test Tooling

User goal:

- Continue the next V2 development step after readiness checks.
- Add an executable real-database smoke test for the final QQ/WeChat cutover path.

Implementation:

- Added `scripts/database_v2_smoke.py`.
- Smoke behavior:
  - writes a report under `logs/database-v2-smoke/<timestamp>/`;
  - skips cleanly when MySQL settings are missing;
  - runs Database V2 readiness checks;
  - bootstraps admin from configured owner bootstrap IDs;
  - sends one normal platform chat through ChatService using `MySQLDatabaseV2Repository`;
  - verifies V2 row counts in `conversations`, `messages`, `model_invocations`, and `persona_evaluations`;
  - optionally runs an admin `查看关系` command when a bootstrap admin id is configured for the selected platform.
- Added helper tests for:
  - expected V2 smoke row count validation;
  - bootstrap id selection;
  - V2 smoke row count SQL.
- Updated `README.md` to document smoke completion criteria.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile scripts/database_v2_smoke.py tests/test_database_v2.py
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests/test_database_v2.py tests/test_storage_database.py tests/test_api.py tests/test_qq_bot.py tests/test_chat_service.py -q
```

Result:

- Compile check: PASS.
- Focused V2 tests: `51 passed`.
- Related V2/API/QQ/ChatService/storage regression tests: `189 passed`.
- Known warning: `.pytest_cache` Windows access denied; tests pass.

Runtime status:

- No real database was created or modified.
- The final real-world completion gate is now executable:
  - apply V2 migrations;
  - run readiness check;
  - run JSONL migration if needed;
  - run `database_v2_smoke.py` for QQ and WeChat with `DATABASE_V2_ENABLED=true`.
### 2026-07-17 Platform Persona Routing: QQ Hu Tao, Weixin Xiaohe

- This decision supersedes the 2026-07-14 rule that removed the Hu Tao runtime persona. Keep the older section as history, but do not use it as the current implementation contract.
- HeadCore remains one shared person-head architecture. Brain, memory, relationship, perception, world context, provider routing, and expression planning are shared; channels do not replace the head.
- Stable platform Self routing is now:
  - QQ / NapCat: `hutao_v1`, display name `胡桃`;
  - Weixin / Hermes: `xiaohe_v1`, display name `小何`;
  - platform-unspecified compatibility requests: generic `PERSONA_PROFILE`, currently `xiaohe_v1`.
- Added `app/persona/platform_router.py` and separate `QQ_PERSONA_*` / `WEIXIN_PERSONA_*` settings.
- Restored a typed Hu Tao profile with clear boundaries: playful but not chaotic, serious around death and farewell, and technical correctness before role flavor.
- ChatService passes the selected profile through prompt construction, response evaluation, fallback responses, memory projection metadata, and recent-conversation assistant labels.
- S5 runtime projections are accepted only when their `profile_id` matches the selected platform profile. Mismatches report `profile_mismatch` and fall back to the built-in platform profile.
- The response gate rejects cross-persona identity markers in both directions: Hu Tao markers under Xiaohe and Xiaohe markers under Hu Tao.
- QQ commands, relationship history labels, README, and control-center text now use Hu Tao. The old `小何表情包` trigger remains only as backward-compatible input text.
- Local persona configuration is UTF-8 and currently selects QQ Hu Tao / Weixin Xiaohe. Never print secrets while inspecting `.env`.
- Validation uses only `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`.

### 2026-07-17 Control Center Redesign And Validation

- Reorganized `/control` around four operational areas: system overview, QQ Hu Tao operations, Weixin Xiaohe operations, and runtime diagnostics.
- Made platform persona ownership explicit: QQ routes to `hutao_v1` / Hu Tao and Weixin routes to `xiaohe_v1` / Xiaohe.
- Added responsive desktop/mobile layouts, stable action states, refresh timestamps, toast feedback, copy feedback, and active section navigation.
- Moved administrator identity and audit details into a collapsible diagnostics section.
- Corrected runtime status semantics: a Hermes executable is reported as installed rather than online, and an unprobed Weixin gateway is reported as degraded.
- Corrected the QQ stack launcher model registration target from `hutao-chatcore` to the configured `xiaohe-chatcore` runtime model.
- Added regression coverage for control-center status truthfulness and QQ launcher model configuration.

Validation:

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests -q -p no:cacheprovider
```

- Full automated suite: `700 passed, 2 skipped`.
- Edge desktop check: 1440 px viewport, no horizontal overflow, no browser console errors or warnings.
- Edge mobile check: 390 px viewport, no horizontal overflow, no browser console errors or warnings.
- Core health endpoint: PASS.

Runtime boundary:

- The control center and automated project tests are ready now.
- Real QQ voice/chat testing still requires NapCat, the OneBot bridge, and the selected TTS service to be running.
- Real Weixin testing still requires the Hermes gateway to be running and paired; an installed executable alone does not prove gateway availability.
- Database V2, persistent memory/persona projections, world awareness, and vision remain dependent on their runtime configuration and external services.

### 2026-07-17 Persistent NapCat WebUI Token

- Added `NAPCAT_WEBUI_SECRET_KEY` as a dedicated secret setting. It is separate from `ONEBOT_ACCESS_TOKEN`, which protects the OneBot network connection.
- `scripts/run_napcat.py` now reads the fixed WebUI secret from the process environment or the project `.env` and passes it only through the NapCat child-process environment.
- Both the stack launcher and the control-center NapCat button use this path, so the behavior is consistent across launch methods.
- Startup output reports only whether persistence is configured and never prints the secret value.
- The control-center QQ guide reports whether the WebUI Token is fixed without exposing it.
- Updated `.env.example` and `docs/qq-napcat-login-guide.md` with the one-time setup and restart behavior.
- Validation with the required `new` environment: `702 passed, 2 skipped`; the skipped tests require a real MySQL integration database.

### 2026-07-18 NapCat Login And Control Authorization Fix

- Diagnosed the NapCat login `Network Error` as a stopped WebUI backend: the cached login page remained visible while port 6099 was no longer listening.
- Diagnosed control-center `[object Object]` alerts as an unformatted `403 {code: admin_required}` response.
- Added a restricted control authorization fallback for `DATABASE_V2_ENABLED=false`: only QQ/Weixin owner IDs explicitly configured in `.env` can act as local control administrators.
- Database V2 remains authoritative after cutover; the fallback is disabled when `DATABASE_V2_ENABLED=true`.
- Updated the control UI to format structured API errors, reveal the administrator verification panel when needed, and avoid sending protected service actions without an actor identity.
- Bumped the control JavaScript asset version so browsers do not retain the broken cached behavior.
- Restarted Core with `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe` and started NapCat through the protected control API.
- Runtime verification: Core port 8000 online, NapCat port 6099 online, WebUI HTTP 200, configured `.env` Token matches NapCat's active persisted configuration without exposing the value.
- Full validation: `706 passed, 2 skipped`; skipped tests require `DATABASE_CONTROL_TEST_DATABASE`.

### 2026-07-18 CosyVoice2 QQ Runtime And Platform World Policy

- Diagnosed the apparent CosyVoice2 hang as two Windows/runtime issues: the full training YAML instantiated unused training objects, and Librosa/Numba stalled while creating cache files in the system temporary directory.
- Added an inference-only CosyVoice2 config, project-local Numba cache, component timing, strict mmap checkpoint loading, and the Hu Tao `epoch_99_whole.pt` flow plus `hutao` speaker embedding runtime.
- Added a localhost FastAPI TTS service, health endpoint, client adapter, typed `cosyvoice2` Provider, QQ routing, control-center service/health/log entries, and QQ stack auto-start using only the required `new` Python environment.
- Real local validation: CUDA model load completed in about 13 seconds; 24 kHz WAV synthesis passed; project TTS routing and FFmpeg conversion produced a QQ MP3. Human voice-quality acceptance and real OneBot `record` send remain separate gates.
- Added explicit world-tool channel policy: QQ/Weixin are `reactive_only`; system-initiated calls are denied. Web/desktop-pet/App are only marked `proactive_capable` for future authorized schedulers.
- Added optional `NAPCAT_QUICK_LOGIN_QQ`; when configured, the launcher passes `-q` without printing the account value.
- Added `.env` source overrides `WORLD_SOURCE_ENABLED_IDS` and `WORLD_SOURCE_LEGAL_APPROVED_IDS`; both gates are required, IDs must already exist in the source manifest, and unknown IDs fail closed.
- Current world-source status remains legally gated: reactive world coordination is enabled, but Amap legal approval is false and all eight news candidates remain disabled and unapproved. Ordinary chat performs no world call.
- Full validation with `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`: `716 passed, 2 skipped`.

### 2026-07-18 Fantasy Operations Control Center Redesign

- Reworked `/control` into an original fantasy-operations terminal while preserving its four operational areas, API routes, DOM contracts, administrator authorization, and existing service actions.
- Used a restrained light workspace, dark castle navigation, serif display titles, fine gold rules, Hu Tao red, and Xiaohe green. The result borrows the atmosphere of fantasy game interfaces without copying game characters, logos, or third-party site components.
- Added a locally stored, optimized WebP atmosphere image and documented its source and license in `app/static/control/assets/README.md`; the page has no runtime image dependency on an external site.
- Kept operational density as the priority: platform ownership, Core/Bridge/NapCat/Hermes/CosyVoice2 status, QQ and Weixin workflows, pairing controls, logs, and diagnostics remain visible and usable.
- Added CosyVoice2 to the control status projection and regression coverage, and retained truthful installed/online/degraded wording for external components.
- Added responsive behavior for the navigation, status grid, workflows, persona labels, code rows, and control actions. The decorative header index is hidden on narrow screens to avoid competing with the refresh action.
- Playwright validation passed at 1440 px desktop and 390 px mobile widths with no horizontal overflow, clipped interactive controls, browser console errors, or warnings. The real refresh action completed successfully.
- Focused control-center tests: `42 passed`. Full suite with the required `new` environment: `717 passed, 2 skipped`.
- Closed the Playwright validation browser after testing. Existing Core, QQ Bridge, NapCat, and CosyVoice2 runtime services were not stopped or restarted by this design task.

### 2026-07-18 Control Center Multi-Page Navigation

- Replaced the single long-page anchor navigation with real control routes: `/control`, `/control/qq`, `/control/weixin`, and `/control/diagnostics`.
- The shared control shell now resolves the current route into one visible workspace, a route-specific document title, header title, description, index label, active navigation state, and `aria-current` marker.
- Overview shortcuts now navigate to the QQ and Weixin control pages. Log shortcuts use stable page anchors, while the Weixin page retains its separate link to the full `/weixin` workspace.
- Hidden workspaces are explicitly removed from both layout and generated pseudo-element output so browsers and assistive technology expose only the current page.
- Added direct-route regression coverage for all four control pages and bumped the control JavaScript and stylesheet cache versions.
- Restarted only Core with the required `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`; QQ Bridge, NapCat, and CosyVoice2 were left running.
- Playwright/Edge verified direct access, navigation clicks, refresh persistence, browser back navigation, correct page titles, and zero console errors or warnings.
- Focused control-center tests: `45 passed`. Full suite: `720 passed, 2 skipped`.
- Closed the Playwright validation browser after testing; no pytest or Playwright test process was left running.

### 2026-07-18 World Tool Recovery, Live Logs, And Weixin Access Boundary

- Diagnosed QQ weather replies that claimed real-time data was unavailable. Audit records proved the world tool was selected, but `最近长沙` was forwarded as the district keyword and the suffix-normalized `长沙市` / `长沙县` candidates were treated as equally ambiguous.
- Added common temporal-modifier cleanup for `最近`, `近期`, and `目前`. District resolution now prefers one literal match and then one unique city-level normalized match, while true same-level same-name locations such as multiple `朝阳区` candidates still require confirmation.
- Performed authorized live Amap checks without exposing the key: district discovery returned `长沙市` and `长沙县`; current weather for adcode `430100` succeeded; the end-to-end QQ-format chat audit then reported `world_context_status=ready`, `weather_current`, and one world item, and its reply contained weather information.
- News and rendered acquisition remain unavailable at runtime: the source catalog has zero enabled news sources and rendered fetch is disabled. This is distinct from the repaired Amap weather path.
- Added QQ/Weixin live log polling every three seconds on their own pages, immediate first load, pause/resume controls, manual refresh, background-tab suspension, automatic retry state, non-overlapping requests, change-only rendering, and bottom-stick behavior.
- Replaced full-file log reads with a bounded reverse tail reader so repeated polling reads at most 1 MiB per source and never calls a model or consumes tokens.
- Expanded control-log redaction to cover tokens, URL keys, numeric account IDs, Weixin identifiers, account fields, and message text. Logs retain direction, state, timing, component, and error information.
- Reorganized the Weixin page into connection information plus live logs, followed by a full-width stranger-access and pairing workspace. This removed the narrow long column, duplicated content, and large empty area.
- Documented the actual Weixin access boundary in both control pages: pairing authorizes someone who already reached the bot; it cannot add a WeChat friend or create a visitor entry. The setup QR returns bot credentials and is not a visitor QR. A new user requires a shareable conversation entry from Tencent iLink/ClawBot; if Tencent exposes none, this project cannot onboard that stranger.
- Made tool capability status explicit: HeadCore world tools execute inside the core chat path, while the current `/v1` compatibility endpoint does not implement the Hermes generic OpenAI `tool_calls` loop. General Hermes plugins therefore remain incompatible even though HeadCore weather works.
- Confirmed the two visible Hermes Python processes are a parent/child launcher chain. The PID file points to the child; they are not duplicate gateways and were left running.
- Playwright/Edge verified live timestamps, pause/resume, QQ and Weixin redaction, the revised Weixin layout, and zero console errors or warnings. Final screenshot: `output/playwright/control-weixin-live-logs-final.png`.
- Focused tests: `57 passed`. Full suite with the required `new` environment: `721 passed, 2 skipped`.
# 2026-07-19 天气线上链路修复与整体验收

- 根因：`app/world/brain.py` 的天气地点清理没有去掉“告诉我/跟我说/和我说”，导致“告诉我长沙天气怎么样”被判为 `needs_location`；模型随后可能生成“缺个探头”等不真实兜底文本。
- 修复：补充常见地点前缀清理；`ChatService` 对 `needs_location`、`needs_location_confirmation`、`needs_route_endpoints`、`disabled`、`unavailable`、`stale` 增加确定性世界工具回复，避免模型编造实时信息。
- 修复：`scripts/cosyvoice2_smoke.py` 增加项目根目录导入路径，直接执行 smoke 不再报 `ModuleNotFoundError: app`。
- 验证：世界专项 `44 passed`；全量 `722 passed, 2 skipped`；runtime preflight PASS；compileall PASS。
- 真实验证：Amap 长沙地区解析和 `430100` 当前天气 PASS；Core 审计为 `ready / weather_current / 1`；Core `/health` 和控制中心页面均 HTTP 200。
- 真实模型：CosyVoice2 加载到 `cuda`；SenseVoiceSmall `cuda:0`、CER 0.0；emotion2vec 5/5 命中但存在模型缺失键警告。
- 当前边界：新闻源目录 8 个但启用 0、渲染采集关闭；Ollama/VLM HTTP 404；Database V2 readiness BLOCKED；微信普通好友添加 UNSUPPORTED；QQ/NapCat 8080 已在线，preflight 的“端口不可用”表示服务正在占用端口，不表示离线。
- 文档：新增 `docs/PROJECT_ACCEPTANCE_REPORT_2026-07-19.md`；更新 `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md` 与 `README.md` 当前快照。所有测试使用 `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`，没有创建新环境或输出密钥。

## 2026-07-19 QQ 语音触发、TTS 启动依赖与 OCR 安全降级

- 真实 NapCat 日志显示天气已成功，但“能发个语音我听听嘛/发个语音我听听”只返回文字。根因之一是触发词只有“发语音”，不能匹配中间带“个”的真实口语。
- 补充“发个语音、发一段语音、来段语音、来个语音、语音我听听”等触发词，并同步对话行为分类器。
- 控制中心启动 QQ Bridge 时，如果 QQ 语音已启用、provider 为 CosyVoice2 且自动启动开关为 true，会先启动 CosyVoice2 服务。
- 启动 7860 CosyVoice2 health PASS；真实调用“能发个语音我听听嘛”成功生成绝对路径 MP3，文件存在且大小正常。QQ Bridge 已重启并重新连接 NapCat；实际 QQ 语音气泡仍需用户发送同一句完成最后一跳验收。
- 本轮真实图片是潮玩公仔展示，不是模型回复猜测的彩妆。Ollama 在线但模型列表为空，当前实际只使用 OCR。OCR 成功现在直接返回读到的文字并明确不能判断物体，不再把品牌文字交给聊天模型进行物体猜测。
- QQ 入站 ASR 与 emotion2vec 模型已有真实样本 PASS，但本轮 NapCat 日志没有语音入站事件；需用户发送一条 QQ 语音后验证 record URL、下载、ASR 和情绪字段。
- 新闻源启用数仍为 0，渲染采集关闭，当前不能查询新闻。
- 验证：QQ/控制中心/视觉专项 `141 passed`；全量 `723 passed, 2 skipped`。仅使用 `new` 环境。

## 2026-07-19 QQ 全好友私聊与唯一管理员关系网

- 真实日志显示陌生好友消息到达 NapCat/QQ Bridge，但 `QQ_BOT_ALLOWED_USERS` 非空导致其在 `decide_qq_message` 阶段以 `user_not_allowed` 跳过，尚未进入 HeadCore 或关系系统。
- 清空 `QQ_BOT_ALLOWED_USERS`：空集合表示允许所有私聊好友。`HUTAO_OWNER_QQ_IDS` 保持唯一管理员账号；群聊继续要求提及。
- 接受的 QQ 消息会先记录联系人活动和平台昵称。策略跳过会记录脱敏 reason，方便区分白名单、群聊提及和空消息。
- 管理员自然问法“刚刚谁给你发信息了/谁给你发消息了/最近谁联系你”现在进入管理员最近聊天查询；原有 `胡桃 联系人`、`胡桃 最近聊天`、`胡桃 查看聊天 <QQ号>` 保留。
- 普通朋友查询他人联系人或聊天记录会被确定性拒绝，不能交给模型猜测或泄露。
- 管理员存储等级统一为 authority=100、affection=100、trust=100；已有管理员 JSONL 记录已更新。普通好友仍按 normal_friend 低权限边界处理，不自动升级关系。
- QQ Bridge 已重启并重新连接 NapCat。配置核对：私聊 allowlist 数量 0、管理员数量 1、群聊要求提及。
- 验证：关系/QQ 专项 `137 passed` 后新增隐私边界专项 `92 passed`；最终全量 `725 passed, 2 skipped`。仅使用 `new` 环境。

## 2026-07-19 CosyVoice2 可懂度修复与内容验收

- 真实 QQ 日志证明 NapCat 已成功发送 22.464 秒语音，故障发生在 QQ/Silk 转码之前的 CosyVoice2 合成阶段。
- 还原原文后，故障 WAV 被 SenseVoiceSmall 识别为“咕咕切奇怪。”，MP3 被识别为“咕咕奇。”，两者相对原文 CER 均为 `1.00`；FFmpeg 转码不是主因。
- 本地官方 `llm.pt` SHA-256 与 ModelScope 官方仓库完全一致；训练 flow、官方 flow、多个随机种子的错误表现一致，排除了 checkpoint 文件损坏、flow 选择和单一随机种子。
- 根因是运行环境依赖漂移：CosyVoice 固定要求 `transformers==4.51.3`，实际运行的是 `5.12.1`，导致 Qwen 语音 token 推理一直运行到长度上限且内容不可懂。
- 使用唯一允许的 `new` Python 安装并固定 `transformers==4.51.3`、`tokenizers==0.21.4`、`huggingface-hub==0.30.2`，没有创建新环境。
- `CosyVoice2Runtime` 现在启动前严格校验三个兼容版本；不匹配时直接失败，不再生成看似成功但不可懂的语音。
- `scripts/cosyvoice2_smoke.py` 默认增加 SenseVoiceSmall 回读和 CER 门槛；`--skip-asr` 仅用于明确只检查加载/文件生成的场景。
- 训练产物真实复测：`epoch_99_whole.pt + hutao embedding` 的“你好，我是胡桃。”为 1.56 秒、CER `0.00`；QQ 原回复为 7.20 秒、CER `0.00`。因此继续使用用户此前训练的 flow 和 speaker embedding，不回退默认音色。
- 验证：语音单测 `12 passed`；QQ/控制中心/语音专项 `151 passed`；全量 `727 passed, 2 skipped`；真实 CosyVoice2 + SenseVoiceSmall 内容 smoke PASS、CER `0.0000`。

## 2026-07-19 CosyVoice2 生产 checkpoint 回退

- 复核历史人工验收和当前配置后确认：`epoch_99_whole.pt` 是未批准部署的研究 checkpoint，历史记录已说明它没有优于官方 base flow + averaged speaker embedding。
- 线上默认已切换为 `CosyVoice2-0.5B/flow.pt`，继续使用 `hutao_train/spk2embedding.pt`；`epoch_99_whole.pt` 未删除，仍可通过 `.env` 手动指定做研究对照。
- `CosyVoice2Runtime` 的默认路径、`.env` 和 `.env.example` 已保持一致，避免控制中心或新部署再次误用研究 checkpoint。
- base flow 通过真实 HTTP TTS、WAV、FFmpeg MP3 和 SenseVoiceSmall 回读验收，短句 CER 为 `0.00`；当前 7860 服务已加载 `flow.pt` 并保持 `ready`。
- 历史 `data/generated_voice/qq` 中存在 32 kHz 分段文件，属于早期 Bert-VITS2 链路；24 kHz 文件才是 CosyVoice2，后续试听必须先确认 provider，不能把两条 TTS 链路当成同一个模型。

## 2026-07-20 胡桃 CosyVoice2 数据重审与 150 Epoch 正式训练

- 全程只使用 `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`，没有创建或切换虚拟环境。训练环境固定为 NumPy 1.26.4、PyWorld 0.3.4、Torch 2.12.1+cu126、Transformers 4.51.3、Tokenizers 0.21.4、Hugging Face Hub 0.30.2；CUDA 在 RTX 4070 Laptop GPU 上可用。
- 原始胡桃数据共 356 条、32.94 分钟。Fun-ASR-Nano、Paraformer 热词和 SenseVoiceSmall 三模型 GPU 审计全部完成；严格共识训练集保留 195 条、16.526 分钟，其中 train 175、dev 20，已排除已知错词与标点碰撞。
- 正式数据位于 `model_training/cosyvoice_hutao/data_retrain_150_v1`。train/dev 的 embedding、speech token、parquet 和绝对路径 `data.list` 均生成完成。
- 修复 Windows 训练兼容性：DataLoader 在 `num_workers=0` 时不再传 `prefetch_factor`；单进程训练不再将 CUDA 模型包装为 DDP；checkpoint 保存兼容普通模型；单进程跳过无意义的 join barrier；多进程 join timeout 兼容新旧 PyTorch API。
- 修复离线 speech token 与 mel 尾帧取整不一致：存在离线 token 时按 `token_count * 40 ms` 裁剪或补齐末尾音频。train 中 44 条、dev 中 3 条固定相差 2 mel 帧的问题已消除；没有在 decoder 内强制裁剪掩盖数据错误。
- `hutao_flow_smoke_v1.yaml` 的真实 1 epoch smoke 通过：训练 13 step，dev loss 0.645603，成功生成 `flow_retrain_150_v1_smoke_v6/epoch_0_whole.pt`。Windows 兼容专项测试 `6 passed`。
- 使用官方 `CosyVoice2-0.5B/flow.pt` 初始化，在独立目录 `exp/hutao_cosyvoice2/flow_retrain_150_v1` 完成 150 epoch 正式训练。epoch 0-149 共 150 个 checkpoint 连续无缺失，最终 checkpoint 为 epoch 149、step 1950、dev loss 0.701178；TensorBoard 日志完整，正式输出约 63.37 GiB。
- 新增可重复启动脚本 `model_training/cosyvoice_hutao/scripts/train_hutao_flow_150.cmd`。脚本固定使用 `new` 环境并在正式目录已有 `init.pt` 时拒绝覆盖。
- 尚未把新 checkpoint 切换为线上模型。后续必须用同一批文本和 SenseVoice 回读，对 epoch 20/40/60/80/100/120/149 做可懂度、音色相似度和人工听感比较，再选批准部署版本；不能默认最后一轮最好。
- 已新增 `scripts/evaluate_hutao_flow_checkpoints.py` 和运行时 flow 热切换接口，一次加载 CosyVoice2 后依次评测 epoch 20/40/60/80/100/120/149，避免重复加载 LLM/HiFT。
- 真实生成 21 条固定文本 WAV，SenseVoiceSmall 回读 CER 全部为 0.0000；CAMPPlus 平均说话人相似度依次为 epoch 20=0.737257、149=0.722642、120=0.715983、60=0.715768、80=0.709215、40=0.707442、100=0.682000。
- 自动客观排序为 20、149、120、60、80、40、100，但该排序只用于缩小人工试听范围。评测产物位于 `model_training/cosyvoice_hutao/test_outputs/flow_retrain_150_v1_evaluation`，包括 JSON、CSV、Markdown、21 条 WAV 和可直接播放并导出选择的 `LISTENING_REVIEW.html`。
- 线上 `.env` 仍保持官方 base flow，没有自动部署任何新 checkpoint。等待人工试听确认后，才允许更新 `QQ_COSYVOICE2_FLOW_CHECKPOINT` 并执行真实 QQ 语音验收。
- 新增第三方训练交接文档 `docs/HUTAO_COSYVOICE2_TRAINING_HANDOFF_2026-07-20.docx` 及同名 Markdown 源文件，完整记录当前框架、环境、原始与共识数据、预训练模型校验值、Windows 补丁、失败训练参数、音色诊断、重训建议和交付验收清单。文档明确现有 150 Epoch Flow checkpoint 不得部署。

## 2026-07-25 Current Development Handoff: Service Desk, Vision Boundary, World APIs

### Product Decisions That Must Be Preserved

- HeadCore is the only cognitive subject. QQ, Weixin, HTTP, audio, camera, browser, world APIs and future interfaces are organs/adapters; they must not introduce a second persona or replace HeadCore reasoning.
- Runtime persona is Hu Tao only: `hutao_v1`. Do not revive or expose Xiaohe as a selectable runtime persona.
- `/control` is the existing operations/control center. Do not redesign, merge into, or modify it as part of ordinary service-page work unless the user explicitly asks.
- `/desk` is a separate ordinary-user service page. It is not an administration page. It may expose chat and user-triggered audio input, but it must not expose admin identity fields, `/control` links, camera start/stop, QQ window capture, operational logs, system topology, database state, configuration, or control API calls.
- Service-page separation is only a UI boundary. It does not replace backend authorization. Do not claim that hiding buttons secures a route.

### Current `/desk` Implementation

- Routes in `app/main.py`: `GET /desk`, `/desk/app.js`, `/desk/style.css`, and `/desk/assets/hutao-avatar.png`.
- Main files: `app/static/desk/index.html`, `app/static/desk/app.js`, `app/static/desk/style.css`, and the local Hu Tao image asset `app/static/desk/assets/hutao-avatar.png`.
- Service page contains: typed chat through `POST /api/v1/chat`; audio-file upload and browser microphone recording through `POST /api/v1/audio/chat/file`; local browser session/user IDs; Core health display through `GET /health`.
- Conversation keyboard behavior: `Enter` sends; `Shift + Enter` inserts a newline; `event.isComposing` prevents accidental sends during IME composition.
- The browser page must be opened through `http://127.0.0.1:8000/desk`, not `file:///.../index.html`. A file-mode warning is intentionally present.
- The current visual design is a Hu Tao-themed service workspace. The avatar is served locally; do not replace it with a remote runtime dependency.

### Explicitly Removed From `/desk`

- Administrator platform/account fields, `/control` link, camera session control, capture controls, perceptual labels, world/operations status, and all JavaScript references to `/api/control/`.
- `tests/test_desk.py` guards this boundary: page HTML must not contain `/control`; service JS must not contain `/api/control/`.

### Vision Status And Required Next Architecture

- Existing camera backend is implemented in `app/camera/` and `app/camera/router.py`: consent sessions, local camera capture, optional QQ video-window capture, short TTL, no raw-frame persistence, no face identification, no emotion conclusion, stable-label confirmation, changes, and optional local Ollama semantic labels constrained to an allowlist.
- The camera endpoints are under `/api/control/camera/*` and require the current control authorization path. The CLI helper is `scripts/camera_control.py`.
- Do not put camera buttons back into `/desk`. The next visual phase is a separate protected visual workbench with server-side administrator session authentication, then reuse the camera APIs behind that authenticated boundary.
- Important security finding: existing control authorization is based on configured platform/account identity passed in request headers and is not a browser login session. It is insufficient to secure a new browser-visible high-privilege visual workbench. Before building that workbench, implement a real server-side login/session design (recommended: local single-admin secret in `.env`, hashed or compared server-side, short-lived `HttpOnly`, `Secure` when HTTPS, `SameSite` cookie, CSRF protection for writes, logout, expiry, audit). Never put the admin secret, platform account ID, or a reusable authorization token into client-side JavaScript/localStorage.
- The user paused this work pending later direction. Do not silently enable camera hardware, QQ capture, Ollama, or external vision models.

### World API Reality At Handoff

- `WORLD_AWARENESS_ENABLED` is currently true; `ChatService` creates `WorldBrainCoordinator(build_world_runtime(settings))` when enabled. The tool is called only for explicit user requests, with deterministic guards against invented real-time facts.
- QWeather is implemented in `app/world/adapters/qweather.py` and is used for current weather and three-day forecasts. Its runtime status on 2026-07-25: adapter registered, `QWEATHER_API_KEY` not configured, `QWEATHER_SOURCE_LEGAL_APPROVED=false`. Therefore weather requests correctly return unavailable rather than calling an unconfigured service.
- To enable QWeather after reviewing its terms, set only in `.env`: `QWEATHER_API_KEY=<secret>` and `QWEATHER_SOURCE_LEGAL_APPROVED=true`. Keep secrets out of code, docs, tests, logs, and chat output. Restart Core after configuration.
- Amap is configured and approved at this handoff and is restricted to district/place/route functions. It is not the weather provider.
- News digest/catalog code exists, but enabled news source count is zero. Sources remain disabled/legal-unapproved in `data/world/sources.json` and corresponding `.env` source-ID gates. Do not enable a feed/API/crawler without source terms review and explicit user approval.
- Current world status was verified without printing keys: world enabled true; Amap configured/approved true; QWeather configured false/approved false; news enabled 0; policy enabled 0.

### Validation And Runtime Snapshot

- Required Python runtime only: `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`.
- Latest full automated run after desk service-boundary changes: `871 passed, 2 skipped` using `python -m pytest tests -q -p no:cacheprovider`.
- Focused desk test passed after the final keyboard/boundary changes: `1 passed`.
- Browser validation used Edge/Playwright: desktop, 390 px mobile, and 320 px narrow width. At 320 px, `innerWidth=320` and `scrollWidth=320`; no horizontal overflow. Browser console had zero errors after final reload.
- Browser behavior was verified without charging the real text model by intercepting `/api/v1/chat` with a mock response. No real camera, microphone, QQ capture, or external world API request was made during this UI test.
- Core was restarted on 2026-07-25 and was listening on `127.0.0.1:8000` (PID can change). `/health`, `/desk`, and the local avatar asset returned HTTP 200.

### Next Conversation Starting Point

1. Read this handoff plus `docs/PROJECT_ARCHITECTURE_AND_OPERATIONS.md` before editing.
2. Ask whether the user wants to implement real local admin session authentication now. Do not create a high-privilege visual browser page before that decision.
3. If the user instead wants world APIs enabled, request that they set the QWeather secret locally and confirm terms approval; then run an explicit, bounded smoke test without logging secrets.
4. Keep `/desk` a service page and `/control` a management page. Treat this as a hard architecture boundary.

## 2026-08-10 Technical Architecture And GitHub Publication Audit

- Added `docs/HUTAOCHATCORE_TECHNICAL_REPORT.md`, a source-based Chinese report covering the current framework, module boundaries, HeadCore/ChatService flow, persona and relationship logic, Provider routing, storage, Database V2, authentication, audio, vision, world tools, Web/PWA, mini program, API groups, deployment, risks and development priorities.
- Classified behavior as verified, conditionally available, partially implemented or retired. QQ/Weixin Bot code is treated as historical rather than an active public-product path, and the reserved streaming ASR route is not reported as complete real-time speech.
- Documented the current Git baseline and two GitHub publication paths: pushing to the existing `origin`, or retaining it as `upstream` and adding a new user-owned `origin`.
- Audited ignored secrets and empty example credential fields without printing any local secret values. No high-confidence private key, GitHub token or real API key was found in tracked content; static scanning is not an absolute guarantee.
- Verified that five local speech-model weights are managed by Git LFS. The tracked worktree is approximately 5.8 GiB and includes a roughly 2.1 GB LFS object, so GitHub plan-specific object, storage and bandwidth limits must be checked before the first push.
- Validation with the required Python environment: `python -m compileall -q app scripts` passed; full offline suite `842 passed, 2 skipped, 2 warnings`; mini-program Node suite `5 passed`; `git lfs fsck` passed.
- The two skipped tests still require explicitly isolated MySQL credentials. No real DeepSeek, MySQL/PostgreSQL, SMTP, Qdrant, ASR/TTS quality, camera, map, weather, news or retired platform integration was claimed as validated.
- Additional publication blockers recorded in the report: no project-level license/security policy, incomplete asset/model provenance, `Dockerfile` copying approximately 8.937 GiB of `data/`, and database migration/readiness gaps that prevent claiming production-safe fresh deployment.
- Additional environment checks: `pip check` failed on OpenCV/NumPy and Parsel/jmespath conflicts; `sentence_transformers` is declared but not importable in the required environment.
- Docker CLI is not installed on the audit machine, so Compose parsing and image/runtime validation were not performed.

