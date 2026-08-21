from asgiref.sync import iscoroutinefunction, markcoroutinefunction


class CustomMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self):
            return self.__acall__(request)
        request.custom_middleware_applied = True
        response = self.get_response(request)
        response["X-Custom-Middleware"] = "applied"
        return response

    async def __acall__(self, request):
        request.custom_middleware_applied = True
        response = await self.get_response(request)
        response["X-Custom-Middleware"] = "applied"
        return response
