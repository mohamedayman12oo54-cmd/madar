"""
OTP delivery: one place that knows HOW a code reaches a person.

Two channels, chosen by the person (teacher signup, student activation):
  * "phone" -> SMS through the backend named by settings.OTP_SMS_BACKEND
  * "email" -> Django's email backend (Gmail/any SMTP)

Failure policy: a backend that cannot deliver raises OTPDeliveryError. The
views decide what that means (flows where the person typed their own
destination tell them; flows that must not reveal whether an account exists
swallow it and rely on "resend").
"""
import logging
from importlib import import_module

from django.conf import settings
from django.core.mail import send_mail

log = logging.getLogger(__name__)


class OTPDeliveryError(Exception):
    pass


def mask_phone(phone: str) -> str:
    phone = phone or ""
    return ("•" * max(len(phone) - 4, 0)) + phone[-4:]


def mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    if not domain:
        return email or ""
    return f"{local[:2]}{'•' * max(len(local) - 2, 1)}@{domain}"


class ConsoleSMSBackend:
    """Development stand-in: logs that an SMS would be sent (never the code
    itself). Outside a DEBUG deployment it raises, so a missing provider is
    a visible failure instead of a flow that silently never delivers."""

    def send(self, phone: str, message: str) -> None:
        if not settings.OTP_SMS_CONSOLE_ALLOWED:
            raise OTPDeliveryError("No SMS provider configured (settings.OTP_SMS_BACKEND).")
        log.info("SMS (console backend, nothing sent) to %s", mask_phone(phone))


def _load_sms_backend():
    path = settings.OTP_SMS_BACKEND
    module, _, cls = path.rpartition(".")
    return getattr(import_module(module), cls)()


def _message(code: str) -> str:
    return f"رمز التحقق الخاص بك في مدار: {code}\nصالح لمدة 5 دقائق. لا تشاركه مع أي شخص."


def send_otp(channel: str, target: str, code: str) -> None:
    """Deliver `code` to `target` over `channel` or raise OTPDeliveryError."""
    try:
        if channel == "email":
            send_mail(
                subject="رمز التحقق من مدار",
                message=_message(code),
                from_email=None,  # DEFAULT_FROM_EMAIL
                recipient_list=[target],
                fail_silently=False,
            )
        else:
            _load_sms_backend().send(target, _message(code))
    except OTPDeliveryError:
        raise
    except Exception as exc:  # SMTP down, bad credentials, provider error...
        log.warning("OTP delivery over %s failed: %s", channel, exc.__class__.__name__)
        raise OTPDeliveryError(str(exc)) from exc


def destination_for(pending) -> str:
    """Where a pending flow's code must go. For password-reset flows `target`
    is whatever the person typed (maybe a local-format number), so the real
    destination is read from the account itself."""
    from .models import PendingAuth, User

    if pending.purpose in (PendingAuth.Purpose.TEACHER_RESET, PendingAuth.Purpose.STUDENT_RESET):
        user = User.objects.filter(pk=pending.payload.get("user_id")).first()
        if user:
            return (user.email if pending.channel == "email" else user.phone) or ""
        return ""
    return pending.target


def deliver(pending, code: str) -> bool:
    """Send `code` for `pending`. Returns False when there is nobody to send
    to (e.g. a reset requested for an unknown account — by design a silent no-op)."""
    dest = destination_for(pending)
    if not dest:
        return False
    send_otp(pending.channel, dest, code)
    return True
