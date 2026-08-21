# pyright: reportMissingImports=false

import asyncio
import contextlib
import importlib.util
import io
import os
from pathlib import Path
from urllib.parse import urlparse

import django
import django.conf
import pytest
from _django_app import R2_LOCATION, django_wsgi_app
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.urls import path
from pyodide.webloop import WebLoop
from worker_durable_object import TestDurableObject  # noqa: F401
from workers import Response, WorkerEntrypoint

BASE_DIR = Path(__file__).parent
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


async def _noop(*args):
    pass


# pytest-asyncio relies on these methods, which older Pyodide WebLoops omit.
WebLoop.shutdown_asyncgens = _noop
WebLoop.shutdown_default_executor = _noop

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


class ResultCollector:
    def __init__(self):
        self.results = {}

    @staticmethod
    def _key(item):
        normalized = []
        if item.cls is not None:
            normalized.append(item.cls.__name__)
        name = getattr(item, "originalname", None) or item.name
        normalized.append(name[len("test_") :] if name.startswith("test_") else name)
        return "__".join(normalized)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        key = self._key(item)

        if report.when == "call":
            if report.passed:
                self.results[key] = {"status": "passed"}
            elif report.skipped:
                self.results[key] = {
                    "status": "skipped",
                    "reason": str(report.longrepr),
                }
            elif report.failed:
                excinfo = call.excinfo
                if excinfo is not None and excinfo.errisinstance(AssertionError):
                    self.results[key] = {
                        "status": "failed",
                        "error": str(excinfo.value),
                    }
                else:
                    self.results[key] = {
                        "status": "error",
                        "error": f"{excinfo.typename}: {excinfo.value}"
                        if excinfo is not None
                        else "unknown error",
                        "traceback": report.longreprtext,
                    }
        elif report.when in ("setup", "teardown") and report.skipped:
            self.results[key] = {
                "status": "skipped",
                "reason": str(report.longrepr),
            }
        elif report.when in ("setup", "teardown") and report.failed:
            self.results[key] = {
                "status": "error",
                "error": report.longreprtext,
                "traceback": report.longreprtext,
            }


class EnvPlugin:
    def __init__(self, env):
        self._env = env

    @pytest.fixture
    def env(self):
        return self._env


class Default(DjangoCF, WorkerEntrypoint):
    def get_app(self):
        return django_wsgi_app()

    async def fetch(self, request):
        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            return self._run_suite(suite_name)
        if path == "/health":
            return Response.json({"ok": True})
        if path.startswith("/django/"):
            return await super().fetch(request)
        return Response.json({"error": "not found"}, status=404)

    def _run_suite(self, suite_name):
        module = f"test_{suite_name}"
        if importlib.util.find_spec(module) is None:
            return Response.json(
                {"error": f"Unknown suite '{suite_name}' (no module '{module}')"},
                status=404,
            )

        collector = ResultCollector()
        saved_loop = asyncio.events._get_running_loop()
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exit_code = pytest.main(
                    ["--pyargs", module, "-p", "no:cacheprovider"],
                    plugins=[collector, EnvPlugin(self.env)],
                )
        finally:
            asyncio.events._set_running_loop(saved_loop)
        if exit_code != 0 and not collector.results:
            return Response.json(
                {
                    "__session__": {
                        "status": "error",
                        "error": f"pytest exit code {exit_code}",
                        "traceback": output.getvalue(),
                    }
                },
                status=500,
            )
        return Response.json(collector.results)
