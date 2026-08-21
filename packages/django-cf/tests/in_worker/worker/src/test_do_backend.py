"""Durable Objects backend tests executed inside workerd."""

# pyright: reportMissingImports=false

import pytest
from django.db import connections

D1_BACKEND = connections["d1"]
DO_BACKEND = connections["do"]


async def get_do_stub(env):
    namespace = env.DO_STORAGE
    object_id = namespace.idFromName("django-cf-backend-tests")
    return namespace.get(object_id)


class TestDODatabaseWrapperProcessQuery:
    def test_process_query_no_params(self):
        wrapper = DO_BACKEND

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s", None
        )

        assert result_query == "SELECT * FROM users WHERE id = ?"
        assert result_params is None

    def test_process_query_with_params(self):
        wrapper = DO_BACKEND

        result_query, result_params = wrapper.process_query(
            "SELECT * FROM users WHERE id = %s AND name = %s", [1, "test"]
        )

        assert result_query == "SELECT * FROM users WHERE id = ? AND name = ?"
        assert result_params == [1, "test"]

    def test_process_query_null_param_replaced_with_literal(self):
        wrapper = DO_BACKEND

        result_query, result_params = wrapper.process_query(
            "INSERT INTO users (name, email) VALUES (%s, %s)", ["test", None]
        )

        assert "null" in result_query
        assert result_params == ["test"]

    def test_process_query_with_defer_foreign_keys(self):
        cursor = DO_BACKEND.cursor()
        cursor.defer_foreign_keys(True)
        try:
            result = DO_BACKEND.process_query(
                "INSERT INTO users (name) VALUES (%s)", ["test"]
            )
        finally:
            cursor.defer_foreign_keys(False)

        assert "PRAGMA defer_foreign_keys = on" in result
        assert "PRAGMA defer_foreign_keys = off" in result


class TestDODatabaseWrapperConfiguration:
    def test_vendor_name(self):
        from django_cf.db.backends.do.base import DatabaseWrapper

        assert DatabaseWrapper.vendor == "cloudflare_durable_objects"
        assert DatabaseWrapper.display_name == "DO"

    def test_get_connection_params_returns_empty(self):
        assert DO_BACKEND.get_connection_params() == {}


class TestDOMissingDateTruncBug:
    def test_do_process_query_missing_date_trunc(self):
        d1_result, _ = D1_BACKEND.process_query(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders",
            ["year", "UTC", "UTC"],
        )
        do_result, _ = DO_BACKEND.process_query(
            "SELECT django_date_trunc(%s, created_at, %s, %s) FROM orders",
            ["year", "UTC", "UTC"],
        )

        assert "django_date_trunc" not in d1_result
        assert "django_date_trunc" in do_result


class TestDOStorageInitialization:
    @pytest.mark.asyncio
    async def test_storage_module_exists(self, env):
        stub = await get_do_stub(env)
        await stub.test_storage_is_configured()

    @pytest.mark.asyncio
    async def test_run_query_uses_configured_storage(self, env):
        stub = await get_do_stub(env)
        await stub.test_run_query_uses_configured_storage()


class TestDOQueryExecution:
    @pytest.mark.asyncio
    async def test_read_query_uses_raw(self, env):
        stub = await get_do_stub(env)
        await stub.test_read_query_uses_raw()


class TestDOExceptionHandling:
    @pytest.mark.asyncio
    async def test_run_query_lets_binding_errors_propagate(self, env):
        stub = await get_do_stub(env)
        await stub.test_binding_errors_propagate()


class TestDOParamConversion:
    def test_boolean_true_not_converted_in_process_query(self):
        wrapper = DO_BACKEND

        result_query, result_params = wrapper.process_query(
            "INSERT INTO test (active) VALUES (%s)", [True]
        )

        assert result_query == "INSERT INTO test (active) VALUES (?)"
        assert result_params == [True]

    def test_multiple_none_params_order_preserved(self):
        wrapper = DO_BACKEND

        result_query, result_params = wrapper.process_query(
            "INSERT INTO test (a, b, c, d) VALUES (%s, %s, %s, %s)",
            [1, None, 2, None],
        )

        assert result_params == [1, 2]
        assert result_query == "INSERT INTO test (a, b, c, d) VALUES (?, null, ?, null)"


class TestDOPragmaReturnTypeBug:
    def test_pragma_returns_string_not_tuple(self):
        cursor = DO_BACKEND.cursor()
        cursor.defer_foreign_keys(True)
        try:
            result = DO_BACKEND.process_query(
                "INSERT INTO users (name) VALUES (%s)", ["test"]
            )
        finally:
            cursor.defer_foreign_keys(False)

        assert isinstance(result, str)
