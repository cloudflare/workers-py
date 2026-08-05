import json

import pytest
from _client import fetch, get_json, post_form, post_json


@pytest.mark.asyncio
async def test_request_method(django_app):
    response, payload = await get_json(django_app, "/echo-method/")

    assert response.status == 200
    assert payload["method"] == "GET"


@pytest.mark.asyncio
async def test_request_get_params(django_app):
    for path, payload in (
        ("/echo-query/?key=value", {"key": "value"}),
        ("/echo-query/?a=1&b=2&c=3", {"a": "1", "b": "2", "c": "3"}),
    ):
        response, data = await get_json(django_app, path)

        assert response.status == 200
        assert data == payload


@pytest.mark.asyncio
async def test_request_post_bodies(django_app):
    for make_request, payload in (
        (
            lambda: post_form(
                django_app,
                "/echo-form/",
                "name=alice&role=worker",
            ),
            {"name": "alice", "role": "worker"},
        ),
        (
            lambda: post_json(
                django_app,
                "/echo-body/",
                {"name": "alice", "active": True},
            ),
            {"name": "alice", "active": True},
        ),
    ):
        response = await make_request()

        assert response.status == 200
        assert json.loads(await response.text()) == payload


@pytest.mark.asyncio
async def test_request_headers(django_app):
    response, payload = await get_json(
        django_app,
        "/echo-headers/",
        headers={"X-Test-Header": "worker", "X-Trace-Id": "123"},
    )

    assert response.status == 200
    payload = {key.lower(): value for key, value in payload.items()}
    assert payload["x-test-header"] == "worker"
    assert payload["x-trace-id"] == "123"


@pytest.mark.asyncio
async def test_request_path_and_content_type(django_app):
    response, payload = await get_json(django_app, "/echo-method/")

    assert response.status == 200
    assert payload["method"] == "GET"
    assert "application/json" in (response.headers.get("Content-Type") or "")


@pytest.mark.asyncio
async def test_response_statuses(django_app):
    for path, status in (("/status/201/", 201), ("/status/302/", 302)):
        response = await fetch(django_app, path)

        assert response.status == status


@pytest.mark.asyncio
async def test_json_response_dict(django_app):
    response, payload = await get_json(django_app, "/echo-query/?a=1")

    assert response.status == 200
    assert isinstance(payload, dict)
    assert payload == {"a": "1"}


@pytest.mark.asyncio
async def test_response_custom_headers(django_app):
    response = await fetch(django_app, "/hello/")

    assert response.status == 200
    assert response.headers.get("X-Custom-Middleware") == "applied"
