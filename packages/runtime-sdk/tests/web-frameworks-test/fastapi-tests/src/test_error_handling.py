"""Tests for FastAPI error handling in the Workers runtime.

Exercises HTTPException (with string and dict details, custom headers),
Pydantic validation errors (body, query, path), custom exception handlers,
and unhandled exceptions.  These are particularly relevant for Pyodide because:

- Pydantic v2 validation and error serialisation run through pydantic-core
  (compiled to WASM); subtle issues in the WASM build would surface here.
- The ASGI adapter must correctly propagate error responses, including custom
  status codes, headers, and JSON bodies through the Workers response path.
- Unhandled exceptions exercise the adapter's error branch (``asgi.py``
  ``process_request`` exception handling).
"""

import pytest
from _client import fetch, get_json, post_json, read_json

# -- HTTPException -----------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_404(fastapi_app):
    """HTTPException with status_code=404 returns the correct status and detail."""
    resp, data = await get_json(fastapi_app, "/errors/not-found")
    assert resp.status == 404
    assert data["detail"] == "Item not found"


@pytest.mark.asyncio
async def test_http_exception_dict_detail(fastapi_app):
    """HTTPException with a dict detail (FastAPI extension over Starlette)."""
    resp, data = await get_json(fastapi_app, "/errors/dict-detail")
    assert resp.status == 403
    assert isinstance(data["detail"], dict)
    assert data["detail"]["msg"] == "Access denied"
    assert data["detail"]["reason"] == "insufficient_scope"


@pytest.mark.asyncio
async def test_http_exception_custom_headers(fastapi_app):
    """HTTPException propagates custom response headers."""
    resp = await fetch(fastapi_app, "/errors/with-headers")
    assert resp.status == 401
    data = await read_json(resp)
    assert data["detail"] == "Invalid token"
    assert resp.headers.get("www-authenticate") == "Bearer"
    assert resp.headers.get("x-error-code") == "TOKEN_EXPIRED"


# -- Pydantic validation errors ----------------------------------------------


@pytest.mark.asyncio
async def test_validation_error_missing_body_fields(fastapi_app):
    """POST with an empty body for a Pydantic model returns 422."""
    resp = await post_json(fastapi_app, "/errors/validate-body", {})
    assert resp.status == 422
    data = await read_json(resp)
    assert "detail" in data
    errors = data["detail"]
    assert isinstance(errors, list)
    assert len(errors) > 0


@pytest.mark.asyncio
async def test_validation_error_wrong_body_types(fastapi_app):
    """POST with wrong types in the body returns 422 with field-level errors."""
    resp = await post_json(
        fastapi_app,
        "/errors/validate-body",
        {"name": 123, "price": "not-a-number", "quantity": "abc"},
    )
    assert resp.status == 422
    data = await read_json(resp)
    errors = data["detail"]
    assert isinstance(errors, list)
    # At least price and quantity should fail validation
    error_fields = []
    for err in errors:
        assert "loc" in err
        assert "msg" in err
        assert "type" in err
        # loc is a list like ["body", "price"]
        if len(err["loc"]) > 1:
            error_fields.append(err["loc"][-1])
    assert "price" in error_fields or "quantity" in error_fields


@pytest.mark.asyncio
async def test_validation_error_body_loc(fastapi_app):
    """Validation error loc for body fields starts with 'body'."""
    resp = await post_json(
        fastapi_app,
        "/errors/validate-body",
        {"name": "ok", "price": "bad", "quantity": 1},
    )
    assert resp.status == 422
    data = await read_json(resp)
    errors = data["detail"]
    assert any(err["loc"][0] == "body" for err in errors)


@pytest.mark.asyncio
async def test_validation_error_query_param(fastapi_app):
    """Non-integer query param triggers 422 with loc including 'query'."""
    resp, data = await get_json(fastapi_app, "/errors/validate-query?count=abc")
    assert resp.status == 422
    errors = data["detail"]
    assert isinstance(errors, list)
    assert any("query" in err["loc"] for err in errors)


@pytest.mark.asyncio
async def test_validation_error_path_param(fastapi_app):
    """Non-integer path param triggers 422 with loc including 'path'."""
    resp, data = await get_json(fastapi_app, "/errors/validate-path/not-a-number")
    assert resp.status == 422
    errors = data["detail"]
    assert isinstance(errors, list)
    assert any("path" in err["loc"] for err in errors)


@pytest.mark.asyncio
async def test_valid_body_passes(fastapi_app):
    """A valid Pydantic model body is accepted and echoed back."""
    resp = await post_json(
        fastapi_app,
        "/errors/validate-body",
        {"name": "Widget", "price": 9.99, "quantity": 5},
    )
    assert resp.status == 200
    data = await read_json(resp)
    assert data["name"] == "Widget"
    assert data["price"] == 9.99


# -- Custom exception handler ------------------------------------------------


@pytest.mark.asyncio
async def test_custom_exception_handler(fastapi_app):
    """A registered exception handler returns its custom response."""
    resp, data = await get_json(fastapi_app, "/errors/custom-exception")
    assert resp.status == 418
    assert data["error_code"] == "TEAPOT"
    assert data["detail"] == "I'm a teapot"


# -- Unhandled exception -----------------------------------------------------


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500(fastapi_app):
    """An unhandled exception in a handler results in a 500 response."""
    resp = await fetch(fastapi_app, "/errors/unhandled")
    assert resp.status == 500
