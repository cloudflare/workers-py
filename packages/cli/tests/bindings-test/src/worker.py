"""Bindings test worker.

Each binding suite lives in a `test_<suite>.py` module written as ordinary pytest
tests (see test_kv.py). The `/run-tests/<suite>` endpoint runs pytest against that
module inside workerd and returns per-test results as JSON, which the host-side
test_bindings.py maps onto individual pytest cases.

To add a new binding: create `src/test_<binding>.py` with pytest tests.
"""

import asyncio
import importlib.util
import sys

import pytest
from pyodide.webloop import WebLoop
from worker_durable_object import (
    TestDurableObject,  # noqa: F401 - import to trigger side effect of registering the Durable Object
)
from workers import Response, WorkerEntrypoint


async def _noop(*args):
    pass


# pytest-asyncio relies on these but in Pyodide < 0.29 WebLoop does not implement them.
WebLoop.shutdown_asyncgens = _noop
WebLoop.shutdown_default_executor = _noop

# Pyodide 0.26.0a2's _cancel_all_tasks calls task.exception() on pending tasks,
# which raises InvalidStateError under Pyodide's WebLoop.
# Ignore this error to prevent pytest-asyncio from crashing.
if sys.version_info < (3, 13):
    asyncio.runners._cancel_all_tasks = lambda loop: None  # type: ignore[attr-defined]


class ResultCollector:
    """pytest plugin that records each test's outcome keyed by its short name.

    The "test_" prefix is stripped so keys match the names registered in
    tests/test_bindings.py (e.g. test_put_and_get -> "put_and_get").
    """

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


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from urllib.parse import urlparse

        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            return self._run_suite(suite_name)
        if path == "/health":
            return Response.json({"ok": True})
        return Response.json({"error": "not found"}, status=404)

    def _run_suite(self, suite_name):
        module = f"test_{suite_name}"
        if importlib.util.find_spec(module) is None:
            return Response.json(
                {"error": f"Unknown suite '{suite_name}' (no module '{module}')"},
                status=404,
            )

        collector = ResultCollector()
        pytest.main(
            ["--pyargs", module, "-p", "no:cacheprovider"],
            plugins=[collector, EnvPlugin(self.env)],
        )
        return Response.json(collector.results)
