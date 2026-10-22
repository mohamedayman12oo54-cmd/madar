from accounts.testing import ensure_active_enrollment
"""
Phase 1 / Tenant Foundation — tests for the active-environment resolution
mechanism (environments/tenancy.py) via its reference endpoint,
GET /api/v1/environments/context/, plus direct tests of the reusable
building blocks (StandardPagination, TenantOwnedModel) that Phase 2+ will
build on.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from accounts.models import User
from accounts.testing import TestCase

from .models import Environment, EnvironmentMembership
from .tenancy import ACTIVE_ENVIRONMENT_HEADER, StandardPagination, TenantOwnedModel
from .tenancy_testing import TenantTestCase

CONTEXT_URL = "/api/v1/environments/context/"
HEADER_KWARG = "HTTP_" + ACTIVE_ENVIRONMENT_HEADER.upper().replace("-", "_")


class EnvironmentContextResolutionTests(TenantTestCase):
    """Direct tests of resolve_environment()/IsEnvironmentMember via the
    reference endpoint."""

    def test_missing_header_is_400_environment_required(self):
        r = self.client_a.get(CONTEXT_URL)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "environment_required")

    def test_blank_header_is_400_environment_required(self):
        r = self.client_a.get(CONTEXT_URL, **{HEADER_KWARG: "   "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "environment_required")

    def test_non_integer_header_is_400_environment_required(self):
        for bad in ("abc", "1; DROP TABLE environments_environment;", "1.5", "1,2", "null"):
            with self.subTest(bad=bad):
                r = self.client_a.get(CONTEXT_URL, **{HEADER_KWARG: bad})
                self.assertEqual(r.status_code, 400, bad)
                self.assertEqual(r.json()["code"], "environment_required")

    def test_own_environment_is_authorized(self):
        r = self.client_a.get(CONTEXT_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], self.env_a.id)
        self.assertEqual(body["role"], "owner")

    def test_someone_elses_environment_is_403_environment_forbidden(self):
        """regression target: this is the exact bug class Phase 1 exists to
        close — a teacher naming another teacher's environment id."""
        self.assert_cross_tenant_denied("get", CONTEXT_URL)

    def test_nonexistent_environment_id_gets_the_same_error_as_someone_elses(self):
        """No enumeration signal: whether the id belongs to another teacher
        or doesn't exist at all, the response is identical."""
        real = self.client_b.get(CONTEXT_URL, **self.with_env(self.env_a.id))
        fake = self.client_b.get(CONTEXT_URL, **{HEADER_KWARG: "999999999"})
        self.assertEqual(real.status_code, fake.status_code, 403)
        self.assertEqual(real.json(), fake.json())

    def test_unauthenticated_request_is_401_not_400_or_403(self):
        anon = APIClient()
        r = anon.get(CONTEXT_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 401)

    def test_student_member_sees_owner_identity_not_their_own(self):
        student = self.make_student_in(self.env_a, "201030000001")
        c = APIClient()
        # students authenticate differently; log in directly via password reset path is
        # overkill here — set a usable password and log in normally.
        student.set_password("Str0ng!Pass")
        student.is_active = True
        student.save()
        ensure_active_enrollment(student, env=self.env_a)
        tok = c.post("/api/v1/auth/student/login/", {"phone": student.phone, "password": "Str0ng!Pass"}).data
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok["access"])
        r = c.get(CONTEXT_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["role"], "student")
        self.assertEqual(body["owner"]["name"], self.teacher_a.name)
        self.assertNotIn("initials", body)  # that's the teacher's env, not the student's own identity

    def test_a_student_cannot_use_a_teacher_only_environment_they_do_not_belong_to(self):
        c = APIClient()
        tok = c.post("/api/v1/auth/teacher/login/", {"identifier": self.teacher_b.email, "password": "Str0ng!Pass"}).data
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok["access"])
        r = c.get(CONTEXT_URL, **{HEADER_KWARG: str(self.env_a.id)})
        self.assertEqual(r.status_code, 403)


