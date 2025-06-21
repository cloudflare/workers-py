from django_cf import DjangoCFDurableObject
from workers import DurableObject


class DOClass(DjangoCFDurableObject, DurableObject):
    def get_app(self):
        from app.wsgi import application  # Update according to your project structure
        return application


async def on_fetch(request, env):
    id = env.ns.idFromName("A")
    obj = env.ns.get(id)
    return await obj.fetch(request)
