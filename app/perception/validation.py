from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.perception.contracts import PerceptionInput


ALLOWED_MIME: dict[str, frozenset[str]] = {
    "audio": frozenset({"audio/wav", "audio/mpeg", "audio/ogg", "audio/flac", "audio/amr"}),
    "image": frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"}),
    "file": frozenset({"text/plain", "application/pdf"}),
    "metadata": frozenset(),
}
MAX_BYTES = {"audio": 25 * 1024 * 1024, "image": 20 * 1024 * 1024, "file": 10 * 1024 * 1024}


class PerceptionInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InputPolicy:
    allowed_roots: tuple[Path, ...] = ()
    remote_timeout_seconds: float = 10.0


def validate_input(value: PerceptionInput, policy: InputPolicy) -> None:
    mime = value.declared_mime or value.mime_type or (value.attachment.media_type if value.attachment else None)
    size = value.declared_size_bytes if value.declared_size_bytes is not None else value.size_bytes
    if size is None and value.attachment:
        size = value.attachment.size_bytes
    allowed = ALLOWED_MIME[str(value.modality)]
    if mime and allowed and mime.lower() not in allowed:
        raise PerceptionInputError("invalid_mime", f"unsupported MIME for {value.modality}")
    limit = MAX_BYTES.get(str(value.modality))
    if limit is not None and size is not None and size > limit:
        raise PerceptionInputError("input_too_large", f"input exceeds {limit} bytes")
    if value.local_path is not None:
        _validate_local_path(value.local_path, policy)
    if value.remote_url is not None:
        _validate_remote_url(value.remote_url)


def _validate_local_path(path: Path, policy: InputPolicy) -> None:
    resolved = path.resolve()
    roots = tuple(root.resolve() for root in policy.allowed_roots)
    if not roots or not any(resolved == root or root in resolved.parents for root in roots):
        raise PerceptionInputError("path_not_allowed", "local path is outside controlled roots")
    if not resolved.is_file():
        raise PerceptionInputError("invalid_input", "local input file does not exist")
    if resolved.stat().st_size == 0:
        raise PerceptionInputError("invalid_input", "local input file is empty")


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PerceptionInputError("invalid_input", "remote URL must be credential-free HTTPS")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise PerceptionInputError("invalid_input", "remote URL hostname cannot be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise PerceptionInputError("private_network_url", "remote URL resolves to a private network")
