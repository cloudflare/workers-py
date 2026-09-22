# pyright: reportMissingImports=false

"""Stock Django PostgreSQL backend running through the HYPERDRIVE_PG binding."""

import psycopg
import pytest
from django.db import connections
from django_db_config import HYPERDRIVE_POSTGRESQL
from django_db_helpers import (
    assert_connectivity,
    assert_crud,
    assert_data_types,
    assert_transaction_rollback,
)


@pytest.fixture(autouse=True)
def close_connections():
    yield
    connections[HYPERDRIVE_POSTGRESQL].close()


def test_connectivity():
    assert_connectivity(HYPERDRIVE_POSTGRESQL)


def test_crud():
    assert_crud(HYPERDRIVE_POSTGRESQL)


def test_data_types():
    assert_data_types(HYPERDRIVE_POSTGRESQL)


def test_transaction_rollback():
    assert_transaction_rollback(HYPERDRIVE_POSTGRESQL)
