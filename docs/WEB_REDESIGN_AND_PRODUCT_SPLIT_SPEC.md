# HutaoChatCore Web Redesign And Product Split Specification

> Status: proposed design baseline
>
> Purpose: establish the product, frontend, delivery, attribution, and client-boundary rules before moving frontend files or rebuilding routes.

## 1. Product Decision

HutaoChatCore becomes a character companion platform where a user can create, configure, and converse with their own role. Hu Tao remains the historical project name and one possible built-in preset, but it is not the visual identity, default character image, soundtrack, or product narrative of the public website.

The public product must never imply that a user is talking to a canon character, that uploaded role materials are officially licensed, or that a voice model has rights that were not declared by its owner.

### Primary user outcome

1. A visitor understands that the product creates private character conversations, not a single themed chat room.
2. A new user can register, create or select a role, and begin a conversation without encountering unavailable features.
3. A returning user can find conversations, role cards, memory controls, data boundaries, and provider settings.
4. A contributor can see which projects, models, assets, and licenses are used before downloading or using a product surface.

### Scope for the first public Web release

Included:

- Text conversation, hold-to-talk audio messages when ASR is genuinely available, reply audio when server-side TTS is genuinely enabled.
- Account, sessions, memories, role-card selection, data controls, and capability status.
- A public landing page, a source and license page, and a future-product directory that clearly distinguishes available, local-only, and planned products.

Not included:

- Public model training, unrestricted voice cloning, background screen capture, browser video calls, generic computer control, Live2D claims without a working runtime, or autonomous game control.

## 2. Design Read

Reading this as: a consumer creator product for anime and role-play users, with an original character-creation language, leaning toward a cinematic editorial landing page and a quiet, high-utility conversation application.

Design dials:

- `DESIGN_VARIANCE: 7`. The landing page uses asymmetric media composition. Product pages use predictable task layouts.
- `MOTION_INTENSITY: 6`. Motion communicates response, selection, and state transitions. It is not continuous decoration.
- `VISUAL_DENSITY: 4`. The landing page leaves room for visual art. Conversation and account screens remain compact and scannable.

### Reference audit

| Reference | Useful lesson | Not copied |
| --- | --- | --- |
| `mineradio.cn` | Single product thesis, cross-platform route, rich media-led first screen, downloads as a real workflow | Its typography, logo, yellow and blue palette, content order, artwork, text, and motion language |
| `vgen.co` | Creator assets are the visual subject; categories and creator rights must be visible | Marketplace behavior, creator art, brands, artwork, wording, or visual assets |
| `reactbits.dev` | Isolated animation components can improve a moment without dictating the whole product | Component code until license and implementation suitability are reviewed |
| `ui.aceternity.com` | Interactive cards and media previews need clear hierarchy and functional controls | Component markup, demonstration assets, and black-card visual treatment |
| `uiverse.io` | Small interaction patterns are useful only after accessibility and mobile behavior are verified | Community snippets without license and maintenance review |

The design deliberately avoids generic AI gradients, repeated equal cards, floating decorative labels, borrowed character art, custom mouse cursors, and IP-specific music.

## 3. Visual System

### 3.1 Brand direction

The product visual language is `Original Anime Creation Studio`.

- Background: charcoal ink with subtle blue-gray depth, not a purple or Genshin palette.
- Accent: coral signal `#F06A63` for the single primary action and selected role state.
- Supporting status colors: jade only for real availability, muted amber only for warnings, red only for destructive or failed states.
- Surfaces: near-black layered panels and fine neutral borders. Cards have a maximum 8px radius. Buttons may be pill-shaped only where their compact command purpose is obvious.
- Type: self-hosted or system Chinese sans stack first. No remote font request is required for first paint.
- Icons: one icon family only. Buttons use familiar icons and accessible labels or tooltips.

### 3.2 Visual assets

The public site needs original visual assets before it can be considered complete:

