from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.audio.schemas import AsrEvent, AsrStartMessage


router = APIRouter(prefix="/api/v1/audio", tags=["audio"])


@router.websocket("/transcribe/stream")
async def transcribe_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        raw_start = await websocket.receive_text()
        start = AsrStartMessage.model_validate_json(raw_start)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "message": (
                        "Streaming ASR route is reserved for FunASR 2pass worker. "
                        "Use scripts/asr_file_smoke.py for current real-model validation."
                    ),
                    "sample_rate": start.sample_rate,
                    "language": start.language,
                    "mode": start.mode,
                },
                ensure_ascii=False,
            )
        )
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_text(
            json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
        )


def as_json(event: AsrEvent) -> str:
    return json.dumps(
        {
            "type": event.type,
            "text": event.text,
            "is_final": event.is_final,
            "start_ms": event.start_ms,
            "end_ms": event.end_ms,
            "confidence": event.confidence,
        },
        ensure_ascii=False,
    )
