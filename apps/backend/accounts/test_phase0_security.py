"""
Phase 0 security regression tests.

Each class is tagged with the finding it guards (S1..S7). They exercise the
real HTTP endpoints, and several were written to FAIL against the pre-Phase-0
code (marked "regression").
"""
from unittest import mock

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import PendingAuth, User
from accounts.testing import TestCase
from environments.models import Environment, EnvironmentMembership

PW = "Str0ng!Pass"
NEW_PW = "N3w!Passw0rd"
LOGIN = "/api/v1/auth/teacher/login/"


def make_teacher(email="t@example.com", phone="201001111111"):
    return User.objects.create_user(
        role=User.Role.TEACHER, name="T", email=email, phone=phone,
        password=PW, is_active=True, is_verified=True,
    )


def make_student(phone="201002222222", active=True):
    return User.objects.create_user(
        role=User.Role.STUDENT, name="S", phone=phone, password=PW if active else None,
        is_active=active, is_verified=active,
    )


def make_pending(purpose, payload=None, target="x", verified=False):
    """Create a PendingAuth with a KNOWN otp (works regardless of DEBUG)."""
    p = PendingAuth(purpose=purpose, payload=payload or {}, target=target)
    code = p.set_new_otp()
    p.verified = verified
    p.save()
    return p, code


def login(client, identifier, password=PW, path=LOGIN, **extra):
    return client.post(path, {"identifier": identifier, "password": password}, **extra)


# ============================================================ S1 throttling ==
class ThrottlingIsEnforcedTests(TestCase):
    """S1 — regression: before Phase 0 NO endpoint was ever throttled
    (ScopedRateThrottle without a view-level scope allows everything)."""

    def setUp(self):
        self.client = APIClient()

    def test_login_ip_limit_returns_429_on_11th_attempt(self):
        # A different identifier each time so only the per-IP limit can trigger.
        codes = [login(self.client, f"nobody{i}@example.com").status_code for i in range(11)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)

    def test_every_login_endpoint_is_throttled(self):
        for path, field in (
            ("/api/v1/auth/team/login/", "identifier"),
            ("/api/v1/auth/teacher/login/", "identifier"),
            ("/api/v1/auth/student/login/", "phone"),
        ):
            with self.subTest(path=path):
                from django.core.cache import cache
                cache.clear()
                last = None
                for i in range(11):
                    last = self.client.post(path, {field: f"2010000000{i:02d}", "password": "x"})
                self.assertEqual(last.status_code, 429, path)
                self.assertEqual(last.data["code"], "throttled")

    def test_login_account_limit_holds_across_many_ips(self):
        """A botnet rotating source IPs still gets only 20 guesses/hour per account."""
        make_teacher()
        codes = [
            login(self.client, "t@example.com", "wrong", REMOTE_ADDR=f"10.9.{i // 200}.{i % 200 + 1}").status_code
            for i in range(21)
        ]
        self.assertEqual(codes[:20], [400] * 20)
        self.assertEqual(codes[20], 429)

    def test_otp_request_limited_per_ip(self):
        codes = [
            self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": f"2011000000{i:02d}"}).status_code
            for i in range(6)
        ]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)

    def test_otp_request_limited_per_phone_across_ips(self):
        """SMS-bombing one number from many IPs is capped, whether or not
        the number belongs to an account (no enumeration signal)."""
        make_teacher(phone="201003333333")
        for phone in ("201003333333", "201009999999"):  # registered / unregistered
            with self.subTest(phone=phone):
                from django.core.cache import cache
                cache.clear()
                codes = [
                    self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": phone},
                                     REMOTE_ADDR=f"10.8.0.{i + 1}").status_code
                    for i in range(6)
                ]
                self.assertEqual(codes, [200, 200, 200, 200, 200, 429])

    def test_otp_verify_limited_per_ip(self):
        import uuid
        codes = [
            self.client.post("/api/v1/auth/otp/teacher-reset/verify/",
                             {"pending_id": str(uuid.uuid4()), "code": "000000"}).status_code
            for i in range(11)
        ]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)

    def test_signup_start_limited_per_phone(self):
        payload = {"name": "n", "email": "a@example.com", "phone": "201004444444", "password": PW, "password2": PW}
        codes = []
        for i in range(6):
            payload["email"] = f"a{i}@example.com"
            codes.append(self.client.post("/api/v1/auth/teacher/signup/", payload, REMOTE_ADDR=f"10.7.0.{i + 1}").status_code)
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)

    def test_throttle_response_shape(self):
        for i in range(11):
            r = login(self.client, f"n{i}@example.com")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.data["code"], "throttled")
        self.assertIn("retry_after_seconds", r.data)

    def test_throttle_works_with_the_production_database_cache(self):
        """Same behaviour on the shared DB cache used when DEBUG=False."""
        from django.core.management import call_command
        db_cache = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "madar_cache"}}
        with override_settings(CACHES=db_cache):
            call_command("createcachetable", verbosity=0)
            codes = [login(self.client, f"db{i}@example.com").status_code for i in range(11)]
        self.assertEqual(codes[10], 429)


