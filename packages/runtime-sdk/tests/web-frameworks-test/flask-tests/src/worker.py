import importlib.util
from urllib.parse import urlparse

import pytest
from flask import Flask

from workers import Response, WorkerEntrypoint, wsgi

app = Flask(__name__)


@app.get("/health")
def health():
    return {"ok": True}


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


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path
        if path.startswith("/run-tests/"):
            return self._run_suite(path[len("/run-tests/") :])
        return await wsgi.fetch(app, request, self.env, self.ctx)

    @staticmethod
    def _run_suite(suite_name):
        module = f"test_{suite_name}"
        if importlib.util.find_spec(module) is None:
            return Response.json(
                {"error": f"Unknown suite '{suite_name}' (no module '{module}')"},
                status=404,
            )

        collector = ResultCollector()
        pytest.main(
            ["--pyargs", module, "-p", "no:cacheprovider"],
            plugins=[collector],
        )
        return Response.json(collector.results)
