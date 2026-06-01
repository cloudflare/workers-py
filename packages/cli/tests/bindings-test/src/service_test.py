async def test_identity_primitives(env):
    svc = env.SERVICE_BINDING
    assert await svc.identity("hello") == "hello"
    assert await svc.identity(42) == 42
    assert await svc.identity(3.14) - 3.14 < 0.001
    assert await svc.identity(True) is True
    assert await svc.identity(False) is False
    assert await svc.identity(None) is None


async def test_identity_dict(env):
    data = {"key": "value", "number": 42, "flag": True}
    result = await env.SERVICE_BINDING.identity(data)
    assert result["key"] == "value"
    assert result["number"] == 42
    assert result["flag"] is True


async def test_identity_list(env):
    data = [1, "two", 3.0, True, None]
    result = await env.SERVICE_BINDING.identity(data)
    assert result == data


async def test_identity_nested_dict(env):
    data = {
        "level1": {
            "level2": {"value": "deep"},
            "list": [1, 2, 3],
        },
        "top": "shallow",
    }
    result = await env.SERVICE_BINDING.identity(data)
    assert result["top"] == "shallow"
    assert result["level1"]["level2"]["value"] == "deep"
    assert result["level1"]["list"] == [1, 2, 3]


async def test_identity_list_of_dicts(env):
    data = [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]
    result = await env.SERVICE_BINDING.identity(data)
    assert result[0]["name"] == "alice"
    assert result[1]["age"] == 25


async def test_identity_empty_collections(env):
    svc = env.SERVICE_BINDING
    assert await svc.identity({}) == {}
    assert await svc.identity([]) == []
    assert await svc.identity("") == ""


async def test_rpc_multiple_args(env):
    result = await env.SERVICE_BINDING.add(10, 32)
    assert result == 42


async def test_rpc_transform_dict(env):
    result = await env.SERVICE_BINDING.transform_dict({"original": True})
    assert result["original"] is True
    assert result["added_by_service"] is True


async def test_rpc_multi_args_mixed_types(env):
    result = await env.SERVICE_BINDING.multi_args(
        "test_name", 42, ["a", "b", "c"], {"meta_key": "meta_value"}
    )
    assert result["name"] == "test_name"
    assert result["count"] == 42
    assert result["item_count"] == 3
    assert "meta_key" in result["meta_keys"]


async def test_rpc_get_nested_return(env):
    result = await env.SERVICE_BINDING.get_nested()
    assert result["top"] == "shallow"
    assert result["level1"]["level2"]["value"] == "deep"
    assert result["level1"]["list"] == [1, 2, 3]


async def test_rpc_default_values_all_provided(env):
    result = await env.SERVICE_BINDING.with_defaults("req", "custom", 5)
    assert result["required"] == "req"
    assert result["optional"] == "custom"
    assert result["count"] == 5


async def test_rpc_default_values_partial(env):
    result = await env.SERVICE_BINDING.with_defaults("req")
    assert result["required"] == "req"
    assert result["optional"] == "default_val"
    assert result["count"] == 0


async def test_unsupported_tuple_raises(env):
    error_msg = None
    try:
        await env.SERVICE_BINDING.identity((1, 2, 3))
    except TypeError as e:
        error_msg = str(e)
    assert error_msg is not None, "expected TypeError for tuple"
    assert "cannot be sent over RPC" in error_msg, f"unexpected error: {error_msg}"


async def test_unsupported_class_instance_raises(env):
    error_msg = None
    try:
        class Custom:
            def __init__(self):
                self.x = 42
        await env.SERVICE_BINDING.identity(Custom())
    except Exception as e:
        error_msg = str(e)
    assert error_msg is not None, "expected error for custom class"
    assert "DataCloneError" in error_msg or "could not be cloned" in error_msg, (
        f"expected DataCloneError, got: {error_msg}"
    )


async def test_fetch_get(env):
    resp = await env.SERVICE_BINDING.fetch("http://service/inspect")
    data = await resp.json()
    assert data["method"] == "GET", f"expected GET, got {data['method']}"


async def test_fetch_post_body(env):
    resp = await env.SERVICE_BINDING.fetch(
        "http://service/inspect",
        method="POST",
        body="hello body",
    )
    data = await resp.json()
    assert data["method"] == "POST", f"expected POST, got {data['method']}"
    assert data["body"] == "hello body", f"expected 'hello body', got {data['body']!r}"


async def test_fetch_post_json(env):
    import json
    payload = json.dumps({"key": "value"})
    resp = await env.SERVICE_BINDING.fetch(
        "http://service/inspect",
        method="POST",
        body=payload,
        headers={"Content-Type": "application/json"},
    )
    data = await resp.json()
    assert data["method"] == "POST"
    assert data["content_type"] == "application/json"
    assert json.loads(data["body"]) == {"key": "value"}


SERVICE_TESTS = {
    "identity_primitives": test_identity_primitives,
    "identity_dict": test_identity_dict,
    "identity_list": test_identity_list,
    "identity_nested_dict": test_identity_nested_dict,
    "identity_list_of_dicts": test_identity_list_of_dicts,
    "identity_empty_collections": test_identity_empty_collections,
    "rpc_multiple_args": test_rpc_multiple_args,
    "rpc_transform_dict": test_rpc_transform_dict,
    "rpc_multi_args_mixed_types": test_rpc_multi_args_mixed_types,
    "rpc_get_nested_return": test_rpc_get_nested_return,
    "rpc_default_values_all_provided": test_rpc_default_values_all_provided,
    "rpc_default_values_partial": test_rpc_default_values_partial,
    "unsupported_tuple_raises": test_unsupported_tuple_raises,
    "unsupported_class_instance_raises": test_unsupported_class_instance_raises,
    "fetch_get": test_fetch_get,
    "fetch_post_body": test_fetch_post_body,
    "fetch_post_json": test_fetch_post_json,
}
