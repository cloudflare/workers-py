from workers import WorkerEntrypoint

# Import all test modules to ensure they are colleded when creating
# a snapshot.
from tests import (
    test_aiohttp_websocket,
    test_langsmith,
    test_pydantic,
    test_rust_packages,
    test_ssl_avoidance,
)


class Default(WorkerEntrypoint):
    async def test(self):
        pass
