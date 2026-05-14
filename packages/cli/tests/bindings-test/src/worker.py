import traceback

from kv_test import KV_TESTS
from workers import Response, WorkerEntrypoint

ALL_TESTS = {
    "kv": KV_TESTS,
}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from urllib.parse import urlparse

        path = urlparse(request.url).path

        if path.startswith("/run-tests/"):
            suite_name = path[len("/run-tests/") :]
            return await self._run_suite(suite_name)
        if path == "/health":
            # health check used in test to make sure the worker is up and running
            return Response.json({"ok": True})
        return Response.json({"error": "not found"}, status=404)

    async def _run_suite(self, suite_name):
        tests = ALL_TESTS.get(suite_name)
        if tests is None:
            available = list(ALL_TESTS.keys())
            return Response.json(
                {"error": f"Unknown suite '{suite_name}'", "available": available},
                status=404,
            )

        results = {}
        for test_name, test_fn in tests.items():
            try:
                await test_fn(self.env)
                results[test_name] = {"status": "passed"}
            except AssertionError as e:
                results[test_name] = {"status": "failed", "error": str(e)}
            except Exception as e:
                results[test_name] = {
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                }
        return Response.json(results)
