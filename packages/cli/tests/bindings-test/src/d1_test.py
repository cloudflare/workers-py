TEST_TABLE = "_test_d1"
TEST_TABLE_TYPES = "_test_d1_types"
TEST_TABLE_BATCH = "_test_d1_batch"
EXEC_TABLE = "_test_d1_exec_tmp"
EXEC_MULTI_TABLE = "_test_d1_exec_multi"


async def _cleanup_d1(db):
    for table in [TEST_TABLE, TEST_TABLE_TYPES, TEST_TABLE_BATCH, EXEC_TABLE, EXEC_MULTI_TABLE]:
        try:
            await db.exec(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass


async def _ensure_tables(db):
    await db.exec(
        f"CREATE TABLE IF NOT EXISTS {TEST_TABLE} "
        f"(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, value TEXT)"
    )
    await db.exec(
        f"CREATE TABLE IF NOT EXISTS {TEST_TABLE_TYPES} "
        f"(id INTEGER PRIMARY KEY, txt TEXT, num REAL, intval INTEGER)"
    )
    await db.exec(
        f"CREATE TABLE IF NOT EXISTS {TEST_TABLE_BATCH} "
        f"(id INTEGER PRIMARY KEY, val TEXT)"
    )


async def test_insert_and_select_via_run(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    insert_result = await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("run_test", "hello").run()
    assert insert_result["success"] is True, f"insert failed: {insert_result!r}"
    meta = insert_result["meta"]
    assert meta["changes"] >= 1
    assert meta["last_row_id"] > 0
    row_id = meta["last_row_id"]
    select_result = await db.prepare(
        f"SELECT id, name, value FROM {TEST_TABLE} WHERE id = ?"
    ).bind(row_id).run()
    rows = select_result["results"]
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    assert rows[0]["name"] == "run_test"
    assert rows[0]["value"] == "hello"


async def test_all_returns_results(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("all_test", "v1").run()
    result = await db.prepare(
        f"SELECT name, value FROM {TEST_TABLE} WHERE name = ?"
    ).bind("all_test").all()
    assert result["success"] is True
    rows = result["results"]
    assert len(rows) >= 1, f"expected >= 1 row, got {len(rows)}"
    assert rows[0]["name"] == "all_test"


async def test_first_returns_single_row(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("first_test", "fv").run()
    row = await db.prepare(
        f"SELECT name, value FROM {TEST_TABLE} WHERE name = ? LIMIT 1"
    ).bind("first_test").first()
    assert row is not None, "first() returned None"
    assert isinstance(row, dict), f"expected dict, got {type(row)}: {row}"
    assert row["name"] == "first_test"
    assert row["value"] == "fv"


async def test_first_with_column_name(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("first_col", "col_val").run()
    value = await db.prepare(
        f"SELECT name, value FROM {TEST_TABLE} WHERE name = ? LIMIT 1"
    ).bind("first_col").first("value")
    assert value == "col_val", f"expected 'col_val', got {value!r}"


async def test_first_on_empty_result(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    row = await db.prepare(
        f"SELECT * FROM {TEST_TABLE} WHERE name = ?"
    ).bind("__nonexistent__xyz__").first()
    assert row is None, f"expected None, got {row!r}"


async def test_raw_returns_arrays(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("raw_test", "rv").run()
    rows = await db.prepare(
        f"SELECT name, value FROM {TEST_TABLE} WHERE name = ? LIMIT 1"
    ).bind("raw_test").raw()
    assert isinstance(rows, list), f"expected list, got {type(rows)}"
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    assert rows[0] == ["raw_test", "rv"], f"row mismatch: {rows!r}"


async def test_raw_with_column_names(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("raw_cols", "rc").run()
    rows = await db.prepare(
        f"SELECT name, value FROM {TEST_TABLE} WHERE name = ? LIMIT 1"
    ).bind("raw_cols").raw({"columnNames": True})
    assert len(rows) == 2, f"expected header + data, got {len(rows)} rows"
    assert rows[0] == ["name", "value"], f"header mismatch: {rows[0]!r}"
    assert rows[1] == ["raw_cols", "rc"], f"row mismatch: {rows[1]!r}"


async def test_bind_null(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, txt) VALUES (?, ?)"
    ).bind(9001, None).run()
    row = await db.prepare(
        f"SELECT txt FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9001).first()
    assert row is not None, "row not found"
    assert row["txt"] is None, f"expected None, got {row['txt']!r}"


async def test_bind_integer(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, intval) VALUES (?, ?)"
    ).bind(9002, 42).run()
    row = await db.prepare(
        f"SELECT intval FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9002).first()
    assert row["intval"] == 42, f"expected 42, got {row['intval']}"


async def test_bind_float(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, num) VALUES (?, ?)"
    ).bind(9003, 3.14).run()
    row = await db.prepare(
        f"SELECT num FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9003).first()
    assert abs(row["num"] - 3.14) < 0.001, f"expected ~3.14, got {row['num']}"


async def test_bind_string(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    value = "hello, D1!"
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, txt) VALUES (?, ?)"
    ).bind(9004, value).run()
    row = await db.prepare(
        f"SELECT txt FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9004).first()
    assert row["txt"] == value, f"expected {value!r}, got {row['txt']!r}"


async def test_bind_boolean(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, intval) VALUES (?, ?)"
    ).bind(9005, True).run()
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, intval) VALUES (?, ?)"
    ).bind(9006, False).run()
    row_true = await db.prepare(
        f"SELECT intval FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9005).first()
    row_false = await db.prepare(
        f"SELECT intval FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9006).first()
    assert row_true["intval"] == 1, f"True should be 1, got {row_true['intval']}"
    assert row_false["intval"] == 0, f"False should be 0, got {row_false['intval']}"


async def test_bind_multiple_parameters(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    await db.prepare(
        f"INSERT INTO {TEST_TABLE_TYPES} (id, txt, num, intval) VALUES (?, ?, ?, ?)"
    ).bind(9007, "multi", 2.71, 100).run()
    row = await db.prepare(
        f"SELECT txt, num, intval FROM {TEST_TABLE_TYPES} WHERE id = ?"
    ).bind(9007).first()
    assert row["txt"] == "multi"
    assert abs(row["num"] - 2.71) < 0.001
    assert row["intval"] == 100


async def test_exec_create_and_query(env):
    db = env.DB
    await _cleanup_d1(db)
    result = await db.exec(
        f"CREATE TABLE IF NOT EXISTS {EXEC_TABLE} (id INTEGER PRIMARY KEY, val TEXT)"
    )
    assert result["count"] >= 1, f"expected count >= 1, got {result['count']}"
    assert result["duration"] >= 0, f"expected duration >= 0, got {result['duration']}"


async def test_exec_multiple_statements(env):
    db = env.DB
    await _cleanup_d1(db)
    result = await db.exec(
        f"CREATE TABLE IF NOT EXISTS {EXEC_MULTI_TABLE} (id INTEGER PRIMARY KEY, val TEXT);\n"
        f"INSERT INTO {EXEC_MULTI_TABLE} (val) VALUES ('a');\n"
        f"INSERT INTO {EXEC_MULTI_TABLE} (val) VALUES ('b');"
    )
    assert result["count"] >= 3, f"expected count >= 3, got {result['count']}"
    rows = await db.prepare(f"SELECT val FROM {EXEC_MULTI_TABLE} ORDER BY val").raw()
    assert rows == [["a"], ["b"]], f"row mismatch: {rows!r}"


async def test_batch_multiple_inserts(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    statements = [
        db.prepare(f"INSERT INTO {TEST_TABLE_BATCH} (id, val) VALUES (?, ?)").bind(1, "batch_a"),
        db.prepare(f"INSERT INTO {TEST_TABLE_BATCH} (id, val) VALUES (?, ?)").bind(2, "batch_b"),
        db.prepare(f"INSERT INTO {TEST_TABLE_BATCH} (id, val) VALUES (?, ?)").bind(3, "batch_c"),
    ]
    results = await db.batch(statements)
    assert results is not None, "batch returned None"
    all_rows = await db.prepare(
        f"SELECT id, val FROM {TEST_TABLE_BATCH} ORDER BY id"
    ).all()
    rows = all_rows["results"]
    assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"
    assert [row["val"] for row in rows] == ["batch_a", "batch_b", "batch_c"]


async def test_run_metadata_fields(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    result = await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("meta_test", "mv").run()
    assert result["success"] is True
    meta = result["meta"]
    for key in ["duration", "changes", "last_row_id", "changed_db", "rows_read", "rows_written", "size_after"]:
        assert key in meta, f"missing {key!r} in meta: {meta!r}"
    assert meta["changes"] >= 1
    assert meta["changed_db"] is True


async def test_update_row(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    insert_result = await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("update_me", "old_value").run()
    row_id = insert_result["meta"]["last_row_id"]
    update_result = await db.prepare(
        f"UPDATE {TEST_TABLE} SET value = ? WHERE id = ?"
    ).bind("new_value", row_id).run()
    assert update_result["meta"]["changes"] == 1
    row = await db.prepare(
        f"SELECT value FROM {TEST_TABLE} WHERE id = ?"
    ).bind(row_id).first()
    assert row["value"] == "new_value", f"expected 'new_value', got {row['value']!r}"


async def test_delete_row(env):
    db = env.DB
    await _cleanup_d1(db)
    await _ensure_tables(db)
    insert_result = await db.prepare(
        f"INSERT INTO {TEST_TABLE} (name, value) VALUES (?, ?)"
    ).bind("delete_me", "gone").run()
    row_id = insert_result["meta"]["last_row_id"]
    delete_result = await db.prepare(
        f"DELETE FROM {TEST_TABLE} WHERE id = ?"
    ).bind(row_id).run()
    assert delete_result["meta"]["changes"] == 1
    row = await db.prepare(
        f"SELECT * FROM {TEST_TABLE} WHERE id = ?"
    ).bind(row_id).first()
    assert row is None, f"row should be deleted, got {row!r}"


async def test_invalid_sql_raises_error(env):
    db = env.DB
    await _cleanup_d1(db)
    raised = False
    try:
        await db.prepare("INVALID SQL GIBBERISH").run()
    except Exception:
        raised = True
    assert raised, "expected error on invalid SQL"


D1_TESTS = {
    "insert_and_select_via_run": test_insert_and_select_via_run,
    "all_returns_results": test_all_returns_results,
    "first_returns_single_row": test_first_returns_single_row,
    "first_with_column_name": test_first_with_column_name,
    "first_on_empty_result": test_first_on_empty_result,
    "raw_returns_arrays": test_raw_returns_arrays,
    "raw_with_column_names": test_raw_with_column_names,
    "bind_null": test_bind_null,
    "bind_integer": test_bind_integer,
    "bind_float": test_bind_float,
    "bind_string": test_bind_string,
    "bind_boolean": test_bind_boolean,
    "bind_multiple_parameters": test_bind_multiple_parameters,
    "exec_create_and_query": test_exec_create_and_query,
    "exec_multiple_statements": test_exec_multiple_statements,
    "batch_multiple_inserts": test_batch_multiple_inserts,
    "run_metadata_fields": test_run_metadata_fields,
    "update_row": test_update_row,
    "delete_row": test_delete_row,
    "invalid_sql_raises_error": test_invalid_sql_raises_error,
}
