"""Binary I/O tests across FastAPI, Pyodide, and workerd."""

import hashlib

import pytest
from _client import build_multipart_bytes, fetch, read_json


@pytest.mark.asyncio
async def test_upload_spills_binary_file_to_virtual_disk(fastapi_app):
    """UploadFile remains correct after SpooledTemporaryFile rolls to disk."""
    payload = bytes(range(256)) * 5120  # 1.25 MiB, above Starlette's 1 MiB limit.
    body, content_type = build_multipart_bytes(
        [("file", "binary.dat", payload)], boundary="----SpoolBoundary"
    )

    resp = await fetch(
        fastapi_app,
        "/platform/upload-spooled",
        method="POST",
        headers={"Content-Type": content_type},
        body=body,
    )
    assert resp.status == 200
    data = await read_json(resp)
    assert data == {
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "reread_matches": True,
        "rolled_to_disk": True,
    }
