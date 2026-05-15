import json


async def _cleanup_r2(bucket):
    cursor = None
    while True:
        options = {"prefix": "_test/", "limit": 1000}
        if cursor:
            options["cursor"] = cursor
        result = await bucket.list(options)
        keys = [obj.key for obj in result.objects]
        if keys:
            await bucket.delete(keys)
        if not result.truncated:
            break
        cursor = result.cursor


async def test_put_and_get_text(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/put_get_text"
    value = "Hello from R2 binding!"
    obj = await bucket.put(key, value)
    assert obj is not None, "put returned None"
    assert obj.key == key
    assert obj.size == len(value)
    body = await bucket.get(key)
    assert body is not None, "get returned None"
    text = await body.text()
    assert text == value, f"text mismatch: {text!r}"
    assert body.bodyUsed is True


async def test_put_and_get_json(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/put_get_json"
    payload = {"message": "hello", "numbers": [1, 2, 3]}
    await bucket.put(key, json.dumps(payload), {
        "httpMetadata": {"contentType": "application/json"},
    })
    body = await bucket.get(key)
    assert body is not None, "get returned None"
    parsed = await body.json()
    assert parsed == payload, f"json mismatch: {parsed!r}"


async def test_put_with_http_metadata(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/http_meta"
    await bucket.put(key, "metadata test", {
        "httpMetadata": {
            "contentType": "text/plain",
            "contentLanguage": "en-US",
            "contentDisposition": "inline",
            "cacheControl": "max-age=3600",
        },
    })
    head = await bucket.head(key)
    assert head is not None, "head returned None"
    meta = head.httpMetadata
    assert meta.contentType == "text/plain"
    assert meta.contentLanguage == "en-US"
    assert meta.contentDisposition == "inline"
    assert meta.cacheControl == "max-age=3600"


async def test_put_with_custom_metadata(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/custom_meta"
    custom = {"author": "test-suite", "version": "1.0"}
    await bucket.put(key, "custom metadata test", {"customMetadata": custom})
    head = await bucket.head(key)
    assert head is not None, "head returned None"
    assert head.customMetadata == custom, f"custom metadata mismatch: {head.customMetadata!r}"


async def test_head_object(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/head_obj"
    content = "head test content"
    await bucket.put(key, content)
    head = await bucket.head(key)
    assert head is not None, "head returned None"
    assert head.key == key
    assert head.size == len(content)
    assert head.etag is not None
    assert head.httpEtag is not None
    assert head.version is not None


async def test_get_nonexistent(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    result = await bucket.get("_test/does_not_exist_12345")
    assert result is None, f"expected None, got {result!r}"


async def test_head_nonexistent(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    result = await bucket.head("_test/does_not_exist_12345")
    assert result is None, f"expected None, got {result!r}"


async def test_delete_single(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/delete_single"
    await bucket.put(key, "to be deleted")
    assert (await bucket.head(key)) is not None, "put failed"
    await bucket.delete(key)
    result = await bucket.head(key)
    assert result is None, "object still exists after delete"


async def test_delete_multiple(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    keys = ["_test/del_multi_1", "_test/del_multi_2", "_test/del_multi_3"]
    for key in keys:
        await bucket.put(key, f"content for {key}")
    await bucket.delete(keys)
    for key in keys:
        result = await bucket.head(key)
        assert result is None, f"{key} still exists after batch delete"


async def test_list_basic(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    for i in range(3):
        await bucket.put(f"_test/list_basic/{i}", f"val-{i}")
    result = await bucket.list({"prefix": "_test/list_basic/"})
    objects = result.objects
    keys = [obj.key for obj in objects]
    assert len(objects) >= 3, f"expected >= 3 objects, got {len(objects)}"
    for i in range(3):
        assert f"_test/list_basic/{i}" in keys, f"missing key {i}"


async def test_list_with_prefix(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    await bucket.put("_test/prefix_a/1", "a1")
    await bucket.put("_test/prefix_a/2", "a2")
    await bucket.put("_test/prefix_b/1", "b1")
    result = await bucket.list({"prefix": "_test/prefix_a/"})
    keys = [obj.key for obj in result.objects]
    assert len(keys) == 2, f"expected 2 objects, got {len(keys)}"
    assert all(k.startswith("_test/prefix_a/") for k in keys), f"prefix filter failed: {keys!r}"


async def test_list_with_limit_and_cursor(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    prefix = "_test/paginate/"
    for i in range(5):
        await bucket.put(f"{prefix}{i:03d}", f"val-{i}")
    page1 = await bucket.list({"prefix": prefix, "limit": 2})
    assert len(page1.objects) == 2, f"first page: expected 2, got {len(page1.objects)}"
    assert page1.truncated, "expected truncated=True"
    assert page1.cursor is not None, "expected cursor"
    page2 = await bucket.list({"prefix": prefix, "limit": 2, "cursor": page1.cursor})
    assert len(page2.objects) == 2, f"second page: expected 2, got {len(page2.objects)}"
    page3 = await bucket.list({"prefix": prefix, "limit": 2, "cursor": page2.cursor})
    assert len(page3.objects) == 1, f"third page: expected 1, got {len(page3.objects)}"
    assert not page3.truncated, "expected truncated=False on last page"


async def test_list_with_delimiter(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    await bucket.put("_test/delim/dir1/file1", "f1")
    await bucket.put("_test/delim/dir1/file2", "f2")
    await bucket.put("_test/delim/dir2/file1", "f1")
    await bucket.put("_test/delim/root_file", "rf")
    result = await bucket.list({"prefix": "_test/delim/", "delimiter": "/"})
    object_keys = [obj.key for obj in result.objects]
    prefixes = result.delimitedPrefixes
    assert "_test/delim/root_file" in object_keys, f"missing root file: {object_keys!r}"
    assert "_test/delim/dir1/" in prefixes, f"missing dir1 prefix: {prefixes!r}"
    assert "_test/delim/dir2/" in prefixes, f"missing dir2 prefix: {prefixes!r}"


async def test_overwrite_object(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/overwrite"
    await bucket.put(key, "version1")
    first = await (await bucket.get(key)).text()
    await bucket.put(key, "version2")
    second = await (await bucket.get(key)).text()
    assert first == "version1"
    assert second == "version2"


async def test_put_empty_body(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/empty_body"
    obj = await bucket.put(key, None)
    assert obj is not None, "put returned None"
    assert obj.size == 0, f"expected size 0, got {obj.size}"
    body = await bucket.get(key)
    assert body is not None, "get returned None"
    text = await body.text()
    assert text == "", f"expected empty string, got {text!r}"


async def test_get_range_offset_length(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/range_test"
    content = "0123456789ABCDEF"
    await bucket.put(key, content)
    body = await bucket.get(key, {"range": {"offset": 4, "length": 6}})
    assert body is not None, "get returned None"
    text = await body.text()
    assert text == "456789", f"range mismatch: {text!r}"


async def test_get_range_suffix(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/range_suffix"
    content = "0123456789ABCDEF"
    await bucket.put(key, content)
    body = await bucket.get(key, {"range": {"suffix": 4}})
    assert body is not None, "get returned None"
    text = await body.text()
    assert text == "CDEF", f"suffix mismatch: {text!r}"


async def test_r2object_properties(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/props"
    content = "properties test"
    obj = await bucket.put(key, content, {
        "httpMetadata": {"contentType": "text/plain"},
        "customMetadata": {"foo": "bar"},
    })
    assert obj.key == key
    assert obj.size == len(content)
    assert isinstance(obj.version, str) and obj.version
    assert isinstance(obj.etag, str) and obj.etag
    assert isinstance(obj.httpEtag, str) and obj.httpEtag.startswith('"')
    assert obj.uploaded is not None
    assert obj.storageClass in ("Standard", "InfrequentAccess", "")
    head = await bucket.head(key)
    assert head.httpMetadata.contentType == "text/plain"
    assert head.customMetadata == {"foo": "bar"}


async def test_multipart_upload(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/multipart"
    upload = await bucket.createMultipartUpload(key, {
        "customMetadata": {"uploadType": "multipart_test"},
    })
    assert upload.key == key
    assert isinstance(upload.uploadId, str) and upload.uploadId
    five_mb = 5 * 1024 * 1024
    part1_data = "A" * five_mb
    part2_data = "B" * 512
    p1 = await upload.uploadPart(1, part1_data)
    p2 = await upload.uploadPart(2, part2_data)
    assert p1.partNumber == 1
    assert p2.partNumber == 2
    assert isinstance(p1.etag, str) and p1.etag
    obj = await upload.complete([p1, p2])
    assert obj.key == key
    assert obj.size == len(part1_data) + len(part2_data)
    body = await bucket.get(key)
    assert body is not None
    text = await body.text()
    assert text == part1_data + part2_data, "multipart content mismatch"


async def test_multipart_abort(env):
    bucket = env.BUCKET
    await _cleanup_r2(bucket)
    key = "_test/multipart_abort"
    upload = await bucket.createMultipartUpload(key)
    assert upload.key == key
    await upload.uploadPart(1, "data to be aborted")
    await upload.abort()
    result = await bucket.head(key)
    assert result is None, "object should not exist after abort"


R2_TESTS = {
    "put_and_get_text": test_put_and_get_text,
    "put_and_get_json": test_put_and_get_json,
    "put_with_http_metadata": test_put_with_http_metadata,
    "put_with_custom_metadata": test_put_with_custom_metadata,
    "head_object": test_head_object,
    "get_nonexistent": test_get_nonexistent,
    "head_nonexistent": test_head_nonexistent,
    "delete_single": test_delete_single,
    "delete_multiple": test_delete_multiple,
    "list_basic": test_list_basic,
    "list_with_prefix": test_list_with_prefix,
    "list_with_limit_and_cursor": test_list_with_limit_and_cursor,
    "list_with_delimiter": test_list_with_delimiter,
    "overwrite_object": test_overwrite_object,
    "put_empty_body": test_put_empty_body,
    "get_range_offset_length": test_get_range_offset_length,
    "get_range_suffix": test_get_range_suffix,
    "r2object_properties": test_r2object_properties,
    "multipart_upload": test_multipart_upload,
    "multipart_abort": test_multipart_abort,
}
