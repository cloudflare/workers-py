import asyncio
import enum
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import HTTPException
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.responses import Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pyodide.webloop import WebLoop
from starlette.background import BackgroundTask

import asgi
from workers import Response, WorkerEntrypoint


async def _noop(*args):
    pass


WebLoop.shutdown_asyncgens = _noop
WebLoop.shutdown_default_executor = _noop

STATIC_DIR = Path(__file__).parent / "static"


class PlatformResource:
    def __init__(self):
        self.closed = False


@asynccontextmanager
async def _platform_lifespan(_app):
    resource = PlatformResource()
    try:
        yield {"platform_resource": resource}
    finally:
        resource.closed = True


app = FastAPI(lifespan=_platform_lifespan)

# --------------------------------------------------------------------------- #
# Shared mutable state used to verify side-effects (e.g. background tasks).
# --------------------------------------------------------------------------- #
_side_effects: dict = {}


# --------------------------------------------------------------------------- #
# Routes exercising the anyio.to_thread.run_sync patch
# --------------------------------------------------------------------------- #


@app.get("/api/hello")
async def api_hello():
    return {"message": "Hello from FastAPI"}


@app.get("/health")
async def health():
    return {"ok": True}


# -- sync route handler (dispatched via run_in_threadpool) -------------------
@app.get("/sync/hello")
def sync_hello():
    """A plain `def` (non-async) route handler."""
    return {"message": "sync hello"}


@app.post("/sync/echo")
def sync_echo(request: Request):
    """Sync POST handler that reads the body."""
    # request.body() is async; the sync handler can still return a dict.
    return {"method": request.method}


# -- sync dependency ---------------------------------------------------------
def _get_greeting():
    """A plain `def` dependency (not async)."""
    return "hello from sync dep"


@app.get("/sync/dep")
async def sync_dep_route(greeting: str = Depends(_get_greeting)):
    """Async handler with a sync dependency."""
    return {"greeting": greeting}


# -- sync background task ----------------------------------------------------
def _bg_task():
    """Sync function executed as a BackgroundTask."""
    _side_effects["bg_ran"] = True


@app.get("/sync/background/run")
async def sync_background_run():
    """Fire a sync background task and return immediately."""
    _side_effects.pop("bg_ran", None)
    return JSONResponse({"submitted": True}, background=BackgroundTask(_bg_task))


@app.get("/sync/background/check")
async def sync_background_check():
    """Return whether the background task has executed."""
    return {"bg_ran": _side_effects.get("bg_ran", False)}


# -- sync iterator streaming response ---------------------------------------
def _sync_chunks():
    """A plain generator (not async) yielding text chunks."""
    for i in range(5):
        yield f"chunk-{i}\n"


@app.get("/sync/stream")
async def sync_stream():
    """StreamingResponse backed by a sync iterator."""
    return StreamingResponse(_sync_chunks(), media_type="text/plain")


# -- file upload (UploadFile.read/write/seek go through run_in_threadpool) ---
@app.post("/upload/single")
async def upload_single(file: UploadFile = File(...)):  # noqa: B008
    """Accept a single file upload and echo its metadata + content."""
    content = await file.read()
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "text": content.decode(errors="replace"),
    }


@app.post("/upload/multiple")
async def upload_multiple(files: list[UploadFile] = File(...)):  # noqa: B008
    """Accept multiple file uploads and echo their metadata."""
    result = []
    for f in files:
        data = await f.read()
        result.append({"filename": f.filename, "size": len(data)})
    return result


# --------------------------------------------------------------------------- #
# Error handling routes
# --------------------------------------------------------------------------- #