1. One original 16:10 hero artwork showing a non-specific anime character creation scene. It may not resemble Hu Tao, Genshin, or another protected character.
2. Three original 4:3 editorial images for role cards, voice packs, and cross-device companion use.
3. Real screenshots of the rebuilt conversation and role studio. No HTML imitation screenshot is allowed.
4. User-provided role artwork is always displayed with source and rights metadata. It is not reused in product marketing without explicit permission.

Generated original artwork can be used after visual review. Third-party art, screenshots, music, and fan assets require an attribution entry and must not be assumed commercial-safe.

### 3.3 Motion rules

- Hero artwork may use a short opacity and transform entrance. It stops under `prefers-reduced-motion`.
- Role selection uses a shared-element or border transition to show the selected identity.
- Chat uses one short thinking state before the first streamed response. It never inserts a fake assistant message.
- Audio playback uses a real progress and availability state. There is no autoplay background music.
- The landing page can use one scroll-reveal system. It must animate only opacity and transform, and no continuous animation may block input or increase mobile heat.

## 4. Information Architecture

| Route | Product role | First release behavior |
| --- | --- | --- |
| `/` | Public official website | Product thesis, real capabilities, product directory, source and license entry, start action |
| `/desk` | Conversation studio | Role selection, text conversation, allowed audio input, memories and dialogue context |
| `/auth` | Account task page | One active view at a time: login, registration, verification, reset. Submission reflects actual backend availability |
| `/me` | Account and data center | Account, active sessions, role cards, memory controls, privacy, provider configuration status |
| `/credits` | Attribution and licensing | Dependencies, model references, artwork and music policy, project links, licenses, commercial-use status |
| `/downloads` | Product directory | Web access plus clear desktop, Voice Studio, and Minecraft future-state entries. No dead download buttons |

`/control` and `/workbench` remain separate administrator-local surfaces. They are not linked from the ordinary public navigation.

## 5. Page Designs

### 5.1 Official website `/`

The home page is a product story, not an oversized feature catalogue.

1. Navigation: wordmark, product anchors, `来源与许可`, and one `开始创作` action. It collapses to a real menu below 1024px.
2. Asymmetric hero: direct headline, one sentence of product value, two distinct actions, and original hero artwork. The headline must fit in two desktop lines.
3. Role creation section: an editorial composition showing that identity, speech style, boundaries, knowledge range, and voice are separate choices.
4. Conversation continuity section: a real rebuilt Desk screenshot with callouts limited to actual functions.
5. Product directory: Web/PWA, Voice Studio, Desktop Companion, and Minecraft Companion. Each item has a truthful availability state and a single applicable action.
6. Trust and attribution section: privacy boundary summary, source disclosure route, and data control route. No invented customer metrics or testimonials.
7. Footer: product links, source and license links, privacy notice, and project status. No fictitious social proof.

### 5.2 Conversation studio `/desk`

The Desk is a task surface. It should feel like an anime creation tool, not a character shrine.

- Desktop: role rail at 288px, conversation as the largest area, contextual role details in a collapsible panel instead of permanent decorative art.
- Tablet: role header becomes a controlled strip above the conversation. Conversation retains at least 540px usable width in landscape where possible.
- Phone: conversation is the first screen. Role switcher, memories, and context live behind bottom navigation or a sheet. The composer respects the safe area and never competes with navigation.
- Empty state: a user without a role sees an explicit `创建角色` action and a concise explanation. The app does not pretend there is a default character.
- Role card: avatar, name, role status, short self-written description, and capability badges. No copyrighted character image is supplied by the platform.
- Conversation: streaming text, recoverable network error, retry, a visible thinking timer, and per-message audio only when a valid `reply_id` and TTS capability exist.
- Memory and context: present information as user data controls, with a native confirmation dialog before deletion.

### 5.3 Authentication `/auth`

Authentication is a focused account operation, not a themed landing screen.

