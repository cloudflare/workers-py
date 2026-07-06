import base64

import js
import pytest
from pyodide.ffi import create_proxy, to_js
from workers._workers import _BindingWrapper

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)


def _make_stream(data):
    def start(controller):
        controller.enqueue(to_js(data))
        controller.close()

    return js.ReadableStream.new(to_js({"start": create_proxy(start)}))


@pytest.mark.asyncio
async def test_is_wrapped(env):
    assert isinstance(env.IMAGES, _BindingWrapper)


@pytest.mark.asyncio
async def test_output_as_png(env):
    pipeline = env.IMAGES.input(_make_stream(PNG_1X1))
    output = await pipeline.output({"format": "image/png"})
    resp = output.response()
    assert resp.headers.get("content-type") == "image/png"


@pytest.mark.asyncio
async def test_transform_and_output(env):
    pipeline = env.IMAGES.input(_make_stream(PNG_1X1))
    transformed = pipeline.transform({"width": 1, "height": 1})
    output = await transformed.output({"format": "image/png"})
    resp = output.response()
    assert resp.headers.get("content-type") == "image/png"
