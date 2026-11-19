from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from rest_framework.response import Response
from rest_framework.views import exception_handler
from rest_framework.exceptions import Throttled


def api_exception_handler(exc, context):
    """Wrap DRF's default handler so every error response has a stable,
    predictable shape ({"detail": ..., "code": ...}) the frontend can rely
    on, and throttled requests get a friendly Arabic message with the
    retry time instead of DRF's default English string."""
    # Values the database refuses (a number too large for the column, a malformed date the ORM chokes on) are the
    # CALLER's mistake: a 400, never an HTTP 500 that looks like a server fault and invites probing.
    # RecursionError: a JSON body nested hundreds of thousands deep overflows the parser's stack before any view code runs.
    if isinstance(exc, (DataError, DjangoValidationError, RecursionError)):
        return Response({"detail": "قيمة غير صالحة في الطلب.", "code": "invalid_value"}, status=400)
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, Throttled):
        wait = int(exc.wait) if exc.wait is not None else None
        code = getattr(exc, "default_code", "")
        own_message = code in ("locked_out", "upload_cooldown")  # these carry their own wording
        response.data = {
            "detail": str(exc.detail) if own_message else "محاولات كثيرة جدًا، برجاء الانتظار قليلًا قبل المحاولة مرة أخرى.",
            "code": code if own_message else "throttled",
            "retry_after_seconds": wait,
        }
        return response

    # Normalize DRF's varied shapes (list / dict / string) into one
    # consistent envelope without losing the field-level detail serializer
    # errors provide (the frontend maps these back onto specific fields).
    if isinstance(response.data, dict) and "detail" not in response.data:
        response.data = {"detail": "تحقق من البيانات المدخلة.", "code": "validation_error", "fields": response.data}
    elif isinstance(response.data, list):
        response.data = {"detail": "تحقق من البيانات المدخلة.", "code": "validation_error", "fields": response.data}

    # Every APIException carries a machine-readable code (default_code, or a
    # custom one set on a subclass — see environments/tenancy.py). Views that
    # build a Response by hand already set "code" themselves; this only fills
    # it in for errors that came from a *raised* exception, so every error
    # response — not just the hand-built ones — has a stable "code" the
    # frontend can branch on without parsing Arabic text.
    if isinstance(response.data, dict) and "code" not in response.data:
        try:
            codes = exc.get_codes()
            response.data["code"] = codes if isinstance(codes, str) else "error"
        except AttributeError:
            response.data["code"] = "error"

    return response
