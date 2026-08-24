import asyncio
import contextlib

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


def _collect(ws, count):
    """Future resolved with the payloads of the first `count` messages."""
    fut = asyncio.get_event_loop().create_future()
    messages = []

    def callback(evt):
        messages.append(evt.data)
        if len(messages) == count and not fut.done():
            fut.set_result(messages)

    proxy = create_proxy(callback)
    _proxies.append(proxy)
    ws.addEventListener("message", proxy)
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


@contextlib.asynccontextmanager
async def _ws_session(path):
    """Accepted client socket, always closed again.

    A test that raises before closing leaves the app awaiting receive(), and
    the runtime keeps the request alive for that task, so the whole worker
    invocation hangs instead of reporting the failure.
    """
    response = await _ws_connect(path)
    ws = response.webSocket
    assert ws is not None
    ws.accept()
    # Without this the payload arrives as a Blob, which cannot be read
    # synchronously in the message callback.
    ws.binaryType = "arraybuffer"
    try:
        yield ws
    finally:
        ws.close()


@pytest.mark.asyncio
async def test_text_frame_arrives_as_asgi_text():
    async with _ws_session("/ws-echo") as ws:
        message = _listen(ws, "message")
        ws.send("hello")
        evt = await asyncio.wait_for(message, TIMEOUT_S)
        assert evt.data == "text=hello"


@pytest.mark.asyncio
async def test_binary_frame_arrives_as_asgi_bytes():
    async with _ws_session("/ws-echo") as ws:
        message = _listen(ws, "message")
        payload = b"\x00\x01binary"
        ws.send(to_js(payload))
        evt = await asyncio.wait_for(message, TIMEOUT_S)
        data = evt.data
        assert not isinstance(data, str), f"delivered to the app as text: {data!r}"
        assert data.to_bytes() == b"bytes=" + payload


@pytest.mark.asyncio
async def test_empty_frames_reach_the_client():
    async with _ws_session("/ws-empty") as ws:
        received = _collect(ws, 3)
        ws.send("go")
        messages = await asyncio.wait_for(received, TIMEOUT_S)
        assert messages[0] == ""
        assert messages[1].to_bytes() == b""
        assert messages[2] == "done"


@pytest.mark.asyncio
async def test_application_close_reaches_client_with_code_and_reason():
    async with _ws_session("/ws-close") as ws:
        closed = _listen(ws, "close")
        ws.send("close")
        event = await asyncio.wait_for(closed, TIMEOUT_S)
        assert event.code == 4001
        assert event.reason == "application-close"


@pytest.mark.asyncio
async def test_environment_reaches_websocket_scope():
    async with _ws_session("/ws-env") as ws:
        message = _listen(ws, "message")
        ws.send("env")
        event = await asyncio.wait_for(message, TIMEOUT_S)
        assert event.data == "worker-environment"


@pytest.mark.asyncio
async def test_app_crash_closes_the_transport():
    async with _ws_session("/ws-crash") as ws:
        close = _listen(ws, "close")
        evt = await asyncio.wait_for(close, TIMEOUT_S)
        assert evt.code == 1011
