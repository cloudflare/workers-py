import pytest


async def _get_stub(env, name="test"):
    ns = env.TEST_DO
    id = ns.idFromName(name)
    return ns.get(id)


@pytest.mark.asyncio
async def test_storage_put_and_get(env):
    stub = await _get_stub(env)
    await stub.test_storage_put_and_get()


@pytest.mark.asyncio
async def test_storage_get_nonexistent(env):
    stub = await _get_stub(env)
    await stub.test_storage_get_nonexistent()


@pytest.mark.asyncio
async def test_storage_put_multiple(env):
    stub = await _get_stub(env)
    await stub.test_storage_put_multiple()


@pytest.mark.asyncio
async def test_storage_get_multiple(env):
    stub = await _get_stub(env)
    await stub.test_storage_get_multiple()


@pytest.mark.asyncio
async def test_storage_delete(env):
    stub = await _get_stub(env)
    await stub.test_storage_delete()


@pytest.mark.asyncio
async def test_storage_delete_multiple(env):
    stub = await _get_stub(env)
    await stub.test_storage_delete_multiple()


@pytest.mark.asyncio
async def test_storage_list(env):
    stub = await _get_stub(env)
    await stub.test_storage_list()


@pytest.mark.asyncio
async def test_storage_list_with_options(env):
    stub = await _get_stub(env)
    await stub.test_storage_list_with_options()


@pytest.mark.asyncio
async def test_storage_delete_all(env):
    stub = await _get_stub(env)
    await stub.test_storage_delete_all()


@pytest.mark.asyncio
async def test_storage_value_types(env):
    stub = await _get_stub(env)
    await stub.test_storage_value_types()


@pytest.mark.asyncio
async def test_sql_exec_and_query(env):
    stub = await _get_stub(env)
    await stub.test_sql_exec_and_query()


@pytest.mark.asyncio
async def test_sql_cursor_one(env):
    stub = await _get_stub(env)
    await stub.test_sql_cursor_one()


@pytest.mark.asyncio
async def test_sql_cursor_column_names(env):
    stub = await _get_stub(env)
    await stub.test_sql_cursor_column_names()


@pytest.mark.asyncio
async def test_sql_cursor_rows_read_written(env):
    stub = await _get_stub(env)
    await stub.test_sql_cursor_rows_read_written()


@pytest.mark.asyncio
async def test_sql_database_size(env):
    stub = await _get_stub(env)
    await stub.test_sql_database_size()


@pytest.mark.asyncio
async def test_alarm_set_get_delete(env):
    stub = await _get_stub(env)
    await stub.test_alarm_set_get_delete()


@pytest.mark.asyncio
async def test_transaction(env):
    stub = await _get_stub(env)
    await stub.test_transaction()


@pytest.mark.asyncio
async def test_ctx_id(env):
    stub = await _get_stub(env)
    await stub.test_ctx_id()


@pytest.mark.asyncio
async def test_namespace_id_from_name(env):
    ns = env.TEST_DO
    id1 = ns.idFromName("deterministic")
    id2 = ns.idFromName("deterministic")
    assert id1.toString() == id2.toString(), "idFromName should be deterministic"
    assert id1.name == "deterministic"


@pytest.mark.asyncio
async def test_namespace_new_unique_id(env):
    ns = env.TEST_DO
    id1 = ns.newUniqueId()
    id2 = ns.newUniqueId()
    assert id1.toString() != id2.toString(), "newUniqueId should produce unique IDs"
    assert len(id1.toString()) == 64, f"expected 64-char hex, got {len(id1.toString())}"


@pytest.mark.asyncio
async def test_namespace_id_from_string(env):
    ns = env.TEST_DO
    original = ns.idFromName("roundtrip")
    hex_str = original.toString()
    restored = ns.idFromString(hex_str)
    assert original.toString() == restored.toString(), "idFromString roundtrip failed"


@pytest.mark.asyncio
async def test_rpc_echo(env):
    stub = await _get_stub(env)
    assert await stub.test_rpc_echo("hello") == "hello"
    assert await stub.test_rpc_echo(42) == 42
    assert await stub.test_rpc_echo(True) is True


@pytest.mark.asyncio
async def test_rpc_dict(env):
    stub = await _get_stub(env)
    result = await stub.test_rpc_dict({"key": "value"})
    assert result["received"]["key"] == "value"
    assert result["added"] is True


@pytest.mark.asyncio
async def test_stub_id(env):
    ns = env.TEST_DO
    id = ns.idFromName("stub_test")
    stub = ns.get(id)
    assert stub.id.toString() == id.toString()
    assert stub.name == "stub_test"


@pytest.mark.asyncio
async def test_fetch(env):
    stub = await _get_stub(env, "fetch_test")
    resp = await stub.fetch("http://fake-host/ping")
    text = await resp.text()
    assert text == "pong from DO", f"expected 'pong from DO', got {text!r}"


@pytest.mark.asyncio
async def test_block_concurrency_while(env):
    stub = await _get_stub(env)
    await stub.test_block_concurrency_while()


@pytest.mark.asyncio
async def test_storage_sync(env):
    stub = await _get_stub(env)
    await stub.test_storage_sync()


@pytest.mark.asyncio
async def test_id_equals(env):
    ns = env.TEST_DO
    id1 = ns.idFromName("equal_test")
    id2 = ns.idFromName("equal_test")
    id3 = ns.idFromName("different")
    assert id1.equals(id2), "same name should produce equal IDs"
    assert not id1.equals(id3), "different names should produce different IDs"
