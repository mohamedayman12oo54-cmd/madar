"""Progressive lock-out: 6 wrong tries -> 5 min lock -> then 5 tries -> 5 min lock -> ..."""
from unittest import mock

from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from accounts import lockout
from accounts.models import User

URL = "/api/v1/auth/teacher/login/"
PHONE = "201001234567"


# The request-rate throttles (10/min per IP ...) are tested elsewhere; here only the lock-out policy matters.
@mock.patch.dict(
    "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
    {k: "100000/min" for k in ("login", "login-account", "otp-verify", "sensitive")},
)
class LockoutTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(phone=PHONE, role=User.Role.TEACHER, name="م", password="Right-Pass-123!", email="t@example.com")
        self.user.is_active = True
        self.user.save()
        self.now = 1_000_000.0
        p = mock.patch("accounts.lockout.time.time", side_effect=lambda: self.now)
        p.start()
        self.addCleanup(p.stop)

    def bad(self):
        return APIClient().post(URL, {"identifier": "t@example.com", "password": "nope"}, format="json")

    def good(self):
        return APIClient().post(URL, {"identifier": "t@example.com", "password": "Right-Pass-123!"}, format="json")

    def test_first_round_allows_six_wrong_tries_then_locks_five_minutes(self):
        for _ in range(6):
            self.assertEqual(self.bad().status_code, 400)
        r = self.bad()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["code"], "locked_out")
        # Even the RIGHT password is refused while locked.
        self.assertEqual(self.good().status_code, 429)
        self.now += lockout.LOCK_SECONDS + 1
        self.assertEqual(self.good().status_code, 200)

    def test_later_rounds_allow_five_tries(self):
        for _ in range(6):
            self.bad()
        self.now += lockout.LOCK_SECONDS + 1
        for _ in range(5):
            self.assertEqual(self.bad().status_code, 400)
        self.assertEqual(self.bad().status_code, 429)
        self.now += lockout.LOCK_SECONDS + 1
        for _ in range(5):
            self.assertEqual(self.bad().status_code, 400)
        self.assertEqual(self.bad().status_code, 429)

    def test_success_resets_the_counters(self):
        for _ in range(5):
            self.bad()
        self.assertEqual(self.good().status_code, 200)
        codes = [self.bad().status_code for _ in range(6)]
        self.assertEqual(codes, [400] * 6)

    def test_lock_is_per_account_and_does_not_reveal_existence(self):
        for _ in range(6):
            APIClient().post(URL, {"identifier": "ghost@example.com", "password": "x"}, format="json")
        r = APIClient().post(URL, {"identifier": "ghost@example.com", "password": "x"}, format="json")
        self.assertEqual(r.status_code, 429)  # same behaviour as a real account
        self.assertEqual(self.good().status_code, 200)  # other accounts unaffected

    def test_retry_after_is_reported(self):
        for _ in range(6):
            self.bad()
        body = self.bad().json()
        self.assertGreater(body["retry_after_seconds"], 0)
        self.assertIn("دقائق", body["detail"])
