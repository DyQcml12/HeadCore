from __future__ import annotations

import asyncio
import inspect


def pytest_pyfunc_call(pyfuncitem) -> bool | None:
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    fixture_names = pyfuncitem._fixtureinfo.argnames
    kwargs = {name: pyfuncitem.funcargs[name] for name in fixture_names}
    asyncio.run(pyfuncitem.obj(**kwargs))
    return True
