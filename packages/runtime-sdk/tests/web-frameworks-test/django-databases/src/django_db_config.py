# pyright: reportMissingImports=false

"""Django settings for stock backends running through Hyperdrive."""

import os

import django
from django.conf import settings

from workers import env

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

HYPERDRIVE_POSTGRESQL = "hyperdrive_postgresql"
HYPERDRIVE_MYSQL = "hyperdrive_mysql"


def _postgresql_database() -> dict[str, object]:
    hyperdrive = env.HYPERDRIVE_PG
    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": hyperdrive.host,
        "PORT": str(hyperdrive.port),
        "USER": hyperdrive.user,
        "PASSWORD": hyperdrive.password,
        "NAME": hyperdrive.database,
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"sslmode": "disable"},
        "DISABLE_SERVER_SIDE_CURSORS": True,
    }


def _mysql_database() -> dict[str, object]:
    hyperdrive = env.HYPERDRIVE_MYSQL
    return {
        "ENGINE": "django.db.backends.mysql",
        "HOST": hyperdrive.host,
        "PORT": str(hyperdrive.port),
        "USER": hyperdrive.user,
        "PASSWORD": hyperdrive.password,
        "NAME": hyperdrive.database,
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"ssl_mode": "DISABLED"},
    }


settings.configure(
    DEBUG=False,
    SECRET_KEY="test-secret-key-for-workers-py",
    INSTALLED_APPS=[],
    DATABASES={
        "default": {"ENGINE": "django.db.backends.dummy"},
        HYPERDRIVE_POSTGRESQL: _postgresql_database(),
        HYPERDRIVE_MYSQL: _mysql_database(),
    },
    TIME_ZONE="UTC",
    USE_TZ=True,
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
)

django.setup()
