from contextlib import contextmanager

from workers import DurableObject


class TestDurableObject(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)

    async def fetch(self, request):
        from urllib.parse import urlparse

        path = urlparse(request.url).path
        if path == "/ping":
            from workers import Response

            return Response("pong from DO")
        from workers import Response

        return Response("not found", status=404)

    async def test_storage_put_and_get(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put("key1", "value1")
        result = await self.ctx.storage.get("key1")
        assert result == "value1", f"expected 'value1', got {result!r}"

    async def test_storage_get_nonexistent(self):
        await self.ctx.storage.deleteAll()
        result = await self.ctx.storage.get("missing")
        assert result is None, f"expected None, got {result!r}"

    async def test_storage_put_multiple(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put({"a": 1, "b": 2, "c": 3})
        a = await self.ctx.storage.get("a")
        b = await self.ctx.storage.get("b")
        c = await self.ctx.storage.get("c")
        assert a == 1 and b == 2 and c == 3, f"got a={a!r}, b={b!r}, c={c!r}"

    async def test_storage_get_multiple(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put({"a": 1, "b": 2})
        result = await self.ctx.storage.get(["a", "b", "missing"])
        assert result.get("a") == 1
        assert result.get("b") == 2

    async def test_storage_delete(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put("to_delete", "gone")
        deleted = await self.ctx.storage.delete("to_delete")
        assert deleted is True, f"expected True, got {deleted!r}"
        result = await self.ctx.storage.get("to_delete")
        assert result is None or repr(result) == "undefined", (
            "expected undefined after delete"
        )

    async def test_storage_delete_multiple(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put({"d1": 1, "d2": 2, "d3": 3})
        count = await self.ctx.storage.delete(["d1", "d2"])
        assert count == 2, f"expected 2, got {count!r}"

    async def test_storage_list(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put({"list:a": 1, "list:b": 2, "list:c": 3, "other": 99})
        result = await self.ctx.storage.list({"prefix": "list:"})
        assert len(result) == 3, f"expected 3 entries, got {len(result)}"
        assert result["list:a"] == 1
        assert result["list:b"] == 2

    async def test_storage_list_with_options(self):
        await self.ctx.storage.deleteAll()
        for i in range(5):
            await self.ctx.storage.put(f"item:{i:03d}", i)
        result = await self.ctx.storage.list({"prefix": "item:", "limit": 2})
        assert len(result) == 2, f"expected 2 entries, got {len(result)}"

    async def test_storage_delete_all(self):
        await self.ctx.storage.put("before_clear", "exists")
        await self.ctx.storage.deleteAll()
        result = await self.ctx.storage.get("before_clear")
        assert result is None or repr(result) == "undefined", (
            "expected undefined after deleteAll"
        )

    async def test_sql_exec_and_query(self):
        self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_sql")
        self.ctx.storage.sql.exec(
            "CREATE TABLE test_sql (id INTEGER PRIMARY KEY, val TEXT)"
        )
        self.ctx.storage.sql.exec(
            "INSERT INTO test_sql (id, val) VALUES (?, ?)", 1, "hello"
        )
        self.ctx.storage.sql.exec(
            "INSERT INTO test_sql (id, val) VALUES (?, ?)", 2, "world"
        )
        rows = self.ctx.storage.sql.exec(
            "SELECT id, val FROM test_sql ORDER BY id"
        ).toArray()
        assert len(rows) == 2, f"expected 2 rows, got {len(rows)}"
        assert rows[0]["id"] == 1 and rows[0]["val"] == "hello"
        assert rows[1]["id"] == 2 and rows[1]["val"] == "world"
        self.ctx.storage.sql.exec("DROP TABLE test_sql")

    async def test_sql_cursor_one(self):
        self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_one")
        self.ctx.storage.sql.exec(
            "CREATE TABLE test_one (id INTEGER PRIMARY KEY, val TEXT)"
        )
        self.ctx.storage.sql.exec("INSERT INTO test_one VALUES (1, 'only')")
        row = self.ctx.storage.sql.exec("SELECT val FROM test_one").one()
        assert row["val"] == "only", f"expected 'only', got {row!r}"
        self.ctx.storage.sql.exec("DROP TABLE test_one")

    async def test_sql_cursor_column_names(self):
        self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_cols")
        self.ctx.storage.sql.exec("CREATE TABLE test_cols (foo INTEGER, bar TEXT)")
        self.ctx.storage.sql.exec("INSERT INTO test_cols VALUES (1, 'a')")
        cursor = self.ctx.storage.sql.exec("SELECT foo, bar FROM test_cols")
        cols = list(cursor.columnNames)
        cursor.toArray()
        del cursor  # free the cursor otherwise we get Error: database table is locked: SQLITE_LOCKED
        assert cols == ["foo", "bar"], f"expected ['foo', 'bar'], got {cols}"
        self.ctx.storage.sql.exec("DROP TABLE test_cols")

    async def test_sql_cursor_rows_read_written(self):
        self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_metrics")
        self.ctx.storage.sql.exec("CREATE TABLE test_metrics (id INTEGER PRIMARY KEY)")
        write_cursor = self.ctx.storage.sql.exec("INSERT INTO test_metrics VALUES (1)")
        write_cursor.toArray()
        rows_written = write_cursor.rowsWritten
        del write_cursor
        assert rows_written >= 1, f"expected rowsWritten >= 1, got {rows_written}"
        read_cursor = self.ctx.storage.sql.exec("SELECT * FROM test_metrics")
        read_cursor.toArray()
        rows_read = read_cursor.rowsRead
        del read_cursor  # free the cursor otherwise we get Error: database table is locked: SQLITE_LOCKED
        assert rows_read >= 1, f"expected rowsRead >= 1, got {rows_read}"
        self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_metrics")

    async def test_sql_database_size(self):
        size = self.ctx.storage.sql.databaseSize
        assert isinstance(size, int | float) and size >= 0, (
            f"expected non-negative number, got {size!r}"
        )

    async def test_alarm_set_get_delete(self):
        await self.ctx.storage.deleteAlarm()
        alarm_before = await self.ctx.storage.getAlarm()
        assert alarm_before is None, f"expected no alarm, got {alarm_before!r}"
        from datetime import datetime, timedelta

        future_time = datetime.now() + timedelta(minutes=1)
        await self.ctx.storage.setAlarm(future_time)
        alarm_after = await self.ctx.storage.getAlarm()
        assert alarm_after is not None, f"expected alarm time, got {alarm_after!r}"
        await self.ctx.storage.deleteAlarm()
        alarm_deleted = await self.ctx.storage.getAlarm()
        assert alarm_deleted is None, "expected no alarm after delete"

    async def test_transaction(self):
        await self.ctx.storage.deleteAll()

        async def txn_body(txn):
            await txn.put("txn_key", "txn_value")
            val = await txn.get("txn_key")
            return val

        result = await self.ctx.storage.transaction(txn_body)
        assert result == "txn_value", f"expected 'txn_value', got {result!r}"
        persisted = await self.ctx.storage.get("txn_key")
        assert persisted == "txn_value", (
            f"expected persisted 'txn_value', got {persisted!r}"
        )

    async def test_ctx_id(self):
        id_str = self.ctx.id.toString()
        assert isinstance(id_str, str) and len(id_str) == 64, (
            f"expected 64-char hex, got {id_str!r}"
        )
        assert self.ctx.id.name is not None, "expected id.name for named DO"

    async def test_block_concurrency_while(self):
        async def init():
            await self.ctx.storage.put("bcw_key", "bcw_value")
            return 42

        result = await self.ctx.blockConcurrencyWhile(init)
        assert result == 42, f"expected 42, got {result!r}"
        val = await self.ctx.storage.get("bcw_key")
        assert val == "bcw_value", f"expected 'bcw_value', got {val!r}"

    async def test_storage_sync(self):
        await self.ctx.storage.put("sync_key", "sync_value")
        await self.ctx.storage.sync()
        result = await self.ctx.storage.get("sync_key")
        assert result == "sync_value", f"expected 'sync_value', got {result!r}"

    async def test_rpc_echo(self, value):
        return value

    async def test_rpc_dict(self, data):
        return {"received": data, "added": True}

    @contextmanager
    def _create_iter_table(self):
        self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_iter")
        self.ctx.storage.sql.exec(
            "CREATE TABLE test_iter (id INTEGER PRIMARY KEY, val TEXT)"
        )
        self.ctx.storage.sql.exec(
            "INSERT INTO test_iter (id, val) VALUES (?, ?)", 1, "alpha"
        )
        self.ctx.storage.sql.exec(
            "INSERT INTO test_iter (id, val) VALUES (?, ?)", 2, "beta"
        )
        self.ctx.storage.sql.exec(
            "INSERT INTO test_iter (id, val) VALUES (?, ?)", 3, "gamma"
        )
        try:
            yield
        finally:
            self.ctx.storage.sql.exec("DROP TABLE IF EXISTS test_iter")

    async def test_sql_cursor_iter(self):
        with self._create_iter_table():
            cursor = self.ctx.storage.sql.exec(
                "SELECT id, val FROM test_iter ORDER BY id"
            )
            rows = [{"id": row["id"], "val": row["val"]} for row in cursor]
            del cursor
            assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"
            assert rows[0]["id"] == 1 and rows[0]["val"] == "alpha"
            assert rows[1]["id"] == 2 and rows[1]["val"] == "beta"
            assert rows[2]["id"] == 3 and rows[2]["val"] == "gamma"

    async def test_sql_cursor_toarray_getitem_int(self):
        with self._create_iter_table():
            cursor = self.ctx.storage.sql.exec(
                "SELECT id, val FROM test_iter ORDER BY id"
            )
            arr = cursor.toArray()
            del cursor
            first_row = arr[0]
            assert first_row["id"] == 1 and first_row["val"] == "alpha", (
                f"expected row with id=1, got {first_row!r}"
            )
            assert len(arr) == 3, f"expected len 3, got {len(arr)}"

    async def test_storage_value_types(self):
        await self.ctx.storage.deleteAll()
        await self.ctx.storage.put("str", "hello")
        await self.ctx.storage.put("int", 42)
        await self.ctx.storage.put("float", 3.14)
        await self.ctx.storage.put("bool", True)
        assert await self.ctx.storage.get("str") == "hello"
        assert await self.ctx.storage.get("int") == 42
        assert abs(await self.ctx.storage.get("float") - 3.14) < 0.001
        assert await self.ctx.storage.get("bool") is True
