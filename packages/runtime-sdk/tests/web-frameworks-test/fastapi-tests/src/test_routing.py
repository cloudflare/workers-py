"""Tests for FastAPI core routing in the Workers runtime.

Exercises path parameter coercion (int, float, Enum, rest-of-path), query
parameter handling (optional, default, list, required, validation), multiple
HTTP methods (PUT, DELETE, PATCH), and APIRouter with prefix.

These are relevant for Pyodide/Workers because:

- Path and query parameter coercion flows through Pydantic v2's
  ``pydantic-core`` (Rust compiled to WASM).  Subtle WASM issues in numeric
  parsing, Enum handling, or constraint validation would surface here.
- The ``{file_path:path}`` converter tests that the ASGI adapter correctly
  percent-decodes ``scope["path"]`` while preserving slashes (see
  ``request_to_scope`` in ``asgi.py``).
- PUT/DELETE/PATCH verify that the adapter propagates ``scope["method"]``
  correctly for all HTTP verbs, not just GET/POST.
- APIRouter with prefix tests Starlette's route composition which is pure
  Python but exercises the full routing table lookup inside the runtime.
"""

import pytest
from _client import fetch, get_json, read_json
from worker import Default

from workers import WorkerEntrypoint


def test_asgi_entrypoint_factory():
    assert Default.__name__ == "Default"
    assert issubclass(Default, WorkerEntrypoint)


# -- Path parameters ---------------------------------------------------------


@pytest.mark.asyncio
async def test_path_param_int(fastapi_app):
    """An integer path parameter is coerced and returned as int."""
    resp, data = await get_json(fastapi_app, "/routing/path-int/42")
    assert resp.status == 200
    assert data["item_id"] == 42
    assert data["type"] == "int"


@pytest.mark.asyncio
async def test_path_param_int_invalid(fastapi_app):
    """A non-integer value for an int path parameter returns 422."""
    resp, data = await get_json(fastapi_app, "/routing/path-int/not-a-number")
    assert resp.status == 422


@pytest.mark.asyncio
async def test_path_param_float(fastapi_app):
    """A float path parameter is coerced correctly."""
    resp, data = await get_json(fastapi_app, "/routing/path-float/3.14")
    assert resp.status == 200
    assert abs(data["value"] - 3.14) < 0.001
    assert data["type"] == "float"


@pytest.mark.asyncio
async def test_path_param_enum(fastapi_app):
    """A str Enum path parameter is validated and its value returned."""
    resp, data = await get_json(fastapi_app, "/routing/path-enum/green")
    assert resp.status == 200
    assert data["colour"] == "green"


@pytest.mark.asyncio
async def test_path_param_enum_invalid(fastapi_app):
    """An invalid Enum value returns 422."""
    resp, data = await get_json(fastapi_app, "/routing/path-enum/yellow")
    assert resp.status == 422


@pytest.mark.asyncio
async def test_path_param_rest(fastapi_app):
    """A {file_path:path} parameter captures slashes."""
    resp, data = await get_json(fastapi_app, "/routing/path-rest/a/b/c.txt")
    assert resp.status == 200
    assert data["file_path"] == "a/b/c.txt"


# -- Query parameters --------------------------------------------------------


@pytest.mark.asyncio
async def test_query_param_optional_present(fastapi_app):
    """An optional query parameter is returned when present."""
    resp, data = await get_json(fastapi_app, "/routing/query?q=hello&skip=5&limit=20")
    assert resp.status == 200
    assert data["q"] == "hello"
    assert data["skip"] == 5
    assert data["limit"] == 20


@pytest.mark.asyncio
async def test_query_param_optional_absent(fastapi_app):
    """Absent optional query parameters use their defaults."""
    resp, data = await get_json(fastapi_app, "/routing/query")
    assert resp.status == 200
    assert data["q"] is None
    assert data["skip"] == 0
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_query_param_required_missing(fastapi_app):
    """A required query parameter missing from the request returns 422."""
    resp, data = await get_json(fastapi_app, "/routing/query-required")
    assert resp.status == 422


@pytest.mark.asyncio
async def test_query_param_required_present(fastapi_app):
    """A required query parameter is accepted when provided."""
    resp, data = await get_json(fastapi_app, "/routing/query-required?name=Alice")
    assert resp.status == 200
    assert data["name"] == "Alice"


@pytest.mark.asyncio
async def test_query_param_list(fastapi_app):
    """Multi-value query parameters are collected into a list."""
    resp, data = await get_json(fastapi_app, "/routing/query-list?tags=a&tags=b&tags=c")
    assert resp.status == 200
    assert data["tags"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_query_param_list_empty(fastapi_app):
    """An absent list query parameter returns the empty default."""
    resp, data = await get_json(fastapi_app, "/routing/query-list")
    assert resp.status == 200
    assert data["tags"] == []


@pytest.mark.asyncio
async def test_query_param_validation_too_short(fastapi_app):
    """A query param shorter than min_length returns 422."""
    resp, data = await get_json(fastapi_app, "/routing/query-validation?q=ab")
    assert resp.status == 422


@pytest.mark.asyncio
async def test_query_param_validation_ok(fastapi_app):
    """A query param within length constraints is accepted."""
    resp, data = await get_json(fastapi_app, "/routing/query-validation?q=hello")
    assert resp.status == 200
    assert data["q"] == "hello"


# -- HTTP methods ------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_method(fastapi_app):
    """PUT with path param and JSON body works."""
    resp = await fetch(
        fastapi_app,
        "/routing/put-item/7",
        method="PUT",
        headers={"Content-Type": "application/json"},
        body='{"name": "Widget", "price": 9.99, "quantity": 1}',
    )
    assert resp.status == 200
    data = await read_json(resp)
    assert data["item_id"] == 7
    assert data["name"] == "Widget"


@pytest.mark.asyncio
async def test_delete_method(fastapi_app):
    """DELETE method returns the expected response."""
    resp = await fetch(fastapi_app, "/routing/delete-item/3", method="DELETE")
    assert resp.status == 200
    data = await read_json(resp)
    assert data["deleted"] == 3


@pytest.mark.asyncio
async def test_patch_method(fastapi_app):
    """PATCH method returns the expected response."""
    resp = await fetch(fastapi_app, "/routing/patch-item/5", method="PATCH")
    assert resp.status == 200
    data = await read_json(resp)
    assert data["patched"] == 5


# -- APIRouter with prefix ---------------------------------------------------


@pytest.mark.asyncio
async def test_api_router_with_prefix(fastapi_app):
    """A route registered via APIRouter(prefix=...) is reachable."""
    resp, data = await get_json(fastapi_app, "/routing/v1/info")
    assert resp.status == 200
    assert data["version"] == 1
    assert data["status"] == "ok"
