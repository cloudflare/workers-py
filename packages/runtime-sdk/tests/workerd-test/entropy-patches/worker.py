# Import all test modules to ensure they are colleded when creating
# a snapshot.
# Import all test modules to ensure they are colleded when creating
# a snapshot.
from tests import (  # noqa: F401
    test_aiohttp_websocket,
    test_langsmith,
    test_numpy,
    test_pydantic,
    test_rust_packages,
    test_ssl_avoidance,
)
from workers import WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def test(self):
        pass
