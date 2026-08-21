import asyncio

import pytest
from pyodide.ffi import create_proxy
from worker import Default

from workers import Request

TIMEOUT_S = 5
_proxies = []


@pytest.mark.asyncio
async def test_generated_entrypoint_serves_fastapi_websocket():
    entrypoint = object.__new__(Default)
    entrypoint.env = {}
    request = Request(
        "http://testserver/websocket/echo", headers={"Upgrade": "websocket"}
    )

    response = await entrypoint.fetch(request)
    assert response.status == 101

    websocket = response.webSocket
    websocket.accept()
    message = asyncio.get_event_loop().create_future()

    def onmessage(event):
        if not message.done():
            message.set_result(event.data)

    proxy = create_proxy(onmessage)
    _proxies.append(proxy)
    websocket.addEventListener("message", proxy)
    try:
        websocket.send("hello")
        assert await asyncio.wait_for(message, TIMEOUT_S) == "echo:hello"
    finally:
        websocket.close()
