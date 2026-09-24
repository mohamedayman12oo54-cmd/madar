from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    return JsonResponse({"status": "ok"})


def not_found(request, exception=None):
    return JsonResponse({"detail": "غير موجود.", "code": "not_found"}, status=404)


def server_error(request):
    """Safe 500 body for API clients: no traceback, no exception text, no
    file paths. The full error is still logged server-side by Django."""
    return JsonResponse({"detail": "حدث خطأ في الخادم.", "code": "server_error"}, status=500)


handler404 = "config.urls.not_found"
handler500 = "config.urls.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/environments/", include("environments.urls")),
]