class AppError(Exception):
    """Custom application error for testing exception handlers."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=418,
        content={"error_code": exc.code, "detail": exc.detail},
    )


class ItemModel(BaseModel):
    name: str
    price: float
    quantity: int


@app.get("/errors/not-found")
async def error_not_found():
    """Raise HTTPException with 404."""
    raise HTTPException(status_code=404, detail="Item not found")


@app.get("/errors/dict-detail")
async def error_dict_detail():
    """Raise HTTPException with a dict detail (FastAPI extension)."""
    raise HTTPException(
        status_code=403,
        detail={"msg": "Access denied", "reason": "insufficient_scope"},
    )


@app.get("/errors/with-headers")
async def error_with_headers():
    """Raise HTTPException with custom response headers."""
    raise HTTPException(
        status_code=401,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer", "X-Error-Code": "TOKEN_EXPIRED"},
    )


@app.post("/errors/validate-body")
async def error_validate_body(item: ItemModel):
    """Accept a Pydantic model; invalid input triggers 422."""
    return {"name": item.name, "price": item.price}


@app.get("/errors/validate-query")
async def error_validate_query(count: int):
    """Require an integer query param; non-integer triggers 422."""
    return {"count": count}


@app.get("/errors/validate-path/{item_id}")
async def error_validate_path(item_id: int):
    """Require an integer path param; non-integer triggers 422."""
    return {"item_id": item_id}


@app.get("/errors/custom-exception")
async def error_custom_exception():
    """Raise a custom exception handled by a registered handler."""
    raise AppError(code="TEAPOT", detail="I'm a teapot")


@app.get("/errors/unhandled")
async def error_unhandled():
    """Raise an unhandled ValueError to trigger a 500."""
    raise ValueError("something went wrong internally")


# --------------------------------------------------------------------------- #
# Response types and request object routes
# --------------------------------------------------------------------------- #


@app.get("/responses/json-201", status_code=201)
async def response_json_201():
    """Return JSON with a custom 201 status code."""
    return {"created": True, "id": 42}


@app.get("/responses/html")
async def response_html():
    """Return an HTMLResponse."""
    return HTMLResponse("<h1>Hello Workers</h1>")


@app.get("/responses/plain-text")
async def response_plain_text():
    """Return a PlainTextResponse."""
    return PlainTextResponse("just plain text")


@app.get("/responses/redirect")
async def response_redirect():
    """Return a RedirectResponse to /api/hello."""
    return RedirectResponse("/api/hello")


async def _async_chunks():
    """An async generator yielding text chunks."""
    for i in range(5):
        yield f"async-chunk-{i}\n"


@app.get("/responses/async-stream")
async def response_async_stream():
    """StreamingResponse backed by an async generator."""
    return StreamingResponse(_async_chunks(), media_type="text/plain")


@app.get("/responses/set-cookie")
async def response_set_cookie():
    """Return a response that sets a cookie."""
    resp = JSONResponse({"cookie": "set"})
    resp.set_cookie(key="session_id", value="abc123", httponly=True, secure=True)
    return resp


@app.get("/responses/read-cookie")
async def response_read_cookie(session_id: str | None = Cookie(default=None)):  # noqa: B008
    """Read a cookie from the request."""
    return {"session_id": session_id}


@app.get("/responses/read-header")
async def response_read_header(
    x_custom_token: str | None = Header(default=None),  # noqa: B008
):
    """Read a custom header from the request."""
    return {"x_custom_token": x_custom_token}


@app.get("/responses/request-url")
async def response_request_url(request: Request):
    """Return URL components from the request object."""
    return {
        "path": request.url.path,
        "query": str(request.url.query),
        "method": request.method,
    }


@app.get("/responses/custom-headers")
async def response_custom_headers():
    """Return a response with custom headers."""
    return FastAPIResponse(
        content="ok",
        media_type="text/plain",
        headers={"X-Request-Id": "req-12345", "X-RateLimit-Remaining": "99"},
    )


@app.get("/responses/no-content", status_code=204)
async def response_no_content():
    """Return 204 No Content (null-body status)."""
    return FastAPIResponse(status_code=204)


# --------------------------------------------------------------------------- #
# Routing routes
# --------------------------------------------------------------------------- #


class Colour(str, enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@app.get("/routing/path-int/{item_id}")
async def routing_path_int(item_id: int):
    """Path parameter coerced to int."""
    return {"item_id": item_id, "type": type(item_id).__name__}


@app.get("/routing/path-float/{value}")
async def routing_path_float(value: float):
    """Path parameter coerced to float."""
    return {"value": value, "type": type(value).__name__}


@app.get("/routing/path-enum/{colour}")
async def routing_path_enum(colour: Colour):
    """Path parameter validated against a str Enum."""
    return {"colour": colour.value}


@app.get("/routing/path-rest/{file_path:path}")
async def routing_path_rest(file_path: str):
    """Path parameter that captures the rest of the path including slashes."""
    return {"file_path": file_path}


@app.get("/routing/query")
async def routing_query(
    q: str | None = None,
    skip: int = 0,
    limit: int = 10,
):
    """Optional and default query parameters."""
    return {"q": q, "skip": skip, "limit": limit}


@app.get("/routing/query-required")
async def routing_query_required(name: str):
    """A required query parameter (no default)."""
    return {"name": name}


@app.get("/routing/query-list")
async def routing_query_list(tags: list[str] = Query(default=[])):  # noqa: B008
    """A multi-value query parameter (?tags=a&tags=b)."""
    return {"tags": tags}


@app.get("/routing/query-validation")
async def routing_query_validation(
    q: str = Query(min_length=3, max_length=50),  # noqa: B008
):
    """A query parameter with min/max length validation."""
    return {"q": q}


@app.put("/routing/put-item/{item_id}")
async def routing_put(item_id: int, item: ItemModel):
    """PUT method with path param and JSON body."""
    return {"item_id": item_id, "name": item.name, "price": item.price}


@app.delete("/routing/delete-item/{item_id}")
async def routing_delete(item_id: int):
    """DELETE method."""
    return {"deleted": item_id}


@app.patch("/routing/patch-item/{item_id}")
async def routing_patch(item_id: int):
    """PATCH method."""
    return {"patched": item_id}


# -- APIRouter with prefix ---------------------------------------------------
v1_router = APIRouter(prefix="/routing/v1")


@v1_router.get("/info")
async def v1_info():
    """Route registered via an APIRouter with prefix."""
    return {"version": 1, "status": "ok"}


app.include_router(v1_router)


@app.get("/platform/lifespan-state")
async def platform_lifespan_state(request: Request):
    resource = request.state.platform_resource
    return {"available": True, "closed": resource.closed}


@app.get("/native-file")
async def native_file():
    """Serve a single bundled file with FastAPI's native FileResponse."""
    return FileResponse(STATIC_DIR / "hello.txt", media_type="text/plain")


