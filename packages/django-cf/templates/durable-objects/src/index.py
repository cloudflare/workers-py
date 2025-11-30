from workers import DurableObject, WorkerEntrypoint

from django_cf import DjangoCFDurableObject


class DjangoDO(DjangoCFDurableObject, DurableObject):
    def get_app(self):
        from app.wsgi import application  # Update according to your project structure
        return application


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Pick a DO name based on the request
        id = self.env.DO_STORAGE.idFromName("A")
        obj = self.env.DO_STORAGE.get(id)
        return await obj.fetch(request)
