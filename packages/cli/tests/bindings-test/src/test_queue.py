import asyncio
import sys

import pytest

pytestmark = [
    pytest.mark.skipif(
        sys.version_info < (3, 13),
        reason="pytest segfaults after running tests",
    ),
    pytest.mark.asyncio,
]

_send_cache = None
_batch_cache = None


def _find(messages, predicate):
    return next(m for m in messages if predicate(m))


async def _get_send_results(env):
    global _send_cache
    if _send_cache is not None:
        return _send_cache

    from worker import RECEIVED_MESSAGES

    RECEIVED_MESSAGES.clear()

    # Send everything at once to reduce the overall test time
    await env.TEST_QUEUE.send("hello queue")
    await env.TEST_QUEUE.send({"key": "value", "number": 42})
    await env.TEST_QUEUE.send(123)
    await env.TEST_QUEUE.send("text message", contentType="text")
    await env.TEST_QUEUE.send(None)
    await env.TEST_QUEUE.send(True)
    await env.TEST_QUEUE.send([1, 2, 3])
    await env.TEST_QUEUE.send("")
    await env.TEST_QUEUE.send({"outer": {"inner": "deep"}, "list": [1, 2]})

    await asyncio.sleep(2)

    assert len(RECEIVED_MESSAGES) >= 9
    _send_cache = list(RECEIVED_MESSAGES)
    return _send_cache


async def _get_batch_results(env):
    global _batch_cache
    if _batch_cache is not None:
        return _batch_cache

    from worker import RECEIVED_MESSAGES

    RECEIVED_MESSAGES.clear()

    await env.TEST_QUEUE.sendBatch(
        [
            {"body": "batch 1"},
            {"body": "batch 2"},
            {"body": "batch 3"},
        ]
    )
    await env.TEST_QUEUE.sendBatch(
        [{"body": "text msg", "contentType": "text"}],
        delaySeconds=0,
    )

    await asyncio.sleep(2)

    assert len(RECEIVED_MESSAGES) >= 4
    _batch_cache = list(RECEIVED_MESSAGES)
    return _batch_cache


async def test_send_string(env):
    msgs = await _get_send_results(env)
    msg = _find(msgs, lambda m: m["body"] == "hello queue")
    assert isinstance(msg["id"], str)
    assert msg["attempts"] >= 1


async def test_send_dict(env):
    msgs = await _get_send_results(env)
    msg = _find(
        msgs,
        lambda m: isinstance(m["body"], dict) and m["body"].get("key") == "value",
    )
    assert msg["body"]["number"] == 42


async def test_send_number(env):
    msgs = await _get_send_results(env)
    _find(msgs, lambda m: m["body"] == 123)


async def test_send_with_content_type(env):
    msgs = await _get_send_results(env)
    _find(msgs, lambda m: m["body"] == "text message")


async def test_send_none(env):
    msgs = await _get_send_results(env)
    _find(msgs, lambda m: m["body"] is None)


async def test_send_bool(env):
    msgs = await _get_send_results(env)
    _find(msgs, lambda m: m["body"] is True)


async def test_send_list(env):
    msgs = await _get_send_results(env)
    _find(msgs, lambda m: m["body"] == [1, 2, 3])


async def test_send_empty_string(env):
    msgs = await _get_send_results(env)
    _find(msgs, lambda m: m["body"] == "")


async def test_send_nested_dict(env):
    msgs = await _get_send_results(env)
    msg = _find(
        msgs,
        lambda m: isinstance(m["body"], dict)
        and isinstance(m["body"].get("outer"), dict),
    )
    assert msg["body"]["outer"]["inner"] == "deep"
    assert msg["body"]["list"] == [1, 2]


async def test_send_batch(env):
    msgs = await _get_batch_results(env)
    bodies = [m["body"] for m in msgs]
    assert "batch 1" in bodies
    assert "batch 2" in bodies
    assert "batch 3" in bodies


async def test_send_batch_with_options(env):
    msgs = await _get_batch_results(env)
    bodies = [m["body"] for m in msgs]
    assert "text msg" in bodies
