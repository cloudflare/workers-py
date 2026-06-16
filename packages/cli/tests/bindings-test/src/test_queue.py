import asyncio

import pytest

pytestmark = pytest.mark.asyncio

_cache = None


def _find(messages, predicate):
    return next(m for m in messages if predicate(m))


# Send everything at once to reduce the overall test time.
# Receiving a message from the queue takes ~2 seconds,
# so batching all sends into a single sleep is more efficient.
async def _send_all_messages(env):
    global _cache
    if _cache is not None:
        return _cache

    from worker import RECEIVED_MESSAGES

    RECEIVED_MESSAGES.clear()

    q = env.TEST_QUEUE
    await asyncio.gather(
        q.send("hello queue"),
        q.send({"key": "value", "number": 42}),
        q.send(123),
        q.send("text message", contentType="text"),
        q.send(None),
        q.send(True),
        q.send([1, 2, 3]),
        q.send(""),
        q.send({"outer": {"inner": "deep"}, "list": [1, 2]}),
        q.sendBatch(
            [
                {"body": "batch 1"},
                {"body": "batch 2"},
                {"body": "batch 3"},
            ]
        ),
        q.sendBatch(
            [{"body": "text msg", "contentType": "text"}],
            delaySeconds=0,
        ),
    )

    await asyncio.sleep(2)

    assert len(RECEIVED_MESSAGES) >= 13
    _cache = list(RECEIVED_MESSAGES)
    return _cache


async def test_send_string(env):
    msgs = await _send_all_messages(env)
    msg = _find(msgs, lambda m: m["body"] == "hello queue")
    assert isinstance(msg["id"], str)
    assert msg["attempts"] >= 1


async def test_send_dict(env):
    msgs = await _send_all_messages(env)
    msg = _find(
        msgs,
        lambda m: isinstance(m["body"], dict) and m["body"].get("key") == "value",
    )
    assert msg["body"]["number"] == 42


async def test_send_number(env):
    msgs = await _send_all_messages(env)
    _find(msgs, lambda m: m["body"] == 123)


async def test_send_with_content_type(env):
    msgs = await _send_all_messages(env)
    _find(msgs, lambda m: m["body"] == "text message")


async def test_send_none(env):
    msgs = await _send_all_messages(env)
    _find(msgs, lambda m: m["body"] is None)


async def test_send_bool(env):
    msgs = await _send_all_messages(env)
    _find(msgs, lambda m: m["body"] is True)


async def test_send_list(env):
    msgs = await _send_all_messages(env)
    _find(msgs, lambda m: m["body"] == [1, 2, 3])


async def test_send_empty_string(env):
    msgs = await _send_all_messages(env)
    _find(msgs, lambda m: m["body"] == "")


async def test_send_nested_dict(env):
    msgs = await _send_all_messages(env)
    msg = _find(
        msgs,
        lambda m: isinstance(m["body"], dict)
        and isinstance(m["body"].get("outer"), dict),
    )
    assert msg["body"]["outer"]["inner"] == "deep"
    assert msg["body"]["list"] == [1, 2]


async def test_send_batch(env):
    msgs = await _send_all_messages(env)
    bodies = [m["body"] for m in msgs]
    assert "batch 1" in bodies
    assert "batch 2" in bodies
    assert "batch 3" in bodies


async def test_send_batch_with_options(env):
    msgs = await _send_all_messages(env)
    bodies = [m["body"] for m in msgs]
    assert "text msg" in bodies
