import asyncio
import datetime

from workers import WorkflowEntrypoint
from workers.workflows import NonRetryableError


class TestWorkflow(WorkflowEntrypoint):
    async def run(self, event, step):
        mode = event["payload"].get("mode", "echo")
        handlers = {
            "echo": self._echo,
            "implicit_deps": self._implicit_deps,
            "concurrent": self._concurrent,
            "sleep": self._sleep,
            "sleep_until": self._sleep_until,
            "wait_for_event": self._wait_for_event,
            "event_metadata": self._event_metadata,
            "ctx": self._ctx,
            "retry": self._retry,
            "non_retryable": self._non_retryable,
            "catch_error": self._catch_error,
            "duplicate_step_names": self._duplicate_step_names,
            "step_output_conversion": self._step_output_conversion,
        }
        handler = handlers.get(mode)
        if handler is None:
            raise ValueError(f"unknown workflow mode: {mode}")
        return await handler(event, step)

    async def _echo(self, event, step):
        payload = event["payload"]

        @step.do("echo")
        async def echo():
            return {"echo": payload}

        return await echo()

    async def _implicit_deps(self, event, step):
        @step.do()
        async def base_value():
            return 10

        @step.do()
        async def derived(base_value):
            return base_value + 5

        return {"derived": await derived()}

    async def _concurrent(self, event, step):
        @step.do()
        async def left():
            return 2

        @step.do()
        async def right():
            return 3

        @step.do(concurrent=True)
        async def combined(left, right):
            return left * right

        return {"combined": await combined()}

    async def _sleep(self, event, step):
        await step.sleep("nap", 0)
        return {"slept": True}

    async def _sleep_until(self, event, step):
        when = datetime.datetime.now() + datetime.timedelta(milliseconds=100)
        await step.sleep_until("nap-until", when)
        return {"slept_until": True}

    async def _wait_for_event(self, event, step):
        received = await step.wait_for_event("await-approval", "approval")
        return {"event_payload": received["payload"]}

    async def _event_metadata(self, event, step):
        return {
            "payload": event["payload"],
            "has_timestamp": "timestamp" in event,
            "instance_id": event.get("instanceId"),
            "workflow_name": event.get("workflowName"),
        }

    async def _ctx(self, event, step):
        @step.do("ctx-step")
        async def read_ctx(ctx):
            return {
                "step_name": ctx["step"]["name"],
                "step_count": ctx["step"]["count"],
                "attempt": int(ctx["attempt"]),
                "has_config": "config" in ctx,
            }

        return await read_ctx()

    async def _retry(self, event, step):
        @step.do(
            "retry-step",
            config={"retries": {"limit": 1, "delay": 0, "backoff": "constant"}},
        )
        async def flaky(ctx):
            if int(ctx["attempt"]) < 2:
                raise ValueError("transient failure")
            return {"succeeded_on_attempt": int(ctx["attempt"])}

        return await flaky()

    async def _non_retryable(self, event, step):
        # Fails on the first attempt with NonRetryableError and would succeed on a
        # second attempt. If the engine honours NonRetryableError the step fails
        # once and `run()` sees a NonRetryableError; if the engine retries, the step
        # completes with `attempt == 2`.
        @step.do(
            "non-retryable-step",
            config={"retries": {"limit": 3, "delay": 0, "backoff": "constant"}},
        )
        async def boom(ctx):
            if int(ctx["attempt"]) < 2:
                raise NonRetryableError("do not retry")
            return {"retried": True, "attempt": int(ctx["attempt"])}

        try:
            result = await boom()
        except NonRetryableError as exc:
            return {
                "retried": False,
                "caught": "NonRetryableError",
                "message": str(exc),
            }
        except Exception as exc:
            return {"retried": False, "caught": type(exc).__name__, "message": str(exc)}
        return result

    async def _duplicate_step_names(self, event, step):
        # The engine disambiguates repeated step names with a counter, so two
        # steps sharing a name must not share memoised results or in-flight tasks.
        @step.do("dup")
        async def first():
            return 1

        @step.do("dup")
        async def second():
            return 2

        # Implicit dependencies resolve by step name, so `dup` refers to the most
        # recently registered closure (`second`) and must return its result.
        @step.do()
        async def uses(dup):
            return dup * 10

        # Run both same-named steps concurrently so they are in flight together.
        concurrent = list(await asyncio.gather(first(), second()))
        return {"concurrent": concurrent, "uses": await uses()}

    async def _step_output_conversion(self, event, step):
        @step.do("produce")
        async def produce():
            return {
                "when": datetime.datetime(2026, 1, 2, 3, 4, 5),
                "nothing": None,
                "nested": {"nothing": None},
            }

        @step.do()
        async def consume(produce):
            return {
                "when_is_datetime": isinstance(produce["when"], datetime.datetime),
                "year": produce["when"].year,
                "nothing_is_none": produce["nothing"] is None,
                "nested_nothing_is_none": produce["nested"]["nothing"] is None,
            }

        return await consume()

    async def _catch_error(self, event, step):
        @step.do(
            "failing-step",
            config={"retries": {"limit": 0, "delay": 0, "backoff": "constant"}},
        )
        async def failing():
            raise TypeError("intentional failure")

        try:
            await failing()
        except Exception as exc:
            return {"caught": type(exc).__name__, "message": str(exc)}
        return {"caught": None}
