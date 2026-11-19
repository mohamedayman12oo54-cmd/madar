"""
Whole-API security sweep. Instead of testing the endpoints somebody remembered to test, this walks the URL
resolver and attacks EVERY /api/v1 route, so a new endpoint that forgot its permission class fails the build.

  1. anonymous: every route that is not on the explicit public list refuses every HTTP method (401/403/404/405);
  2. wrong account type: students, teachers and guardians never get anything from the team console, and teachers
     and students never succeed on another role's routes;
  3. hostile bodies: wrong JSON shapes / nesting never produce a 500 (an unhandled exception is an attack surface);
  4. ambient credentials: a Django session cookie (what CSRF abuses) authenticates nothing on the API;
  5. the public list itself is pinned, so adding a public route is a conscious, reviewed change.
"""
import re
import uuid

from django.contrib.auth import get_user_model
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from accounts.testing import TestCase
from environments.tenancy_testing import PASSWORD, TenantTestCase

User = get_user_model()

# The ONLY routes an anonymous caller may reach (logins, OTP steps, public QR forms, signed-ticket streams, the
# payment provider's webhook and the health probe). Each is rate limited / signed / verified by its own view.
PUBLIC = {
    "api/v1/health/",
    "api/v1/auth/teacher/login/", "api/v1/auth/teacher/signup/", "api/v1/auth/teacher/signup/environment/",
    "api/v1/auth/teacher/forgot/", "api/v1/auth/teacher/forgot/reset/",
    "api/v1/auth/student/login/", "api/v1/auth/student/claim/", "api/v1/auth/student/claim/activate/",
    "api/v1/auth/student/forgot/", "api/v1/auth/student/forgot/reset/",
    "api/v1/auth/team/login/", "api/v1/auth/token/refresh/", "api/v1/auth/logout/",
    "api/v1/auth/otp/<str:flow>/verify/", "api/v1/auth/otp/<str:flow>/resend/",
    "api/v1/academics/register/<str:token>/", "api/v1/academics/register/<str:token>/submit/",
    "api/v1/scheduling/checkin/<str:token>/", "api/v1/scheduling/checkin/<str:token>/submit/",
    "api/v1/billing/webhooks/kashier/",
    "api/v1/content/stream/", "api/v1/content/document/",
    "api/v1/parent/login/", "api/v1/parent/request/", "api/v1/parent/verify/",
}
METHODS = ("get", "post", "put", "patch", "delete")
REFUSED = {401, 403, 404, 405}


