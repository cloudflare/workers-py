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
from django.http import JsonResponse, HttpResponse, HttpResponseNotFound
from django.urls import path, include
from django.contrib.auth.decorators import user_passes_test
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models.functions import TruncYear, TruncMonth, TruncDay, TruncHour, TruncQuarter, TruncWeek
from .models import BankTransaction

def is_superuser(user):
    return user.is_authenticated and user.is_superuser

# @user_passes_test(is_superuser)
def create_admin_view(request):
    User = get_user_model()
    username = 'admin' # Or get from request, config, etc.
    email = 'admin@example.com' # Or get from request, config, etc.
    # IMPORTANT: Change this password or manage it securely!
    password = 'password'

    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, password)
        return JsonResponse({"status": "success", "message": f"Admin user '{username}' created."})
    else:
        return JsonResponse({"status": "info", "message": f"Admin user '{username}' already exists."})

def run_migrations_view(request):
    """Run Django migrations."""
    try:
        call_command('migrate', verbosity=0)
        return JsonResponse({"status": "success", "message": "Migrations completed"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

# R2 Storage Test Endpoints
def r2_upload_view(request):
    """Test endpoint for uploading files to R2."""
    if request.method == 'POST':
        try:
            uploaded_file = request.FILES.get('file')
            path = request.POST.get('path')

            if not uploaded_file or not path:
                return JsonResponse({"status": "error", "message": "Missing file or path"}, status=400)

            # Save file to R2
            saved_path = default_storage.save(path, ContentFile(uploaded_file.read()))

            return JsonResponse({"status": "success", "path": saved_path})
        except Exception as e:
            print(str(e))
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)


def r2_download_view(request):
    """Test endpoint for downloading files from R2."""
    path = request.GET.get('path')

    if not path:
        return JsonResponse({"status": "error", "message": "Missing path parameter"}, status=400)

    try:
        if not default_storage.exists(path):
            return HttpResponseNotFound("File not found")

        with default_storage.open(path, 'rb') as f:
            content = f.read()

        return HttpResponse(content, content_type='application/octet-stream')
    except Exception as e:
        print(str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def r2_exists_view(request):
    """Test endpoint for checking if a file exists in R2."""
    path = request.GET.get('path')

    if not path:
        return JsonResponse({"status": "error", "message": "Missing path parameter"}, status=400)

    try:
        exists = default_storage.exists(path)
        return JsonResponse({"exists": exists})
    except Exception as e:
        print(str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def r2_delete_view(request):
    """Test endpoint for deleting files from R2."""
    if request.method == 'POST':
        try:
            path = request.POST.get('path')

            if not path:
                return JsonResponse({"status": "error", "message": "Missing path parameter"}, status=400)

            default_storage.delete(path)
            return JsonResponse({"status": "success"})
        except Exception as e:
            print(str(e))
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)


def r2_listdir_view(request):
    """Test endpoint for listing files in R2."""
    path = request.GET.get('path', '')

    try:
        directories, files = default_storage.listdir(path)
        return JsonResponse({"directories": list(directories), "files": list(files)})
    except Exception as e:
        print(str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def r2_size_view(request):
    """Test endpoint for getting file size from R2."""
    path = request.GET.get('path')

    if not path:
        return JsonResponse({"status": "error", "message": "Missing path parameter"}, status=400)

    try:
        size = default_storage.size(path)
        return JsonResponse({"size": size})
    except Exception as e:
        print(str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def date_trunc_test_view(request):
    """Test endpoint for date truncation functions."""
    try:
        truncation_type = request.GET.get('type', 'month')

        trunc_map = {
            'year': TruncYear,
            'quarter': TruncQuarter,
            'month': TruncMonth,
            'week': TruncWeek,
            'day': TruncDay,
            'hour': TruncHour,
        }

        if truncation_type not in trunc_map:
            return JsonResponse({
                "status": "error",
                "message": f"Invalid truncation type. Supported types: {', '.join(trunc_map.keys())}"
            }, status=400)

        trunc_class = trunc_map[truncation_type]

        results = BankTransaction.objects.annotate(
            truncated=trunc_class('created_at')
        ).values('truncated').distinct().order_by('truncated')

        return JsonResponse({
            "status": "success",
            "type": truncation_type,
            "results": [str(r['truncated']) for r in results]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)


def date_trunc_create_transaction_view(request):
    """Create test transactions for date truncation testing."""
    try:
        if request.method == 'POST':
            description = request.POST.get('description', 'Test Transaction')
            balance = request.POST.get('balance', '100.00')
            credit = request.POST.get('credit', '0.00')
            debit = request.POST.get('debit', '0.00')
            BankTransaction.objects.create(
                description=description,
                balance=balance,
                credit=credit,
                debit=debit,
                value_date='2025-01-01',
                movement_date='2025-01-01'
            )
            return JsonResponse({"status": "success", "message": "Transaction created"})

        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def date_trunc_clear_transactions_view(request):
    """Clear all test transactions."""
    try:
        if request.method == 'POST':
            BankTransaction.objects.all().delete()
            return JsonResponse({"status": "success", "message": "All transactions cleared"})

        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


urlpatterns = [
    path('admin/', admin.site.urls),

    # Management endpoints
    path('__run_migrations__/', run_migrations_view, name='run_migrations'),
    path('__create_admin__/', create_admin_view, name='create_admin'),

    # R2 Storage Test endpoints - for testing only
    path('__r2_upload__/', r2_upload_view, name='r2_upload'),
    path('__r2_download__/', r2_download_view, name='r2_download'),
    path('__r2_exists__/', r2_exists_view, name='r2_exists'),
    path('__r2_delete__/', r2_delete_view, name='r2_delete'),
    path('__r2_listdir__/', r2_listdir_view, name='r2_listdir'),
    path('__r2_size__/', r2_size_view, name='r2_size'),

    # Date truncation test endpoints
    path('__date_trunc_test__/', date_trunc_test_view, name='date_trunc_test'),
    path('__date_trunc_create_transaction__/', date_trunc_create_transaction_view, name='date_trunc_create_transaction'),
    path('__date_trunc_clear_transactions__/', date_trunc_clear_transactions_view, name='date_trunc_clear_transactions'),
]
