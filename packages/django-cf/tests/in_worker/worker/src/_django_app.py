# pyright: reportMissingImports=false

import functools

R2_LOCATION = "in-worker-media"


@functools.cache
def django_wsgi_app():
    from django.core.wsgi import get_wsgi_application

    return get_wsgi_application()
