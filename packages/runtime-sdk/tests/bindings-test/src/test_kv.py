import json

import pytest


async def _cleanup_kv(kv):
    options = {"prefix": "_test:", "limit": 1000}
    while True:
        result = await kv.list(options)
        for key_entry in result["keys"]:
            await kv.delete(key_entry["name"])
        if result["list_complete"]:
            break
        options["cursor"] = result.get("cursor")


@pytest.mark.asyncio
async def test_put_and_get_text(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:put_get_text"
    value = "hello from KV"
    await kv.put(key, value)
    result = await kv.get(key)
    assert result == value


@pytest.mark.asyncio
async def test_get_nonexistent(env):
    kv = env.KV
    await _cleanup_kv(kv)
    result = await kv.get("_test:does_not_exist_12345")
    assert result is None


@pytest.mark.asyncio
async def test_put_and_get_json(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:put_get_json"
    payload = {"message": "hello", "numbers": [1, 2, 3]}
    await kv.put(key, json.dumps(payload))
    result = await kv.get(key, "json")
    assert isinstance(result, dict)
    assert result == payload


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_put_empty_value(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:empty_value"
    await kv.put(key, "")
    result = await kv.get(key)
    assert result == ""


@pytest.mark.asyncio
async def test_delete(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:delete"
    await kv.put(key, "to be deleted")
    assert await kv.get(key) == "to be deleted"
    await kv.delete(key)
    result = await kv.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.delete("_test:does_not_exist_67890")


@pytest.mark.asyncio
async def test_put_with_metadata(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:metadata"
    metadata = {"author": "test-suite", "version": "1.0"}
    await kv.put(key, "metadata test", metadata=metadata)
    result = await kv.getWithMetadata(key)
    assert result["value"] == "metadata test"
    assert result["metadata"] is not None, "expected metadata"
    assert result["metadata"] == metadata


@pytest.mark.asyncio
async def test_get_with_metadata_nonexistent(env):
    kv = env.KV
    await _cleanup_kv(kv)
    result = await kv.getWithMetadata("_test:does_not_exist_meta")
    assert result["value"] is None
    assert result["metadata"] is None


@pytest.mark.asyncio
async def test_put_with_expiration_ttl(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:expiration_ttl"
    await kv.put(key, "expires soon", expirationTtl=60)
    result = await kv.get(key)
    assert result == "expires soon"
    listed = await kv.list(prefix=key)
    matching = [k for k in listed["keys"] if k["name"] == key]
    assert len(matching) == 1, "key not found in list"
    assert matching[0].get("expiration") is not None, "expected expiration to be set"


@pytest.mark.asyncio
async def test_list_basic(env):
    kv = env.KV
    await _cleanup_kv(kv)
    for i in range(3):
        await kv.put(f"_test:list_basic:{i}", f"val-{i}")
    result = await kv.list(prefix="_test:list_basic:")
    keys = result["keys"]
    names = [k["name"] for k in keys]
    assert len(keys) >= 3
    assert result["list_complete"]
    for i in range(3):
        assert f"_test:list_basic:{i}" in names, f"missing key {i}"


@pytest.mark.asyncio
async def test_list_with_prefix(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("_test:prefix_a:1", "a1")
    await kv.put("_test:prefix_a:2", "a2")
    await kv.put("_test:prefix_b:1", "b1")
    result = await kv.list(prefix="_test:prefix_a:")
    names = [k["name"] for k in result["keys"]]
    assert len(names) == 2
    assert all(n.startswith("_test:prefix_a:") for n in names), (
        f"prefix filter failed: {names!r}"
    )


@pytest.mark.asyncio
async def test_list_with_limit_and_cursor(env):
    kv = env.KV
    await _cleanup_kv(kv)
    prefix = "_test:paginate:"
    for i in range(5):
        await kv.put(f"{prefix}{i:03d}", f"val-{i}")
    page1 = await kv.list(prefix=prefix, limit=2)
    assert len(page1["keys"]) == 2
    assert not page1["list_complete"], "expected list_complete=False"
    assert page1.get("cursor") is not None, "expected cursor on first page"
    page2 = await kv.list(prefix=prefix, limit=2, cursor=page1["cursor"])
    assert len(page2["keys"]) == 2
    page3 = await kv.list(prefix=prefix, limit=2, cursor=page2["cursor"])
    assert len(page3["keys"]) == 1
    assert page3["list_complete"], "expected list_complete=True on last page"


@pytest.mark.asyncio
async def test_list_empty_prefix(env):
    kv = env.KV
    await _cleanup_kv(kv)
    result = await kv.list(prefix="_test:nonexistent_prefix_xyz:")
    assert len(result["keys"]) == 0
    assert result["list_complete"]


@pytest.mark.asyncio
async def test_list_with_metadata(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:list_meta"
    metadata = {"tag": "listed"}
    await kv.put(key, "has metadata", metadata=metadata)
    result = await kv.list(prefix=key)
    matching = [k for k in result["keys"] if k["name"] == key]
    assert len(matching) == 1
    assert matching[0].get("metadata") is not None, "expected metadata in list result"
    assert matching[0]["metadata"] == metadata, (
        f"metadata mismatch: {matching[0]['metadata']!r}"
    )


@pytest.mark.asyncio
async def test_get_with_metadata_has_metadata(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:gwm_meta"
    metadata = {"env": "test", "version": 2}
    await kv.put(key, "value with meta", metadata=metadata)
    result = await kv.getWithMetadata(key)
    assert result["value"] == "value with meta"
    assert result["metadata"] == metadata


@pytest.mark.asyncio
async def test_get_type_as_options_dict(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:get_type_opts"
    payload = {"x": "hello"}
    await kv.put(key, json.dumps(payload))
    result = await kv.get(key, type="json")
    assert isinstance(result, dict)
    assert result["x"] == "hello"


@pytest.mark.asyncio
async def test_get_arraybuffer(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:get_ab"
    await kv.put(key, "binary test data")
    result = await kv.get(key, "arrayBuffer")
    assert result is not None
    assert isinstance(result, memoryview)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_get_multiple_keys(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("_test:multi:a", "val-a")
    await kv.put("_test:multi:b", "val-b")
    result = await kv.get(["_test:multi:a", "_test:multi:b", "_test:multi:nonexistent"])
    assert isinstance(result, dict)
    assert result.get("_test:multi:a") == "val-a"
    assert result.get("_test:multi:b") == "val-b"
    assert result.get("_test:multi:nonexistent") is None


@pytest.mark.asyncio
async def test_get_multiple_keys_json(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("_test:multi_json:a", json.dumps({"val": "a"}))
    await kv.put("_test:multi_json:b", json.dumps({"val": "b"}))
    result = await kv.get(["_test:multi_json:a", "_test:multi_json:b"], "json")
    assert isinstance(result, dict)
    assert result["_test:multi_json:a"]["val"] == "a"
    assert result["_test:multi_json:b"]["val"] == "b"


@pytest.mark.asyncio
async def test_put_dict_expiration_ttl(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:dict_ttl"
    await kv.put(key, "dict ttl", {"expirationTtl": 60})
    result = await kv.get(key)
    assert result == "dict ttl"
    listed = await kv.list({"prefix": key})
    matching = [k for k in listed["keys"] if k["name"] == key]
    assert len(matching) == 1
    assert matching[0].get("expiration") is not None


@pytest.mark.asyncio
async def test_put_dict_metadata(env):
    kv = env.KV
    await _cleanup_kv(kv)
    key = "_test:dict_meta"
    await kv.put(key, "dict meta", {"metadata": {"source": "dict"}})
    result = await kv.getWithMetadata(key)
    assert result["value"] == "dict meta"
    assert result["metadata"]["source"] == "dict"


@pytest.mark.asyncio
async def test_none_options_put(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("_test:none_opts", "value", None)
    result = await kv.get("_test:none_opts")
    assert result == "value"


@pytest.mark.asyncio
async def test_none_options_list(env):
    kv = env.KV
    await _cleanup_kv(kv)
    await kv.put("_test:none_list", "val")
    result = await kv.list(None)
    assert result["list_complete"] is True


@pytest.mark.asyncio
async def test_binding_not_iterable(env):
    kv = env.KV
    with pytest.raises(TypeError, match="KvNamespace.*is not iterable"):
        for _ in kv:
            pass


@pytest.mark.asyncio
async def test_binding_no_len(env):
    kv = env.KV
    with pytest.raises(TypeError, match="KvNamespace.*has no len"):
        len(kv)
