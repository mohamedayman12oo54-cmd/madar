"""Input hygiene that has to hold for EVERY endpoint, so it lives in one place instead of in each view."""
from django.http import JsonResponse

_BAD = {"detail": "طلب غير صالح.", "code": "invalid_request"}


class NullByteGuardMiddleware:
    """Refuses a request that smuggles a NUL character (raw, `%00`, or JSON `\u0000`) into the path, the query string
    or a JSON body. PostgreSQL cannot store NUL in text, so such a value turns into a database error (HTTP 500)
    wherever it reaches a query — and it is a classic filter-bypass / truncation trick besides. Binary uploads are
    multipart, not JSON, and are left alone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_qs = request.META.get("QUERY_STRING", "")
        if "\x00" in request.path or "%00" in request.path or "\x00" in raw_qs or "%00" in raw_qs.lower():
            return JsonResponse(_BAD, status=400)
        ctype = (request.META.get("CONTENT_TYPE") or "").lower()
        if ctype.startswith("application/json") and request.method in ("POST", "PUT", "PATCH"):
            body = request.body  # already size-limited by DATA_UPLOAD_MAX_MEMORY_SIZE
            if b"\x00" in body or b"\u0000" in body.lower():
                return JsonResponse(_BAD, status=400)
        return self.get_response(request)
