import asyncio
import importlib.util
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.responses import Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from pyodide.webloop import WebLoop
from starlette.background import BackgroundTask

import asgi
from workers import Response, WorkerEntrypoint


async def _noop(*args):
    pass


WebLoop.shutdown_asyncgens = _noop
WebLoop.shutdown_default_executor = _noop

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI()

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