- One active form only. A password visibility icon changes the type of the same field. It never creates a duplicate password input.
- Labels remain above inputs. Validation errors appear below the relevant input. Server errors remain near the submit action.
- No `返回对话` bypass action is visible to an anonymous visitor. A validated `return_to` route runs only after login succeeds.
- When public authentication is disabled, fields remain readable but the unavailable state and disabled submission are honest.
- Loading locks the current form and preserves entered data after a recoverable failure.

### 5.4 Personal center `/me`

The personal center manages data and identity. It is not a decorative personal notebook.

- Account overview: display name, verified state, current session, and sign-out.
- My roles: role cards, version, active scope, source declaration, and edit action when Role Studio is implemented.
- Memory: searchable list, scope, source, correction, export request status, and destructive delete confirmation.
- Privacy: microphone, voice reply, desktop visual capabilities, data retention, and current consent state. Each state names the actual source of truth.
- Provider settings: later only. A user-owned API key is encrypted server-side, rendered as a mask, revocable, and never returned to browser JavaScript.

## 6. Functional Contract

The redesign must preserve current public APIs while removing Hu Tao-specific markup and copy.

| UI action | Current server contract | Redesign requirement |
| --- | --- | --- |
| Text conversation | `POST /api/v1/chat/stream` | Stream into one assistant message, show thinking state before first chunk, restore composer on failure |
| Audio message | `POST /api/v1/audio/chat/file` | Hold-to-talk only, explicit microphone permission and clear transcription failure |
| Auth state | `GET /api/v1/auth/status` | Controls real enabled, disabled, registration, and password reset paths |
| Login and logout | `/api/v1/auth/*` | Web uses HttpOnly session cookie plus CSRF. Mobile uses the existing Bearer response only over HTTPS |
| Memory | `GET /api/v1/memories`, `DELETE /api/v1/memories/{memory_id}` | Read, correct or delete only the current authorized user's records |
| Dialogue context | `GET /api/v1/dialogue-context` | Show bounded status, not hidden reasoning or an invented world state |
| Reply TTS | `/api/v1/voice/status`, `POST /api/v1/voice/synthesize` | Render only when backend returns available and a short-lived reply token exists |

No public page may call `/api/control/*`, `/workbench`, camera capture, configuration, logs, or database control endpoints.

## 7. Attribution, Sources, And Non-commercial Status

`/credits` must be implemented before public release. Its entries are data-backed rather than hard-coded marketing claims.

Each entry contains:

```text
name
category: framework | model | dataset | adapter | artwork | audio | reference project
upstream URL
license or terms URL
local usage description
version or commit when known
commercial status: confirmed | restricted | unknown | not allowed
attribution text required by upstream
review date
```

Rules:

- `unknown`, `restricted`, and `not allowed` dependencies make the relevant feature unavailable in any commercial deployment.
- A reference project is credited as inspiration only. It does not imply copied code or endorsement.
- User uploaded datasets, role materials, and Voice Packs are private by default and have their own rights declaration.
- No music provider, character asset, dataset, or model is represented as commercially licensed without a recorded review.

## 8. Frontend Migration

The existing static pages can be migrated without changing their public paths. No directory is moved until its direct tests are updated first.

| Current location | Target location | Route remains |
| --- | --- | --- |
| `app/static/desk/` | `app/static/web/studio/` | `/desk` |
| `app/static/auth/` | `app/static/web/account/` | `/auth` |
| `app/static/profile/` | `app/static/web/profile/` | `/me` |
| `app/static/shared/` | `app/static/web/shared/` | `/ui/*` |
| none | `app/static/web/site/` | `/` |
| none | `app/static/web/credits/` | `/credits` |
| none | `app/static/web/downloads/` | `/downloads` |

Migration sequence:

1. Add tests for `/`, `/credits`, and static asset route behavior before adding page code.
2. Create the generic shared token system while keeping compatibility routes for `/ui/theme.css` and shared assets.
3. Add the public official website and credits page. These pages do not require private APIs.
4. Move and replace Desk markup, style, and client script while preserving `/desk` API calls and behavioral tests.
5. Move and replace account and profile pages while preserving form field names, authenticated endpoints, and CSRF behavior.
6. Remove Hu Tao-only files, music iframe behavior, custom cursor assets, and hard-coded character image routes only after no page or test imports them.

