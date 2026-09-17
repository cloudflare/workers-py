from workers import WorkflowEntrypoint
from workers.workflows import NonRetryableError


class TestWorkflow(WorkflowEntrypoint):
    """
    Exercises the error path between Python steps and the Workflows engine.

    The JS side (worker.js) plays the engine and records the errors each step callback
    throws; the results returned from here record what `run()` sees once the engine rethrows.
    """

    async def run(self, event, step):
        results = {}

        @step.do("non_retryable")
        async def non_retryable():
            raise NonRetryableError("do not retry")

        try:
            await non_retryable()
        except NonRetryableError as e:
            results["non_retryable"] = {
                "caught": "NonRetryableError",
                "message": str(e),
            }
        except Exception as e:  # pragma: no cover - reported to the JS side
            results["non_retryable"] = {"caught": type(e).__name__, "message": str(e)}

        @step.do("non_retryable_no_message")
        async def non_retryable_no_message():
            raise NonRetryableError()

        try:
            await non_retryable_no_message()
        except NonRetryableError as e:
            results["non_retryable_no_message"] = {
                "caught": "NonRetryableError",
                "message": str(e),
            }
        except Exception as e:  # pragma: no cover - reported to the JS side
            results["non_retryable_no_message"] = {
                "caught": type(e).__name__,
                "message": str(e),
            }

        # Ordinary Python exceptions are not translated: they reach the engine as a
        # PythonError and come back with their type recovered from the traceback.
        @step.do("type_error")
        async def type_error():
            raise TypeError("intentional type error")

        try:
            await type_error()
        except TypeError as e:
            results["type_error"] = {"caught": "TypeError", "message": str(e)}
        except Exception as e:  # pragma: no cover - reported to the JS side
            results["type_error"] = {"caught": type(e).__name__, "message": str(e)}

        # A successful step still works through the wrapped `step`, including receiving
        # the step context and the workflow event.
        @step.do("ok")
        async def ok(ctx):
            return {"attempt": ctx["attempt"], "payload": event["payload"]}

        results["ok"] = await ok()

        # Steps using the other `step` methods are forwarded to the engine untouched.
        await step.sleep("nap", "1 second")
        results["slept"] = True

        return results
