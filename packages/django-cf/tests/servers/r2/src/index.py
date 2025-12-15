from workers import WorkerEntrypoint
from django_cf import DjangoCF
from app.wsgi import application

class Default(DjangoCF, WorkerEntrypoint):
    def get_app(self):
        return application
