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
import math
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import Throttled
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle

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

    target_fields = ("identifier", "phone", "email")

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


class BillingCheckoutRateThrottle(UserRateThrottle):
    """Each checkout creates a PaymentAttempt and an outbound call to the payment provider: cap per user
    so a stolen/abusive session cannot spray the provider (or fill the table) with sessions."""

    scope = "billing-checkout"


class BillingCancelRateThrottle(UserRateThrottle):
    scope = "billing-cancel"


class BillingStatusRateThrottle(UserRateThrottle):
    """Read endpoints incl. the post-checkout poll (the UI polls every 3 s for up to 3 min)."""

    scope = "billing-status"


class BillingWebhookRateThrottle(IPRateThrottle):
    """Bounds the CPU an unauthenticated caller can burn on HMAC checks. Deliberately generous: the
    provider retries from a handful of IPs, and a throttled (429) delivery is simply retried later."""

    scope = "billing-webhook"


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


class GuardianMessageRateThrottle(UserRateThrottle):
    scope = "guardian-message"


class PasswordChangeRateThrottle(UserRateThrottle):
    scope = "password-change"


class ScanRateThrottle(UserRateThrottle):
    """Badge scanning is a tight loop in a classroom (a whole group in a few
    minutes), so the cap is generous — it exists to stop a scripted attacker
    grinding tokens or replaying writes, not to slow a teacher down."""

    scope = "scan"


class ExamAnswerRateThrottle(UserRateThrottle):
    """Autosave while a student sits an exam: one write per answer, generous per minute."""

    scope = "exam-answer"


class ExamEventRateThrottle(UserRateThrottle):
    """Integrity signals from the exam page. Bounded so a script cannot flood the log."""

    scope = "exam-event"


# ---- guardian code login ---------------------------------------------------
class GuardianLoginRateThrottle(IPRateThrottle):
    scope = "guardian-login"


class GuardianPhoneRateThrottle(TargetRateThrottle):
    """Caps guesses of the student code for ONE guardian phone number."""

    scope = "guardian-phone"
    target_fields = ("phone",)


class GuardianCodeRateThrottle(SimpleRateThrottle):
    """Caps guesses of the guardian phone for ONE student code. Keyed on the
    normalised code (case/space/dash-insensitive, like the login itself) so
    \"ba5-n64\" and \"BA5N64\" share a bucket."""

    scope = "guardian-code"

    def get_cache_key(self, request, view):
        data = request.data
        raw = data.get("student_code") if isinstance(data, dict) else None
        if not isinstance(raw, str):
            return None
        code = "".join(ch for ch in raw.upper() if ch.isalnum())
        if not code:
            return None
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:32]
        return self.cache_format % {"scope": self.scope, "ident": digest}


class GuardianReplyRateThrottle(SimpleRateThrottle):
    """A guardian's replies to the teacher. A guardian has no user row (their `pk` is None, which would put
    every guardian in ONE shared bucket), so the bucket is the child's enrolment."""

    scope = "guardian-reply"

    def get_cache_key(self, request, view):
        enrollment_id = getattr(getattr(request, "user", None), "enrollment_id", None)
        if enrollment_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": enrollment_id}


# ---- session self check-in (public, unauthenticated) -------------------------
class CheckinIPRateThrottle(IPRateThrottle):
    """A whole class may share one NAT address, so this is generous; the
    per-phone and per-link caps below are what stop guessing."""

    scope = "checkin-ip"


class CheckinPhoneRateThrottle(TargetRateThrottle):
    """Caps attempts on ONE phone number (someone trying to check a classmate in)."""

    scope = "checkin-phone"
    target_fields = ("phone",)


class CheckinLinkRateThrottle(SimpleRateThrottle):
    """Caps ALL attempts on one check-in link, whoever sends them - this is what makes the
    6-digit code unguessable within the link's lifetime."""

    scope = "checkin-link"

    def get_cache_key(self, request, view):
        token = getattr(view, "kwargs", {}).get("token", "")
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
        return self.cache_format % {"scope": self.scope, "ident": digest}


# ---- student self-registration (public, unauthenticated) ----------------------
class RegisterIPRateThrottle(IPRateThrottle):
    """A class may share one NAT address, so this is generous; the link and phone caps stop abuse."""

    scope = "register-ip"


