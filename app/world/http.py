from __future__ import annotations

from typing import Any, Protocol


class HttpResponse(Protocol):
    status_code: int
    content: bytes

    def json(self) -> Any: ...


class AsyncHttpClient(Protocol):
    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...
