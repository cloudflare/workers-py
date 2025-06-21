from django_cf import DjangoCFDurableObject
from workers import DurableObject


class DjangoDO(DjangoCFDurableObject, DurableObject):
    def get_app(self):
        from app.wsgi import application  # Update according to your project structure
        return application


async def on_fetch(request, env):
    id = env.DO_STORAGE.idFromName("A")
    obj = env.DO_STORAGE.get(id)
    return await obj.fetch(request)