The current route names remain stable. A later React or component-based frontend migration is optional and must not block this static FastAPI release.

## 9. WeChat Mini Program Without WeChat Cloud Development

The mini program uses Hutao Core as its own backend. It does not use WeChat Cloud Functions, Cloud Database, or Cloud Storage.

```text
WeChat Mini Program
  -> HTTPS api.example.com
  -> reverse proxy
  -> Hutao Core FastAPI
  -> MySQL, Core services, LLM provider
```

Current state:

- `miniprogram/config.js` already exposes a single `apiBaseUrl` configuration point.
- `POST /api/v1/auth/mobile/login` already returns a Bearer session for the existing email and password login flow.
- Production must use a domain name with valid TLS, ICP and WeChat domain-whitelist requirements. It cannot use `127.0.0.1`, `localhost`, or a raw server IP.

Future WeChat-native login is a separate feature, not a UI-only switch:

1. The user calls `wx.login()` to receive a temporary code.
2. The mini program posts the code to a new Core exchange endpoint over HTTPS.
3. Core exchanges the code server-side with WeChat, maps the resulting stable identity to an internal profile, and issues a short-lived Core session.
4. The mini program stores only the short-lived session using platform-safe storage and sends it as a Bearer token.
5. Core refreshes, revokes, audits, and rate-limits the session. The WeChat AppSecret remains only in Core environment configuration.

The mini program reuses text chat, voice message upload, replies, memories, and account state. It does not expose the visual workbench, system controls, local training, screen capture, or desktop automation.

## 10. Later Native Products

### Desktop Companion

Desktop is a local capability host that renders a user-owned model or a built-in demonstration model. Model import must define supported format, source rights, minimum texture resolution, animation map, audio format, performance tier, and deletion behavior before a model can be displayed.

The first desktop release uses text chat, local ASR, optional local TTS, and a visible consent gateway. Screen reading and computer control are off by default, scoped to a user-chosen window or task, and never copied into Web or mini program features.

### Voice Studio

Voice Studio remains a separate local application wrapping the existing GPT-SoVITS workflow. It imports user-authorized audio, cleans and labels it locally, trains locally, creates a private Voice Pack, and gives the desktop app a local TTS provider. It does not change HeadCore, persona, or the language model.

### Minecraft Companion

Minecraft begins as local read-only support. A permitted mod or local bridge emits structured game events. The companion offers chat and voice guidance. No screen scraping, process-memory access, public-server botting, anti-cheat evasion, or autonomous gameplay belongs in the first release.

## 11. Acceptance Gates

The Web release is not ready because a page opens. It is ready only when:

- Every route works from 320px to 1920px without horizontal overflow, clipped text, inaccessible controls, or fixed input overlap.
- Light and dark modes meet contrast requirements. Reduced motion removes all nonessential animation.
- Loading, empty, unauthorized, unavailable, network error, and retry states are designed and manually checked.
- No Hu Tao, Genshin, Liyue, Wangsheng, hard-coded Hu Tao avatar, custom cursor, or NetEase music behavior appears in public role-creation pages.
- The landing page uses approved original assets and real product screenshots.
- `/credits` has an entry for every borrowed project, model, dataset, runtime, asset, and package that requires attribution or licensing review.
- Web and mini program never call privileged local control endpoints.
- Browser regression tests, backend tests, and desktop, tablet, and phone Playwright checks pass before release.

## 12. Next Implementation Slice

The first code slice is deliberately small and test-first:

1. Add tests proving `/`, `/credits`, and their static CSS and JavaScript routes exist.
2. Add the generic shared token layer and a public official website shell.
3. Add a credits data file and render it as a plain, reviewable page.
4. Capture browser screenshots at desktop, tablet, and phone widths.

Only after that slice is accepted should the implementation move `/desk`, `/auth`, and `/me` from their Hu Tao-specific static directories into the generic Web structure.
