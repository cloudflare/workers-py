import asyncio

import pytest
from pyodide.ffi import create_proxy, to_js

from workers import env

TIMEOUT_S = 5

# Proxies must outlive the listeners they back; keep them per-module.
_proxies = []


def _listen(ws, event_type):
    """Future resolved with the first event of the given type."""
    fut = asyncio.get_event_loop().create_future()

    def callback(evt):
        if not fut.done():
            fut.set_result(evt)

    proxy = create_proxy(callback)
    _proxies.append(proxy)
    ws.addEventListener(event_type, proxy)
    return fut


async def _ws_connect(path):
    # Upgrade through the raw JS binding (as durable-object-websocket's
    # tester.js does): the SDK fetch wrapper routes through pyfetch, whose
    # implicit abort signal interferes with long-lived upgraded connections.
    from js import Object

    raw = env.SELF._binding
    return await asyncio.wait_for(
        raw.fetch(
            f"http://example.com{path}",
            to_js(
                {"headers": {"Upgrade": "websocket"}},
                dict_converter=Object.fromEntries,
            ),
        ),
        TIMEOUT_S,
    )


import json


async def _events():
    response = await asyncio.wait_for(
        env.SELF.fetch("http://example.com/ws-events"), TIMEOUT_S
    )
    return json.loads(await response.text())


@pytest.mark.asyncio
async def test_client_close_reaches_app_as_disconnect():
    response = await _ws_connect("/ws")
    ws = response.webSocket
    assert ws is not None
    ws.accept()
    before = len(await _events())
    ws.close(1000, "bye")
    deadline = asyncio.get_event_loop().time() + TIMEOUT_S
    while asyncio.get_event_loop().time() < deadline:
        events = await _events()
        if len(events) > before:
            assert events[-1]["type"] == "disconnect"
            return
        await asyncio.sleep(0.2)
    pytest.fail("the app never observed the client's disconnect")
