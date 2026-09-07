# pyright: reportMissingImports=false

from _django_app import django_wsgi_app
from django.db import connections
from workers import DurableObject

from django_cf import DjangoCFDurableObject
from django_cf.db.backends.do.storage import get_storage


class TestDurableObject(DjangoCFDurableObject, DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)

    def get_app(self):
        return django_wsgi_app()

    @property
    def database(self):
        return connections["do"]

    async def create_orm_table(self):
        from _do_orm_app import CREATE_DO_TABLE_SQL, DROP_DO_TABLE_SQL

        sql = self.ctx.storage.sql
        sql.exec(DROP_DO_TABLE_SQL)
        sql.exec(CREATE_DO_TABLE_SQL)

    async def drop_orm_table(self):
        from _do_orm_app import DROP_DO_TABLE_SQL

        self.ctx.storage.sql.exec(DROP_DO_TABLE_SQL)

    async def test_storage_is_configured(self):
        from workers.entrypoints import DurableObjectContext

        assert isinstance(self.ctx, DurableObjectContext)
        assert get_storage() is not None

    async def test_run_query_uses_configured_storage(self):
        table = "_django_cf_do_configured_storage"
        sql = self.ctx.storage.sql
        sql.exec(f"DROP TABLE IF EXISTS {table}")
        sql.exec(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")
        sql.exec(f"INSERT INTO {table} VALUES (?, ?)", 1, "ok")

        rows = sql.exec(f"SELECT id, value FROM {table}").raw().toArray()
        assert isinstance(rows, list)
        assert rows == [[1, "ok"]]

        result = self.database.run_query(
            f"SELECT id, value FROM {table} WHERE id = %s", [1]
        )

        assert list(result) == [(1, "ok")]
        sql.exec(f"DROP TABLE {table}")

    async def test_read_query_uses_raw(self):
        table = "_django_cf_do_empty_read"
        sql = self.ctx.storage.sql
        sql.exec(f"DROP TABLE IF EXISTS {table}")
        sql.exec(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")

        result = self.database.run_query(f"SELECT * FROM {table}")

        assert result.fetchall() == []
        sql.exec(f"DROP TABLE {table}")

    async def test_binding_errors_propagate(self):
        table = "_django_cf_do_missing_table"
        self.ctx.storage.sql.exec(f"DROP TABLE IF EXISTS {table}")

        try:
            self.database.run_query(f"SELECT * FROM {table}")
        except Exception as exc:
            assert "no such table" in str(exc).lower()
        else:
            raise AssertionError("expected the real Durable Object binding to raise")
