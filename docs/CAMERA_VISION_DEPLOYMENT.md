# Camera Vision Deployment

## Scope

The camera extension is a local, consent-gated perception organ for HeadCore. It does not create a second agent, identify people, retain frames, upload camera data, or write automatic long-term memories.

## Install

Use the project runtime. Installation is explicit because the camera dependencies and local model weights are optional.

```powershell
cd D:\Programming-file\Graduation-Project\HutaoChatCore
& D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe -m pip install -r requirements-vision.txt
```

MediaPipe provides pose, hand, and non-identifying face-landmark cues. YOLO is optional. Download a model only through a separately reviewed local process, then set an existing local file path. The runtime never downloads a model.

## Configuration

In `.env`, keep the default-disabled values until a local user explicitly approves a test:

```env
CAMERA_PERCEPTION_ENABLED=true
CAMERA_LOCAL_CAPTURE_ENABLED=true
CAMERA_SESSION_MAX_SECONDS=300
CAMERA_OBSERVATION_TTL_SECONDS=15
CAMERA_CAPTURE_INTERVAL_SECONDS=2
CAMERA_TEMPORAL_CONFIRMATION_COUNT=2
CAMERA_TEMPORAL_WINDOW_SECONDS=8
CAMERA_MEDIAPIPE_ENABLED=true
CAMERA_YOLO_MODEL_PATH=D:/models/yolo-local.pt
CAMERA_RAW_FRAME_RETENTION_SECONDS=0
CAMERA_FACE_IDENTIFICATION_ENABLED=false
CAMERA_CLOUD_UPLOAD_ENABLED=false
```

`CAMERA_YOLO_MODEL_PATH` may remain empty. It must point to an already existing local file when enabled. Raw-frame retention, face identification, and cloud upload are rejected by the runtime even if someone changes the values.

## Local Specialized Models Only

The camera runtime does not call Ollama, Qwen, or any other generative VLM. It derives only bounded labels from local YOLO and MediaPipe components, then validates them against the camera contract. It never downloads a model, stores a frame, or sends a frame to a cloud service.

For the intended specialist-model evolution and evidence/temporal-fusion design, see [LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md](LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md). A model must be approved, present as a local file, and measured on the target machine before it is enabled.

## Local Control Commands

Use the local control helper only with an account that is already configured as a Core administrator. It sends the actor identity as control headers and relies on the Core authorization check. It never sends the camera bridge token or calls the internal context endpoint.

```powershell
cd D:\Programming-file\Graduation-Project\HutaoChatCore
$actor = "YOUR_ADMIN_QQ_ID"
& D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\camera_control.py --actor-user-id $actor session-start
```

Always stop both capture and the session after the call:

```powershell
& D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\camera_control.py --actor-user-id $actor capture-stop --session-id SESSION_ID
& D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\camera_control.py --actor-user-id $actor session-stop --session-id SESSION_ID
```

## Standalone Camera Test

No chat platform is required to validate the local visual pipeline. After enabling the camera settings and creating a consented session, start the local camera source:

```powershell
& D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\camera_control.py --actor-user-id $actor camera-capture-start --session-id SESSION_ID
& D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\camera_control.py --actor-user-id $actor capture-status --session-id SESSION_ID
```

This opens only the configured `camera_slot` for the active consented session. Use `capture-stop` followed by `session-stop` when finished.

## Controlled Flow

1. An administrator creates a session with explicit `consent_granted=true`.
2. The administrator starts capture for that session. OpenCV opens only the selected local camera slot.
3. Each frame remains in process memory, local adapters emit bounded labels, and the frame is immediately discarded.
4. Only active sessions, matching administrators, valid timestamps, confidence at least `0.85`, and repeated labels within the temporal window can form a short-lived private `vision_event`.
5. Stop capture or stop the session to release the device. A stopped or expired session rejects later observations.

## Acceptance Boundaries

Automated tests cover the contracts, consent state, expiry, resource release with a simulated camera, and model-independent normalization. A real-camera acceptance needs a physical camera, Windows privacy permission, installed optional dependencies, and an administrator request. It must verify the device indicator, no files under `data/` are created from frames, capture stop releases the camera, and no person identity or emotion statement appears in output.
