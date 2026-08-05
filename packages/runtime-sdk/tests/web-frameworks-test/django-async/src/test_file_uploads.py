import pytest
from _client import build_multipart, get_json


def _normalize_files_payload(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "files" in payload:
            return payload["files"]
        return [payload]
    return []


@pytest.mark.asyncio
async def test_single_file_upload(django_asgi_app):
    for filename, content, expected in (
        ("test.txt", "hello", {"name": "test.txt", "content": "hello", "size": 5}),
        (
            "meta.txt",
            "metadata",
            {"name": "meta.txt", "size": len("metadata")},
        ),
        ("content.txt", "known content", {"content": "known content"}),
    ):
        body, content_type = build_multipart([("file", filename, content)])
        response, payload = await get_json(
            django_asgi_app,
            "/upload/single/",
            method="POST",
            headers={"Content-Type": content_type},
            body=body,
        )

        assert response.status == 200
        for key, value in expected.items():
            assert payload[key] == value


@pytest.mark.asyncio
async def test_multiple_file_upload(django_asgi_app):
    body, content_type = build_multipart(
        [("file", "one.txt", "one"), ("file", "two.txt", "two")]
    )
    response, payload = await get_json(
        django_asgi_app,
        "/upload/multiple/",
        method="POST",
        headers={"Content-Type": content_type},
        body=body,
    )
    files = _normalize_files_payload(payload)

    assert response.status == 200
    assert len(files) == 2
    assert [file_info["name"] for file_info in files] == ["one.txt", "two.txt"]
    assert all(file_info["size"] > 0 for file_info in files)
