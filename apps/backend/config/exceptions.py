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
        response.data = {
            "detail": "محاولات كثيرة جدًا، برجاء الانتظار قليلًا قبل المحاولة مرة أخرى.",
            "code": "throttled",
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

    return response
