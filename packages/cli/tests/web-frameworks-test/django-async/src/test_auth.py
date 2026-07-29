import pytest
from _client import cookie_value, fetch, get_json, post_json, read_json


async def _login(django_asgi_app, password="testpass123"):
    response = await post_json(
        django_asgi_app,
        "/auth/login/",
        {"username": "testuser", "password": password},
    )
    payload = await read_json(response)
    sessionid = cookie_value(response.headers.get("Set-Cookie"), "sessionid")
    return response, payload, sessionid


@pytest.mark.asyncio
async def test_auth_login_success(django_asgi_app):
    response, payload, _ = await _login(django_asgi_app)

    assert response.status == 200
    assert payload["authenticated"] is True


@pytest.mark.asyncio
async def test_auth_login_failure(django_asgi_app):
    response, payload, _ = await _login(django_asgi_app, password="wrong-password")

    assert response.status == 200
    assert payload["authenticated"] is False


@pytest.mark.asyncio
async def test_auth_user_anonymous(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/auth/user/")

    assert response.status == 200
    assert payload["is_authenticated"] is False


@pytest.mark.asyncio
async def test_auth_user_after_login(django_asgi_app):
    _, _, sessionid = await _login(django_asgi_app)
    assert sessionid is not None

    response, payload = await get_json(
        django_asgi_app, "/auth/user/", headers={"Cookie": f"sessionid={sessionid}"}
    )

    assert response.status == 200
    assert payload["is_authenticated"] is True
    assert payload["username"] == "testuser"


@pytest.mark.asyncio
async def test_auth_logout(django_asgi_app):
    _, _, sessionid = await _login(django_asgi_app)
    assert sessionid is not None

    logout_response = await post_json(
        django_asgi_app,
        "/auth/logout/",
        {},
        headers={"Cookie": f"sessionid={sessionid}"},
    )
    assert logout_response.status == 200
    cleared = cookie_value(logout_response.headers.get("Set-Cookie"), "sessionid")
    assert cleared is not None
    assert cleared.strip('"') == ""


@pytest.mark.asyncio
async def test_auth_protected_access(django_asgi_app):
    _, _, sessionid = await _login(django_asgi_app)
    assert sessionid is not None

    anon = await fetch(django_asgi_app, "/auth/protected/")
    assert anon.status == 302
    assert anon.headers.get("Location") is not None

    response, payload = await get_json(
        django_asgi_app,
        "/auth/protected/",
        headers={"Cookie": f"sessionid={sessionid}"},
    )
    assert response.status == 200
    assert payload["protected"] is True