def all_routes():
    out = []

    def walk(patterns, prefix=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                out.append(prefix + str(p.pattern))

    walk(get_resolver().url_patterns)
    return sorted(r for r in out if r.startswith("api/v1/"))


def concrete(route):
    path = re.sub(r"<int:[^>]+>", "1", route)
    path = re.sub(r"<uuid:[^>]+>", str(uuid.UUID(int=0)), path)
    path = re.sub(r"<(?:str|path):[^>]+>", "x", path)
    return "/" + path


ROUTES = all_routes()
PRIVATE = [r for r in ROUTES if r not in PUBLIC]


def client():
    return APIClient(raise_request_exception=False)


class RouteInventoryTests(TestCase):
    def test_the_sweep_really_sees_the_whole_api(self):
        self.assertGreater(len(ROUTES), 150)
        self.assertTrue(any(r.startswith("api/v1/control/") for r in ROUTES))
        self.assertFalse(PUBLIC - set(ROUTES), "the public list names routes that do not exist (stale entry)")

    def test_the_public_list_is_exactly_the_reviewed_set(self):
        self.assertEqual(len(PUBLIC), 26)


class AnonymousSweepTests(TestCase):
    def test_every_non_public_route_refuses_every_method_without_credentials(self):
        failures = []
        c = client()
        for route in PRIVATE:
            for m in METHODS:
                r = getattr(c, m)(concrete(route), {}, format="json")
                if r.status_code not in REFUSED:
                    failures.append(f"{m.upper()} /{route} -> {r.status_code}")
        self.assertEqual(failures, [], "routes that answered an anonymous caller:\n" + "\n".join(failures))

    def test_a_garbage_or_malformed_credential_is_refused_like_no_credential(self):
        failures = []
        for header in ("Bearer not.a.jwt", "Bearer ", "Basic YWRtaW46YWRtaW4=", "Parent forged", "Token abc", "Bearer " + "A" * 4000):
            c = client()
            c.credentials(HTTP_AUTHORIZATION=header)
            for route in ("api/v1/auth/me/", "api/v1/control/users/", "api/v1/billing/subscription/", "api/v1/parent/overview/"):
                r = c.get(concrete(route))
                if r.status_code not in {401, 403}:
                    failures.append(f"{header[:20]!r} {route} -> {r.status_code}")
        self.assertEqual(failures, [])


class _Accounts(TenantTestCase):
    def setUp(self):
        super().setUp()
        from academics.models import Enrollment, Grade
        from environments.models import EnvironmentMembership

        self.student = User.objects.create_user(role="student", name="طالب", phone="201555700001", password=PASSWORD,
                                                is_active=True, is_verified=True)
        EnvironmentMembership.objects.create(user=self.student, environment=self.env_a, role="student")
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=10)
        self.enr = Enrollment.objects.create(environment=self.env_a, student=self.student, grade=self.grade,
                                             parent_phone="201700000001")
        self.team_user = User.objects.create_user(username="legacy@madar", role="team", name="قديم", password=PASSWORD,
                                                  is_active=True, is_verified=True)

    def login(self, kind, ident, pw=PASSWORD):
        body = {"phone": ident, "password": pw} if kind == "student" else {"identifier": ident, "password": pw}
        r = client().post(f"/api/v1/auth/{kind}/login/", body, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c = client()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        return c

    def guardian(self):
        from parents.auth import issue_session

        c = client()
        c.credentials(HTTP_AUTHORIZATION="Parent " + issue_session(self.enr))
        return c


class WrongRoleSweepTests(_Accounts):
    def _control_routes(self):
        return [r for r in PRIVATE if r.startswith("api/v1/control/") and "/customer/" not in r]

    def test_no_non_team_account_gets_anything_from_the_team_console(self):
        teacher = self.login("teacher", "a@example.com")
        student = self.login("student", "201555700001")
        guardian = self.guardian()
        failures = []
        for who, c in (("teacher", teacher), ("student", student), ("guardian", guardian)):
            for route in self._control_routes():
                for m in METHODS:
                    r = getattr(c, m)(concrete(route), {}, format="json", **self.with_env(self.env_a.id))
                    if r.status_code not in REFUSED:
                        failures.append(f"{who} {m.upper()} /{route} -> {r.status_code}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_a_team_account_with_no_role_can_do_nothing_in_the_console_except_read_its_own_permissions(self):
        c = self.login("team", "legacy@madar")
        failures = []
        for route in self._control_routes():
            if route.endswith("control/me/"):
                continue
            for m in METHODS:
                r = getattr(c, m)(concrete(route), {}, format="json")
                if r.status_code not in REFUSED:
                    failures.append(f"{m.upper()} /{route} -> {r.status_code}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_a_read_only_role_can_never_write_anything_in_the_console(self):
        from control.models import Role, TeamProfile

        analyst = User.objects.create_user(username="an@madar", role="team", name="محلل", password=PASSWORD,
                                           is_active=True, is_verified=True)
        TeamProfile.objects.create(user=analyst, role=Role.objects.get(key="analyst"))
        c = self.login("team", "an@madar")
        failures = []
        for route in self._control_routes():
            for m in ("post", "put", "patch", "delete"):
                r = getattr(c, m)(concrete(route), {}, format="json")
                if r.status_code not in REFUSED:
                    failures.append(f"{m.upper()} /{route} -> {r.status_code}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_team_accounts_cannot_use_the_customer_ticket_api_and_customers_cannot_use_team_routes(self):
        team = self.login("team", "legacy@madar")
        failures = []
        for route in [r for r in PRIVATE if "/customer/" in r]:
            r = team.get(concrete(route))
            if r.status_code not in REFUSED:
                failures.append(f"team GET /{route} -> {r.status_code}")
        guardian = self.guardian()
        for route in [r for r in PRIVATE if "/customer/" in r]:
            r = guardian.get(concrete(route))
            if r.status_code not in REFUSED:
                failures.append(f"guardian GET /{route} -> {r.status_code}")
        self.assertEqual(failures, [])

    def test_a_student_cannot_use_any_teacher_only_route(self):
        student = self.login("student", "201555700001")
        failures = []
        teacher_only = [r for r in PRIVATE if r.startswith(("api/v1/academics/", "api/v1/scheduling/schedules", "api/v1/scheduling/sessions",
                                                           "api/v1/scheduling/attendance", "api/v1/scheduling/recitation", "api/v1/scheduling/scan",
                                                           "api/v1/evaluation/", "api/v1/financials/", "api/v1/guardian-messages/",
                                                           "api/v1/billing/checkout", "api/v1/billing/subscription/cancel"))
                        and "register" not in r]
        for route in teacher_only:
            for m in METHODS:
                r = getattr(student, m)(concrete(route), {}, format="json", **self.with_env(self.env_a.id))
                if r.status_code not in REFUSED:
                    failures.append(f"student {m.upper()} /{route} -> {r.status_code}")
        self.assertEqual(failures, [], "\n".join(failures))


class HostileBodyTests(_Accounts):
    """An unhandled exception (HTTP 500) on attacker-shaped input is itself a finding: it leaks behaviour and is
    often the first step towards something worse."""

    SHAPES = (None, [], "x", 12345, True, [[[[[[]]]]]], {"a": {"b": {"c": [1, {"d": None}]}}}, {"id": "1; DROP TABLE x"},
              {"phone": ["1"], "password": {"x": 1}}, {"identifier": 1, "password": None}, {"": ""}, {"x" * 300: "y" * 5000})

    def _hit(self, c, routes, with_env=False):
        bad = []
        for route in routes:
            for body in self.SHAPES:
                for m in ("post", "patch", "put"):
                    kw = self.with_env(self.env_a.id) if with_env else {}
                    r = getattr(c, m)(concrete(route), body, format="json", **kw)
                    if r.status_code >= 500:
                        bad.append(f"{m.upper()} /{route} body={str(body)[:40]!r} -> {r.status_code}")
        return bad

    def test_a_pathologically_nested_json_body_is_a_400_not_a_crash(self):
        """`[[[[…` 200k deep overflows Python's recursion limit inside the JSON parser (a RecursionError, i.e. HTTP 500)."""
        deep = ("[" * 200_000).encode()
        deep_obj = (b'{"a":' * 50_000) + b"1" + (b"}" * 50_000)
        teacher = self.login("teacher", "a@example.com")
        for c in (client(), teacher):
            for path in ("/api/v1/auth/teacher/login/", "/api/v1/auth/student/login/", "/api/v1/academics/grades/",
                         "/api/v1/auth/change-password/"):
                for body in (deep, deep_obj):
                    r = c.post(path, data=body, content_type="application/json", **self.with_env(self.env_a.id))
                    self.assertIn(r.status_code, (400, 401, 403, 413), f"{path} -> {r.status_code}")

    def test_nul_characters_are_refused_everywhere_instead_of_reaching_the_database(self):
        teacher = self.login("teacher", "a@example.com")
        self.assertEqual(teacher.get("/api/v1/academics/enrollments/?search=a%00b", **self.with_env(self.env_a.id)).status_code, 400)
        self.assertEqual(client().post("/api/v1/auth/teacher/login/", {"identifier": "a\u0000b", "password": "x"}, format="json").status_code, 400)
        self.assertEqual(client().get("/api/v1/health/%00").status_code, 400)

    def test_public_endpoints_never_crash_on_hostile_json(self):
        bad = self._hit(client(), sorted(PUBLIC - {"api/v1/health/", "api/v1/billing/webhooks/kashier/"}))
        self.assertEqual(bad, [], "\n".join(bad))

    def test_the_webhook_never_crashes_on_hostile_bodies_and_never_accepts_unsigned_ones(self):
        c = client()
        for body in self.SHAPES:
            r = c.post("/api/v1/billing/webhooks/kashier/", body, format="json")
            self.assertLess(r.status_code, 500, str(body)[:40])
            self.assertNotIn(r.status_code, (200, 201, 202), "an unsigned webhook must not be accepted")

    def test_teacher_endpoints_never_crash_on_hostile_json(self):
        teacher = self.login("teacher", "a@example.com")
        routes = [r for r in PRIVATE if r.startswith("api/v1/") and not r.startswith("api/v1/control/")
                  and "stream" not in r and "uploads" not in r]
        bad = self._hit(teacher, routes, with_env=True)
        self.assertEqual(bad, [], "\n".join(bad))

    def test_student_endpoints_never_crash_on_hostile_json(self):
        student = self.login("student", "201555700001")
        routes = [r for r in PRIVATE if r.startswith("api/v1/") and not r.startswith("api/v1/control/") and "stream" not in r
                  and "uploads" not in r]
        bad = self._hit(student, routes, with_env=True)
        self.assertEqual(bad, [], "\n".join(bad))

    def test_the_team_console_never_crashes_on_hostile_json(self):
        from control.models import Role, TeamProfile

        root = User.objects.create_user(username="root@madar", role="team", name="مدير", password=PASSWORD,
                                        is_active=True, is_verified=True)
        TeamProfile.objects.create(user=root, role=Role.objects.get(key="super_admin"))
        c = self.login("team", "root@madar")
        bad = self._hit(c, [r for r in PRIVATE if r.startswith("api/v1/control/") and "/customer/" not in r])
        self.assertEqual(bad, [], "\n".join(bad))

    def test_hostile_query_strings_never_crash_the_console(self):
        from control.models import Role, TeamProfile

        root = User.objects.create_user(username="root2@madar", role="team", name="مدير", password=PASSWORD,
                                        is_active=True, is_verified=True)
        TeamProfile.objects.create(user=root, role=Role.objects.get(key="super_admin"))
        c = self.login("team", "root2@madar")
        evil = ["page=-1", "page=abc", "page=99999999999999999999", "page_size=0", "page_size=-5", "page_size=1000000",
                "sort=%00", "sort=-;DROP TABLE", "range=custom&from=9999-99-99&to=x", "range=%00", "environment=abc",
                "search=" + "%27%20OR%201%3D1--", "search=" + "%E0%A4%A", "status[]=1", "export=csv&page=x", "assignee=-1",
                "created_from=not-a-date", "from=2020-13-45", "kind=%00", "role=<script>"]
        bad = []
        gets = [r for r in PRIVATE if r.startswith("api/v1/control/") and "/customer/" not in r]
        for route in gets:
            for q in evil:
                r = c.get(concrete(route) + "?" + q)
                if r.status_code >= 500:
                    bad.append(f"GET /{route}?{q} -> {r.status_code}")
        self.assertEqual(bad, [], "\n".join(bad))


class AmbientCredentialTests(_Accounts):
    def test_a_django_session_cookie_authenticates_nothing_on_the_api(self):
        """CSRF abuses credentials the browser attaches by itself. The API only accepts an explicit bearer token, so
        even a perfectly valid logged-in admin SESSION does not make a cross-site POST succeed."""
        admin = User.objects.create_superuser(username="boss", password=PASSWORD, role="team", name="boss")
        c = client()
        self.assertTrue(c.login(username="boss", password=PASSWORD))
        for route in ("api/v1/auth/me/", "api/v1/control/users/", "api/v1/control/overview/", "api/v1/billing/subscription/"):
            self.assertIn(c.get(concrete(route)).status_code, (401, 403), route)
        for route in ("api/v1/auth/change-password/", "api/v1/control/users/1/suspend/", "api/v1/billing/checkout/"):
            self.assertIn(c.post(concrete(route), {}, format="json").status_code, (401, 403), route)
        self.assertEqual(admin.role, "team")

    def test_no_view_enables_session_authentication(self):
        from django.conf import settings

        classes = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
        self.assertNotIn("rest_framework.authentication.SessionAuthentication", classes)
        self.assertNotIn("rest_framework.authentication.BasicAuthentication", classes)
        self.assertFalse(getattr(settings, "CORS_ALLOW_CREDENTIALS", False))


class TokenForgeryTests(_Accounts):
    """Attacks on the bearer token itself (the only credential the API accepts)."""

    def _b64(self, obj):
        import base64
        import json

        return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()

    def _claims(self, user, ttype="access", **extra):
        import time

        now = int(time.time())
        return {"token_type": ttype, "exp": now + 600, "iat": now, "jti": "forged", "user_id": user.pk, "sv": user.session_version,
                "role": user.role, **extra}

    def _get(self, token):
        c = client()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return c.get("/api/v1/auth/me/").status_code

    def test_alg_none_and_wrong_key_and_tampered_payload_are_all_rejected(self):
        import jwt

        victim = User.objects.create_user(username="v@madar", role="team", name="مدير", password=PASSWORD, is_active=True, is_verified=True)
        claims = self._claims(victim)
        # 1. unsigned token claiming to be the team account
        unsigned = self._b64({"alg": "none", "typ": "JWT"}) + "." + self._b64(claims) + "."
        self.assertEqual(self._get(unsigned), 401)
        # 2. signed with an attacker-chosen key
        self.assertEqual(self._get(jwt.encode(claims, "attacker-key-0123456789-0123456789", algorithm="HS256")), 401)
        # 3. a real token whose payload was edited to another user id (signature no longer matches)
        real = self.login("teacher", "a@example.com").handler._credentials if False else None  # noqa: F841
        r = client().post("/api/v1/auth/teacher/login/", {"identifier": "a@example.com", "password": PASSWORD}, format="json")
        head, payload, sig = r.data["access"].split(".")
        import base64
        import json

        body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        body["user_id"] = victim.pk
        self.assertEqual(self._get(f"{head}.{self._b64(body)}.{sig}"), 401)
        # 4. algorithm confusion: asking for a different algorithm than the server's
        self.assertEqual(self._get(jwt.encode(claims, "x" * 40, algorithm="HS512")), 401)

    def test_a_refresh_token_is_not_an_access_token(self):
        r = client().post("/api/v1/auth/teacher/login/", {"identifier": "a@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(self._get(r.data["refresh"]), 401)

    def test_an_access_token_is_not_a_refresh_token(self):
        r = client().post("/api/v1/auth/teacher/login/", {"identifier": "a@example.com", "password": PASSWORD}, format="json")
        out = client().post("/api/v1/auth/token/refresh/", {"refresh": r.data["access"]}, format="json")
        self.assertIn(out.status_code, (400, 401))

    def test_an_expired_token_and_a_stale_session_version_are_rejected(self):
        import jwt
        from django.conf import settings

        self.assertEqual(self._get(jwt.encode({**self._claims(self.team_user), "exp": 1}, settings.SECRET_KEY, algorithm="HS256")), 401)
        stale = jwt.encode({**self._claims(self.team_user, sv=self.team_user.session_version + 7)}, settings.SECRET_KEY, algorithm="HS256")
        self.assertEqual(self._get(stale), 401)

    def test_a_token_for_a_deleted_or_deactivated_account_stops_working_at_once(self):
        c = self.login("teacher", "a@example.com")
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 200)
        User.objects.filter(pk=self.teacher_a.pk).update(is_active=False)
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 401)

    def test_the_role_claim_in_a_token_is_never_trusted(self):
        """Authorisation reads the role from the DATABASE row. A genuinely signed token whose `role` claim says "team"
        for a teacher account still gets nothing from the console."""
        import jwt
        from django.conf import settings

        forged_role = jwt.encode(self._claims(self.teacher_a, role="team"), settings.SECRET_KEY, algorithm="HS256")
        c = client()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + forged_role)
        self.assertEqual(c.get("/api/v1/control/overview/").status_code, 403)
        self.assertEqual(c.get("/api/v1/control/me/").status_code, 403)
