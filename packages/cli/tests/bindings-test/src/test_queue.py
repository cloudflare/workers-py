import asyncio
import sys

import pytest

# FIXME: This doesn't seem to happen in prod environment.
#        But for some reason, pytest segfaults after running tests in dev environment (workerd).
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 13),
    reason="pytest segfaults after running tests",
)


async def _send_and_receive(env, body, **send_opts):
    from worker import RECEIVED_MESSAGES

    RECEIVED_MESSAGES.clear()
    await env.TEST_QUEUE.send(body, **send_opts)
    await asyncio.sleep(2)
    assert len(RECEIVED_MESSAGES) > 0, "no messages received by consumer"
    return RECEIVED_MESSAGES[-1]


@pytest.mark.asyncio
async def test_send_string(env):
    msg = await _send_and_receive(env, "hello queue")
    assert msg["body"] == "hello queue"
    assert isinstance(msg["id"], str)
    assert msg["attempts"] >= 1


@pytest.mark.asyncio
async def test_send_dict(env):
    msg = await _send_and_receive(env, {"key": "value", "number": 42})
    assert msg["body"]["key"] == "value"
    assert msg["body"]["number"] == 42


@pytest.mark.asyncio
async def test_send_number(env):
    msg = await _send_and_receive(env, 123)
    assert msg["body"] == 123


@pytest.mark.asyncio
async def test_send_with_content_type(env):
    msg = await _send_and_receive(env, "text message", contentType="text")
    assert msg["body"] == "text message"


@pytest.mark.asyncio
async def test_send_none(env):
    msg = await _send_and_receive(env, None)
    assert msg["body"] is None


@pytest.mark.asyncio
async def test_send_bool(env):
    msg = await _send_and_receive(env, True)
    assert msg["body"] is True


@pytest.mark.asyncio
async def test_send_list(env):
    msg = await _send_and_receive(env, [1, 2, 3])
    assert msg["body"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_send_empty_string(env):
    msg = await _send_and_receive(env, "")
    assert msg["body"] == ""


@pytest.mark.asyncio
async def test_send_batch(env):
    from worker import RECEIVED_MESSAGES

    RECEIVED_MESSAGES.clear()
    batch = [
        {"body": "batch 1"},
        {"body": "batch 2"},
        {"body": "batch 3"},
    ]
    await env.TEST_QUEUE.sendBatch(batch)
    await asyncio.sleep(2)

    assert len(RECEIVED_MESSAGES) >= 3
    bodies = [m["body"] for m in RECEIVED_MESSAGES]
    assert "batch 1" in bodies
    assert "batch 2" in bodies
    assert "batch 3" in bodies


@pytest.mark.asyncio
async def test_send_batch_with_options(env):
    from worker import RECEIVED_MESSAGES

    RECEIVED_MESSAGES.clear()
    batch = [
        {"body": "text msg", "contentType": "text"},
    ]
    await env.TEST_QUEUE.sendBatch(batch, delaySeconds=0)
    await asyncio.sleep(2)

    assert len(RECEIVED_MESSAGES) >= 1
    assert RECEIVED_MESSAGES[-1]["body"] == "text msg"


@pytest.mark.asyncio
async def test_send_nested_dict(env):
    msg = await _send_and_receive(env, {"outer": {"inner": "deep"}, "list": [1, 2]})
    assert msg["body"]["outer"]["inner"] == "deep"
    assert msg["body"]["list"] == [1, 2]
