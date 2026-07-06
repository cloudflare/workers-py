import json

import pytest
from _client import fetch, post_form


@pytest.mark.asyncio
async def test_form_validation(django_asgi_app):
    for label, body in (
        (
            "valid",
            "name=alice&email=alice%40example.com&age=21&category=general&message=hello",
        ),
        ("missing_required", "name=alice"),
        ("invalid_email", "name=alice&email=not-an-email&age=21&category=general"),
        (
            "custom_clean",
            "name=banned&email=user%40example.com&age=21&category=general",
        ),
        ("cross_field", "name=alice&email=alice%40example.com&age=17&category=support"),
    ):
        response = await post_form(django_asgi_app, "/form/validate/", body)

        assert response.status == 200
        payload = json.loads(await response.text())
        if label == "valid":
            assert payload["valid"] is True
            assert payload.get("data")
        elif label == "missing_required":
            assert payload["valid"] is False
            assert payload.get("errors")
        elif label == "invalid_email":
            assert payload["valid"] is False
            assert "email" in payload.get("errors", {})
        elif label == "custom_clean":
            assert payload["valid"] is False
            assert "name" in payload.get("errors", {})
        else:
            assert payload["valid"] is False
            assert payload.get("errors")


@pytest.mark.asyncio
async def test_form_get_renders_html(django_asgi_app):
    response = await fetch(django_asgi_app, "/form/validate/")

    assert response.status == 200
    body = await response.text()
    assert "<form" in body
    assert 'name="email"' in body or 'name="name"' in body
