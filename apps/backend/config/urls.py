from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, register_converter


class BoundedInt:
    """The `<int:pk>` of every route in the API. Django's own converter accepts any number of digits, so
    `/users/99999999999999999999/` reached the database and came back as an HTTP 500 ("bigint out of range").
    Nine digits fit every id column; anything longer cannot name a real row and is a plain 404 at the router."""

    regex = "[0-9]{1,9}"

    def to_python(self, value):
        return int(value)

    def to_url(self, value):
        return str(value)


# Registered BEFORE any path() below (and before include() imports an app's urls) so it replaces the built-in `int`.
register_converter(BoundedInt, "int")


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
    path("api/v1/health/", health),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/environments/", include("environments.urls")),
    path("api/v1/academics/", include("academics.urls")),
    path("api/v1/billing/", include("billing.urls")),
    path("api/v1/scheduling/", include("scheduling.urls")),
    path("api/v1/financials/", include("financials.urls")),
    path("api/v1/evaluation/", include("evaluation.urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/content/", include("content.urls")),
    path("api/v1/ai/", include("ai.urls")),
    path("api/v1/knowledge/", include("knowledge.urls")),
    path("api/v1/parent/", include("parents.urls")),
    path("api/v1/guardian-messages/", include("parents.teacher_urls")),
    path("api/v1/student/exams/", include("learning.student_urls")),
    path("api/v1/exams/", include("learning.urls")),
    path("api/v1/student/", include("studentarea.urls")),
    path("api/v1/control/", include("control.urls")),
]

if settings.ENABLE_ADMIN:
    urlpatterns.insert(0, path(settings.ADMIN_URL, admin.site.urls))
