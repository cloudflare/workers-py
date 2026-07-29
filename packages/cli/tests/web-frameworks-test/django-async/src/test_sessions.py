import pytest
from _client import cookie_value, fetch, get_json, post_json


@pytest.mark.asyncio
async def test_session_set_and_get_values(django_asgi_app):
    for data in ({"color": "blue"}, {"color": "blue", "size": "large"}):
        set_response = await post_json(django_asgi_app, "/session/set/", data)

        assert set_response.status == 200
        cookie = cookie_value(set_response.headers.get("Set-Cookie"), "sessionid")
        assert cookie

        get_response, payload = await get_json(
            django_asgi_app,
            "/session/get/",
            headers={"Cookie": f"sessionid={cookie}"},
        )

        assert get_response.status == 200
        assert payload == data


@pytest.mark.asyncio
async def test_session_flush(django_asgi_app):
    set_response = await post_json(django_asgi_app, "/session/set/", {"color": "blue"})

    assert set_response.status == 200
    cookie = cookie_value(set_response.headers.get("Set-Cookie"), "sessionid")

    flush_response = await fetch(
        django_asgi_app,
        "/session/flush/",
        method="POST",
        headers={"Cookie": f"sessionid={cookie}"},
    )

    assert flush_response.status == 200
    flushed_cookie = cookie_value(flush_response.headers.get("Set-Cookie"), "sessionid")

    get_response, payload = await get_json(
        django_asgi_app,
        "/session/get/",
        headers={"Cookie": f"sessionid={flushed_cookie or ''}"},
    )

    assert get_response.status == 200
    assert payload == {}


@pytest.mark.asyncio
async def test_session_overwrites(django_asgi_app):
    first_response = await post_json(
        django_asgi_app, "/session/set/", {"color": "blue"}
    )

    assert first_response.status == 200
    cookie = cookie_value(first_response.headers.get("Set-Cookie"), "sessionid")

    second_response = await post_json(
        django_asgi_app,
        "/session/set/",
        {"color": "red"},
        headers={"Cookie": f"sessionid={cookie}"},
    )

    assert second_response.status == 200
    updated_cookie = cookie_value(
        second_response.headers.get("Set-Cookie"), "sessionid"
    )

    get_response, payload = await get_json(
        django_asgi_app,
        "/session/get/",
        headers={"Cookie": f"sessionid={updated_cookie}"},
    )

    assert get_response.status == 200
    assert payload == {"color": "red"}


@pytest.mark.asyncio
async def test_session_cookie_present(django_asgi_app):
    response = await post_json(django_asgi_app, "/session/set/", {"color": "blue"})

    assert response.status == 200
    assert cookie_value(response.headers.get("Set-Cookie"), "sessionid")


@pytest.mark.asyncio
async def test_session_empty_initially(django_asgi_app):
    response, payload = await get_json(django_asgi_app, "/session/get/")

    assert response.status == 200
    assert payload == {}
