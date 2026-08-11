"""Database backend tests executed inside workerd."""

# pyright: reportMissingImports=false

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import workers


def make_d1_wrapper(defer_foreign_keys=False):
    from django_cf.db.backends.d1.base import DatabaseWrapper

    wrapper = DatabaseWrapper.__new__(DatabaseWrapper)
    cursor_state = SimpleNamespace(_defer_foreign_keys=defer_foreign_keys)
    wrapper.cursor = lambda: cursor_state
    wrapper.binding = "DB"
    wrapper.run_sync = lambda value: value
    return wrapper


def make_do_wrapper(defer_foreign_keys=False):
    from django_cf.db.backends.do.base import DatabaseWrapper

    wrapper = DatabaseWrapper.__new__(DatabaseWrapper)
    cursor_state = SimpleNamespace(_defer_foreign_keys=defer_foreign_keys)
    wrapper.cursor = lambda: cursor_state
    return wrapper


class FakeD1Statement:
    def __init__(
        self, *, raw_result=None, all_result=None, raw_error=None, all_error=None
    ):
        self.raw_result = raw_result or []
        self.all_result = all_result or {"results": [], "meta": {}}
        self.raw_error = raw_error
        self.all_error = all_error
        self.bound_params = None

    def bind(self, *params):
        self.bound_params = params
        return self

    def raw(self):
        if self.raw_error is not None:
            raise self.raw_error
        return self.raw_result

    def all(self):
        if self.all_error is not None:
            raise self.all_error
        return self.all_result


class FakeD1Binding:
    def __init__(self, statement):
        self.statement = statement
        self.prepared_queries = []

    def prepare(self, query):
        self.prepared_queries.append(query)
        return self.statement


class FakeDOArray:
    def __init__(self, data):
        self.data = data

    def toArray(self):
        return self

    def to_py(self):
        return self.data


class FakeDOStatement:
    def __init__(self, data, *, rows_read=0, rows_written=0):
        self.data = data
        self.rowsRead = rows_read
        self.rowsWritten = rows_written

    def raw(self):
        return FakeDOArray(self.data)