# ================================================= S2 client-IP / proxy trust ==
class ProxyTrustTests(TestCase):
    """S2 — X-Forwarded-For must not be a way around rate limits."""

    def setUp(self):
        self.client = APIClient()

    def test_spoofed_xff_does_not_evade_throttle_by_default(self):
        """regression: rotating X-Forwarded-For gave every request a fresh bucket."""
        codes = [
            login(self.client, f"x{i}@example.com", HTTP_X_FORWARDED_FOR=f"203.0.113.{i}").status_code
            for i in range(11)
        ]
        self.assertEqual(codes[10], 429)

    def test_default_num_proxies_is_zero(self):
        self.assertEqual(settings.REST_FRAMEWORK["NUM_PROXIES"], 0)

    def test_with_one_trusted_proxy_only_the_proxy_appended_address_counts(self):
        drf = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
        with override_settings(REST_FRAMEWORK=drf):
            # Attacker prepends fake addresses; the trusted proxy appends the
            # real client address last. Same real client -> same bucket.
            codes = [
                login(self.client, f"x{i}@example.com",
                      HTTP_X_FORWARDED_FOR=f"198.51.100.{i}, 192.0.2.50").status_code
                for i in range(11)
            ]
            self.assertEqual(codes[10], 429)
            # A genuinely different client (different appended address) is unaffected.
            other = login(self.client, "y@example.com", HTTP_X_FORWARDED_FOR="198.51.100.1, 192.0.2.99")
            self.assertEqual(other.status_code, 400)


# ==================================================== S3 (server) rotation ==
class RefreshRotationContractTests(TestCase):
    """S3 — the frontend fix relies on this server contract: every refresh
    returns a NEW refresh token and blacklists the one that was used."""

    def test_refresh_returns_new_refresh_and_old_one_is_dead(self):
        make_teacher()
        c = APIClient()
        tokens = login(c, "t@example.com").data
        r1 = c.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]})
        self.assertEqual(r1.status_code, 200)
        self.assertIn("refresh", r1.data)
        self.assertNotEqual(r1.data["refresh"], tokens["refresh"])
        # replaying the old refresh token is rejected...
        self.assertEqual(c.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)
        # ...while the rotated one keeps the session alive
        self.assertEqual(c.post("/api/v1/auth/token/refresh/", {"refresh": r1.data["refresh"]}).status_code, 200)


