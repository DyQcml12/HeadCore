from __future__ import annotations

import asyncio

import httpx

from app.main import app


def test_archived_visual_surfaces_are_not_registered_in_the_runtime() -> None:
    async def request() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return (
                await client.get("/workbench"),
                await client.get("/api/v1/visual/context"),
                await client.get("/api/workbench/status"),
                await client.get("/api/control/camera/sessions/not-registered/capture/status"),
            )

    responses = asyncio.run(request())

    assert [response.status_code for response in responses] == [404, 404, 404, 404]


def test_archived_visual_routes_do_not_appear_in_openapi() -> None:
    paths = app.openapi()["paths"]

    assert "/workbench" not in paths
    assert "/api/v1/visual/context" not in paths
    assert not any("camera" in path or "workbench" in path for path in paths)
