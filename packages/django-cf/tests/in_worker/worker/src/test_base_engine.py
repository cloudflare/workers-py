"""Base engine tests executed inside workerd."""

# pyright: reportMissingImports=false

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestCFResult:
    def test_init(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.data == data
        assert result.lastrowid is None
        assert result.rowcount == -1

    def test_iter(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b")]
        result = CFResult(data)

        assert list(result) == [(1, "a"), (2, "b")]

    def test_set_lastrowid(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult([])
        result.set_lastrowid(42)

        assert result.lastrowid == 42

    def test_set_rowcount(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult([])
        result.set_rowcount(10)

        assert result.rowcount == 10

    def test_fetchone_with_data(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        row = result.fetchone()
        assert row == (1, "a")
        assert result.data == data
        assert result.fetchall() == [(2, "b"), (3, "c")]
        assert result.fetchone() is None

    def test_fetchone_empty(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult([])

        assert result.fetchone() is None

    def test_fetchall(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.fetchall() == [(1, "a"), (2, "b"), (3, "c")]
        assert result.data == data
        assert result.fetchall() == []

    def test_fetchall_empty(self):
        from django_cf.db.base_engine import CFResult

        assert CFResult([]).fetchall() == []

    def test_fetchmany_default(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.fetchmany() == [(1, "a")]
        assert result.data == data

    def test_fetchmany_specific_size(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        rows = result.fetchmany(2)
        assert rows == [(1, "a"), (2, "b")]
        assert result.data == data
        assert result.fetchmany(2) == [(3, "c")]
        assert result.fetchmany(2) == []

    def test_fetchmany_non_positive_size_does_not_advance(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.fetchmany(0) == []
        assert result.fetchone() == (1, "a")

        result = CFResult(data)

        assert result.fetchmany(-1) == []
        assert result.fetchone() == (1, "a")

    def test_fetchmany_more_than_available(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b")]
        result = CFResult(data)

        rows = result.fetchmany(5)
        assert rows == [(1, "a"), (2, "b")]
        assert result.data == data
        assert result.fetchone() is None

    def test_fetchone_then_fetchall_returns_remaining_rows(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.fetchone() == (1, "a")
        assert result.fetchall() == [(2, "b"), (3, "c")]
        assert result.data == data
        assert result.fetchone() is None

    def test_from_object_with_list_rows(self):
        from django_cf.db.base_engine import CFResult

        data = [[1, "hello", True], [2, "world", False]]
        result = CFResult.from_object("SELECT * FROM test", None, data)

        assert list(result) == [(1, "hello", True), (2, "world", False)]

    def test_from_object_with_dict_rows(self):
        from django_cf.db.base_engine import CFResult

        data = [{"id": 1, "name": "hello"}, {"id": 2, "name": "world"}]
        result = CFResult.from_object("SELECT * FROM test", None, data)

        assert len(list(result)) == 2

    def test_from_object_insert_rowcount(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            "INSERT INTO test VALUES (1)", None, [], rows_read=0, rows_written=5
        )

        assert result.rowcount == 5

    def test_from_object_update_rowcount(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            'UPDATE test SET name = "new"', None, [], rows_read=0, rows_written=3
        )

        assert result.rowcount == 3

    def test_from_object_delete_rowcount(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            "DELETE FROM test WHERE id = 1", None, [], rows_read=0, rows_written=2
        )

        assert result.rowcount == 2

    def test_from_object_select_rowcount(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            "SELECT * FROM test", None, [[1], [2], [3]], rows_read=3, rows_written=0
        )

        assert result.rowcount == 3

    def test_from_object_lastrowid(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult.from_object(
            "INSERT INTO test VALUES (1)", None, [], last_row_id=42
        )

        assert result.lastrowid == 42


class TestIsReadOnlyQuery:
    def test_select_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query("SELECT * FROM users") is True
        assert is_read_only_query("  SELECT id FROM users WHERE id = 1") is True
        assert is_read_only_query("select * from users") is True

    def test_insert_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('INSERT INTO users (name) VALUES ("test")') is False

    def test_update_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query('UPDATE users SET name = "new" WHERE id = 1') is False

    def test_delete_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query("DELETE FROM users WHERE id = 1") is False

    def test_create_table_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query("CREATE TABLE users (id INT)") is False

    def test_alter_table_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query("ALTER TABLE users ADD COLUMN email TEXT") is False

    def test_drop_table_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query("DROP TABLE users") is False

    def test_replace_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert (
            is_read_only_query('REPLACE INTO users (id, name) VALUES (1, "test")')
            is False
        )

    def test_empty_query(self):
        from django_cf.db.base_engine import is_read_only_query

        assert is_read_only_query("") is False
        assert is_read_only_query("   ") is False


class TestReplaceDateTruncInSql:
    def test_no_date_trunc(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = 'SELECT * FROM users WHERE created_at > "2023-01-01"'
        assert replace_date_trunc_in_sql(sql) == sql

    def test_django_date_trunc_replacement(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        result = replace_date_trunc_in_sql(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders"
        )

        assert "CASE %s" in result
        assert "STRFTIME" in result
        assert "django_date_trunc" not in result

    def test_django_datetime_trunc_replacement(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        result = replace_date_trunc_in_sql(
            "SELECT django_datetime_trunc(%s, created_at, %s, %s) FROM orders"
        )

        assert "CASE %s" in result
        assert "django_datetime_trunc" not in result

    def test_year_truncation_in_case(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        result = replace_date_trunc_in_sql(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders"
        )

        assert "WHEN 'year'" in result
        assert "%Y-01-01" in result

    def test_month_truncation_in_case(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        result = replace_date_trunc_in_sql(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders"
        )

        assert "WHEN 'month'" in result
        assert "%Y-%m-01" in result

    def test_day_truncation_in_case(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        result = replace_date_trunc_in_sql(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders"
        )

        assert "WHEN 'day'" in result
        assert "DATE(created_at)" in result

    def test_multiple_date_truncs(self):
        from django_cf.db.base_engine import replace_date_trunc_in_sql

        sql = """SELECT django_date_trunc(%s, created_at, %s, %s),
                        django_date_trunc(%s, updated_at, %s, %s) FROM orders"""
        result = replace_date_trunc_in_sql(sql)

        assert "django_date_trunc" not in result
        assert result.count("CASE %s") == 2


class TestCFDatabase:
    def test_connect(self):
        from django_cf.db.base_engine import CFDatabase

        mock_wrapper = MagicMock()
        db = CFDatabase.connect(mock_wrapper)

        assert db.databaseWrapper == mock_wrapper

    def test_cursor_returns_fresh_cursor_each_call(self):
        from django_cf.db.base_engine import CFCursor, CFDatabase

        db = CFDatabase(MagicMock())
        first_cursor = db.cursor()
        second_cursor = db.cursor()

        assert isinstance(first_cursor, CFCursor)
        assert isinstance(second_cursor, CFCursor)
        assert first_cursor is not second_cursor
        assert first_cursor.database is db
        assert second_cursor.database is db

    def test_commit_does_nothing(self):
        from django_cf.db.base_engine import CFDatabase

        assert CFDatabase(MagicMock()).commit() is None

    def test_rollback_does_nothing(self):
        from django_cf.db.base_engine import CFDatabase

        assert CFDatabase(MagicMock()).rollback() is None

    def test_close_does_nothing(self):
        from django_cf.db.base_engine import CFDatabase

        assert CFDatabase(MagicMock()).close() is None

    def test_defer_foreign_keys(self):
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        db.defer_foreign_keys(True)
        assert db._defer_foreign_keys is True
        db.defer_foreign_keys(False)
        assert db._defer_foreign_keys is False

    def test_cursor_defer_foreign_keys_proxies_database_state(self):
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        first_cursor = db.cursor()
        second_cursor = db.cursor()

        first_cursor.defer_foreign_keys(True)
        assert db._defer_foreign_keys is True
        assert second_cursor._defer_foreign_keys is True

        second_cursor.defer_foreign_keys(False)
        assert db._defer_foreign_keys is False
        assert first_cursor._defer_foreign_keys is False

    def test_execute_converts_boolean_true(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("INSERT INTO test VALUES (%s)", (True,))

        assert mock_wrapper.run_query.call_args[0][1] == (1,)

    def test_execute_converts_boolean_false(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("INSERT INTO test VALUES (%s)", (False,))

        assert mock_wrapper.run_query.call_args[0][1] == (0,)

    def test_execute_converts_decimal_to_string(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("INSERT INTO test VALUES (%s)", (Decimal("10.5"),))

        assert mock_wrapper.run_query.call_args[0][1] == ("10.5",)

    def test_execute_no_params(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("SELECT * FROM test")

        assert mock_wrapper.run_query.call_args[0] == ("SELECT * FROM test", None)

    def test_execute_returns_cursor(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        cursor = CFDatabase(mock_wrapper).cursor()

        assert cursor.execute("SELECT * FROM test") is cursor

    def test_fetchone_delegates_to_result(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([(1, "test")])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("SELECT * FROM test")

        assert cursor.fetchone() == (1, "test")

    def test_fetchall_delegates_to_result(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([(1, "a"), (2, "b")])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("SELECT * FROM test")

        assert len(cursor.fetchall()) == 2

    def test_cursors_keep_independent_results(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.side_effect = [CFResult([(1,), (2,)]), CFResult([(9,)])]
        db = CFDatabase(mock_wrapper)
        outer_cursor = db.cursor()
        inner_cursor = db.cursor()

        outer_cursor.execute("SELECT * FROM outer_table")
        inner_cursor.execute("SELECT * FROM inner_table")

        assert inner_cursor.fetchone() == (9,)
        assert sorted(outer_cursor.fetchall()) == [(1,), (2,)]

    def test_lastrowid_property(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([])
        mock_result.set_lastrowid(42)
        mock_wrapper.run_query.return_value = mock_result
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("INSERT INTO test VALUES (1)")

        assert cursor.lastrowid == 42

    def test_rowcount_property(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([])
        mock_result.set_rowcount(5)
        mock_wrapper.run_query.return_value = mock_result
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute('UPDATE test SET name = "new"')

        assert cursor.rowcount == 5

    def test_cursor_close_is_noop_and_keeps_result(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([(1,), (2,)])
        cursor = CFDatabase(mock_wrapper).cursor()

        cursor.execute("SELECT * FROM test")

        assert cursor.close() is None
        assert sorted(cursor.fetchall()) == [(1,), (2,)]


class TestCFDatabaseFeatures:
    def test_transactions_disabled(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        features = CFDatabaseFeatures(MagicMock())

        assert features.atomic_transactions is False
        assert features.supports_transactions is False

    def test_savepoints_disabled(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        features = CFDatabaseFeatures(MagicMock())

        assert features.uses_savepoints is False
        assert features.can_release_savepoints is False

    def test_constraint_checks_disabled(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        features = CFDatabaseFeatures(MagicMock())

        assert features.can_defer_constraint_checks is False
        assert features.supports_pragma_foreign_key_check is False

    def test_max_query_params(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        assert CFDatabaseFeatures(MagicMock()).max_query_params == 100

    def test_bulk_insert_enabled(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        features = CFDatabaseFeatures(MagicMock())

        assert features.has_bulk_insert is True
        assert features.can_return_columns_from_insert is True


class TestCFDatabaseWrapper:
    def test_get_database_version(self):
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, "__init__", lambda self, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            assert wrapper.get_database_version() == (4,)

    def test_close_does_nothing(self):
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, "__init__", lambda self, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            assert wrapper.close() is None

    def test_savepoint_not_allowed(self):
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, "__init__", lambda self, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            assert wrapper._savepoint_allowed() is False

    def test_start_transaction_under_autocommit_is_noop(self):
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, "__init__", lambda self, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            assert wrapper._start_transaction_under_autocommit() is None

    def test_is_usable_always_true(self):
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, "__init__", lambda self, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            assert wrapper.is_usable() is True

    def test_run_query_not_implemented(self):
        from django_cf.db.base_engine import CFDatabaseWrapper

        with patch.object(CFDatabaseWrapper, "__init__", lambda self, *args: None):
            wrapper = CFDatabaseWrapper.__new__(CFDatabaseWrapper)
            with pytest.raises(NotImplementedError):
                wrapper.run_query("SELECT 1")


class TestCFDatabaseOperations:
    def test_bulk_insert_sql(self):
        from django_cf.db.base_engine import CFDatabaseOperations

        ops = CFDatabaseOperations(MagicMock())

        fields = ["id", "name"]
        placeholder_rows = [("%s", "%s"), ("%s", "%s")]
        assert (
            ops.bulk_insert_sql(fields, placeholder_rows) == "VALUES (%s, %s), (%s, %s)"
        )

    def test_last_executed_query_no_params(self):
        from django_cf.db.base_engine import CFDatabaseOperations

        ops = CFDatabaseOperations(MagicMock())
        sql = "SELECT * FROM test"

        assert ops.last_executed_query(None, sql, None) == sql

    def test_last_executed_query_with_params(self):
        from django_cf.db.base_engine import CFDatabaseOperations

        mock_wrapper = MagicMock()
        mock_wrapper.connection = MagicMock()
        mock_wrapper.connection.cursor.return_value = MagicMock()
        ops = CFDatabaseOperations(mock_wrapper)

        result = ops.last_executed_query(None, "SELECT * FROM test WHERE id = %s", [1])

        assert isinstance(result, str)
        assert "SELECT * FROM test WHERE id" in result

    def test_last_executed_query_catches_formatting_errors(self):
        from django_cf.db.base_engine import CFDatabaseOperations

        ops = CFDatabaseOperations(MagicMock())
        sql = "SELECT * FROM test WHERE id = %s AND name = %s"

        assert ops.last_executed_query(None, sql, (1,)) == sql

    def test_last_executed_query_does_not_catch_keyboard_interrupt(self):
        from django_cf.db.base_engine import CFDatabaseOperations

        ops = CFDatabaseOperations(MagicMock())

        class BadStr:
            def __str__(self):
                raise KeyboardInterrupt()

            def __format__(self, spec):
                raise KeyboardInterrupt()

        ops._quote_params_for_last_executed_query = lambda params: (BadStr(),)

        with pytest.raises(KeyboardInterrupt):
            ops.last_executed_query(None, "SELECT * FROM test WHERE id = %s", [1])


class TestCFSQLCompiler:
    def test_replace_date_trunc_functions_year(self):
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)
        result = compiler._replace_date_trunc_functions(
            "SELECT django_date_trunc('year', created_at) FROM orders"
        )

        assert 'STRFTIME("%Y-01-01", created_at)' in result
        assert "django_date_trunc" not in result

    def test_replace_date_trunc_functions_month(self):
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)
        result = compiler._replace_date_trunc_functions(
            "SELECT django_date_trunc('month', created_at) FROM orders"
        )

        assert 'STRFTIME("%Y-%m-01", created_at)' in result

    def test_replace_date_trunc_functions_day(self):
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)
        result = compiler._replace_date_trunc_functions(
            "SELECT django_date_trunc('day', created_at) FROM orders"
        )

        assert "DATE(created_at)" in result

    def test_replace_date_trunc_functions_hour(self):
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)
        result = compiler._replace_date_trunc_functions(
            "SELECT django_date_trunc('hour', created_at) FROM orders"
        )

        assert 'STRFTIME("%Y-%m-%d %H:00:00", created_at)' in result

    def test_replace_date_trunc_functions_unknown_kind(self):
        from django_cf.db.base_engine import CFSQLCompiler

        compiler = CFSQLCompiler.__new__(CFSQLCompiler)
        result = compiler._replace_date_trunc_functions(
            "SELECT django_date_trunc('unknown', created_at) FROM orders"
        )

        assert "django_date_trunc('unknown', created_at)" in result
