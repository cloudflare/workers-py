from django.http import JsonResponse
from django.urls import path

app_name = "api"


async def info(request):
    return JsonResponse({"namespace": "api-v1"})


urlpatterns = [
    path("info/", info, name="info"),
]
