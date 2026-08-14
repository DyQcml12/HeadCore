from __future__ import annotations

import asyncio
import sys


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """uvicorn loop factory for HutaoChatCore.

    On Windows, uvicorn's default factory returns ``ProactorEventLoop`` which
    cannot run psycopg's async driver (no ``add_reader`` support). PostgreSQL
    storage therefore requires a selector-based loop; on other platforms the
    default policy loop is kept.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
