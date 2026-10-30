from rest_framework.views import exception_handler
from rest_framework.exceptions import Throttled


def api_exception_handler(exc, context):
    """Wrap DRF's default handler so every error response has a stable,
    predictable shape ({"detail": ..., "code": ...}) the frontend can rely
    on, and throttled requests get a friendly Arabic message with the
    retry time instead of DRF's default English string."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, Throttled):
        wait = int(exc.wait) if exc.wait is not None else None
        locked = getattr(exc, "default_code", "") == "locked_out"
        response.data = {
            "detail": str(exc.detail) if locked else "محاولات كثيرة جدًا، برجاء الانتظار قليلًا قبل المحاولة مرة أخرى.",
            "code": "locked_out" if locked else "throttled",
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
