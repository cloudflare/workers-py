from pathlib import Path

import pytest
from testlib.entrypoint import TestRunnerEntrypoint

import asgi

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = str(BASE_DIR / "templates")


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
        "django_app.middleware.CustomAsyncMiddleware",
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

django_asgi_app = ASGIHandler()


class DjangoAppPlugin:
    @pytest.fixture
    def django_asgi_app(self):
        return django_asgi_app


class Default(TestRunnerEntrypoint):
    app = django_asgi_app

    async def fetch(self, request):
        result = await super().fetch(request)
        if result.status == 404:
            result = await asgi.fetch(django_asgi_app, request, self.env, self.ctx)
        return result

    def plugins(self):
        return super().plugins() + [DjangoAppPlugin()]
