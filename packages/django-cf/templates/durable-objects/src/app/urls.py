"""
URL configuration for app project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path


def create_admin(request):
    User = get_user_model()

    admin_exists = User.objects.filter(username='admin').exists()

    if not admin_exists:
        User.objects.create_superuser('admin', 'admin@do.com', 'password')
        return JsonResponse({"admin": "created"})

    return JsonResponse({"admin": "already exists"})


def run_migrations_view(request):
    try:
        call_command("migrate")
        return JsonResponse({"status": "success", "message": "Migrations applied."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


urlpatterns = [
    path('create-admin', create_admin),
    path('migrate', run_migrations_view),
    path('admin/', admin.site.urls),
]
