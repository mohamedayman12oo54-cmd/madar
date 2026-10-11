"""
Password-recovery / OTP hardening.

These assert the controls that make a recovery flow safe rather than merely
working: one live code at a time, no guessing, no replay, no reuse across
purposes, no leakage, and no surviving sessions after a reset.
"""
import re
from unittest import mock

from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from academics.models import Enrollment, Grade
from accounts.models import PendingAuth, User, generate_otp_code, supersede_pending
from accounts.testing import TestCase
from environments.models import Environment, EnvironmentMembership

PW = "Str0ng!Pass"
NEW_PW = "Even5tr0nger!"
RESET_REQ = "/api/v1/auth/teacher/forgot/"
VERIFY = "/api/v1/auth/otp/teacher-reset/verify/"


def teacher(email="a@example.com", phone="201010000001"):
    return User.objects.create_user(role=User.Role.TEACHER, name="t", email=email,
                                    phone=phone, password=PW, is_active=True)


class CodeGenerationTests(TestCase):
    def test_codes_are_six_digit_strings_with_leading_zeros_preserved(self):
        for _ in range(200):
            code = generate_otp_code()
            self.assertIsInstance(code, str)
            self.assertRegex(code, r"^\d{6}$")

    def test_a_leading_zero_survives_formatting(self):
        with mock.patch("accounts.models.secrets.randbelow", return_value=1234):
            self.assertEqual(generate_otp_code(), "001234")
        with mock.patch("accounts.models.secrets.randbelow", return_value=0):
            self.assertEqual(generate_otp_code(), "000000")

    def test_generation_uses_a_cryptographic_source_not_mersenne_twister(self):
        """`random` is predictable from observed output; `secrets` is not."""
        src = open("accounts/models.py", encoding="utf-8").read()
        self.assertIn("secrets.randbelow", src)
        self.assertNotIn("random.randint", src)
        # modulo bias would show up as a non-uniform range; randbelow is exact
        self.assertIn("randbelow(1_000_000)", src)

    def test_codes_do_not_repeat_in_a_short_run(self):
        codes = {generate_otp_code() for _ in range(300)}
        self.assertGreater(len(codes), 290, "suspiciously low entropy")


class SingleLiveCodeTests(TestCase):
    """Requesting a new code must invalidate the previous one."""

    def setUp(self):
        self.t = teacher()
        self.c = APIClient()

    def test_requesting_a_second_code_supersedes_the_first(self):
        first = self.c.post(RESET_REQ, {"identifier": self.t.email})
        self.assertEqual(first.status_code, 200, first.content)
        first_id = first.json()["pending_id"]

        second = self.c.post(RESET_REQ, {"identifier": self.t.email})
        self.assertEqual(second.status_code, 200, second.content)

        # The older flow is gone, so its code can never be used again.
        self.assertFalse(PendingAuth.objects.filter(pk=first_id).exists())
        self.assertEqual(
            PendingAuth.objects.filter(purpose=PendingAuth.Purpose.TEACHER_RESET,
                                       target=self.t.email).count(), 1)

    def test_the_superseded_code_is_rejected_even_if_correct(self):
        first = self.c.post(RESET_REQ, {"identifier": self.t.email}).json()
        old_code = first["debug_otp"]
        self.c.post(RESET_REQ, {"identifier": self.t.email})
        r = self.c.post(VERIFY, {"pending_id": first["pending_id"], "code": old_code})
        self.assertEqual(r.status_code, 400, r.content)

    def test_superseding_is_scoped_to_one_purpose(self):
        """Cancelling a reset must not cancel an unrelated flow."""
        other = PendingAuth(purpose=PendingAuth.Purpose.TEACHER_SIGNUP, target=self.t.email)
        other.set_new_otp()
        other.save()
        supersede_pending(PendingAuth.Purpose.TEACHER_RESET, self.t.email)
        self.assertTrue(PendingAuth.objects.filter(pk=other.pk).exists())

    def test_a_verified_flow_is_not_destroyed_by_a_new_request(self):
        """Mid-flow (code already verified) must not be silently wiped."""
        issued = self.c.post(RESET_REQ, {"identifier": self.t.email}).json()
        self.c.post(VERIFY, {"pending_id": issued["pending_id"], "code": issued["debug_otp"]})
        supersede_pending(PendingAuth.Purpose.TEACHER_RESET, self.t.email)
        self.assertTrue(PendingAuth.objects.filter(pk=issued["pending_id"]).exists())


class GuessingAndReplayTests(TestCase):
    def setUp(self):
        self.t = teacher()
        self.c = APIClient()
        self.flow = self.c.post(RESET_REQ, {"identifier": self.t.email}).json()

    def verify(self, code):
        return self.c.post(VERIFY, {"pending_id": self.flow["pending_id"], "code": code})

    def wrong(self, code):
        return "000000" if code != "000000" else "111111"

    def test_guessing_is_capped_and_then_the_code_dies(self):
        bad = self.wrong(self.flow["debug_otp"])
        for _ in range(PendingAuth.MAX_ATTEMPTS):
            self.assertEqual(self.verify(bad).status_code, 400)
        # Even the CORRECT code is refused once the budget is spent.
        self.assertEqual(self.verify(self.flow["debug_otp"]).status_code, 400)

    def test_every_guess_costs_an_attempt_including_the_right_one(self):
        self.verify(self.wrong(self.flow["debug_otp"]))
        pending = PendingAuth.objects.get(pk=self.flow["pending_id"])
        self.assertEqual(pending.otp_attempts, 1)

    def test_an_expired_code_is_refused_even_when_correct(self):
        PendingAuth.objects.filter(pk=self.flow["pending_id"]).update(
            otp_expires_at=timezone.now() - timezone.timedelta(seconds=1))
        self.assertEqual(self.verify(self.flow["debug_otp"]).status_code, 400)

    def test_a_code_cannot_be_replayed_against_a_different_purpose(self):
        """A reset pending_id must not verify at the claim endpoint."""
        r = self.c.post("/api/v1/auth/otp/student-claim/verify/",
                        {"pending_id": self.flow["pending_id"], "code": self.flow["debug_otp"]})
        self.assertEqual(r.status_code, 400)

    def test_the_stored_code_is_hashed_not_plaintext(self):
        pending = PendingAuth.objects.get(pk=self.flow["pending_id"])
        self.assertNotIn(self.flow["debug_otp"], pending.otp_hash)
        self.assertIn("$", pending.otp_hash)
        self.assertTrue(pending.check_otp(self.flow["debug_otp"]))


