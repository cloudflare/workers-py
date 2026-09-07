# pyright: reportMissingImports=false

import os
from pathlib import Path
from urllib.parse import urlparse

import django
import django.conf
import pytest
from _django_app import R2_LOCATION, django_wsgi_app
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.urls import path
from testlib.entrypoint import TestRunnerEntrypoint
from worker_durable_object import TestDurableObject  # noqa: F401

BASE_DIR = Path(__file__).parent
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


if not django.conf.settings.configured:
    django.conf.settings.configure(
        DEBUG=False,
        SECRET_KEY="django-cf-host-only-tests",
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["*"],
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            },
            "d1": {
                "ENGINE": "django_cf.db.backends.d1",
                "CLOUDFLARE_BINDING": "DB",
            },
            "do": {
                "ENGINE": "django_cf.db.backends.do",
            },
        },
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        },
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        MEDIA_URL="/media/",
        STORAGES={
            "default": {
                "BACKEND": "django_cf.storage.R2Storage",
                "OPTIONS": {
                    "binding": "BUCKET",
                    "location": R2_LOCATION,
                },
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        },
        USE_TZ=True,
        TIME_ZONE="UTC",
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    )

django.setup()

from _do_orm_app import urlpatterns as do_orm_urlpatterns  # noqa: E402

from django_cf import DjangoCF  # noqa: E402


def _django_binary_view(request):
    return HttpResponse(bytes(range(256)), content_type="application/octet-stream")


def _django_streaming_view(request):
    def chunks():
        for value in range(5):
            yield bytes([value]) * 1024

    return StreamingHttpResponse(chunks(), content_type="application/octet-stream")


def _django_cookies_view(request):
    response = HttpResponse(b"cookies", content_type="text/plain")
    response.set_cookie("first", "1")
    response.set_cookie("second", "2")
    return response


def _django_meta_view(request, segment):
    env = request.META.get("workers.env")
    return JsonResponse(
        {
            "path": request.path_info,
            "segment": segment,
            "values": request.GET.getlist("value"),
            "has_env": env is not None,
            "has_bucket": hasattr(env, "BUCKET"),
        }
    )


def _django_body_view(request):
    response = HttpResponse(request.body, content_type="application/octet-stream")
    response["X-Request-Method"] = request.method
    return response


def _django_headers_view(request):
    return JsonResponse(
        {
            "cf_access": request.META.get("HTTP_CF_ACCESS_JWT_ASSERTION"),
            "custom": request.META.get("HTTP_X_CUSTOM_HEADER"),
            "content_type": request.META.get("CONTENT_TYPE"),
            "content_length": request.META.get("CONTENT_LENGTH"),
        }
    )


urlpatterns = [
    path("django/binary/", _django_binary_view),
    path("django/stream/", _django_streaming_view),
    path("django/cookies/", _django_cookies_view),
    path("django/meta/<str:segment>/", _django_meta_view),
    path("django/body/", _django_body_view),
    path("django/headers/", _django_headers_view),
    *do_orm_urlpatterns,
]


class EnvPlugin:
    def __init__(self, env):
        self._env = env

    @pytest.fixture
    def env(self):
        return self._env


class Default(DjangoCF, TestRunnerEntrypoint):
    def get_app(self):
        return django_wsgi_app()

    async def fetch(self, request):
        path = urlparse(request.url).path
        if path.startswith("/django/"):
            return await DjangoCF.fetch(self, request)
        return await TestRunnerEntrypoint.fetch(self, request)
