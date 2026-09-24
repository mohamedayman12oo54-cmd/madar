"""
Rate limiting for the unauthenticated / abuse-prone endpoints.

Why these are NOT ScopedRateThrottle subclasses (Phase 0 / S1): DRF's
ScopedRateThrottle takes its scope from a `throttle_scope` attribute on the
*view* and silently allows every request when that attribute is missing. The
original classes only set a class-level `scope`, which ScopedRateThrottle
overwrites on every call — so no request was ever throttled. These classes
extend SimpleRateThrottle directly, so the scope on the class is the scope
that is enforced, and attaching the class to a view is all that is needed.

Client IP comes from DRF's `get_ident()`, which honours
`REST_FRAMEWORK["NUM_PROXIES"]` (settings.py). With the default of 0,
X-Forwarded-For is ignored entirely, so a client cannot mint a fresh
throttle bucket per request by spoofing that header.

Three keying strategies:
  * IP        — coarse protection against one client hammering an endpoint
  * account / target — keyed on the identifier (phone/email) in the request
    body, so many IPs cannot brute-force one account or spam one phone
    number with OTPs. The key is a hash of the normalized identifier and is
    derived from the *input*, never from whether an account exists, so the
    throttle itself is not an enumeration oracle.
  * user      — for authenticated endpoints, keyed on the user id
"""
import hashlib

from rest_framework.throttling import SimpleRateThrottle

from .models import normalize_phone


def normalize_target(raw: str) -> str:
    """Canonical form of a phone/email identifier, for throttle keys only."""
    value = (raw or "").strip()
    if "@" in value:
        return value.lower()
    return normalize_phone(value) or value.lower()


class IPRateThrottle(SimpleRateThrottle):
    """Always keyed on the client IP, even if a (possibly stolen/expired)
    Authorization header is present on an unauthenticated endpoint."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class UserRateThrottle(SimpleRateThrottle):
    """Keyed on the authenticated user id (falls back to IP)."""

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        ident = user.pk if user is not None and user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class TargetRateThrottle(SimpleRateThrottle):
    """Keyed on a hash of the identifier submitted in the request body.
    Requests without a usable identifier are not counted here (the IP
    throttles and serializer validation still apply)."""

    target_fields = ("identifier", "phone")

    def get_cache_key(self, request, view):
        data = request.data
        if not isinstance(data, dict):
            return None
        for field in self.target_fields:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                digest = hashlib.sha256(normalize_target(value).encode("utf-8")).hexdigest()[:32]
                return self.cache_format % {"scope": self.scope, "ident": digest}
        return None


# ---- IP-keyed --------------------------------------------------------------
class LoginRateThrottle(IPRateThrottle):
    scope = "login"


class OTPRequestRateThrottle(IPRateThrottle):
    scope = "otp-request"


class OTPVerifyRateThrottle(IPRateThrottle):
    scope = "otp-verify"


class SensitiveRateThrottle(IPRateThrottle):
    scope = "sensitive"


# ---- identifier-keyed ------------------------------------------------------
class LoginAccountRateThrottle(TargetRateThrottle):
    """Caps password guesses per account regardless of how many IPs are used."""

    scope = "login-account"


class OTPTargetRateThrottle(TargetRateThrottle):
    """Caps OTP messages per phone/identifier (SMS cost + harassment)."""

    scope = "otp-target"


# ---- user-keyed ------------------------------------------------------------
class StudentAddRateThrottle(UserRateThrottle):
    scope = "student-add"