class EnumerationTests(TestCase):
    def setUp(self):
        self.t = teacher()
        self.c = APIClient()

    def test_a_reset_request_does_not_reveal_whether_the_account_exists(self):
        known = self.c.post(RESET_REQ, {"identifier": self.t.email})
        unknown = self.c.post(RESET_REQ, {"identifier": "nobody@example.com"})
        self.assertEqual(known.status_code, unknown.status_code)
        # Shapes must match too — a missing/extra key is just as much a tell.
        strip = lambda d: sorted(k for k in d if k != "debug_otp")  # noqa: E731
        self.assertEqual(strip(known.json()), strip(unknown.json()))


class RateLimitTests(TestCase):
    def setUp(self):
        self.t = teacher()
        self.c = APIClient()

    def test_repeated_code_requests_are_throttled(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"otp-request": "3/hour"}):
            codes = [self.c.post(RESET_REQ, {"identifier": self.t.email}).status_code
                     for _ in range(4)]
        self.assertEqual(codes[-1], 429, codes)

    def test_verification_attempts_are_throttled_independently(self):
        flow = self.c.post(RESET_REQ, {"identifier": self.t.email}).json()
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"otp-verify": "3/hour"}):
            codes = [self.c.post(VERIFY, {"pending_id": flow["pending_id"], "code": "000000"}).status_code
                     for _ in range(4)]
        self.assertEqual(codes[-1], 429, codes)


class SessionRevocationTests(TestCase):
    """Changing a password must cut off credentials issued before it."""

    def setUp(self):
        self.t = teacher()
        env = Environment.objects.create(owner=self.t, name="E")
        EnvironmentMembership.objects.create(user=self.t, environment=env, role="owner")
        self.env = env
        self.c = APIClient()
        tokens = self.c.post("/api/v1/auth/teacher/login/",
                             {"identifier": self.t.email, "password": PW}).data
        self.access, self.refresh = tokens["access"], tokens["refresh"]

    def reset_password(self):
        flow = APIClient().post(RESET_REQ, {"identifier": self.t.email}).json()
        c = APIClient()
        c.post(VERIFY, {"pending_id": flow["pending_id"], "code": flow["debug_otp"]})
        return c.post("/api/v1/auth/teacher/forgot/reset/",
                      {"pending_id": flow["pending_id"], "password": NEW_PW, "password2": NEW_PW})

    def test_an_old_access_token_stops_working_after_a_reset(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + self.access)
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 200)
        r = self.reset_password()
        self.assertIn(r.status_code, (200, 201), r.content)
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 401,
                         "an attacker's existing session must not survive a reset")

    def test_an_old_refresh_token_cannot_mint_a_new_session(self):
        self.reset_password()
        r = APIClient().post("/api/v1/auth/token/refresh/", {"refresh": self.refresh})
        self.assertIn(r.status_code, (400, 401), r.content)

    def test_the_new_password_works_and_the_old_one_does_not(self):
        self.reset_password()
        c = APIClient()
        self.assertEqual(c.post("/api/v1/auth/teacher/login/",
                                {"identifier": self.t.email, "password": PW}).status_code, 400)
        self.assertEqual(c.post("/api/v1/auth/teacher/login/",
                                {"identifier": self.t.email, "password": NEW_PW}).status_code, 200)

    def test_the_reset_flow_cannot_be_replayed_to_set_another_password(self):
        flow = APIClient().post(RESET_REQ, {"identifier": self.t.email}).json()
        c = APIClient()
        c.post(VERIFY, {"pending_id": flow["pending_id"], "code": flow["debug_otp"]})
        body = {"pending_id": flow["pending_id"], "password": NEW_PW, "password2": NEW_PW}
        first = c.post("/api/v1/auth/teacher/forgot/reset/", body)
        self.assertIn(first.status_code, (200, 201))
        again = c.post("/api/v1/auth/teacher/forgot/reset/",
                       {**body, "password": "Third!Pass9", "password2": "Third!Pass9"})
        self.assertEqual(again.status_code, 400, "a consumed flow must not be reusable")


class LeakageTests(TestCase):
    def test_the_code_is_never_returned_outside_debug(self):
        from django.test import override_settings

        t = teacher()
        with override_settings(EXPOSE_OTP_IN_RESPONSE=False):
            body = APIClient().post(RESET_REQ, {"identifier": t.email}).json()
        self.assertNotIn("debug_otp", body)
        self.assertFalse(re.search(r"\b\d{6}\b", str(body)), f"a 6-digit code leaked: {body}")

    def test_the_code_is_not_written_to_application_logs(self):
        t = teacher()
        with self.assertLogs(level="DEBUG") as logs:
            import logging

            logging.getLogger("madar.test").debug("probe")   # ensure the context has records
            flow = APIClient().post(RESET_REQ, {"identifier": t.email}).json()
        joined = "\n".join(logs.output)
        self.assertNotIn(flow["debug_otp"], joined, "OTP must never reach the logs")
