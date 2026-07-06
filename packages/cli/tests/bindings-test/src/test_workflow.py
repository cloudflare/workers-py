import asyncio

import pytest
from js import Object
from pyodide.ffi import JsProxy, to_js

pytestmark = pytest.mark.asyncio


TERMINAL = ("complete", "errored", "terminated")


async def _poll(instance, until=TERMINAL, timeout=10.0):
    elapsed = 0.0
    interval = 0.1
    while elapsed < timeout:
        status = await instance.status()
        assert not isinstance(status, JsProxy)
        if status["status"] in until:
            return status
        await asyncio.sleep(interval)
        elapsed += interval
    raise AssertionError(f"workflow did not reach {until} within {timeout}s")


async def _poll_until_settled(instance, timeout=20.0):
    """Poll until the workflow leaves the queued/running states.

    Returns the first status that is either terminal or waiting (e.g. blocked on
    an event), without depending on the exact runtime-specific waiting label.
    """
    elapsed = 0.0
    interval = 0.1
    status = await instance.status()
    while elapsed < timeout:
        if status["status"] not in ("queued", "running"):
            return status
        await asyncio.sleep(interval)
        elapsed += interval
        status = await instance.status()
    return status


async def test_create_with_explicit_id(env):
    instance = await env.MY_WORKFLOW.create(
        {"id": "explicit-create-id", "params": {"name": "py"}}
    )
    assert instance.id == "explicit-create-id"


async def test_get_returns_instance(env):
    created = await env.MY_WORKFLOW.create(
        {"id": "get-target-id", "params": {"name": "py"}}
    )
    fetched = await env.MY_WORKFLOW.get(created.id)
    assert not isinstance(fetched, JsProxy)
    assert fetched.id == "get-target-id"


async def test_status_round_trips_payload(env):
    instance = await env.MY_WORKFLOW.create(
        {"params": {"name": "py", "nested": {"n": 42}}}
    )
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["echo"]["name"] == "py"
    assert status["output"]["echo"]["nested"]["n"] == 42


async def test_create_batch(env):
    instances = await env.MY_WORKFLOW.create_batch(
        [
            {"id": "batch-id-a", "params": {"n": 1}},
            {"id": "batch-id-b", "params": {"n": 2}},
        ]
    )
    assert not any(isinstance(i, JsProxy) for i in instances)
    assert [i.id for i in instances] == ["batch-id-a", "batch-id-b"]


async def test_send_event(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "wait_for_event"}})
    settled = await _poll_until_settled(instance)
    assert settled["status"] not in TERMINAL, f"ended before event: {dict(settled)!r}"
    await instance.send_event({"type": "approval", "payload": {"approved": True}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["event_payload"]["approved"] is True


async def test_step_implicit_dependencies(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "implicit_deps"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["derived"] == 15


async def test_step_concurrent_dependencies(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "concurrent"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["combined"] == 6


async def test_step_sleep(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "sleep"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["slept"] is True


async def test_step_sleep_until(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "sleep_until"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["slept_until"] is True


async def test_step_context(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "ctx"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    out = status["output"]
    assert out["step_name"] == "ctx-step"
    assert out["step_count"] >= 1
    assert out["attempt"] >= 1
    assert out["has_config"] is True


async def test_event_metadata(env):
    instance = await env.MY_WORKFLOW.create(
        {"id": "meta-id", "params": {"mode": "event_metadata", "tag": "xyz"}}
    )
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    out = status["output"]
    assert out["payload"]["tag"] == "xyz"
    assert out["has_timestamp"] is True
    assert out["instance_id"] == "meta-id"
    assert isinstance(out["workflow_name"], str) and out["workflow_name"]


async def test_step_retry_config(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "retry"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["succeeded_on_attempt"] == 2


async def test_non_retryable_error(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "non_retryable"}})
    status = await _poll(instance)
    assert status["status"] == "errored", f"unexpected status: {dict(status)!r}"


async def test_error_handling_catch(env):
    instance = await env.MY_WORKFLOW.create({"params": {"mode": "catch_error"}})
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    # Per the docs, a step error propagates to run() and is catchable with
    # `except Exception`. Neither the concrete type nor the original message is
    # guaranteed to survive the RPC layer, so we assert the reliable contract:
    # the error was caught and a message was produced.
    assert status["output"]["caught"] is not None
    assert status["output"]["message"]


# The tests below pass pre-converted (to_js) objects, the legacy pattern from the
# Workflows docs, to ensure existing code keeps working now that the binding
# auto-converts plain Python objects.


def _to_js(value):
    return to_js(value, dict_converter=Object.fromEntries)


async def test_create_with_to_js_options(env):
    instance = await env.MY_WORKFLOW.create(
        _to_js({"id": "to-js-create-id", "params": {"name": "js"}})
    )
    assert not isinstance(instance, JsProxy)
    assert instance.id == "to-js-create-id"


async def test_create_batch_with_to_js_options(env):
    instances = await env.MY_WORKFLOW.create_batch(
        [
            _to_js({"id": "to-js-batch-a", "params": {"n": 1}}),
            _to_js({"id": "to-js-batch-b", "params": {"n": 2}}),
        ]
    )
    assert [i.id for i in instances] == ["to-js-batch-a", "to-js-batch-b"]


async def test_status_round_trips_to_js_payload(env):
    instance = await env.MY_WORKFLOW.create(
        _to_js({"params": {"name": "js", "nested": {"n": 7}}})
    )
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["echo"]["name"] == "js"
    assert status["output"]["echo"]["nested"]["n"] == 7


async def test_send_event_with_to_js(env):
    instance = await env.MY_WORKFLOW.create(
        _to_js({"params": {"mode": "wait_for_event"}})
    )
    settled = await _poll_until_settled(instance)
    assert settled["status"] not in TERMINAL, f"ended before event: {dict(settled)!r}"
    await instance.send_event(
        _to_js({"type": "approval", "payload": {"approved": True}})
    )
    status = await _poll(instance)
    assert status["status"] == "complete", f"unexpected status: {dict(status)!r}"
    assert status["output"]["event_payload"]["approved"] is True
