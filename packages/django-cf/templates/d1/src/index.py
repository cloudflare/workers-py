from workers import WorkerEntrypoint
from django_cf import DjangoCF

class Default(DjangoCF, WorkerEntrypoint):
    async def get_app(self):
        from app.wsgi import application
        return application
