"""D1 backend tests executed inside workerd."""

# pyright: reportMissingImports=false

import pytest
from django.db import connections

D1_BACKEND = connections["d1"]


class TestD1DatabaseWrapperProcessQuery:
    def test_process_query_no_params(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s", None
        )

        assert result_query == "SELECT * FROM users WHERE id = ?"
        assert result_params is None

    def test_process_query_with_params(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s AND name = %s", [1, "test"]
        )

        assert result_query == "SELECT * FROM users WHERE id = ? AND name = ?"
        assert result_params == [1, "test"]

    def test_process_query_null_param_replaced_with_literal(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name, email) VALUES (%s, %s)", ["test", None]
        )

        assert "null" in result_query
        assert result_params == ["test"]

    def test_process_query_all_null_params(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name, email) VALUES (%s, %s)", [None, None]
        )

        assert result_query == "INSERT INTO users (name, email) VALUES (null, null)"
        assert result_params == []

    def test_process_query_mixed_params(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query(
            "UPDATE users SET name = %s, email = %s, age = %s WHERE id = %s",
            ["test", None, 25, None],
        )

        assert result_params == ["test", 25]
        assert result_query.count("?") == 2
        assert result_query.count("null") == 2

    def test_process_query_with_defer_foreign_keys(self):
        cursor = D1_BACKEND.cursor()
        cursor.defer_foreign_keys(True)
        try:
            result = D1_BACKEND.process_query(
                "INSERT INTO users (name) VALUES (%s)", ["test"]
            )
        finally:
            cursor.defer_foreign_keys(False)

        assert "PRAGMA defer_foreign_keys = on" in result
        assert "PRAGMA defer_foreign_keys = off" in result

    def test_process_query_date_trunc_replacement(self):
        wrapper = D1_BACKEND

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

        from django_cf.db.backends.d1.base import DatabaseWrapper

        wrapper = DatabaseWrapper({"CLOUDFLARE_BINDING": None}, "missing-binding")

        with pytest.raises(ImproperlyConfigured) as exc_info:
            wrapper.get_connection_params()

        assert "CLOUDFLARE_BINDING" in str(exc_info.value)

    def test_valid_binding_returns_params(self):
        assert D1_BACKEND.get_connection_params() == {"binding": "DB"}


class TestD1ExceptionHandling:
    @pytest.mark.xfail(
        reason=(
            "The `except Exception: raise Error(Error.new().stack)` handler in `run_query` swallows this and re-raises a JS Error. Removing that handler is a separate change; these pass once it lands."
        ),
        strict=True,
    )
    def test_run_query_lets_binding_errors_propagate(self):
        wrapper = D1_BACKEND

        with pytest.raises(Exception, match="no such table"):
            wrapper.run_query("SELECT * FROM _django_cf_d1_missing_table")


class TestD1RunQuery:
    def test_read_query_returns_rows(self):
        wrapper = D1_BACKEND
        table = "_django_cf_d1_read"
        wrapper.run_query(f"DROP TABLE IF EXISTS {table}")
        wrapper.run_query(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")
        wrapper.run_query(f"INSERT INTO {table} VALUES (%s, %s)", [1, "hello"])
        wrapper.run_query(f"INSERT INTO {table} VALUES (%s, %s)", [2, "world"])

        result = wrapper.run_query(
            f"SELECT id, value FROM {table} WHERE id >= %s ORDER BY id", [1]
        )

        assert list(result) == [(1, "hello"), (2, "world")]
        wrapper.run_query(f"DROP TABLE {table}")

    def test_write_query_returns_meta(self):
        wrapper = D1_BACKEND
        table = "_django_cf_d1_write"
        wrapper.run_query(f"DROP TABLE IF EXISTS {table}")
        wrapper.run_query(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")

        result = wrapper.run_query(
            f"INSERT INTO {table} (id, value) VALUES (%s, %s)", [1, "x"]
        )

        assert list(result) == []
        assert result.rowcount == 1
        assert result.lastrowid == 1
        wrapper.run_query(f"DROP TABLE {table}")


class TestD1ParameterHandling:
    def test_empty_params_list(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query("SELECT * FROM users", [])

        assert result_query == "SELECT * FROM users"
        assert result_params == []

    def test_special_characters_in_params(self):
        wrapper = D1_BACKEND

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name) VALUES (%s)", ["test'; DROP TABLE users; --"]
        )

        assert result_params == ["test'; DROP TABLE users; --"]
        assert "?" in result_query

    def test_unicode_params(self):
        wrapper = D1_BACKEND

        _, result_params = wrapper.process_query(
            "INSERT INTO users (name) VALUES (%s)", [""]
        )

        assert result_params == [""]

    def test_large_number_of_params(self):
        wrapper = D1_BACKEND

        placeholders = ", ".join(["%s"] * 50)
        result_query, result_params = wrapper.process_query(
            f"INSERT INTO test VALUES ({placeholders})", list(range(50))
        )

        assert result_query.count("?") == 50
        assert len(result_params) == 50
