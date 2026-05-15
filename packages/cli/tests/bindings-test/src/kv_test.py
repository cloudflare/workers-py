import json


async def _cleanup_kv(kv):
    cursor = None
    while True:
        options = {"prefix": "_test:", "limit": 1000}
        if cursor:
            options["cursor"] = cursor
        result = await kv.list(options)
        for key_entry in result["keys"]:
            await kv.delete(key_entry["name"])
        if result["list_complete"]:
            break
        cursor = result.get("cursor")


async def test_put_and_get_text(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:put_get_text"
    value = "hello from KV"
    await kv.put(key, value)
    result = await kv.get(key)
    assert result == value, f"expected {value!r}, got {result!r}"


async def test_get_nonexistent(env):
    kv = env.KV
    await _cleanup_kv(kv)
    result = await kv.get("_test:does_not_exist_12345")
    assert result is None, f"expected None, got {result!r}"


async def test_put_and_get_json(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:put_get_json"
    payload = {"message": "hello", "numbers": [1, 2, 3]}
    await kv.put(key, json.dumps(payload))
    result = await kv.get(key, "json")
    assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
    assert result == payload, f"json mismatch: {result!r}"


async def test_put_overwrite(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:overwrite"
    await kv.put(key, "version1")
    first = await kv.get(key)
    await kv.put(key, "version2")
    second = await kv.get(key)
    assert first == "version1"
    assert second == "version2"


async def test_put_empty_value(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:empty_value"
    await kv.put(key, "")
    result = await kv.get(key)
    assert result == "", f"expected empty string, got {result!r}"


async def test_delete(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:delete"
    await kv.put(key, "to be deleted")
    assert await kv.get(key) == "to be deleted"
    await kv.delete(key)
    result = await kv.get(key)
    assert result is None, f"expected None after delete, got {result!r}"


async def test_delete_nonexistent(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.delete("_test:does_not_exist_67890")


async def test_put_with_metadata(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:metadata"
    metadata = {"author": "test-suite", "version": "1.0"}
    await kv.put(key, "metadata test", {"metadata": metadata})
    result = await kv.getWithMetadata(key)
    assert result["value"] == "metadata test"
    assert result["metadata"] is not None, "expected metadata"
    assert result["metadata"] == metadata, f"metadata mismatch: {result['metadata']!r}"


async def test_get_with_metadata_nonexistent(env):
    kv = env.KV
    await _cleanup_kv(kv)
    result = await kv.getWithMetadata("_test:does_not_exist_meta")
    assert result["value"] is None, f"expected None value, got {result['value']!r}"
    assert result["metadata"] is None, f"expected None metadata, got {result['metadata']!r}"


async def test_put_with_expiration_ttl(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:expiration_ttl"
    await kv.put(key, "expires soon", {"expirationTtl": 60})
    result = await kv.get(key)
    assert result == "expires soon", f"value mismatch: {result!r}"
    listed = await kv.list({"prefix": key})
    matching = [k for k in listed["keys"] if k["name"] == key]
    assert len(matching) == 1, f"key not found in list"
    assert matching[0].get("expiration") is not None, "expected expiration to be set"


async def test_list_basic(env):
    kv = env.KV
    await _cleanup_kv(kv)
    for i in range(3):
        await kv.put(f"_test:list_basic:{i}", f"val-{i}")
    result = await kv.list({"prefix": "_test:list_basic:"})
    keys = result["keys"]
    names = [k["name"] for k in keys]
    assert len(keys) >= 3, f"expected >= 3 keys, got {len(keys)}"
    assert result["list_complete"]
    for i in range(3):
        assert f"_test:list_basic:{i}" in names, f"missing key {i}"


async def test_list_with_prefix(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("_test:prefix_a:1", "a1")
    await kv.put("_test:prefix_a:2", "a2")
    await kv.put("_test:prefix_b:1", "b1")
    result = await kv.list({"prefix": "_test:prefix_a:"})
    names = [k["name"] for k in result["keys"]]
    assert len(names) == 2, f"expected 2 keys, got {len(names)}"
    assert all(n.startswith("_test:prefix_a:") for n in names), f"prefix filter failed: {names!r}"


async def test_list_with_limit_and_cursor(env):
    kv = env.KV
    await _cleanup_kv(kv)
    prefix = "_test:paginate:"
    for i in range(5):
        await kv.put(f"{prefix}{i:03d}", f"val-{i}")
    page1 = await kv.list({"prefix": prefix, "limit": 2})
    assert len(page1["keys"]) == 2, f"first page: expected 2, got {len(page1['keys'])}"
    assert not page1["list_complete"], "expected list_complete=False"
    assert page1.get("cursor") is not None, "expected cursor on first page"
    page2 = await kv.list({"prefix": prefix, "limit": 2, "cursor": page1["cursor"]})
    assert len(page2["keys"]) == 2, f"second page: expected 2, got {len(page2['keys'])}"
    page3 = await kv.list({"prefix": prefix, "limit": 2, "cursor": page2["cursor"]})
    assert len(page3["keys"]) == 1, f"third page: expected 1, got {len(page3['keys'])}"
    assert page3["list_complete"], "expected list_complete=True on last page"


async def test_list_empty_prefix(env):
    kv = env.KV
    await _cleanup_kv(kv)
    result = await kv.list({"prefix": "_test:nonexistent_prefix_xyz:"})
    assert len(result["keys"]) == 0, f"expected 0 keys, got {len(result['keys'])}"
    assert result["list_complete"]


async def test_list_with_metadata(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:list_meta"
    metadata = {"tag": "listed"}
    await kv.put(key, "has metadata", {"metadata": metadata})
    result = await kv.list({"prefix": key})
    matching = [k for k in result["keys"] if k["name"] == key]
    assert len(matching) == 1, f"expected one key, got {len(matching)}"
    assert matching[0].get("metadata") is not None, "expected metadata in list result"
    assert matching[0]["metadata"] == metadata, f"metadata mismatch: {matching[0]['metadata']!r}"


KV_TESTS = {
    "put_and_get_text": test_put_and_get_text,
    "get_nonexistent": test_get_nonexistent,
    "put_and_get_json": test_put_and_get_json,
    "put_overwrite": test_put_overwrite,
    "put_empty_value": test_put_empty_value,
    "delete": test_delete,
    "delete_nonexistent": test_delete_nonexistent,
    "put_with_metadata": test_put_with_metadata,
    "get_with_metadata_nonexistent": test_get_with_metadata_nonexistent,
    "put_with_expiration_ttl": test_put_with_expiration_ttl,
    "list_basic": test_list_basic,
    "list_with_prefix": test_list_with_prefix,
    "list_with_limit_and_cursor": test_list_with_limit_and_cursor,
    "list_empty_prefix": test_list_empty_prefix,
    "list_with_metadata": test_list_with_metadata,
}
