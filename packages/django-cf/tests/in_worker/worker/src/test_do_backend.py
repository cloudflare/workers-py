"""Durable Objects backend tests executed inside workerd."""

# pyright: reportMissingImports=false

from types import SimpleNamespace

import pytest


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
    def test_vendor_name(self):
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