# ================================================ S4 password reset revokes ==
class PasswordResetRevokesSessionsTests(TestCase):
    """S4 — regression: a reset left old refresh AND access tokens working."""

    def _reset(self, client, purpose, user, flow):
        p, code = make_pending(purpose, {"user_id": user.id}, target="x")
        ok = client.post(f"/api/v1/auth/otp/{flow}/verify/", {"pending_id": str(p.id), "code": code})
        self.assertEqual(ok.status_code, 200)
        path = "/api/v1/auth/teacher/forgot/reset/" if flow == "teacher-reset" else "/api/v1/auth/student/forgot/reset/"
        return client.post(path, {"pending_id": str(p.id), "password": NEW_PW, "password2": NEW_PW})

    def _assert_revoked(self, attacker, tokens):
        stolen = APIClient()
        stolen.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.assertEqual(stolen.get("/api/v1/auth/me/").status_code, 401, "old ACCESS token must stop working")
        self.assertEqual(
            attacker.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}).status_code, 401,
            "old REFRESH token must stop working",
        )

    def test_teacher_reset_revokes_existing_sessions(self):
        user = make_teacher()
        c = APIClient()
        tokens = login(c, "t@example.com").data
        me = APIClient(); me.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.assertEqual(me.get("/api/v1/auth/me/").status_code, 200)  # sanity: valid before reset

        r = self._reset(APIClient(), PendingAuth.Purpose.TEACHER_RESET, user, "teacher-reset")
        self.assertEqual(r.status_code, 200)
        self._assert_revoked(APIClient(), tokens)

        # the new password works and yields a working session
        fresh = login(APIClient(), "t@example.com", NEW_PW)
        self.assertEqual(fresh.status_code, 200)
        ok = APIClient(); ok.credentials(HTTP_AUTHORIZATION="Bearer " + fresh.data["access"])
        self.assertEqual(ok.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(login(APIClient(), "t@example.com", PW).status_code, 400)

    def test_student_reset_revokes_existing_sessions(self):
        user = make_student()
        c = APIClient()
        tokens = c.post("/api/v1/auth/student/login/", {"phone": user.phone, "password": PW}).data
        r = self._reset(APIClient(), PendingAuth.Purpose.STUDENT_RESET, user, "student-reset")
        self.assertEqual(r.status_code, 200)
        self._assert_revoked(APIClient(), tokens)

    def test_revocation_only_affects_the_reset_account(self):
        victim, bystander = make_teacher(), make_teacher("b@example.com", "201005555555")
        bt = login(APIClient(), "b@example.com").data
        self._reset(APIClient(), PendingAuth.Purpose.TEACHER_RESET, victim, "teacher-reset")
        other = APIClient(); other.credentials(HTTP_AUTHORIZATION="Bearer " + bt["access"])
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(APIClient().post("/api/v1/auth/token/refresh/", {"refresh": bt["refresh"]}).status_code, 200)

    def test_pending_reset_id_is_single_use(self):
        user = make_teacher()
        p, code = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": user.id})
        c = APIClient()
        c.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": str(p.id), "code": code})
        body = {"pending_id": str(p.id), "password": NEW_PW, "password2": NEW_PW}
        self.assertEqual(c.post("/api/v1/auth/teacher/forgot/reset/", body).status_code, 200)
        self.assertEqual(c.post("/api/v1/auth/teacher/forgot/reset/", body).status_code, 400)

    def test_session_version_bump_invalidates_access_tokens_immediately(self):
        user = make_teacher()
        tokens = login(APIClient(), "t@example.com").data
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 200)
        User.objects.filter(pk=user.pk).update(session_version=5)
        r = c.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, 401)

    def test_legacy_tokens_without_sv_claim_still_work_until_revoked(self):
        """Tokens minted before this release have no `sv` claim (== version 0)."""
        user = make_teacher()
        legacy = RefreshToken.for_user(user)  # no "sv"
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION="Bearer " + str(legacy.access_token))
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 200)
        User.objects.filter(pk=user.pk).update(session_version=1)
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 401)