class FakeDOStorage:
    def __init__(self, statement=None, *, error=None):
        self.statement = statement
        self.error = error
        self.calls = []

    def exec(self, query, *params):
        if self.error is not None:
            raise self.error
        self.calls.append((query, params))
        return self.statement


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
        assert row == (3, "c")
        assert len(result.data) == 2

    def test_fetchone_empty(self):
        from django_cf.db.base_engine import CFResult

        result = CFResult([])

        assert result.fetchone() is None

    def test_fetchall(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.fetchall() == [(3, "c"), (2, "b"), (1, "a")]
        assert len(result.data) == 0

    def test_fetchall_empty(self):
        from django_cf.db.base_engine import CFResult

        assert CFResult([]).fetchall() == []

    def test_fetchmany_default(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        assert result.fetchmany() == [(3, "c")]
        assert len(result.data) == 2

    def test_fetchmany_specific_size(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b"), (3, "c")]
        result = CFResult(data)

        rows = result.fetchmany(2)
        assert len(rows) == 2
        assert len(result.data) == 1

    def test_fetchmany_more_than_available(self):
        from django_cf.db.base_engine import CFResult

        data = [(1, "a"), (2, "b")]
        result = CFResult(data)

        rows = result.fetchmany(5)
        assert len(rows) == 2
        assert len(result.data) == 0

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

    def test_cursor_returns_self(self):
        from django_cf.db.base_engine import CFDatabase

        db = CFDatabase(MagicMock())
        assert db.cursor() is db

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

    def test_execute_converts_boolean_true(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        db = CFDatabase(mock_wrapper)

        db.execute("INSERT INTO test VALUES (%s)", (True,))

        assert mock_wrapper.run_query.call_args[0][1] == (1,)

    def test_execute_converts_boolean_false(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        db = CFDatabase(mock_wrapper)

        db.execute("INSERT INTO test VALUES (%s)", (False,))

        assert mock_wrapper.run_query.call_args[0][1] == (0,)

    def test_execute_converts_decimal_to_string(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        db = CFDatabase(mock_wrapper)

        db.execute("INSERT INTO test VALUES (%s)", (Decimal("10.5"),))

        assert mock_wrapper.run_query.call_args[0][1] == ("10.5",)

    def test_execute_no_params(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([])
        db = CFDatabase(mock_wrapper)

        db.execute("SELECT * FROM test")

        assert mock_wrapper.run_query.call_args[0] == ("SELECT * FROM test", None)

    def test_fetchone_delegates_to_result(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([(1, "test")])
        db = CFDatabase(mock_wrapper)

        db.execute("SELECT * FROM test")

        assert db.fetchone() == (1, "test")

    def test_fetchall_delegates_to_result(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_wrapper.run_query.return_value = CFResult([(1, "a"), (2, "b")])
        db = CFDatabase(mock_wrapper)

        db.execute("SELECT * FROM test")

        assert len(db.fetchall()) == 2

    def test_lastrowid_property(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([])
        mock_result.set_lastrowid(42)
        mock_wrapper.run_query.return_value = mock_result
        db = CFDatabase(mock_wrapper)

        db.execute("INSERT INTO test VALUES (1)")

        assert db.lastrowid == 42

    def test_rowcount_property(self):
        from django_cf.db.base_engine import CFDatabase, CFResult

        mock_wrapper = MagicMock()
        mock_result = CFResult([])
        mock_result.set_rowcount(5)
        mock_wrapper.run_query.return_value = mock_result
        db = CFDatabase(mock_wrapper)

        db.execute('UPDATE test SET name = "new"')

        assert db.rowcount == 5


class TestCFDatabaseFeatures:
    def test_transactions_disabled(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        features = CFDatabaseFeatures(MagicMock())

        assert features.atomic_transactions is False
        assert features.supports_transactions is False

    def test_savepoints_disabled(self):
        from django_cf.db.base_engine import CFDatabaseFeatures

        assert CFDatabaseFeatures(MagicMock()).can_release_savepoints is False

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


class TestD1DatabaseWrapperProcessQuery:
    def test_process_query_no_params(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s", None
        )

        assert result_query == "SELECT * FROM users WHERE id = ?"
        assert result_params is None

    def test_process_query_with_params(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s AND name = %s", [1, "test"]
        )

        assert result_query == "SELECT * FROM users WHERE id = ? AND name = ?"
        assert result_params == [1, "test"]

    def test_process_query_null_param_replaced_with_literal(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name, email) VALUES (%s, %s)", ["test", None]
        )

        assert "null" in result_query
        assert result_params == ["test"]

    def test_process_query_all_null_params(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name, email) VALUES (%s, %s)", [None, None]
        )

        assert result_query == "INSERT INTO users (name, email) VALUES (null, null)"
        assert result_params == []

    def test_process_query_mixed_params(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query(
            "UPDATE users SET name = %s, email = %s, age = %s WHERE id = %s",
            ["test", None, 25, None],
        )

        assert result_params == ["test", 25]
        assert result_query.count("?") == 2
        assert result_query.count("null") == 2

    def test_process_query_with_defer_foreign_keys(self):
        result = make_d1_wrapper(True).process_query(
            "INSERT INTO users (name) VALUES (%s)", ["test"]
        )

        assert "PRAGMA defer_foreign_keys = on" in result
        assert "PRAGMA defer_foreign_keys = off" in result

    def test_process_query_date_trunc_replacement(self):
        wrapper = make_d1_wrapper()

        result_query, _ = wrapper.process_query(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders",
            ["year", "UTC", "UTC"],
        )

        assert "django_date_trunc" not in result_query
        assert "CASE" in result_query or "STRFTIME" in result_query


class TestD1DatabaseWrapperConfiguration:
    def test_vendor_and_display_name(self):
        from django_cf.db.backends.d1.base import DatabaseWrapper

        assert DatabaseWrapper.vendor == "cloudflare_d1"
        assert DatabaseWrapper.display_name == "D1"


class TestD1GetConnectionParams:
    def test_missing_binding_raises_error(self):
        from django.core.exceptions import ImproperlyConfigured

        wrapper = make_d1_wrapper()
        wrapper.settings_dict = {"CLOUDFLARE_BINDING": None}

        with pytest.raises(ImproperlyConfigured) as exc_info:
            wrapper.get_connection_params()

        assert "CLOUDFLARE_BINDING" in str(exc_info.value)

    def test_valid_binding_returns_params(self):
        wrapper = make_d1_wrapper()
        wrapper.settings_dict = {"CLOUDFLARE_BINDING": "MY_DB"}

        assert wrapper.get_connection_params() == {"binding": "MY_DB"}


class TestD1ExceptionHandling:
    @pytest.mark.xfail(
        reason=(
            "The `except Exception: raise Error(Error.new().stack)` handler in `run_query` swallows this and re-raises a JS Error. Removing that handler is a separate change; these pass once it lands."
        ),
        strict=True,
    )
    def test_run_query_lets_binding_errors_propagate(self, monkeypatch):
        wrapper = make_d1_wrapper()
        error = RuntimeError("binding boom")
        monkeypatch.setattr(
            workers,
            "env",
            SimpleNamespace(DB=FakeD1Binding(FakeD1Statement(raw_error=error))),
        )

        with pytest.raises(RuntimeError, match="binding boom"):
            wrapper.run_query("SELECT * FROM test")


class TestD1RunQuery:
    def test_read_query_returns_rows(self, monkeypatch):
        wrapper = make_d1_wrapper()
        statement = FakeD1Statement(raw_result=[[1, "hello"], [2, "world"]])
        binding = FakeD1Binding(statement)
        monkeypatch.setattr(workers, "env", SimpleNamespace(DB=binding))

        result = wrapper.run_query("SELECT * FROM test WHERE id = %s", [1])

        assert list(result) == [(1, "hello"), (2, "world")]
        assert statement.bound_params == (1,)
        assert binding.prepared_queries == ["SELECT * FROM test WHERE id = ?"]

    def test_write_query_returns_meta(self, monkeypatch):
        wrapper = make_d1_wrapper()
        statement = FakeD1Statement(
            all_result={
                "results": [["ok"]],
                "meta": {"rows_read": 1, "rows_written": 2, "last_row_id": 9},
            }
        )
        monkeypatch.setattr(
            workers, "env", SimpleNamespace(DB=FakeD1Binding(statement))
        )

        result = wrapper.run_query("INSERT INTO test VALUES (%s)", ["x"])

        assert list(result) == [("ok",)]
        assert result.rowcount == 2
        assert result.lastrowid == 9


class TestD1ParameterHandling:
    def test_empty_params_list(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query("SELECT * FROM users", [])

        assert result_query == "SELECT * FROM users"
        assert result_params == []

    def test_special_characters_in_params(self):
        wrapper = make_d1_wrapper()

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name) VALUES (%s)", ["test'; DROP TABLE users; --"]
        )

        assert result_params == ["test'; DROP TABLE users; --"]
        assert "?" in result_query

    def test_unicode_params(self):
        wrapper = make_d1_wrapper()

        _, result_params = wrapper.process_query(
            "INSERT INTO users (name) VALUES (%s)", [""]
        )

        assert result_params == [""]

    def test_large_number_of_params(self):
        wrapper = make_d1_wrapper()

        placeholders = ", ".join(["%s"] * 50)
        result_query, result_params = wrapper.process_query(
            f"INSERT INTO test VALUES ({placeholders})", list(range(50))
        )

        assert result_query.count("?") == 50
        assert len(result_params) == 50


class TestDODatabaseWrapperProcessQuery:
    def test_process_query_no_params(self):
        wrapper = make_do_wrapper()

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s", None
        )

        assert result_query == "SELECT * FROM users WHERE id = ?"
        assert result_params is None

    def test_process_query_with_params(self):
        wrapper = make_do_wrapper()

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s AND name = %s", [1, "test"]
        )

        assert result_query == "SELECT * FROM users WHERE id = ? AND name = ?"
        assert result_params == [1, "test"]

    def test_process_query_null_param_replaced_with_literal(self):
        wrapper = make_do_wrapper()

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name, email) VALUES (%s, %s)", ["test", None]
        )

        assert "null" in result_query
        assert result_params == ["test"]

    def test_process_query_with_defer_foreign_keys(self):
        result = make_do_wrapper(True).process_query(
            "INSERT INTO users (name) VALUES (%s)", ["test"]
        )

        assert "PRAGMA defer_foreign_keys = on" in result
        assert "PRAGMA defer_foreign_keys = off" in result


class TestDODatabaseWrapperConfiguration:
    def test_vendor_and_display_name(self):
        from django_cf.db.backends.do.base import DatabaseWrapper

        assert DatabaseWrapper.vendor == "cloudflare_durable_objects"
        assert DatabaseWrapper.display_name == "DO"

    def test_get_connection_params_returns_empty(self):
        assert make_do_wrapper().get_connection_params() == {}


class TestDOMissingDateTruncBug:
    def test_do_process_query_missing_date_trunc(self):
        d1_result, _ = make_d1_wrapper().process_query(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders",
            ["year", "UTC", "UTC"],
        )
        do_result, _ = make_do_wrapper().process_query(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders",
            ["year", "UTC", "UTC"],
        )

        assert "django_date_trunc" not in d1_result
        assert "django_date_trunc" in do_result


class TestDOStorageInitialization:
    def test_storage_module_exists(self):
        from django_cf.db.backends.do import storage

        storage.set_storage(None)
        assert storage.get_storage() is None

    def test_run_query_uses_configured_storage(self):
        from django_cf.db.backends.do import storage

        fake_storage = FakeDOStorage(FakeDOStatement([[1, "ok"]], rows_read=1))
        storage.set_storage(fake_storage)

        result = make_do_wrapper().run_query("SELECT * FROM test WHERE id = %s", [1])

        assert list(result) == [(1, "ok")]
        assert fake_storage.calls == [("SELECT * FROM test WHERE id = ?", (1,))]


class TestDOQueryExecution:
    def test_read_query_uses_raw(self):
        from django_cf.db.backends.do import storage

        fake_storage = FakeDOStorage(FakeDOStatement([], rows_read=0, rows_written=0))
        storage.set_storage(fake_storage)

        result = make_do_wrapper().run_query("SELECT * FROM users")

        assert result.fetchall() == []


class TestDOExceptionHandling:
    def test_run_query_lets_binding_errors_propagate(self):
        from django_cf.db.backends.do import storage

        storage.set_storage(FakeDOStorage(error=RuntimeError("storage boom")))

        with pytest.raises(RuntimeError, match="storage boom"):
            make_do_wrapper().run_query("SELECT * FROM test")


class TestDOParamConversion:
    def test_boolean_true_not_converted_in_process_query(self):
        wrapper = make_do_wrapper()

        result_query, result_params = wrapper.process_query(
            "INSERT INTO test (active) VALUES (%s)", [True]
        )

        assert result_query == "INSERT INTO test (active) VALUES (?)"
        assert result_params == [True]

    def test_multiple_none_params_order_preserved(self):
        wrapper = make_do_wrapper()

        result_query, result_params = wrapper.process_query(
            "INSERT INTO test (a, b, c, d) VALUES (%s, %s, %s, %s)",
            [1, None, 2, None],
        )

        assert result_params == [1, 2]
        assert result_query == "INSERT INTO test (a, b, c, d) VALUES (?, null, ?, null)"


class TestDOPragmaReturnTypeBug:
    def test_pragma_returns_string_not_tuple(self):
        result = make_do_wrapper(True).process_query(
            "INSERT INTO users (name) VALUES (%s)", ["test"]
        )

        assert isinstance(result, str)
