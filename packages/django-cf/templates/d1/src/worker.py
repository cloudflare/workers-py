from django_cf import DjangoCFAdapter


async def on_fetch(request, env):
    from app.wsgi import application  # Import application inside on_fetch
    adapter = DjangoCFAdapter(application)
    return await adapter.handle_request(request)
