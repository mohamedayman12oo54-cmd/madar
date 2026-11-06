"""Login sessions: logout ends THIS session immediately (its access token too, not only its refresh token),
refresh rotation does not let a replayed token through, and other sessions are untouched."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import RevokedSession, User
from .session_revocation import revoke_all_sessions
from .testing import TestCase

PW = "Str0ng!Pass"
LOGIN = "/api/v1/auth/teacher/login/"
REFRESH = "/api/v1/auth/token/refresh/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"


class SessionLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            role=User.Role.TEACHER, name="T", email="t@example.com", phone="201001234501", password=PW,
            is_active=True, is_verified=True)

    def login(self):
        r = APIClient().post(LOGIN, {"identifier": "t@example.com", "password": PW})
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def me(self, access):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return c.get(ME)

    # ---------------------------------------------------------------- logout --
    def test_logout_ends_the_access_token_immediately(self):
        t = self.login()
        self.assertEqual(self.me(t["access"]).status_code, 200)
        self.assertEqual(APIClient().post(LOGOUT, {"refresh": t["refresh"]}).status_code, 205)
        r = self.me(t["access"])
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["code"], "session_revoked")

    def test_logout_also_kills_the_refresh_token(self):
        t = self.login()
        APIClient().post(LOGOUT, {"refresh": t["refresh"]})
        self.assertEqual(APIClient().post(REFRESH, {"refresh": t["refresh"]}).status_code, 401)

    def test_logout_without_any_access_token_still_revokes(self):
        t = self.login()  # the access token may already have expired: the refresh token alone is enough
        self.assertEqual(APIClient().post(LOGOUT, {"refresh": t["refresh"]}).status_code, 205)
        self.assertEqual(self.me(t["access"]).status_code, 401)

    def test_logout_is_idempotent(self):
        t = self.login()
        self.assertEqual(APIClient().post(LOGOUT, {"refresh": t["refresh"]}).status_code, 205)
        self.assertEqual(APIClient().post(LOGOUT, {"refresh": t["refresh"]}).status_code, 205)
        self.assertEqual(RevokedSession.objects.count(), 1)

    def test_logout_with_a_refresh_token_another_tab_already_rotated_still_ends_the_session(self):
        t = self.login()
        rotated = APIClient().post(REFRESH, {"refresh": t["refresh"]}).data  # tab A refreshed first
        # tab B only has the old refresh token, which is now blacklisted
        self.assertEqual(APIClient().post(LOGOUT, {"refresh": t["refresh"]}).status_code, 205)
        self.assertEqual(self.me(rotated["access"]).status_code, 401)
        self.assertEqual(APIClient().post(REFRESH, {"refresh": rotated["refresh"]}).status_code, 401)

    def test_logout_only_ends_that_session(self):
        phone, laptop = self.login(), self.login()
        APIClient().post(LOGOUT, {"refresh": phone["refresh"]})
        self.assertEqual(self.me(phone["access"]).status_code, 401)
        self.assertEqual(self.me(laptop["access"]).status_code, 200)
        self.assertEqual(APIClient().post(REFRESH, {"refresh": laptop["refresh"]}).status_code, 200)

    def test_logout_rejects_garbage_and_non_refresh_tokens_without_changing_anything(self):
        t = self.login()
        for bad in ("", "not-a-token", t["access"], None):
            with self.subTest(bad=bad):
                r = APIClient().post(LOGOUT, {"refresh": bad} if bad is not None else {})
                self.assertEqual(r.status_code, 400)
        self.assertEqual(RevokedSession.objects.count(), 0)
        self.assertEqual(self.me(t["access"]).status_code, 200)

    def test_a_token_signed_with_another_key_cannot_log_anyone_out(self):
        t = self.login()
        sid = RefreshToken(t["refresh"])["sid"]
        forged = RefreshToken.for_user(self.user)
        forged["sid"] = sid
        raw = str(forged).rsplit(".", 1)[0] + ".AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        self.assertEqual(APIClient().post(LOGOUT, {"refresh": raw}).status_code, 400)
        self.assertEqual(self.me(t["access"]).status_code, 200)

    # -------------------------------------------------------------- rotation --
    def test_refresh_rotates_and_the_replayed_token_is_refused(self):
        t = self.login()
        r = APIClient().post(REFRESH, {"refresh": t["refresh"]})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.data["refresh"], t["refresh"])
        self.assertEqual(APIClient().post(REFRESH, {"refresh": t["refresh"]}).status_code, 401)  # replay
        self.assertEqual(APIClient().post(REFRESH, {"refresh": r.data["refresh"]}).status_code, 200)

    def test_the_session_id_survives_rotation(self):
        t = self.login()
        r = APIClient().post(REFRESH, {"refresh": t["refresh"]}).data
        self.assertEqual(AccessToken(t["access"])["sid"], AccessToken(r["access"])["sid"])
        # (the old refresh token is blacklisted by the rotation, so read its claims without the blacklist check)
        self.assertEqual(token_backend.decode(t["refresh"])["sid"], token_backend.decode(r["refresh"])["sid"])

    def test_every_login_gets_its_own_session_id(self):
        self.assertNotEqual(AccessToken(self.login()["access"])["sid"], AccessToken(self.login()["access"])["sid"])

    # --------------------------------------------------------- other switches --
    def test_a_token_from_before_session_ids_existed_still_works(self):
        refresh = RefreshToken.for_user(self.user)
        refresh["sv"] = self.user.session_version
        self.assertEqual(self.me(str(refresh.access_token)).status_code, 200)

    def test_revoke_all_sessions_still_cuts_every_device(self):
        a, b = self.login(), self.login()
        revoke_all_sessions(self.user)
        self.assertEqual(self.me(a["access"]).status_code, 401)
        self.assertEqual(self.me(b["access"]).status_code, 401)

    def test_the_revocation_outlives_the_access_token_so_a_late_refresh_cannot_revive_the_session(self):
        t = self.login()
        rotated = APIClient().post(REFRESH, {"refresh": t["refresh"]}).data
        APIClient().post(LOGOUT, {"refresh": t["refresh"]})
        row = RevokedSession.objects.get()
        self.assertGreater(row.expires_at, timezone.now() + timedelta(days=13))
        self.assertEqual(APIClient().post(REFRESH, {"refresh": rotated["refresh"]}).status_code, 401)

    def test_expired_revocations_are_cleaned_up_on_the_next_logout(self):
        RevokedSession.objects.create(sid="old", expires_at=timezone.now() - timedelta(minutes=5))
        t = self.login()
        APIClient().post(LOGOUT, {"refresh": t["refresh"]})
        self.assertFalse(RevokedSession.objects.filter(sid="old").exists())

    # ---------------------------------------------------------- login errors --
    def test_wrong_password_and_unknown_account_are_indistinguishable(self):
        wrong = APIClient().post(LOGIN, {"identifier": "t@example.com", "password": "Wr0ng!Pass"})
        unknown = APIClient().post(LOGIN, {"identifier": "nobody@example.com", "password": "Wr0ng!Pass"})
        self.assertEqual((wrong.status_code, wrong.json()), (unknown.status_code, unknown.json()))
        self.assertIn(wrong.status_code, (400, 401))
