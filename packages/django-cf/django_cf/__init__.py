import os
from io import BytesIO


async def handle_wsgi(request, app):
    os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'false')
    from js import Object, Response, URL, console

    url = URL.new(request.url)
    assert url.protocol[-1] == ":"
    scheme = url.protocol[:-1]
    path = url.pathname
    assert "?".startswith(url.search[0:1])
    query_string = url.search[1:]
    method = str(request.method).upper()

    host = url.host.split(':')[0]

    wsgi_request = {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'QUERY_STRING': query_string,
        'SERVER_NAME': host,
        'SERVER_PORT': url.port,
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.input': BytesIO(b''),
        'wsgi.errors': console.error,
        'wsgi.version': (1, 0),
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': True,
        'wsgi.url_scheme': scheme,
    }

    if request.headers.get('content-type'):
        wsgi_request['CONTENT_TYPE'] = request.headers.get('content-type')

    if request.headers.get('content-length'):
        wsgi_request['CONTENT_LENGTH'] = request.headers.get('content-length')

    for header in request.headers.items():
        wsgi_request[f'HTTP_{header[0].upper()}'] = header[1]

    if method in ['POST', 'PUT', 'PATCH']:
        body = (await request._js_request.arrayBuffer()).to_bytes()
        wsgi_request['wsgi.input'] = BytesIO(body)

    def start_response(status_str, response_headers):
        nonlocal status, headers
        status = status_str
        headers = response_headers

    try:
        resp = app(wsgi_request, start_response)
    except Exception as exc:
        # library should always print or console log the exception, because a production django should not show end users errors
        print('Caught exception while loading application:', exc.__str__())
        print(exc)

        raise exc

    status = resp.status_code
    headers = resp.headers

    final_response = Response.new(
        resp.content.decode('utf-8'), headers=Object.fromEntries(headers.items()), status=status
    )

    for k, v in resp.cookies.items():
        value = str(v)
        final_response.headers.set('Set-Cookie', value.replace('Set-Cookie: ', '', 1));

    return final_response


class DjangoCF:
    def get_app(self):
        raise NotImplementedError("Please implement implement get_app in your django_cf worker")

    async def fetch(self, request):
        return await handle_wsgi(request, self.get_app())


class DjangoCFDurableObject:
    def get_app(self):
        raise NotImplementedError("Please implement implement get_app in your django_cf worker")

    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env

        from django_cf.db.backends.do.storage import set_storage
        set_storage(self.ctx.storage.sql)

    def fetch(self, request):
        return handle_wsgi(request, self.get_app())
