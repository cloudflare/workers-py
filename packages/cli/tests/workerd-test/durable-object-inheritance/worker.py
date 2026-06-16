# Regression test: multi-level inheritance from DurableObject / WorkerEntrypoint.
# https://github.com/cloudflare/workers-py/issues/125
# _wrap_subclass must not double-wrap ctx and env when the hierarchy is >1 deep.

from workers import DurableObject, WorkerEntrypoint
from workers._workers import _EnvWrapper


class BaseDurableObject(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        # Fails if ctx is double-wrapped: DurableObjectContext(DurableObjectContext(...))
        self.ctx.storage.sql.exec("SELECT NULL")

    async def shared_method(self):
        return "from base"


class LeafDurableObject(BaseDurableObject):
    async def hello(self):
        return "hello from leaf"

    async def check_env(self):
        return self.env is not None

    async def check_ctx(self):
        return self.ctx is not None

    async def check_storage(self):
        self.ctx.storage.sql.exec("SELECT NULL")
        return True


class LeafDurableObjectWithInit(BaseDurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.custom_attr = "custom"

    async def hello(self):
        return "hello with init"

    async def check_custom(self):
        return self.custom_attr == "custom"

    async def check_storage(self):
        self.ctx.storage.sql.exec("SELECT NULL")
        return True


class BaseEntrypoint(WorkerEntrypoint):
    def get_name(self):
        return "base"


class Default(BaseEntrypoint):
    async def test(self, ctrl):
        id1 = self.env.DO_LEAF.idFromName("leaf-test")
        obj1 = self.env.DO_LEAF.get(id1)
        assert await obj1.hello() == "hello from leaf"
        assert await obj1.shared_method() == "from base"
        assert await obj1.check_env()
        assert await obj1.check_ctx()
        assert await obj1.check_storage()

        id2 = self.env.DO_LEAF_INIT.idFromName("leaf-init-test")
        obj2 = self.env.DO_LEAF_INIT.get(id2)
        assert await obj2.hello() == "hello with init"
        assert await obj2.check_custom()
        assert await obj2.check_storage()

        assert self.get_name() == "base"
        assert self.env is not None

        # env must be wrapped exactly once: _EnvWrapper(js_env), not _EnvWrapper(_EnvWrapper(js_env))
        assert isinstance(self.env, _EnvWrapper)
        assert not isinstance(self.env._env, _EnvWrapper)
