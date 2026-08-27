import asyncio
import importlib.util
from pathlib import Path

import pytest
from pyodide.webloop import WebLoop

import asgi
from workers import Response, WorkerEntrypoint

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = str(BASE_DIR / "templates")


async def _noop(*args):
    pass


WebLoop.shutdown_asyncgens = _noop
WebLoop.shutdown_default_executor = _noop

import django.conf  # noqa: E402

django.conf.settings.configure(
    DEBUG=False,
    SECRET_KEY="test-secret-key-for-workers-py",
    ROOT_URLCONF="django_app.urls",
    ALLOWED_HOSTS=["*"],
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.auth",
        "rest_framework",
        "corsheaders",
    ],
    MIDDLEWARE=[
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "django_app.middleware.CustomMiddleware",
    ],
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [TEMPLATES_DIR],
            "APP_DIRS": False,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                ],
                "builtins": ["django_app.templatetags.custom_tags"],
            },
        }
    ],
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    },
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
    AUTHENTICATION_BACKENDS=["django_app.auth_backend.InMemoryBackend"],
    DATABASES={},
    TIME_ZONE="UTC",
    USE_TZ=True,
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    CORS_ALLOWED_ORIGINS=[
        "http://localhost:3000",
        "https://example.com",
    ],
    CORS_ALLOW_CREDENTIALS=True,
    CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://.*\.example\.com$"],
    REST_FRAMEWORK={
        "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
        "DEFAULT_PARSER_CLASSES": [
            "rest_framework.parsers.JSONParser",
            "rest_framework.parsers.FormParser",
            "rest_framework.parsers.MultiPartParser",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "10/min",
            "user": "100/min",
        },
    },
)

import django  # noqa: E402

django.setup()

from django.core.handlers.asgi import ASGIHandler  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler  # noqa: E402


class SyncWSGIHandler(WSGIHandler):
    """WSGI handler serving the sync mirror of the URLconf.

    Django adapts async views under WSGI with ``async_to_sync``, which raises
    when a loop is already running (always true in workerd). The WSGI side
    therefore resolves against ``urls_sync``, whose views are natively sync.
    """

    def get_response(self, request):
        request.urlconf = "django_app.urls_sync"
        return super().get_response(request)


django_asgi_app = ASGIHandler()
django_wsgi_app = SyncWSGIHandler()

APPS = {"asgi": django_asgi_app, "wsgi": django_wsgi_app}


class ResultCollector:
    def __init__(self):
        self.results = {}

    @staticmethod
    def _key(item):
        name = item.name
        return name[len("test_") :] if name.startswith("test_") else name

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


class DjangoAppPlugin:
    def __init__(self, mode):
        self._mode = mode

    def pytest_configure(self, config):
        config.addinivalue_line(
            "markers", "asgi_only: run only against the ASGI app, skip otherwise"
        )

    def pytest_runtest_setup(self, item):
        if self._mode != "asgi" and item.get_closest_marker("asgi_only"):
            pytest.skip(f"async-only Django feature, not applicable to {self._mode}")

    @pytest.fixture
    def django_app(self):
        return APPS[self._mode]


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(request.url)
        path = parsed.path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            mode = parse_qs(parsed.query).get("mode", ["asgi"])[0]
            return self._run_suite(suite_name, mode)
        if path == "/health":
            return Response.json({"ok": True})

        return await asgi.fetch(django_asgi_app, request, self.env, self.ctx)

    def _run_suite(self, suite_name, mode):
        module = f"test_{suite_name}"
        if importlib.util.find_spec(module) is None:
            return Response.json(
                {"error": f"Unknown suite '{suite_name}' (no module '{module}')"},
                status=404,
            )
        if mode not in APPS:
            return Response.json(
                {"error": f"Unknown mode '{mode}' (expected one of {sorted(APPS)})"},
                status=400,
            )

        collector = ResultCollector()
        # pytest-asyncio drives each test through asyncio.Runner, which calls
        # asyncio.new_event_loop(). In Pyodide that constructs a WebLoop whose
        # __init__ calls asyncio._set_running_loop(self) and is never restored on
        # close(), so after pytest.main() the running loop points at an abandoned
        # WebLoop. Save and restore it so the next request's fetch coroutine runs
        # on the real workerd-driven loop instead of hanging on a dead one.
        # TODO: fix this behavior in Pyodide
        saved_loop = asyncio.events._get_running_loop()
        try:
            pytest.main(
                ["--pyargs", module, "-p", "no:cacheprovider"],
                plugins=[
                    collector,
                    EnvPlugin(self.env),
                    DjangoAppPlugin(mode),
                ],
            )
        finally:
            asyncio.events._set_running_loop(saved_loop)
        return Response.json(collector.results)