class LogoutRevokesRefreshTokenTests(TestCase):
    def test_logout_works_without_a_valid_access_token(self):
        """regression: with an expired access token logout returned 401 and the
        refresh token stayed alive."""
        make_teacher()
        tokens = login(APIClient(), "t@example.com").data
        anon = APIClient()  # no Authorization header at all
        self.assertEqual(anon.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}).status_code, 205)
        self.assertEqual(anon.post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_logout_rejects_garbage_and_missing_tokens(self):
        c = APIClient()
        self.assertEqual(c.post("/api/v1/auth/logout/", {"refresh": "not-a-token"}).status_code, 400)
        self.assertEqual(c.post("/api/v1/auth/logout/", {}).status_code, 400)
        self.assertEqual(c.post("/api/v1/auth/logout/", {"refresh": 123}).status_code, 400)


# ==================================================== S6 OTP atomic + resend ==
class OTPAtomicityAndResendLimitTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # These tests exercise the PER-FLOW limits (attempts / resends); lift
        # the per-IP throttles so they cannot mask them.
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"otp-verify": "10000/hour", "otp-request": "10000/hour"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _verify(self, p, code):
        return self.client.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": str(p.id), "code": code})

    def _resend(self, p):
        return self.client.post("/api/v1/auth/otp/teacher-reset/resend/", {"pending_id": str(p.id)})

    def test_lost_race_for_the_last_attempt_cannot_verify(self):
        """regression: verification was read-modify-write, so N parallel guesses
        could all pass the `attempts < MAX` check. Here another request takes the
        LAST attempt after this one passed the pre-check; a correct code must
        still be refused."""
        p, code = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": 1})
        PendingAuth.objects.filter(pk=p.pk).update(otp_attempts=PendingAuth.MAX_ATTEMPTS - 1)

        def rival_takes_last_attempt(self_):
            PendingAuth.objects.filter(pk=self_.pk).update(otp_attempts=PendingAuth.MAX_ATTEMPTS)
            return False  # "not expired"

        with mock.patch.object(PendingAuth, "is_otp_expired", rival_takes_last_attempt):
            r = self._verify(p, code)
        self.assertEqual(r.status_code, 400)
        p.refresh_from_db()
        self.assertFalse(p.verified)

    def test_every_guess_consumes_an_attempt_and_locks_after_max(self):
        p, code = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": 1})
        for _ in range(PendingAuth.MAX_ATTEMPTS):
            self.assertEqual(self._verify(p, "000000" if code != "000000" else "111111").status_code, 400)
        locked = self._verify(p, code)  # even the CORRECT code is refused now
        self.assertEqual(locked.status_code, 400)
        p.refresh_from_db()
        self.assertFalse(p.verified)
        self.assertEqual(p.otp_attempts, PendingAuth.MAX_ATTEMPTS)

    def test_correct_code_verifies(self):
        p, code = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": 1})
        r = self._verify(p, code)
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertTrue(p.verified)

    def test_resend_is_capped_and_count_is_never_reset(self):
        """regression: resend was unlimited and reset the attempt counter."""
        p, _ = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": 1})
        for _ in range(PendingAuth.MAX_RESENDS):
            self.assertEqual(self._resend(p).status_code, 200)
        over = self._resend(p)
        self.assertEqual(over.status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.resend_count, PendingAuth.MAX_RESENDS)

    def test_total_guess_budget_is_bounded_across_resends(self):
        """An attacker who guesses, resends, guesses, resends... gets exactly
        MAX_ATTEMPTS * (MAX_RESENDS + 1) real guesses in total, then nothing
        (regression: resend reset the counter with no limit)."""
        p, _ = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": 1})
        wrong_code_answers = 0
        for _round in range(PendingAuth.MAX_RESENDS + 3):
            for _ in range(PendingAuth.MAX_ATTEMPTS + 2):  # spend this code's budget (and then some)
                r = self._verify(p, "999999")
                self.assertEqual(r.status_code, 400)
                if "غير صحيح" in str(r.data):
                    wrong_code_answers += 1
            self._resend(p)  # new code + fresh per-code attempts, until the cap refuses
        self.assertEqual(wrong_code_answers, PendingAuth.MAX_ATTEMPTS * (PendingAuth.MAX_RESENDS + 1))
        p.refresh_from_db()
        self.assertEqual(p.resend_count, PendingAuth.MAX_RESENDS)

    def test_resend_issues_a_fresh_code_and_resets_only_the_attempts_of_that_code(self):
        p, old = make_pending(PendingAuth.Purpose.TEACHER_RESET, {"user_id": 1})
        self._verify(p, "000000" if old != "000000" else "111111")
        self.assertEqual(self._resend(p).status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.otp_attempts, 0)
        self.assertEqual(p.resend_count, 1)

    def test_cross_purpose_pending_cannot_be_verified_or_resent(self):
        p, code = make_pending(PendingAuth.Purpose.STUDENT_CLAIM, {"user_id": 1})
        self.assertEqual(self._verify(p, code).status_code, 400)
        self.assertEqual(self._resend(p).status_code, 400)


# ====================================================== S7 signup is atomic ==
class SignupAtomicityTests(TestCase):
    def _verified_signup_pending(self, email="new@example.com", phone="201006666666"):
        from django.contrib.auth.hashers import make_password
        p, _ = make_pending(
            PendingAuth.Purpose.TEACHER_SIGNUP,
            {"name": "Teacher", "email": email, "phone": phone, "password_hash": make_password(PW)},
            target=phone, verified=True,
        )
        return p

    def _finish(self, client, p, name="بيئتي"):
        return client.post("/api/v1/auth/teacher/signup/environment/", {"pending_id": str(p.id), "name": name})

    def test_happy_path_creates_user_environment_membership_together(self):
        p = self._verified_signup_pending()
        r = self._finish(APIClient(), p)
        self.assertEqual(r.status_code, 201)
        u = User.objects.get(email="new@example.com")
        env = Environment.objects.get(owner=u)
        self.assertTrue(EnvironmentMembership.objects.filter(user=u, environment=env, role="owner").exists())
        self.assertFalse(PendingAuth.objects.filter(pk=p.pk).exists())

    def test_failure_midway_leaves_nothing_behind(self):
        """regression: user + environment stayed committed when the
        membership insert failed (and the teacher could never retry)."""
        p = self._verified_signup_pending()
        c = APIClient()
        c.raise_request_exception = False
        with mock.patch.object(EnvironmentMembership.objects, "create", side_effect=RuntimeError("boom")):
            r = self._finish(c, p)
        self.assertEqual(r.status_code, 500)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())
        self.assertEqual(Environment.objects.count(), 0)
        self.assertEqual(EnvironmentMembership.objects.count(), 0)
        self.assertTrue(PendingAuth.objects.filter(pk=p.pk).exists(), "flow must remain retryable")
        # and the retry works
        self.assertEqual(self._finish(APIClient(), p).status_code, 201)

    def test_email_taken_between_steps_returns_409_and_writes_nothing(self):
        """regression: this raced into an unhandled IntegrityError (HTTP 500)."""
        p = self._verified_signup_pending()
        make_teacher(email="new@example.com", phone="201007777777")  # someone registers first
        r = self._finish(APIClient(), p)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Environment.objects.count(), 0)
        self.assertEqual(User.objects.filter(email="new@example.com").count(), 1)

    def test_pending_id_can_create_only_one_account(self):
        p = self._verified_signup_pending()
        c = APIClient()
        self.assertEqual(self._finish(c, p).status_code, 201)
        self.assertEqual(self._finish(c, p).status_code, 400)
        self.assertEqual(User.objects.filter(email="new@example.com").count(), 1)

    def test_unverified_pending_cannot_finish_signup(self):
        p = self._verified_signup_pending()
        PendingAuth.objects.filter(pk=p.pk).update(verified=False)
        self.assertEqual(self._finish(APIClient(), p).status_code, 400)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())


class StudentClaimActivationTests(TestCase):
    def test_claim_cannot_take_over_an_already_active_student(self):
        """A claim-pending is only valid for a still-unclaimed account."""
        s = make_student("201008888888", active=True)
        p, code = make_pending(PendingAuth.Purpose.STUDENT_CLAIM, {"user_id": s.id}, verified=True)
        r = APIClient().post("/api/v1/auth/student/claim/activate/",
                             {"pending_id": str(p.id), "password": NEW_PW, "password2": NEW_PW})
        self.assertEqual(r.status_code, 400)
        s.refresh_from_db()
        self.assertTrue(s.check_password(PW), "existing password must be untouched")
