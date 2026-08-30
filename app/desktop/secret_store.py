from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def read_secret(path: Path, name: str) -> str:
    values = _read_values(path)
    return str(values.get(name) or "")


def write_secret(path: Path, name: str, value: str) -> None:
    clean_name = name.strip()
    clean_value = value.strip()
    if not clean_name or not clean_value:
        return
    values = _read_values(path)
    values[clean_name] = clean_value
    payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
    encrypted = _protect(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _read_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(_unprotect(path.read_bytes()).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _protect(payload: bytes) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("DPAPI secret storage requires Windows")
    return _crypt(payload, protect=True)


def _unprotect(payload: bytes) -> bytes:
    if sys.platform != "win32":
        raise ValueError("DPAPI secret storage requires Windows")
    return _crypt(payload, protect=False)


def _crypt(payload: bytes, *, protect: bool) -> bytes:
    buffer = ctypes.create_string_buffer(payload)
    input_blob = _DataBlob(
        len(payload),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if protect:
        succeeded = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "HuTaoAssistant",
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        )
    else:
        succeeded = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        )
    if not succeeded:
        raise OSError(ctypes.get_last_error(), "Windows DPAPI operation failed")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
