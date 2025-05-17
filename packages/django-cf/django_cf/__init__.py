import os
from io import BytesIO

class DjangoCFAdapter:
    def __init__(self, app):
        self.app = app

    async def handle_request(self, request):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'false')
        from js import Object, Response, URL, console

        headers = []
        for header in request.headers:
            headers.append(tuple([header[0], header[1]]))

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

        for header in request.headers:
            wsgi_request[f'HTTP_{header[0].upper()}'] = header[1]

        if method in ['POST', 'PUT', 'PATCH']:
            body = (await request.arrayBuffer()).to_bytes()
            wsgi_request['wsgi.input'] = BytesIO(body)

        def start_response(status_str, response_headers):
            nonlocal status, headers
            status = status_str
            headers = response_headers

        resp = self.app(wsgi_request, start_response)
        status = resp.status_code
        headers = resp.headers

        final_response = Response.new(
            resp.content.decode('utf-8'), headers=Object.fromEntries(headers.items()), status=status
        )

        for k, v in resp.cookies.items():
            value = str(v)
            final_response.headers.set('Set-Cookie', value.replace('Set-Cookie: ', '', 1));

        return final_response
