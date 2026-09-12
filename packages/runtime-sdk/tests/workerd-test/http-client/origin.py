import json

from workers import Response, WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = request.url
        path = url.split("?", 1)[0].rsplit("/", 1)[-1]

        match path:
            case "echo":
                return Response.json(
                    {
                        "method": request.method,
                        "url": url,
                        "custom": request.headers.get("X-Custom"),
                        "content_type": request.headers.get("Content-Type"),
                        "body": (await request.bytes()).decode(),
                    }
                )
            case "body":
                return Response(await request.text())
            case "lines":
                return Response("first\nsecond\nthird\n")
            case "head":
                return Response(
                    "body that HEAD must not expose", headers={"X-Origin": "head"}
                )
            case "redirect":
                return Response(
                    "",
                    status=302,
                    headers={"Location": "http://example.com:80/final"},
                )
            case "final":
                return Response("redirected")
            case "error":
                return Response(
                    "teapot body",
                    status=418,
                    status_text="I'm a Teapot",
                    headers={"X-Error": "expected"},
                )
            case "auth":
                if request.headers.get("Authorization") != "Basic dXNlcjpwYXNz":
                    return Response(
                        "authentication required",
                        status=401,
                        headers={"WWW-Authenticate": 'Basic realm="compat"'},
                    )
                return Response("authenticated")
            case "set-cookie":
                return Response(
                    "cookie set", headers={"Set-Cookie": "session=abc; Path=/"}
                )
            case "cookie":
                return Response(request.headers.get("Cookie") or "")
            case _:
                return Response(json.dumps({"unexpected_url": url}), status=404)
