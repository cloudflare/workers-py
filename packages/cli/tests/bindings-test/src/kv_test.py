async def _cleanup_kv(kv):
    result = await kv.list()
    for item in result.keys:
        await kv.delete(item.name)


async def test_put_and_get(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("hello", "world")
    value = await kv.get("hello")
    assert value == "world", f"Expected 'world', got {value!r}"


KV_TESTS = {
    "test_put_and_get": test_put_and_get,
}
