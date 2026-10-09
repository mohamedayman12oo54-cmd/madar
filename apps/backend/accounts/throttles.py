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
    from .phones import try_canonical_phone

    value = (raw or "").strip()
    if "@" in value:
        return value.lower()
    # Canonical form first: "010 1234 5678", "+20 10 1234 5678" and
    # "201012345678" must all share ONE bucket, or varying the format would
    # mint a fresh throttle allowance per request.
    return try_canonical_phone(value, default_country="EG") or normalize_phone(value) or value.lower()


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


class AISubmitRateThrottle(UserRateThrottle):
    """AI submissions cost real compute/money once a real provider is wired
    in — cap them per teacher."""

    scope = "ai-submit"


class RefreshRateThrottle(IPRateThrottle):
    """Token refresh is unauthenticated by nature; cap it per IP (generous,
    because a whole classroom can share one NAT address)."""

    scope = "token-refresh"


class BroadcastRateThrottle(UserRateThrottle):
    scope = "broadcast"


class PasswordChangeRateThrottle(UserRateThrottle):
    scope = "password-change"


class ScanRateThrottle(UserRateThrottle):
    """Badge scanning is a tight loop in a classroom (a whole group in a few
    minutes), so the cap is generous — it exists to stop a scripted attacker
    grinding tokens or replaying writes, not to slow a teacher down."""

    scope = "scan"