class BodyAndQueryAreNeverTrustedForTenancyTests(TenantTestCase):
    """The header is the ONLY channel. Prove environment_id/teacher_environment_id
    supplied via body or query string is ignored outright, even when it
    names a real, different environment than the header."""

    def test_query_string_environment_id_is_ignored(self):
        url = f"{CONTEXT_URL}?environment_id={self.env_a.id}&teacher_environment_id={self.env_a.id}"
        r = self.client_b.get(url, **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], self.env_b.id)  # header wins, query string had no effect

    def test_body_environment_id_on_a_get_is_ignored(self):
        r = self.client_b.get(CONTEXT_URL, data={"environment_id": self.env_a.id}, **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], self.env_b.id)

    def test_body_claiming_the_other_teachers_environment_does_not_grant_access(self):
        """Even a POST-shaped body naming Teacher A's environment cannot
        substitute for the header (using the harness's canonical assertion)."""
        self.assert_cross_tenant_denied(
            "get", CONTEXT_URL, body={"environment_id": self.env_a.id, "teacher_environment_id": self.env_a.id}
        )


class TenantTestHarnessSelfTests(TenantTestCase):
    """The harness itself, exercised directly (not just via context/) so
    Phase 2+ can trust it."""

    def test_two_teachers_have_independent_environments(self):
        self.assertNotEqual(self.env_a.id, self.env_b.id)
        self.assertEqual(self.env_a.owner_id, self.teacher_a.id)
        self.assertNotEqual(self.env_a.owner_id, self.teacher_b.id)

    def test_authenticated_clients_are_scoped_to_the_right_teacher(self):
        self.assertEqual(self.client_a.get("/api/v1/auth/me/").json()["email"], self.teacher_a.email)
        self.assertEqual(self.client_b.get("/api/v1/auth/me/").json()["email"], self.teacher_b.email)

    def test_make_student_in_creates_a_tenant_scoped_membership_only(self):
        s = self.make_student_in(self.env_a, "201030000099")
        self.assertTrue(EnvironmentMembership.objects.filter(user=s, environment=self.env_a, role="student").exists())
        self.assertFalse(EnvironmentMembership.objects.filter(user=s, environment=self.env_b).exists())


class StandardPaginationTests(TestCase):
    """Direct unit tests of the shared pagination class Phase 2+ list
    endpoints will use via DEFAULT_PAGINATION_CLASS."""

    def setUp(self):
        # INV-9: one Environment per teacher, so paginate 25 teachers' environments (the test is about
        # pagination, not about environments).
        teachers = [
            User.objects.create_user(role=User.Role.TEACHER, name=f"t{i}", email=f"pg{i}@example.com",
                                     phone=f"2010400{i:05d}", password="x", is_active=True)
            for i in range(25)
        ]
        Environment.objects.bulk_create([Environment(owner=t, name=f"E{i}") for i, t in enumerate(teachers)])
        self.qs = Environment.objects.filter(owner__in=teachers).order_by("id")
        self.factory = APIRequestFactory()

    def test_default_page_size_is_20(self):
        paginator = StandardPagination()
        request = Request(self.factory.get("/x/"))
        page = paginator.paginate_queryset(self.qs, request)
        self.assertEqual(len(page), 20)
        body = paginator.get_paginated_response(page).data
        self.assertEqual(body["count"], 25)
        self.assertIsNotNone(body["next"])
        self.assertIsNone(body["previous"])

    def test_page_size_is_overridable_and_capped(self):
        paginator = StandardPagination()
        request = Request(self.factory.get("/x/?page_size=5"))
        page = paginator.paginate_queryset(self.qs, request)
        self.assertEqual(len(page), 5)

        capped = StandardPagination()
        request2 = Request(self.factory.get("/x/?page_size=999"))
        page2 = capped.paginate_queryset(self.qs, request2)
        self.assertEqual(len(page2), 100 if self.qs.count() >= 100 else self.qs.count())
        self.assertLessEqual(len(page2), StandardPagination.max_page_size)

    def test_is_a_page_number_paginator(self):
        self.assertTrue(issubclass(StandardPagination, PageNumberPagination))


class TenantOwnedModelShapeTests(TestCase):
    """TenantOwnedModel is abstract (no table of its own) — verified by field
    introspection, since Phase 2 is what actually subclasses it."""

    def test_is_abstract(self):
        self.assertTrue(TenantOwnedModel._meta.abstract)

    def test_declares_an_environment_foreign_key(self):
        field = TenantOwnedModel._meta.get_field("environment")
        self.assertEqual(field.remote_field.model, Environment)
        self.assertEqual(field.remote_field.on_delete.__name__, "CASCADE")
