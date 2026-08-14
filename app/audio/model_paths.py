from __future__ import annotations

from pathlib import Path

from app.core.config import PROJECT_ROOT


LOCAL_MODELSCOPE_ROOT = PROJECT_ROOT / "data" / "models" / "modelscope"


def resolve_modelscope_model(model: str) -> str:
    local_path = LOCAL_MODELSCOPE_ROOT / Path(*model.split("/"))
    if local_path.exists():
        return str(local_path)
    return model


def resolve_funasr_aux_model(model: str | None) -> str | None:
    if not model:
        return None
    aliases = {
        "fsmn-vad": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        "ct-punc": "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
    }
    return resolve_modelscope_model(aliases.get(model, model))