# Mounted before the catch-all below so `/static/*` is handled by Starlette's
# own filesystem-backed static file app rather than the Assets binding.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/{path:path}")
async def frontend(path: str, request: Request):
    """Proxy static asset requests to the Workers Assets binding."""
    env = request.scope["env"]
    asset_url = f"https://assets.local/{path}"
    resp = await env.ASSETS.fetch(asset_url)
    body = await resp.bytes()
    headers = dict(resp.headers)
    return FastAPIResponse(content=body, status_code=resp.status, headers=headers)


class ResultCollector:
    def __init__(self):
        self.results = {}

    @staticmethod
    def _key(item):
        name = item.name
        return name[len("test_") :] if name.startswith("test_") else name

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        key = self._key(item)

        if report.when == "call":
            if report.passed:
                self.results[key] = {"status": "passed"}
            elif report.skipped:
                self.results[key] = {
                    "status": "skipped",
                    "reason": str(report.longrepr),
                }
            elif report.failed:
                excinfo = call.excinfo
                if excinfo is not None and excinfo.errisinstance(AssertionError):
                    self.results[key] = {
                        "status": "failed",
                        "error": str(excinfo.value),
                    }
                else:
                    self.results[key] = {
                        "status": "error",
                        "error": f"{excinfo.typename}: {excinfo.value}"
                        if excinfo is not None
                        else "unknown error",
                        "traceback": report.longreprtext,
                    }
        elif report.when in ("setup", "teardown") and report.skipped:
            self.results[key] = {
                "status": "skipped",
                "reason": str(report.longrepr),
            }
        elif report.when in ("setup", "teardown") and report.failed:
            self.results[key] = {
                "status": "error",
                "error": report.longreprtext,
                "traceback": report.longreprtext,
            }


class EnvPlugin:
    def __init__(self, env):
        self._env = env

    @pytest.fixture
    def env(self):
        return self._env


class FastAPIAppPlugin:
    @pytest.fixture
    def fastapi_app(self):
        return app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from urllib.parse import urlparse

        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            return self._run_suite(suite_name)

        return await asgi.fetch(app, request, self.env, self.ctx)

    def _run_suite(self, suite_name):
        module = f"test_{suite_name}"
        if importlib.util.find_spec(module) is None:
            return Response.json(
                {"error": f"Unknown suite '{suite_name}' (no module '{module}')"},
                status=404,
            )

        collector = ResultCollector()
        saved_loop = asyncio.events._get_running_loop()
        try:
            pytest.main(
                ["--pyargs", module, "-p", "no:cacheprovider"],
                plugins=[
                    collector,
                    EnvPlugin(self.env),
                    FastAPIAppPlugin(),
                ],
            )
        finally:
            asyncio.events._set_running_loop(saved_loop)
        return Response.json(collector.results)
