from asgiref.sync import iscoroutinefunction, markcoroutinefunction


class CustomAsyncMiddleware:
    async_capable = True
    sync_capable = False

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    async def __call__(self, request):
        request.custom_middleware_applied = True
        response = await self.get_response(request)
        response["X-Custom-Middleware"] = "applied"
        return response