class RegisterPhoneRateThrottle(TargetRateThrottle):
    """Caps submissions for ONE phone number (someone enrolling a stranger's number over and over)."""

    scope = "register-phone"
    target_fields = ("phone",)


class RegisterLinkRateThrottle(SimpleRateThrottle):
    """Caps ALL submissions through one link, whoever sends them: a leaked link cannot be used to
    flood the roster, and a teacher's real class still fits."""

    scope = "register-link"

    def get_cache_key(self, request, view):
        token = getattr(view, "kwargs", {}).get("token", "")
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
        return self.cache_format % {"scope": self.scope, "ident": digest}


# ---- attempts, then a cooldown ---------------------------------------------
class AttemptCooldownThrottle(BaseThrottle):
    """"N tries, then wait": the first `limit` requests go through; the moment the last allowed one is
    used a cooldown of `cooldown` seconds starts, during which every request is refused with the exact
    time left (the UI shows it as a timer). When it ends the allowance is full again.

    Unlike the sliding-window rates above this is a lock the person can SEE and wait out, which is what a
    teacher needs after several failed uploads. Keyed on the user; settings (`limit_setting`,
    `cooldown_setting`) decide the numbers so ops can tune them without a deploy of code."""

    scope = "attempt-cooldown"
    limit_setting = "ATTEMPT_COOLDOWN_LIMIT"
    cooldown_setting = "ATTEMPT_COOLDOWN_SECONDS"
    default_limit = 5
    default_cooldown = 300

    def __init__(self):
        self.limit = max(1, int(getattr(settings, self.limit_setting, self.default_limit)))
        self.cooldown = max(1, int(getattr(settings, self.cooldown_setting, self.default_cooldown)))
        self._wait = None

    def _ident(self, request):
        user = getattr(request, "user", None)
        return user.pk if user is not None and user.is_authenticated else self.get_ident(request)

    def allow_request(self, request, view):
        ident = self._ident(request)
        lock_key = f"throttle_{self.scope}_lock_{ident}"
        count_key = f"throttle_{self.scope}_count_{ident}"
        now = time.time()

        locked_until = cache.get(lock_key)
        if locked_until and locked_until > now:
            self._wait = locked_until - now
            return False

        # The counter forgets itself after one cooldown of silence, so slow, occasional tries never add up.
        if cache.add(count_key, 1, timeout=self.cooldown):
            count = 1
        else:
            try:
                count = cache.incr(count_key)
            except ValueError:  # expired between add() and incr()
                cache.set(count_key, 1, timeout=self.cooldown)
                count = 1

        if count >= self.limit:  # that was the last allowed try: the cooldown starts now
            cache.set(lock_key, now + self.cooldown, timeout=self.cooldown)
            cache.delete(count_key)
        return True

    def wait(self):
        return self._wait


class AttemptCooldown(Throttled):
    """429 whose body says how long to wait (code `upload_cooldown`, `retry_after_seconds`)."""

    default_code = "upload_cooldown"

    def __init__(self, wait, limit):
        seconds = max(1, int(math.ceil(wait or 1)))
        minutes, rest = divmod(seconds, 60)
        left = f"{minutes}:{rest:02d}"
        super().__init__(
            wait=seconds,
            detail=f"استخدمت محاولات الرفع المتاحة ({limit}). يمكنك المحاولة مرة أخرى بعد {left} دقيقة.",
        )
        self.limit = limit


class VideoUploadStartThrottle(AttemptCooldownThrottle):
    """Starting a video upload: ATTEMPTS tries, then a COOLDOWN (defaults 5 and 5 minutes)."""

    scope = "video-upload-start"
    limit_setting = "VIDEO_UPLOAD_ATTEMPTS"
    cooldown_setting = "VIDEO_UPLOAD_COOLDOWN_SECONDS"


class VideoUploadChunkThrottle(UserRateThrottle):
    """The chunks of an upload that is already running. They are NOT upload attempts, so they must not eat the
    attempts allowance (a 1 GB video is ~60 chunks); this only stops a runaway client."""

    scope = "video-upload-chunk"
