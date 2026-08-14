# Local Model Installation Map

## Rules

Use only the project Python runtime:

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe'
```

Do not install Ollama, Qwen VLM, or any other generative visual-language model for this project. QQ and WeChat Bot runtimes are removed and need no model, account, or gateway dependency.

All downloaded weights belong below `HutaoChatCore/data/models/`; `external/` is reserved for separately versioned local applications such as the existing GPT-SoVITS checkout. Do not place model weights in a user-profile cache when a project-local location is available.

## Required And Optional Models

| Capability | Model | Exact local location | Status |
| --- | --- | --- | --- |
| Speech recognition | `iic/SenseVoiceSmall` | `data/models/modelscope/iic/SenseVoiceSmall/` | Existing runtime path |
| VAD for ASR | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | `data/models/modelscope/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch/` | Existing runtime path |
| Punctuation for ASR | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | `data/models/modelscope/iic/punc_ct-transformer_cn-en-common-vocab471067-large/` | Existing runtime path |
| Audio expression cue | `iic/emotion2vec_plus_large` | `data/models/modelscope/iic/emotion2vec_plus_large/` | Existing runtime path |
| Object detection | YOLO11n ONNX or approved YOLOv8n ONNX | `data/models/vision/yolo/yolo11n.onnx` | Future vision-worker input; current camera accepts an explicit local YOLO path |
| Body pose | MediaPipe Pose Landmarker Lite | `data/models/vision/mediapipe/pose_landmarker_lite.task` | Future pinned asset |
| Hand gesture | MediaPipe Gesture Recognizer | `data/models/vision/mediapipe/gesture_recognizer.task` | Future pinned asset |
| Face cues only | MediaPipe Face Landmarker | `data/models/vision/mediapipe/face_landmarker.task` | Future pinned asset; never use face identity features |
| OCR | RapidOCR ONNX assets | `data/models/vision/ocr/rapidocr/` | Future worker configuration; current QQ OCR path is removed |
| Action sequence | MoViNet-A0 ONNX or TFLite | `data/models/vision/action/movinet_a0/` | Add only after benchmark |
| Speech generation | Existing GPT-SoVITS checkout and approved voice weights | `external/GPT-SoVITS-v2pro-20250604/` | Service is separate from Core and currently unavailable |

The ASR code already resolves the four ModelScope paths above from `data/models/modelscope/`. If one of those folders is absent, it falls back to the model identifier, which may trigger a remote download. For offline deployment, pre-populate every listed folder, keep `disable_update=true`, and block outbound network access for the service process after verification.

## Installation Order

1. Install code dependencies only:

```powershell
cd D:\Programming-file\Graduation-Project\HutaoChatCore
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pip install -r requirements.txt
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pip install -r requirements-vision.txt
```

2. Download each approved weight on a reviewed machine, record its source URL, license, version and SHA-256 in a deployment record, then copy it to the exact directory in this document.
3. Configure only the existing local camera setting after an approved YOLO weight exists:

```env
CAMERA_YOLO_MODEL_PATH=./data/models/vision/yolo/yolo11n.onnx
CAMERA_MEDIAPIPE_ENABLED=true
```

4. Run the preflight and a fixed-corpus benchmark before enabling camera capture. Do not treat an import check as a perception-quality result.

## What Not To Install

- Do not install Ollama or Qwen for image understanding.
- Do not install NoneBot, OneBot, NapCat, or Hermes for this backend.
- Do not enable face recognition, remote frame upload, or automatic long-term storage of visual observations.
- Do not deploy MoViNet or an emotion classifier until it has passed the target hardware latency and accuracy acceptance described in `LOCAL_FIRST_VISUAL_WORLD_MODEL_DESIGN.md`.
