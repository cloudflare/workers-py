from pyodide.webloop import WebLoop
from dataclasses import dataclass
from typing import Any
import asyncio
from io import StringIO

import sys
import importlib.util
from asyncio import InvalidStateError
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from urllib.parse import urlparse
from workers import Response, WorkerEntrypoint
import pytest


class EnvPlugin:
    def __init__(self, env):
        self._env = env

    @pytest.fixture
    def env(self):
        return self._env


class ResultCollector:
    """Record each pytest result under its host-suite test name."""

    def __init__(self):
        self.results = {}

    @staticmethod
    def _key(item):
        normalized = []
        if item.cls is not None:
            normalized.append(item.cls.__name__)
        name = getattr(item, "originalname", None) or item.name
        normalized.append(name[len("test_") :] if name.startswith("test_") else name)
        return "__".join(normalized)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        key = self._key(item)
        if report.passed:
            self.results[key] = {"status": "passed"}
        elif report.skipped:
            self.results[key] = {
                "status": "skipped",
                "reason": str(report.longrepr),
            }
        elif report.failed:
            result = {"status": "failed", "traceback": report.longreprtext}
            self.results[key] = result
            if report.when == "call":
                excinfo = call.excinfo
                if excinfo is None:
                    result["error"] = "unknown error"
                elif excinfo.errisinstance(AssertionError):
                    result["error"] = str(excinfo.value)
                    del result["traceback"]
                else:
                    result["error"] = f"{excinfo.typename}: {excinfo.value}"
            else:
                result["error"] = report.longreprtext
                del result["traceback"]


async def _noop(*args):
    pass


def _cancel_all_tasks(loop):
    """
    Pyodide 0.26.0a2's WebLoop causes InvalidStateError when _cancel_all_tasks
    calls task.exception() on done-but-not-cancelled tasks. Replace with a
    version that cancels tasks but tolerates that error.
    """
    to_cancel = asyncio.tasks.all_tasks(loop)
    if not to_cancel:
        return
    for task in to_cancel:
        task.cancel()
    loop.run_until_complete(asyncio.tasks.gather(*to_cancel, return_exceptions=True))
    for task in to_cancel:
        if task.cancelled():
            continue
        try:
            if task.exception() is not None:
                loop.call_exception_handler(
                    {
                        "message": "unhandled exception during asyncio.run() shutdown",
                        "exception": task.exception(),
                        "task": task,
                    }
                )
        # Note: This exception catch is added from the original implementation
        except (InvalidStateError, RuntimeError):
            pass


@contextmanager
def restore_loop():
    saved_loop = asyncio.events._get_running_loop()
    try:
        yield
    finally:
        asyncio.events._set_running_loop(saved_loop)


@contextmanager
def patch_asyncio():
    # pytest-asyncio relies on these methods, which older Pyodide WebLoops omit.
    orig_shutdown_asyncgens = WebLoop.shutdown_asyncgens
    orig_shutdown_default_executor = WebLoop.shutdown_default_executor
    orig_cancel_all_tasks = asyncio.runners._cancel_all_tasks  # type: ignore[attr-defined]

    WebLoop.shutdown_asyncgens = _noop
    WebLoop.shutdown_default_executor = _noop
    if sys.version_info < (3, 13):
        asyncio.runners._cancel_all_tasks = _cancel_all_tasks  # type: ignore[attr-defined]
    try:
        yield
    finally:
        WebLoop.shutdown_asyncgens = orig_shutdown_asyncgens
        WebLoop.shutdown_default_executor = orig_shutdown_default_executor
        asyncio.runners._cancel_all_tasks = orig_cancel_all_tasks  # type: ignore[attr-defined]


@dataclass
class TestRunnerResult:
    payload: Any
    status: int


class TestRunner:
    def __init__(self, env):
        self.env = env
        self.collector = ResultCollector()

    def plugins(self):
        return [
            self.collector,
            EnvPlugin(self.env),
        ]

    def run_suite(self, suite_name):
        module = f"test_{suite_name}"
        if importlib.util.find_spec(module) is None:
            return TestRunnerResult(
                {"error": f"Unknown suite '{suite_name}' (no module '{module}')"},
                status=404,
            )

        output = StringIO()
        with (
            restore_loop(),
            patch_asyncio(),
            redirect_stdout(output),
            redirect_stderr(output),
        ):
            exit_code = pytest.main(
                ["--pyargs", module, "-p", "no:cacheprovider"],
                plugins=self.plugins(),
            )
        if exit_code != 0 and not self.collector.results:
            return TestRunnerResult(
                {
                    "__session__": {
                        "status": "error",
                        "error": f"pytest exit code {exit_code}",
                        "traceback": output.getvalue(),
                    }
                },
                status=500,
            )
        return TestRunnerResult(self.collector.results, 200)


class TestRunnerEntrypoint(WorkerEntrypoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner = TestRunner(self.env)

    async def fetch(self, request):
        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            result = self.runner.run_suite(suite_name)
            return Response.json(result.payload, result.status)
        if path == "/health":
            return Response.json({"ok": True})
        return Response.json({"error": "not found"}, status=404)
