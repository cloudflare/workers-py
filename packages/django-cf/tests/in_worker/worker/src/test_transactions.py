"""
D1 and Durable objects (backed by D1) does not support transaction.

This test verifies that the transaction behavior is consistent with the documentation
"""

# pyright: reportMissingImports=false

import contextlib
from unittest.mock import patch

import pytest
from django.db import connections, transaction
from django.db.transaction import TransactionManagementError

ALIASES = ("d1", "do")
TRANSACTION_CONTROL_SQL = ("BEGIN", "SAVEPOINT", "RELEASE")


def _get_connection(alias):
    connection = connections[alias]
    connection.ensure_connection()
    return connection


def _restore_connection_state(connection):
    connection.run_on_commit = []
    connection.run_commit_hooks_on_set_autocommit_on = False
    connection.rollback_exc = None
    connection.needs_rollback = False
    connection.closed_in_transaction = False
    connection.in_atomic_block = False
    connection.atomic_blocks = []
    connection.savepoint_ids = []
    connection.commit_on_exit = True
    connection.autocommit = True


def _select_one(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT 1")
    return cursor.fetchone()


@contextlib.contextmanager
def _capture_run_query(connection, alias, captured_sql):
    if alias == "do":
        from django_cf.db.base_engine import CFResult

        def fake_run_query(query, params=None):
            captured_sql.append(query)
            if query.strip().upper() == "SELECT 1":
                return CFResult.from_object(query, params, [[1]], rows_read=1)
            raise AssertionError(f"unexpected SQL for do alias: {query}")

        with patch.object(connection, "run_query", side_effect=fake_run_query):
            yield
    else:
        original_run_query = connection.run_query

        def capture_run_query(query, params=None):
            captured_sql.append(query)
            return original_run_query(query, params)

        with patch.object(connection, "run_query", side_effect=capture_run_query):
            yield


def test_ensure_connection_starts_in_autocommit():
    for alias in ALIASES:
        connection = _get_connection(alias)
        try:
            assert connection.get_autocommit() is True
            assert connection.autocommit is True
        finally:
            _restore_connection_state(connection)


def test_on_commit_outside_atomic_executes_immediately():
    for alias in ALIASES:
        connection = _get_connection(alias)
        fired = []
        try:
            # Outside of atomic, on_commit should execute immediately
            transaction.on_commit(
                lambda alias=alias, fired=fired: fired.append(alias), using=alias
            )

            assert fired == [alias]
            assert connection.run_on_commit == []
        finally:
            _restore_connection_state(connection)


def test_on_commit_inside_successful_atomic_defers_until_exit():
    for alias in ALIASES:
        connection = _get_connection(alias)
        fired = []
        try:
            # Inside atomic, on_commit should defer execution until the transaction commits
            with transaction.atomic(using=alias):
                transaction.on_commit(
                    lambda alias=alias, fired=fired: fired.append(alias),
                    using=alias,
                )

                assert fired == []
                assert len(connection.run_on_commit) == 1

            assert fired == [alias]
            assert connection.run_on_commit == []
            assert connection.get_autocommit() is True
        finally:
            _restore_connection_state(connection)


def test_failed_outer_atomic_discards_on_commit_and_recovers():
    for alias in ALIASES:
        connection = _get_connection(alias)
        captured_sql = []
        fired = []
        try:
            with _capture_run_query(connection, alias, captured_sql):
                with pytest.raises(RuntimeError, match="boom"):
                    with transaction.atomic(using=alias):
                        transaction.on_commit(
                            lambda alias=alias, fired=fired: fired.append(alias),
                            using=alias,
                        )
                        raise RuntimeError("boom")

                assert fired == []
                assert connection.run_on_commit == []
                assert connection.needs_rollback is False
                assert connection.get_autocommit() is True
                assert _select_one(connection) == (1,)
        finally:
            _restore_connection_state(connection)


def test_caught_inner_atomic_exception_blocks_queries_until_outer_exit():
    for alias in ALIASES:
        connection = _get_connection(alias)
        captured_sql = []
        try:
            with _capture_run_query(connection, alias, captured_sql):
                with pytest.raises(TransactionManagementError):
                    with transaction.atomic(using=alias):
                        try:
                            with transaction.atomic(using=alias):
                                raise RuntimeError("boom")
                        except RuntimeError:
                            assert connection.needs_rollback is True
                            _select_one(connection)

                assert connection.needs_rollback is False
                assert connection.get_autocommit() is True
                assert _select_one(connection) == (1,)
        finally:
            _restore_connection_state(connection)


def test_nested_atomic_emits_no_transaction_control_sql():
    for alias in ALIASES:
        connection = _get_connection(alias)
        captured_sql = []

        try:
            with _capture_run_query(connection, alias, captured_sql):
                with transaction.atomic(using=alias):
                    with transaction.atomic(using=alias):
                        assert _select_one(connection) == (1,)

            assert any("SELECT 1" in query.upper() for query in captured_sql)
            assert not any(
                keyword in query.upper()
                for query in captured_sql
                for keyword in TRANSACTION_CONTROL_SQL
            )
        finally:
            _restore_connection_state(connection)
