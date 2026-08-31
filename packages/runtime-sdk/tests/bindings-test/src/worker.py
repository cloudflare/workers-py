"""Bindings test worker.

Each binding suite lives in a `test_<suite>.py` module written as ordinary pytest
tests (see test_kv.py). The `/run-tests/<suite>` endpoint runs pytest against that
module inside workerd and returns per-test results as JSON, which the host-side
test_bindings.py maps onto individual pytest cases.

To add a new binding: create `src/test_<binding>.py` with pytest tests.
"""

from testlib.entrypoint import TestRunnerEntrypoint
from worker_durable_object import (
    TestDurableObject,  # noqa: F401 - import to trigger side effect of registering the Durable Object
)
from worker_workflow import (
    TestWorkflow,  # noqa: F401 - import to trigger side effect of registering the Workflow
)

RECEIVED_MESSAGES = []


class Default(TestRunnerEntrypoint):
    async def queue(self, batch, env, ctx):
        for message in batch.messages:
            RECEIVED_MESSAGES.append(
                {
                    "id": message.id,
                    "body": message.body,
                    "attempts": message.attempts,
                }
            )
            message.ack()
