# pyright: reportMissingImports=false

import asyncio
import contextlib
import importlib.util
import io
from pathlib import Path
from urllib.parse import urlparse

import django
import django.conf
import pytest
from django.http import HttpResponse, JsonResponse
from workers import Response, WorkerEntrypoint

BASE_DIR = Path(__file__).parent

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
            }
        },
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        },
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        USE_TZ=True,
        TIME_ZONE="UTC",
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    )

django.setup()

from django_cf import handle_wsgi  # noqa: E402

urlpatterns = []


def _wsgi_header_echo_app(environ, start_response):
    payload = {
        "cf_access": environ.get("HTTP_CF_ACCESS_JWT_ASSERTION"),
        "custom": environ.get("HTTP_X_CUSTOM_HEADER"),
        "content_type": environ.get("CONTENT_TYPE"),
        "content_length": environ.get("CONTENT_LENGTH"),
    }
    return JsonResponse(payload)


def _wsgi_body_echo_app(environ, start_response):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length)
    return HttpResponse(body, content_type="application/octet-stream")


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


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            return self._run_suite(suite_name)
        if path == "/health":
            return Response.json({"ok": True})
        if path == "/wsgi/headers":
            return await handle_wsgi(request, _wsgi_header_echo_app)
        if path == "/wsgi/body":
            return await handle_wsgi(request, _wsgi_body_echo_app)
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
