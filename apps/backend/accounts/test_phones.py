"""Country-aware mobile number validation (accounts/phones.py)."""
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from accounts.phones import COUNTRIES, PhoneError, canonical_phone, country_of
from accounts.testing import TestCase

VALID = {
    "+20 100 123 4567": "201001234567", "00201001234567": "201001234567", "+201001234567": "201001234567",
    "+٢٠ ١٠٠ ١٢٣ ٤٥٦٧": "201001234567",              # Arabic-Indic digits
    "+20 0100 123 4567": "201001234567",             # stray trunk 0 after the code
    "+966 55 123 4567": "966551234567", "+971 50 123 4567": "971501234567",
    "+965 5001 2345": "96550012345", "+962 79 012 3456": "962790123456",
    "+964 791 234 5678": "9647912345678", "+212 612 345 678": "212612345678",
}
INVALID = [
    "", "   ", "abc", "+20abc", "+20 1301234567", "+20 100123456", "+20 10012345678",   # Egypt: bad prefix / length
    "+966 4 123 4567", "+966 5123456", "+971 51 234 5678",                            # KSA / UAE
    "+999 123456789", "+1 202 555 0123",                                              # unsupported country
    "1001234567", "01001234567",                                                      # no country code (strict)
    "+20 100 123 4567; DROP TABLE", "+" + "2" * 40, "<script>",
]


class CanonicalPhoneTests(SimpleTestCase):
    def test_valid_numbers_normalise_to_one_canonical_form(self):
        for raw, expected in VALID.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonical_phone(raw), expected)

    def test_invalid_numbers_are_rejected_with_an_arabic_message(self):
        for raw in INVALID:
            with self.subTest(raw=raw):
                with self.assertRaises(PhoneError) as ctx:
                    canonical_phone(raw)
                self.assertTrue(ctx.exception.message_ar)

    def test_every_country_accepts_its_own_example_and_rejects_a_wrong_length(self):
        for c in COUNTRIES:
            with self.subTest(country=c.iso):
                self.assertEqual(canonical_phone("+" + c.dial + c.example), c.dial + c.example)
                self.assertEqual(country_of(c.dial + c.example).iso, c.iso)
                with self.assertRaises(PhoneError):
                    canonical_phone("+" + c.dial + c.example + "0")

    def test_dial_codes_are_prefix_free(self):
        dials = [c.dial for c in COUNTRIES]
        for a in dials:
            for b in dials:
                if a != b:
                    self.assertFalse(b.startswith(a), (a, b))

    def test_lenient_login_reads_local_numbers_as_egyptian_only(self):
        self.assertEqual(canonical_phone("01001234567", "EG"), "201001234567")
        self.assertEqual(canonical_phone("201001234567", "EG"), "201001234567")
        self.assertEqual(canonical_phone("+966551234567", "EG"), "966551234567")
        with self.assertRaises(PhoneError):
            canonical_phone("0551234567", "EG")  # a Saudi-looking local number is NOT guessed


class PhoneInApiTests(TestCase):
    def test_signup_rejects_wrong_country_format_and_accepts_arabic_digits(self):
        c = APIClient()
        base = {"name": "أحمد علي", "email": "p1@example.com", "password": "Str0ng!Pass", "password2": "Str0ng!Pass"}
        bad = c.post("/api/v1/auth/teacher/signup/", {**base, "phone": "+20 1301234567"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("phone", bad.json()["fields"])
        ok = c.post("/api/v1/auth/teacher/signup/", {**base, "phone": "+٢٠ ١٠٠ ١٢٣ ٤٥٦٧"})
        self.assertEqual(ok.status_code, 200, ok.content)

    def test_same_real_number_in_different_formats_is_one_account(self):
        from accounts.models import User

        User.objects.create_user(role="teacher", name="T", email="t@example.com", phone="201001234567", password="Str0ng!Pass", is_active=True)
        c = APIClient()
        for ident in ("+20 100 123 4567", "01001234567", "٠١٠٠١٢٣٤٥٦٧", "201001234567"):
            r = c.post("/api/v1/auth/teacher/login/", {"identifier": ident, "password": "Str0ng!Pass"})
            self.assertEqual(r.status_code, 200, ident)


class ThrottleHardeningTests(TestCase):
    def test_every_format_of_one_number_shares_one_throttle_bucket(self):
        from accounts.throttles import normalize_target

        keys = {normalize_target(x) for x in ("010 0123 4567", "+20 100 123 4567", "201001234567", "٠١٠٠١٢٣٤٥٦٧")}
        self.assertEqual(keys, {"201001234567"})

    def test_token_refresh_is_rate_limited(self):
        from unittest import mock

        from rest_framework.throttling import SimpleRateThrottle

        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"token-refresh": "2/hour"}):
            codes = [APIClient().post("/api/v1/auth/token/refresh/", {"refresh": "not-a-token"}).status_code for _ in range(3)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:2])


class LegacyPhoneMigrationTests(TestCase):
    """Accounts created before country-aware validation were stored as typed;
    the migration must make them log in again, and never guess."""

    def run_migration(self):
        import importlib

        from django.apps import apps

        importlib.import_module("accounts.migrations.0004_canonical_phones").canonicalize_phones(apps, None)

    def test_legacy_formats_become_canonical_and_can_log_in(self):
        from accounts.models import User

        pw = "Str0ng!Pass"
        a = User.objects.create_user(role="teacher", name="A", email="a@example.com", phone="01065692895", password=pw, is_active=True)
        b = User.objects.create_user(role="student", name="B", phone="1119998888", password=pw, is_active=True)
        c = User.objects.create_user(role="teacher", name="C", email="c@example.com", phone="201001234567", password=pw, is_active=True)
        self.run_migration()
        for user in (a, b, c):
            user.refresh_from_db()
        self.assertEqual((a.phone, b.phone, c.phone), ("201065692895", "201119998888", "201001234567"))
        self.assertEqual(APIClient().post("/api/v1/auth/teacher/login/", {"identifier": "01065692895", "password": pw}).status_code, 200)

    def test_unconvertible_and_colliding_numbers_are_left_alone(self):
        from accounts.models import User

        bad = User.objects.create_user(role="student", name="X", phone="123456789", password=None, is_active=False)
        keep = User.objects.create_user(role="student", name="K", phone="201065692895", password=None, is_active=False)
        dup = User.objects.create_user(role="student", name="D", phone="01065692895", password=None, is_active=False)
        self.run_migration()
        for u in (bad, keep, dup):
            u.refresh_from_db()
        self.assertEqual((bad.phone, keep.phone, dup.phone), ("123456789", "201065692895", "01065692895"))

    def test_is_idempotent(self):
        from accounts.models import User

        User.objects.create_user(role="teacher", name="A", email="a@example.com", phone="01065692895", password="Str0ng!Pass", is_active=True)
        self.run_migration()
        self.run_migration()
        self.assertEqual(User.objects.get().phone, "201065692895")
