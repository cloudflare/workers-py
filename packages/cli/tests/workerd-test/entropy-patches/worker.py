import asyncio
import os
import sys

import pytest
from pyodide.webloop import WebLoop
from workers import WorkerEntrypoint


async def noop(*args):
    pass


# pytest-asyncio relies on these but in Pyodide < 0.29 WebLoop does not implement them
WebLoop.shutdown_asyncgens = noop
WebLoop.shutdown_default_executor = noop

if sys.version_info < (3, 13):
    asyncio.runners._cancel_all_tasks = lambda loop: None  # type: ignore[attr-defined]


class Default(WorkerEntrypoint):
    async def test(self):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        assert pytest.main(args) == 0
