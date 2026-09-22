# pyright: reportMissingImports=false

"""Stock Django MySQL backend running through the HYPERDRIVE_MYSQL binding."""

import MySQLdb
import pytest
from django.db import connections
from django_db_config import HYPERDRIVE_MYSQL
from django_db_helpers import (
    assert_connectivity,
    assert_crud,
    assert_data_types,
    assert_transaction_rollback,
)
from MySQLdb import _mysql


@pytest.fixture(autouse=True)
def close_connections():
    yield
    connections[HYPERDRIVE_MYSQL].close()


def test_connectivity():
    assert_connectivity(HYPERDRIVE_MYSQL)


def test_crud():
    assert_crud(HYPERDRIVE_MYSQL)


def test_data_types():
    assert_data_types(HYPERDRIVE_MYSQL)


def test_transaction_rollback():
    assert_transaction_rollback(HYPERDRIVE_MYSQL)
