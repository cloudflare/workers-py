# pyright: reportMissingImports=false

"""Runner for the MySQL/Hyperdrive suite that executes inside workerd.

``/run-tests/<suite>`` runs ``test_<suite>.py`` under pytest and returns
per-test results; ``/mysql-probe/<role>`` serves one leg of the overlapping
connection probe, which the suite drives through the ``SELF`` service binding.
"""

import asyncio
import contextlib
import importlib.util
import io
from urllib.parse import urlparse

import pytest
from workers import Response, WorkerEntrypoint

MYSQL_PROBE_PREFIX = "/mysql-probe/"


class ResultCollector:
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


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            return self._run_suite(path[len("/run-tests/") :])
        if path.startswith(MYSQL_PROBE_PREFIX):
            from test_mysql_backend import handle_probe

            return await handle_probe(self.env, path[len(MYSQL_PROBE_PREFIX) :])
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
        # pytest-asyncio drives each test through asyncio.Runner, which calls
        # asyncio.new_event_loop(). In Pyodide that constructs a WebLoop whose
        # __init__ calls asyncio._set_running_loop(self) and never restores it on
        # close(), so after pytest.main() the running loop points at an abandoned
        # WebLoop. Save and restore it so the next request's fetch coroutine runs
        # on the real workerd-driven loop instead of hanging on a dead one.
        saved_loop = asyncio.events._get_running_loop()
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exit_code = pytest.main(
                    ["--pyargs", module, "-p", "no:cacheprovider"],
                    plugins=[collector, EnvPlugin(self.env)],
                )
        finally:
            asyncio.events._set_running_loop(saved_loop)
        if exit_code != 0 and not collector.results:
            return Response.json(
                {
                    "__session__": {
                        "status": "error",
                        "error": f"pytest exit code {exit_code}",
                        "traceback": output.getvalue(),
                    }
                },
                status=500,
            )
        return Response.json(collector.results)
