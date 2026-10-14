from accounts.testing import TestCase, ensure_active_enrollment
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import PendingAuth, User
from environments.models import Environment, EnvironmentMembership

VALID_PW = "Str0ng!Pass"


class TeamLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="team@madar", role=User.Role.TEAM, name="Team",
            password=VALID_PW, is_active=True, is_verified=True,
        )

    def test_login_success(self):
        r = self.client.post("/api/v1/auth/team/login/", {"identifier": "team@madar", "password": VALID_PW})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

    def test_login_wrong_password(self):
        r = self.client.post("/api/v1/auth/team/login/", {"identifier": "team@madar", "password": "nope"})
        self.assertEqual(r.status_code, 400)

    def test_login_unknown_identifier(self):
        r = self.client.post("/api/v1/auth/team/login/", {"identifier": "nobody@madar", "password": VALID_PW})
        self.assertEqual(r.status_code, 400)


class TeacherLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            role=User.Role.TEACHER, name="Ahmed", email="ahmed@example.com", phone="201001234567",
            password=VALID_PW, is_active=True, is_verified=True,
        )

    def test_login_with_email(self):
        r = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "ahmed@example.com", "password": VALID_PW})
        self.assertEqual(r.status_code, 200)

    def test_login_with_phone(self):
        r = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "201001234567", "password": VALID_PW})
        self.assertEqual(r.status_code, 200)

    def test_login_inactive_rejected(self):
        self.user.is_active = False
        self.user.save()
        r = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "201001234567", "password": VALID_PW})
        self.assertEqual(r.status_code, 400)


class TeacherSignupFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_full_signup_flow(self):
        # step 0: basic info
        r = self.client.post("/api/v1/auth/teacher/signup/", {
            "name": "Sara", "email": "sara@example.com", "phone": "201112223344",
            "password": VALID_PW, "password2": VALID_PW,
        })
        self.assertEqual(r.status_code, 200, r.data)
        pending_id = r.data["pending_id"]
        self.assertIn("debug_otp", r.data)  # DEBUG=True in test settings
        code = r.data["debug_otp"]

        # user must not exist yet — only after full flow completes
        self.assertFalse(User.objects.filter(email="sara@example.com").exists())

        # step 1: wrong otp increments attempts, doesn't verify
        bad = self.client.post("/api/v1/auth/otp/teacher-signup/verify/", {"pending_id": pending_id, "code": "000000"})
        self.assertEqual(bad.status_code, 400)

        # step 1: correct otp
        ok = self.client.post("/api/v1/auth/otp/teacher-signup/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(ok.status_code, 200, ok.data)

        # step 2: environment -> creates the real user + environment + tokens
        env_resp = self.client.post("/api/v1/auth/teacher/signup/environment/", {
            "pending_id": pending_id, "name": "مجموعات الرياضيات", "subject_stage": "الثانوية",
        })
        self.assertEqual(env_resp.status_code, 201, env_resp.data)
        self.assertIn("access", env_resp.data)

        user = User.objects.get(email="sara@example.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_verified)
        self.assertEqual(Environment.objects.filter(owner=user).count(), 1)
        self.assertEqual(EnvironmentMembership.objects.filter(user=user, role="owner").count(), 1)

        # pending record consumed — replay should fail
        replay = self.client.post("/api/v1/auth/teacher/signup/environment/", {
            "pending_id": pending_id, "name": "x",
        })
        self.assertEqual(replay.status_code, 400)

    def test_cannot_skip_otp_step(self):
        r = self.client.post("/api/v1/auth/teacher/signup/", {
            "name": "X", "email": "x@example.com", "phone": "201112223300",
            "password": VALID_PW, "password2": VALID_PW,
        })
        pending_id = r.data["pending_id"]
        # never verified -> environment step must reject
        env_resp = self.client.post("/api/v1/auth/teacher/signup/environment/", {
            "pending_id": pending_id, "name": "Env",
        })
        self.assertEqual(env_resp.status_code, 400)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(role=User.Role.TEACHER, email="dup@example.com", phone="201000000001", password=VALID_PW)
        r = self.client.post("/api/v1/auth/teacher/signup/", {
            "name": "Y", "email": "dup@example.com", "phone": "201999999999",
            "password": VALID_PW, "password2": VALID_PW,
        })
        self.assertEqual(r.status_code, 400)

    def test_weak_password_rejected(self):
        r = self.client.post("/api/v1/auth/teacher/signup/", {
            "name": "Z", "email": "z@example.com", "phone": "201888888888",
            "password": "weak", "password2": "weak",
        })
        self.assertEqual(r.status_code, 400)

    def test_mismatched_passwords_rejected(self):
        r = self.client.post("/api/v1/auth/teacher/signup/", {
            "name": "Z", "email": "z2@example.com", "phone": "201888888800",
            "password": VALID_PW, "password2": "Different1!",
        })
        self.assertEqual(r.status_code, 400)


class TeacherForgotPasswordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            role=User.Role.TEACHER, name="Ahmed", email="ahmed2@example.com", phone="201005556666",
            password=VALID_PW, is_active=True, is_verified=True,
        )

    def test_full_reset_flow(self):
        r = self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": "ahmed2@example.com"})
        self.assertEqual(r.status_code, 200)
        pending_id, code = r.data["pending_id"], r.data["debug_otp"]

        v = self.client.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(v.status_code, 200)

        new_pw = "NewStr0ng!Pass"
        reset = self.client.post("/api/v1/auth/teacher/forgot/reset/", {
            "pending_id": pending_id, "password": new_pw, "password2": new_pw,
        })
        self.assertEqual(reset.status_code, 200)

        old = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "ahmed2@example.com", "password": VALID_PW})
        self.assertEqual(old.status_code, 400)
        fresh = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "ahmed2@example.com", "password": new_pw})
        self.assertEqual(fresh.status_code, 200)

    def test_unknown_identifier_does_not_leak(self):
        """Response shape must be identical whether or not the account exists."""
        known = self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": "ahmed2@example.com"})
        unknown = self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": "ghost@example.com"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(set(known.data.keys()), set(unknown.data.keys()))

    def test_reset_fails_for_unknown_identifier_flow(self):
        r = self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": "ghost2@example.com"})
        pending_id, code = r.data["pending_id"], r.data["debug_otp"]
        v = self.client.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(v.status_code, 200)  # otp itself is real and verifies fine
        reset = self.client.post("/api/v1/auth/teacher/forgot/reset/", {
            "pending_id": pending_id, "password": "NewStr0ng!Pass", "password2": "NewStr0ng!Pass",
        })
        self.assertEqual(reset.status_code, 400)  # but there's no real account behind it


class StudentClaimFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="Mr. X", email="mrx@example.com", phone="201234500000",
            password=VALID_PW, is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="Class A")
        self.pre_reg = User.objects.create_user(
            role=User.Role.STUDENT, name="Student One", phone="201230001111",
            is_active=False, password=None,
        )
        EnvironmentMembership.objects.create(user=self.pre_reg, environment=self.env, role="student")
        self.enrollment = ensure_active_enrollment(self.pre_reg, env=self.env)
        self.code = self.enrollment.qr_token

    def claim_body(self, **kw):
        return {"channel": "phone", "phone": "201230001111", "student_code": self.code, **kw}

    def test_claim_unknown_code_returns_not_found(self):
        r = self.client.post("/api/v1/auth/student/claim/", self.claim_body(student_code="AAAAAA"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get("code"), "not_found")

    def test_full_claim_flow(self):
        r = self.client.post("/api/v1/auth/student/claim/", self.claim_body())
        self.assertEqual(r.status_code, 200)
        pending_id, code = r.data["pending_id"], r.data["debug_otp"]

        v = self.client.post("/api/v1/auth/otp/student-claim/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(v.status_code, 200)

        activate = self.client.post("/api/v1/auth/student/claim/activate/", {
            "pending_id": pending_id, "password": VALID_PW, "password2": VALID_PW,
        })
        self.assertEqual(activate.status_code, 201, activate.data)
        # No session on activation: the student is sent to the login page.
        self.assertNotIn("access", activate.data)
        self.assertNotIn("refresh", activate.data)

        self.pre_reg.refresh_from_db()
        self.assertTrue(self.pre_reg.is_active)

        login = self.client.post("/api/v1/auth/student/login/", {"phone": "201230001111", "password": VALID_PW})
        self.assertEqual(login.status_code, 200)

    def test_already_claimed_cannot_be_claimed_again(self):
        self.pre_reg.is_active = True
        self.pre_reg.save()
        r = self.client.post("/api/v1/auth/student/claim/", self.claim_body())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get("code"), "not_found")


class StudentForgotPasswordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            role=User.Role.STUDENT, name="Student", phone="201230005555",
            password=VALID_PW, is_active=True,
        )
        ensure_active_enrollment(self.student)

    def test_full_reset_flow(self):
        r = self.client.post("/api/v1/auth/student/forgot/", {"phone": "201230005555"})
        self.assertEqual(r.status_code, 200)
        pending_id, code = r.data["pending_id"], r.data["debug_otp"]

        v = self.client.post("/api/v1/auth/otp/student-reset/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(v.status_code, 200)

        new_pw = "NewStr0ng!Pass"
        reset = self.client.post("/api/v1/auth/student/forgot/reset/", {
            "pending_id": pending_id, "password": new_pw, "password2": new_pw,
        })
        self.assertEqual(reset.status_code, 200)

        old = self.client.post("/api/v1/auth/student/login/", {"phone": "201230005555", "password": VALID_PW})
        self.assertEqual(old.status_code, 400)
        fresh = self.client.post("/api/v1/auth/student/login/", {"phone": "201230005555", "password": new_pw})
        self.assertEqual(fresh.status_code, 200)

    def test_unknown_phone_does_not_leak(self):
        known = self.client.post("/api/v1/auth/student/forgot/", {"phone": "201230005555"})
        unknown = self.client.post("/api/v1/auth/student/forgot/", {"phone": "201230009999"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(set(known.data.keys()), set(unknown.data.keys()))

    def test_otp_cannot_cross_into_claim_flow(self):
        """A student-reset OTP must not verify against student-claim, even
        though both flows are keyed by the same phone number."""
        r = self.client.post("/api/v1/auth/student/forgot/", {"phone": "201230005555"})
        pending_id, code = r.data["pending_id"], r.data["debug_otp"]
        cross = self.client.post("/api/v1/auth/otp/student-claim/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(cross.status_code, 400)


class OTPSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_max_attempts_locks_out(self):
        r = self.client.post("/api/v1/auth/student/claim/", {"phone": "201230002222"})
        # no pre-registered student -> not_found, but we can still test
        # attempt-lockout using a teacher-reset pending (always created)
        r2 = self.client.post("/api/v1/auth/teacher/forgot/", {"identifier": "whoever@example.com"})
        pending_id = r2.data["pending_id"]
        for _ in range(PendingAuth.MAX_ATTEMPTS):
            bad = self.client.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": pending_id, "code": "111111"})
            self.assertEqual(bad.status_code, 400)
        one_more = self.client.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": pending_id, "code": "111111"})
        self.assertEqual(one_more.status_code, 400)
        self.assertIn("محاولات", str(one_more.data))

    def test_otp_cannot_be_replayed_across_purposes(self):
        """A signup OTP must not verify against the reset endpoint even
        with the same pending_id format — purposes are strictly isolated."""
        r = self.client.post("/api/v1/auth/teacher/signup/", {
            "name": "P", "email": "p@example.com", "phone": "201230003333",
            "password": VALID_PW, "password2": VALID_PW,
        })
        pending_id, code = r.data["pending_id"], r.data["debug_otp"]
        cross = self.client.post("/api/v1/auth/otp/teacher-reset/verify/", {"pending_id": pending_id, "code": code})
        self.assertEqual(cross.status_code, 400)


class MeAndLogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            role=User.Role.TEACHER, name="Ahmed", email="ame@example.com", phone="201009998888",
            password=VALID_PW, is_active=True,
        )

    def test_me_requires_auth(self):
        r = self.client.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, 401)

    def test_me_with_token(self):
        login = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "ame@example.com", "password": VALID_PW})
        access = login.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        r = self.client.get("/api/v1/auth/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["role"], "teacher")

    def test_logout_blacklists_refresh(self):
        login = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "ame@example.com", "password": VALID_PW})
        refresh = login.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        out = self.client.post("/api/v1/auth/logout/", {"refresh": refresh})
        self.assertEqual(out.status_code, 205)
        again = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh})
        self.assertEqual(again.status_code, 401)


class HealthCheckTests(TestCase):
    def test_health_endpoint(self):
        r = self.client.get("/api/v1/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})


class UsernameAutoGenerationTests(TestCase):
    """Regression test: creating users via get_or_create/update_or_create
    (bypassing UserManager.create_user) must not leave `username` blank —
    two blank usernames collide under the unique constraint. This bit the
    seed_demo command during development; save() now guarantees a
    username for any creation path, not just create_user()."""

    def test_get_or_create_does_not_collide(self):
        u1, _ = User.objects.get_or_create(phone="201230000001", defaults={"role": User.Role.STUDENT})
        u2, _ = User.objects.get_or_create(phone="201230000002", defaults={"role": User.Role.STUDENT})
        self.assertTrue(u1.username)
        self.assertTrue(u2.username)
        self.assertNotEqual(u1.username, u2.username)

    def test_update_or_create_does_not_collide(self):
        u1, _ = User.objects.update_or_create(phone="201230000003", defaults={"role": User.Role.STUDENT})
        u2, _ = User.objects.update_or_create(phone="201230000004", defaults={"role": User.Role.STUDENT})
        self.assertNotEqual(u1.username, u2.username)
