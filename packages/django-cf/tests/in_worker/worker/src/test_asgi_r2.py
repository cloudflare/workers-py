"""ASGI R2 tests executed inside workerd."""

# pyright: reportMissingImports=false

from uuid import uuid4

import pytest
from _asgi_client import fetch
from django.core.files.base import ContentFile
from django.core.handlers.asgi import ASGIHandler
from django.http import HttpResponse
from django.test import override_settings
from django.urls import path

from django_cf.storage import R2Storage


async def r2_view(request):
    del request
    storage = R2Storage(binding="BUCKET", location=f"asgi-r2-{uuid4().hex}")
    content = b"asgi-r2-content"
    saved_name = None

    try:
        saved_name = storage.save("payload.bin", ContentFile(content))
        r2_file = storage.open(saved_name, "rb")
        try:
            loaded = r2_file.read()
        finally:
            r2_file.close()
    finally:
        if saved_name is not None:
            storage.delete(saved_name)

    return HttpResponse(loaded, content_type="application/octet-stream")


urlpatterns = [path("asgi/r2/", r2_view)]


async def _fetch_r2_response(path_name):
    with override_settings(ROOT_URLCONF=__name__):
        app = ASGIHandler()
        return await fetch(app, path_name)


@pytest.mark.asyncio
async def test_asgi_r2_save_and_read():
    response = await _fetch_r2_response("/asgi/r2/")

    assert response.status == 200
    assert await response.text() == "asgi-r2-content"
