from workers import wsgi


async def handle_wsgi(request, app, env=None):
    return await wsgi.fetch(app, request, env)


class DjangoCF:
    def get_app(self):
        raise NotImplementedError("Please implement get_app in your django_cf worker")

    async def fetch(self, request):
        return await handle_wsgi(request, self.get_app(), self.env)


class DjangoCFDurableObject:
    def get_app(self):
        raise NotImplementedError("Please implement get_app in your django_cf worker")

    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env

        from django_cf.db.backends.do.storage import set_storage

        set_storage(self.ctx.storage.sql)

    def fetch(self, request):
        return handle_wsgi(request, self.get_app(), self.env)
