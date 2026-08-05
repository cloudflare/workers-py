import re

import pytest
from _client import cookie_value, fetch, post_json, read_json


@pytest.mark.asyncio
async def test_csrf_form_renders_token(django_asgi_app):
    response = await fetch(django_asgi_app, "/csrf/form/")
    body = await response.text()
    cookie_token = cookie_value(response.headers.get("Set-Cookie"), "csrftoken")

    assert response.status == 200
    assert "csrfmiddlewaretoken" in body or "csrf_token" in body
    assert cookie_token is not None


@pytest.mark.asyncio
async def test_post_without_csrf_rejected(django_asgi_app):
    response = await fetch(
        django_asgi_app,
        "/csrf/form/",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body="field=value",
    )

    assert response.status == 403


@pytest.mark.asyncio
async def test_csrf_exempt_allows_post(django_asgi_app):
    response = await post_json(django_asgi_app, "/csrf/exempt/", {"value": "ok"})

    assert response.status == 200
    assert await read_json(response) == {"csrf_exempt": True}


@pytest.mark.asyncio
async def test_csrf_form_token_post(django_asgi_app):
    get_response = await fetch(django_asgi_app, "/csrf/form/")
    body = await get_response.text()
    form_token = None
    for pattern in (
        r'name="csrfmiddlewaretoken" value="([^"]+)"',
        r"csrfmiddlewaretoken.+?value=['\"]([^'\"]+)['\"]",
    ):
        match = re.search(pattern, body)
        if match:
            form_token = match.group(1)
            break
    cookie_token = cookie_value(get_response.headers.get("Set-Cookie"), "csrftoken")

    assert form_token is not None
    assert cookie_token is not None

    post_response = await fetch(
        django_asgi_app,
        "/csrf/form/",
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"csrftoken={cookie_token}",
            "X-CSRFToken": cookie_token,
        },
        body=f"csrfmiddlewaretoken={form_token}&field=value",
    )

    assert post_response.status == 200
