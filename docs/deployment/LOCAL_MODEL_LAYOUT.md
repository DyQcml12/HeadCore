# Local Model Layout And Semantic Memory

This project does not need Ollama for semantic memory, ASR, TTS, or the planned specialist vision pipeline. Keep model files separate from the repository so source updates, Docker images, and model assets have independent lifecycles.

## Recommended Directories

Development machine:

```text
D:\HutaoModels\
  embedding\bge-m3\
  asr\sensevoice-small\
  audio-emotion\emotion2vec-plus-large\
  vision\object-detection\
  vision\face-expression\
  vision\pose-and-hands\
  voice\hutao\
```

Server:

```text
/srv/hutao/models/
  embedding/bge-m3/
  asr/sensevoice-small/
  audio-emotion/emotion2vec-plus-large/
  vision/object-detection/
  vision/face-expression/
  vision/pose-and-hands/
  voice/hutao/
```

`/srv/hutao/models` is mounted read-only at `/models` for the semantic-memory worker. The server configuration should therefore use `SEMANTIC_MEMORY_EMBEDDING_MODEL_PATH=/models/bge-m3`.

## Semantic Memory

Use `BAAI/bge-m3` as the production embedding model. It is multilingual, suitable for Chinese conversational recall, and produces 1024-dimensional dense vectors. Download it before enabling the worker, then place the complete Hugging Face/Sentence-Transformers directory at `embedding/bge-m3`.

For a laptop-only smoke test, `BAAI/bge-small-zh-v1.5` is a smaller alternative. It is not a quality-equivalent replacement for cross-topic, cross-language long-term recall, so do not mix its vectors with a `bge-m3` Qdrant collection. A model replacement requires creating a new Qdrant collection or rebuilding the existing derived index.

Enable the semantic worker only after V2 migration is complete:

```text
SEMANTIC_MEMORY_ENABLED=true
SEMANTIC_MEMORY_QDRANT_URL=http://qdrant:6333
SEMANTIC_MEMORY_EMBEDDING_PROVIDER=local_sentence_transformer
SEMANTIC_MEMORY_EMBEDDING_MODEL_PATH=/models/bge-m3
SEMANTIC_MEMORY_EMBEDDING_DEVICE=cpu
```

The worker creates the Qdrant collection with cosine distance and a keyword payload index for `profile_id`. Qdrant has no memory text authority: it contains only `record_id`, `profile_id`, vector, and revision. MySQL remains the source of truth and can rebuild the vector index through `semantic_memory_outbox`.

## Specialist Perception Plan

Do not use a general visual LLM as the always-on camera loop. Use specialized local components and emit bounded observations for HeadCore:

| Capability | Recommended local component | Output boundary |
| --- | --- | --- |
| Object and scene entities | Ultralytics YOLO11 or YOLOv8 ONNX model | class, box, confidence, track id |
| Face landmarks and coarse expression cues | MediaPipe Face Landmarker plus a local facial-expression ONNX classifier | landmarks, expression probabilities, confidence |
| Pose and gesture | MediaPipe Pose and Hand Landmarker | joints, gesture labels, confidence |
| Text in image | RapidOCR ONNX | recognized text, regions, confidence |
| Speech content | FunASR SenseVoice Small | transcript, language, quality score |
| Speech affect | emotion2vec | probability distribution, not a psychological diagnosis |

The vision runtime should fuse timestamped observations over a short window, track uncertainty, and pass only compact evidence to HeadCore. It must not identify people by default, infer sensitive traits, or activate a camera without a separate explicit consent gate. A future world model should operate on these verified observations and tool evidence, not raw frames or unsupported model narratives.

## Voice Models

Keep the existing voice runtime assets under `voice/hutao` and do not place training checkpoints in the production model directory until they pass listening evaluation. TTS should consume the final response text after expression cleanup; ASR and TTS performance must be measured separately from LLM latency.
