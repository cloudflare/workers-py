import pytest
from _client import fetch


@pytest.mark.asyncio
async def test_template_hello(django_asgi_app):
    response = await fetch(django_asgi_app, "/template/hello/")

    assert response.status == 200
    assert "Hello, World!" in await response.text()


@pytest.mark.asyncio
async def test_template_inheritance(django_asgi_app):
    response = await fetch(django_asgi_app, "/template/inheritance/")

    assert response.status == 200
    body = await response.text()
    assert "Base content" in body or "Child content" in body


@pytest.mark.asyncio
async def test_template_context_variable(django_asgi_app):
    response = await fetch(django_asgi_app, "/template/context/")

    assert response.status == 200
    body = await response.text()
    compact = "".join(body.split())
    assert "hello" in body.lower()
    assert "1" in body and "2" in body and "3" in body
    assert "HELLO" in body
    assert "Hello, Worker!" in body
    assert "1,2,3" in compact
    assert "12" in compact
