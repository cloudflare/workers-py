from workers import Response, WorkerEntrypoint


class ServiceBinding(WorkerEntrypoint):
    async def fetch(self, request):
        from urllib.parse import urlparse
        path = urlparse(request.url).path
        if path == "/echo":
            body = await request.text()
            return Response(body)
        if path == "/inspect":
            body = await request.text()
            return Response.json({
                "method": request.method,
                "url": request.url,
                "body": body,
                "content_type": request.headers.get("Content-Type") or "",
            })
        return Response("service b", status=200)

    async def identity(self, value):
        return value

    async def add(self, a, b):
        return a + b

    async def transform_dict(self, data):
        data["added_by_service"] = True
        return data

    async def get_nested(self):
        return {
            "level1": {
                "level2": {"value": "deep"},
                "list": [1, 2, 3],
            },
            "top": "shallow",
        }

    async def multi_args(self, name, count, items, meta):
        return {
            "name": name,
            "count": count,
            "item_count": len(list(items)),
            "meta_keys": list(meta.keys()),
        }

    async def with_defaults(self, required, optional="default_val", count=0):
        return {
            "required": required,
            "optional": optional,
            "count": count,
        }
