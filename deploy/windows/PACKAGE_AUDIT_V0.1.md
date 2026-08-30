# HuTao Assistant 0.1 Windows package audit

> **0.2 delta (unmeasured):** the launcher now opens the local app through a
> three-tier window strategy (`pywebview` native window → chromeless Edge/Chrome
> `--app` window → default browser), the in-app uninstall button really launches
> `unins000.exe` via `POST /api/v1/desktop/uninstall`, and a voice status card
> reports whether the local GPT-SoVITS service (9880) is reachable through
> `GET /api/v1/desktop/voice/status`. These paths have not yet been re-measured
> or re-smoke-tested on a packaged build.

Validated on Windows 10/11-compatible x64 packaging on 2026-08-28.

## Measured release

- Installer: `HuTaoAssistant-Setup-0.1.0.exe`
- Installer size: 19.30 MiB
- Installed application payload: 44.61 MiB, 782 files
- Idle application working set during smoke test: about 80 MiB
- Installer SHA-256: `767B5B174767FFC0733328DF8E5E0E90192947FDAAEB51DFA5E23C85FD5C2336`
- Code signature: not signed

Model API calls, image size, chat length, local model selection, and optional
database services determine CPU, GPU, RAM, disk, and network use beyond this
idle baseline.

## Included

- `HuTaoAssistant.exe` and its embedded Python 3.11 runtime
- FastAPI/Uvicorn HTTP and WebSocket runtime
- Desktop configuration, chat, vision-routing, memory, permission, and local
  settings UI
- DeepSeek/OpenAI-compatible API adapters
- Windows DPAPI secret storage
- Hu Tao persona registration already present in application code
- Standard Windows uninstaller and Apps & Features registration

## Excluded from the core installer

- Repository source history, tests, logs, temporary output, build caches, and
  frontend developer dependencies
- `.env`, API keys, existing chats, local configuration, and generated indexes
- `external/` and `model_training/`
- Torch, ModelScope, Transformers, FunASR, local sentence-transformers,
  Ultralytics, MediaPipe, OpenCV, Playwright, and model weights
- GPT-SoVITS training runtime and third-party archives

## Optional packs and release blockers

- Qdrant is currently an external semantic index service; it is configurable
  but not bundled or automatically started by version 0.1.
- Local ASR, local embeddings, local camera inference, and voice training must
  be separate optional installers or downloads.
- The Hu Tao voice model and any third-party training framework must not be
  publicly redistributed until character, voice, model, framework, and archive
  licenses have been reviewed and the original creator/tutorial attribution is
  recorded.
- Public releases should be Authenticode-signed before download distribution.

## Smoke-test results

- Packaged and installed application returned HTTP 200 and service `ready`.
- Runtime data resolved beneath the user-selected installation directory.
- Desktop and 390 x 844 mobile layouts had no horizontal overflow or browser
  console errors.
- Silent uninstall removed program files and the Apps & Features registration
  while preserving test chat and model data.
