# The tests in this file are primarily spread across Default.fetch() (in this module) and
# Default.fetch() (in server.py).
#
# The code in `Default.test()` (in this module) is used to actually perform the testing and its
# behaviour doesn't need to strictly be held consistent. In fact it uses the JS fetch, so it's not
# going to follow the SDK at all.

import os
from functools import wraps

from testlib.entrypoint import run_pytest

from workers import (
    WorkerEntrypoint,
)

RESPONSE_HANDLER = None


def response_handler(handler):
    global RESPONSE_HANDLER

    @wraps(handler)
    async def wrapper(request):
        global RESPONSE_HANDLER
        try:
            return await handler(request)
        finally:
            RESPONSE_HANDLER = None

    RESPONSE_HANDLER = wrapper
    return wrapper


class Default(WorkerEntrypoint):
    # Each path in this handler is its own test. The URLs that are being fetched
    # here are defined in server.py.
    async def fetch(self, request):
        if RESPONSE_HANDLER is None:
            raise RuntimeError("No handler")
        return await RESPONSE_HANDLER(request)

    async def scheduled(self, ctrl, env, ctx):
        assert ctrl.scheduledTime == 1000
        assert ctrl.cron == "* * * * 30"

    async def test(self):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        if self.env.color:
            args.append("--color=yes")
        run_pytest(args)
