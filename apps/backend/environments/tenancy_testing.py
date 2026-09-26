"""
Reusable cross-tenant test harness (Phase 1). Phase 2+ domain-app tests
(`grades`, `groups`, `sessions`, ...) should subclass `TenantTestCase`
instead of writing their own two-teacher setup from scratch.
"""
from accounts.models import User
from accounts.testing import TestCase

from .models import Environment, EnvironmentMembership
from .tenancy import ACTIVE_ENVIRONMENT_HEADER

PASSWORD = "Str0ng!Pass"
_HEADER_KWARG = "HTTP_" + ACTIVE_ENVIRONMENT_HEADER.upper().replace("-", "_")


class TenantTestCase(TestCase):
    """Sets up two independent teachers, each owning one environment, plus
    an APIClient authenticated as each — the minimum fixture every
    cross-tenant test needs. `self.a` / `self.b` throughout.
    """

    def setUp(self):
        super().setUp()
        from rest_framework.test import APIClient

        self.teacher_a, self.env_a = self._make_teacher_env("a@example.com", "201020000001", "بيئة أ")
        self.teacher_b, self.env_b = self._make_teacher_env("b@example.com", "201020000002", "بيئة ب")
        self.client_a = self._authenticated(APIClient(), "a@example.com")
        self.client_b = self._authenticated(APIClient(), "b@example.com")

    # -- fixtures ------------------------------------------------------
    def _make_teacher_env(self, email, phone, env_name):
        teacher = User.objects.create_user(
            role=User.Role.TEACHER, name=email, email=email, phone=phone, password=PASSWORD, is_active=True,
        )
        env = Environment.objects.create(owner=teacher, name=env_name)
        EnvironmentMembership.objects.create(user=teacher, environment=env, role=EnvironmentMembership.Role.OWNER)
        return teacher, env

    def _authenticated(self, client, email):
        r = client.post("/api/v1/auth/teacher/login/", {"identifier": email, "password": PASSWORD})
        assert r.status_code == 200, r.content
        client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        return client

    def make_student_in(self, env, phone, name="طالب"):
        student = User.objects.create_user(role=User.Role.STUDENT, name=name, phone=phone, password=None, is_active=False)
        EnvironmentMembership.objects.create(user=student, environment=env, role=EnvironmentMembership.Role.STUDENT)
        return student

    # -- header helper ---------------------------------------------------
    def with_env(self, environment_id):
        """kwargs to splat into client.get/post/...: `**self.with_env(env.id)`."""
        return {_HEADER_KWARG: str(environment_id)}

    # -- the actual cross-tenant assertion --------------------------------
    def assert_cross_tenant_denied(self, method, url, *, body=None, expect_status=403, expect_code="environment_forbidden"):
        """The canonical check: Teacher B calling `url` with Teacher A's
        environment in the header (the one channel that's supposed to
        matter) must be denied — regardless of what `body` also claims.
        `body`, if given, is sent AS WELL, deliberately including
        environment_id/teacher_environment_id-shaped fields where relevant,
        to prove the body is never consulted for tenant authorization.
        """
        call = getattr(self.client_b, method.lower())
        kwargs = self.with_env(self.env_a.id)
        r = call(url, data=body, **kwargs) if body is not None else call(url, **kwargs)
        self.assertEqual(r.status_code, expect_status, r.content)
        if expect_code:
            self.assertEqual(r.json().get("code"), expect_code)
        return r
