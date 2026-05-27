async def _get_stub(env, name="test"):
    ns = env.TEST_DO
    id = ns.idFromName(name)
    return ns.get(id)


async def test_storage_put_and_get(env):
    stub = await _get_stub(env)
    await stub.test_storage_put_and_get()


async def test_storage_get_nonexistent(env):
    stub = await _get_stub(env)
    await stub.test_storage_get_nonexistent()


async def test_storage_put_multiple(env):
    stub = await _get_stub(env)
    await stub.test_storage_put_multiple()


async def test_storage_get_multiple(env):
    stub = await _get_stub(env)
    await stub.test_storage_get_multiple()


async def test_storage_delete(env):
    stub = await _get_stub(env)
    await stub.test_storage_delete()


async def test_storage_delete_multiple(env):
    stub = await _get_stub(env)
    await stub.test_storage_delete_multiple()


async def test_storage_list(env):
    stub = await _get_stub(env)
    await stub.test_storage_list()


async def test_storage_list_with_options(env):
    stub = await _get_stub(env)
    await stub.test_storage_list_with_options()


async def test_storage_delete_all(env):
    stub = await _get_stub(env)
    await stub.test_storage_delete_all()


async def test_storage_value_types(env):
    stub = await _get_stub(env)
    await stub.test_storage_value_types()


async def test_sql_exec_and_query(env):
    stub = await _get_stub(env)
    await stub.test_sql_exec_and_query()


async def test_sql_cursor_one(env):
    stub = await _get_stub(env)
    await stub.test_sql_cursor_one()


async def test_sql_cursor_column_names(env):
    stub = await _get_stub(env)
    await stub.test_sql_cursor_column_names()


async def test_sql_cursor_rows_read_written(env):
    stub = await _get_stub(env)
    await stub.test_sql_cursor_rows_read_written()


async def test_sql_database_size(env):
    stub = await _get_stub(env)
    await stub.test_sql_database_size()


async def test_alarm_set_get_delete(env):
    stub = await _get_stub(env)
    await stub.test_alarm_set_get_delete()


async def test_transaction(env):
    stub = await _get_stub(env)
    await stub.test_transaction()


async def test_ctx_id(env):
    stub = await _get_stub(env)
    await stub.test_ctx_id()


async def test_namespace_id_from_name(env):
    ns = env.TEST_DO
    id1 = ns.idFromName("deterministic")
    id2 = ns.idFromName("deterministic")
    assert id1.toString() == id2.toString(), "idFromName should be deterministic"
    assert id1.name == "deterministic"


async def test_namespace_new_unique_id(env):
    ns = env.TEST_DO
    id1 = ns.newUniqueId()
    id2 = ns.newUniqueId()
    assert id1.toString() != id2.toString(), "newUniqueId should produce unique IDs"
    assert len(id1.toString()) == 64, f"expected 64-char hex, got {len(id1.toString())}"


async def test_namespace_id_from_string(env):
    ns = env.TEST_DO
    original = ns.idFromName("roundtrip")
    hex_str = original.toString()
    restored = ns.idFromString(hex_str)
    assert original.toString() == restored.toString(), "idFromString roundtrip failed"


async def test_rpc_echo(env):
    stub = await _get_stub(env)
    assert await stub.test_rpc_echo("hello") == "hello"
    assert await stub.test_rpc_echo(42) == 42
    assert await stub.test_rpc_echo(True) is True


async def test_rpc_dict(env):
    stub = await _get_stub(env)
    result = await stub.test_rpc_dict({"key": "value"})
    assert result["received"]["key"] == "value"
    assert result["added"] is True


async def test_stub_id(env):
    ns = env.TEST_DO
    id = ns.idFromName("stub_test")
    stub = ns.get(id)
    assert stub.id.toString() == id.toString()
    assert stub.name == "stub_test"


async def test_fetch(env):
    stub = await _get_stub(env, "fetch_test")
    resp = await stub.fetch("http://fake-host/ping")
    text = await resp.text()
    assert text == "pong from DO", f"expected 'pong from DO', got {text!r}"


async def test_block_concurrency_while(env):
    stub = await _get_stub(env)
    await stub.test_block_concurrency_while()


async def test_storage_sync(env):
    stub = await _get_stub(env)
    await stub.test_storage_sync()


async def test_id_equals(env):
    ns = env.TEST_DO
    id1 = ns.idFromName("equal_test")
    id2 = ns.idFromName("equal_test")
    id3 = ns.idFromName("different")
    assert id1.equals(id2), "same name should produce equal IDs"
    assert not id1.equals(id3), "different names should produce different IDs"


DO_TESTS = {
    "storage_put_and_get": test_storage_put_and_get,
    "storage_get_nonexistent": test_storage_get_nonexistent,
    "storage_put_multiple": test_storage_put_multiple,
    "storage_get_multiple": test_storage_get_multiple,
    "storage_delete": test_storage_delete,
    "storage_delete_multiple": test_storage_delete_multiple,
    "storage_list": test_storage_list,
    "storage_list_with_options": test_storage_list_with_options,
    "storage_delete_all": test_storage_delete_all,
    "storage_value_types": test_storage_value_types,
    "sql_exec_and_query": test_sql_exec_and_query,
    "sql_cursor_one": test_sql_cursor_one,
    "sql_cursor_column_names": test_sql_cursor_column_names,
    "sql_cursor_rows_read_written": test_sql_cursor_rows_read_written,
    "sql_database_size": test_sql_database_size,
    "alarm_set_get_delete": test_alarm_set_get_delete,
    "transaction": test_transaction,
    "ctx_id": test_ctx_id,
    "namespace_id_from_name": test_namespace_id_from_name,
    "namespace_new_unique_id": test_namespace_new_unique_id,
    "namespace_id_from_string": test_namespace_id_from_string,
    "rpc_echo": test_rpc_echo,
    "rpc_dict": test_rpc_dict,
    "stub_id": test_stub_id,
    "fetch": test_fetch,
    "block_concurrency_while": test_block_concurrency_while,
    "storage_sync": test_storage_sync,
    "id_equals": test_id_equals,
}
