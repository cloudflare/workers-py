# Regression test: multi-level inheritance from DurableObject / WorkerEntrypoint.
# https://github.com/cloudflare/workers-py/issues/125
# _wrap_subclass must not double-wrap ctx and env when the hierarchy is >1 deep.

from workers import DurableObject, WorkerEntrypoint
from workers._workers import DurableObjectContext, _EnvWrapper


def assert_wrapped_once(obj):
    assert isinstance(obj.env, _EnvWrapper), "env should be an _EnvWrapper"
    assert not isinstance(obj.env._env, _EnvWrapper), "env should not be double-wrapped"


def assert_do_wrapped_once(obj):
    assert_wrapped_once(obj)
    assert isinstance(obj.ctx, DurableObjectContext), (
        "ctx should be a DurableObjectContext"
    )
    assert not isinstance(obj.ctx._ctx, DurableObjectContext), (
        "ctx should not be double-wrapped"
    )


class BaseDurableObject(DurableObject):
    def __init__(self, ctx, env):
        assert isinstance(env, _EnvWrapper)
        assert isinstance(ctx, DurableObjectContext)
        super().__init__(ctx, env)
        assert_do_wrapped_once(self)
        self.ctx.storage.sql.exec("SELECT NULL")

    async def shared_method(self):
        return "from base"


class LeafDurableObject(BaseDurableObject):
    async def hello(self):
        return "hello from leaf"

    async def verify_wrapping(self):
        assert_do_wrapped_once(self)
        self.ctx.storage.sql.exec("SELECT NULL")
        return True


class LeafDurableObjectWithInit(BaseDurableObject):
    def __init__(self, ctx, env):
        assert isinstance(env, _EnvWrapper)
        assert isinstance(ctx, DurableObjectContext)
        super().__init__(ctx, env)
        assert_do_wrapped_once(self)
        self.custom_attr = "custom"

    async def hello(self):
        return "hello with init"

    async def verify_wrapping(self):
        assert_do_wrapped_once(self)
        assert self.custom_attr == "custom"
        self.ctx.storage.sql.exec("SELECT NULL")
        return True


class RedundantBaseDO(BaseDurableObject, DurableObject):
    async def hello(self):
        return "hello from redundant"

    async def verify_wrapping(self):
        assert_do_wrapped_once(self)
        self.ctx.storage.sql.exec("SELECT NULL")
        return True


class BaseEntrypoint(WorkerEntrypoint):
    def get_name(self):
        return "base"


class RedundantBaseEntrypoint(BaseEntrypoint, WorkerEntrypoint):
    def get_name(self):
        return "redundant"


class Default(RedundantBaseEntrypoint):
    async def test(self, ctrl):
        class Env:
            pass

        x = _EnvWrapper(Env)
        assert _EnvWrapper(x) is x
        assert x._env is Env

        y = DurableObjectContext(Env)
        assert DurableObjectContext(y) is y
        assert y._ctx is Env

        assert_wrapped_once(self)
        assert self.get_name() == "redundant"

        id1 = self.env.DO_LEAF.idFromName("leaf-test")
        obj1 = self.env.DO_LEAF.get(id1)
        assert await obj1.hello() == "hello from leaf"
        assert await obj1.shared_method() == "from base"
        assert await obj1.verify_wrapping()

        id2 = self.env.DO_LEAF_INIT.idFromName("leaf-init-test")
        obj2 = self.env.DO_LEAF_INIT.get(id2)
        assert await obj2.hello() == "hello with init"
        assert await obj2.verify_wrapping()

        id3 = self.env.DO_REDUNDANT.idFromName("redundant-test")
        obj3 = self.env.DO_REDUNDANT.get(id3)
        assert await obj3.hello() == "hello from redundant"
        assert await obj3.verify_wrapping()
