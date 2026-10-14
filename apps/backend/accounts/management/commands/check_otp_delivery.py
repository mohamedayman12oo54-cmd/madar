"""Smoke-test OTP delivery with the CURRENT settings.

    python manage.py check_otp_delivery --email you@gmail.com
    python manage.py check_otp_delivery --phone 201001234567
    python manage.py check_otp_delivery --email you@gmail.com --phone 2010...

Sends a real message (code 000000, clearly labelled as a test) through the same
code path the signup / activation flows use, and reports exactly what would
make a real user see "تعذّر إرسال رمز التحقق".
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.delivery import OTPDeliveryError, mask_email, mask_phone, send_otp
from accounts.phones import PhoneError, canonical_phone


class Command(BaseCommand):
    help = "Sends a test OTP over email and/or SMS using the configured backends."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument("--phone")

    def handle(self, *args, **options):
        email, phone = options["email"], options["phone"]
        if not email and not phone:
            raise CommandError("Give --email and/or --phone.")

        if email:
            backend = settings.EMAIL_BACKEND
            self.stdout.write(f"Email backend: {backend}")
            if backend.endswith("console.EmailBackend"):
                self.stdout.write(self.style.WARNING(
                    "Console backend: the message is printed below, NOT delivered. "
                    "Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend to send for real."))
            elif backend.endswith("smtp.EmailBackend") and not (settings.EMAIL_HOST and settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD):
                raise CommandError("EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD must all be set.")
            self._try("email", email, mask_email(email))

        if phone:
            try:
                phone = canonical_phone(phone)
            except PhoneError as exc:
                raise CommandError(exc.message_ar)
            self.stdout.write(f"SMS backend: {settings.OTP_SMS_BACKEND}")
            self._try("phone", phone, mask_phone(phone))

    def _try(self, channel, target, shown):
        try:
            send_otp(channel, target, "000000")
        except OTPDeliveryError as exc:
            raise CommandError(f"{channel} delivery to {shown} FAILED: {exc}")
        self.stdout.write(self.style.SUCCESS(f"{channel} delivery to {shown}: accepted by the backend."))
