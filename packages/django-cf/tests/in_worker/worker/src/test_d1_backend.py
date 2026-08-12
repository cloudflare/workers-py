"""D1 backend tests executed inside workerd."""

# pyright: reportMissingImports=false

from types import SimpleNamespace

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
    def test_vendor_name(self):
        from django_cf.db.backends.d1.base import DatabaseWrapper

        assert DatabaseWrapper.vendor == "cloudflare_d1"

    def test_display_name(self):
        from django_cf.db.backends.d1.base import DatabaseWrapper

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
