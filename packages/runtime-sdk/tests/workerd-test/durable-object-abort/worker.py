from unittest import TestCase

from workers import DurableObject, Response, WorkerEntrypoint

assertRaisesRegex = TestCase().assertRaisesRegex


class AbortingDurableObject(DurableObject):
    def __init__(self, state, env):
        super().__init__(state, env)
        self.storage = state.storage

    async def fetch(self, request):
        return Response("ok")

    async def do_abort(self):
        self.ctx.abort("test abort reason")

    async def ping(self):
        return "pong"

    async def get_counter(self):
        value = await self.storage.get("counter")
        if value is None:
            value = 0

        value += 1
        await self.storage.put("counter", value)
        return value


class Default(WorkerEntrypoint):
    async def test(self):
        do_id = self.env.ABORTER.idFromName("abort-test")
        obj = self.env.ABORTER.get(do_id)

        response = await obj.fetch("http://foo.com/")
        assert await response.text() == "ok"

        assert await obj.ping() == "pong"
        assert await obj.get_counter() == 1

        with assertRaisesRegex(Exception, "test abort reason"):
            await obj.do_abort()

        obj2 = self.env.ABORTER.get(do_id)

        assert await obj2.ping() == "pong"

        response2 = await obj2.fetch("http://foo.com/")
        assert await response2.text() == "ok"

        # DO should be recreated, so the counter should be 1
        assert await obj2.get_counter() == 1
