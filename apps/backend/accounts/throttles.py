from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    scope = "login"


class OTPRequestRateThrottle(ScopedRateThrottle):
    scope = "otp-request"


class OTPVerifyRateThrottle(ScopedRateThrottle):
    scope = "otp-verify"


class SensitiveRateThrottle(ScopedRateThrottle):
    scope = "sensitive"
