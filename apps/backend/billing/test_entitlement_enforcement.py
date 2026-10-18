"""
BILL-WU-011 — entitlement enforcement integration: `RequiresCapability`
consulted after `IsEnvironmentMember` (ADR-018), on both the Web and
Worker paths (OP-PARITY).

AC-BILL-011-6 (the worker re-check) is covered in
`ai.tests.WorkerEntitlementRecheckTests` instead of here: it necessarily
references `ai.models.AIOperation`, which the static check in
`billing.test_webhooks.NoAIIdempotencyReuseTests` (AC-BILL-020-5, ADR-017)
forbids anywhere under this directory — that check protects billing's own
CODE from coupling to `AIOperation`/`idempotency_key`, and a test file
living here is still "under this directory" to an AST walk that doesn't
distinguish test code from production code. Living in `ai/tests.py`
instead is also just the more natural home: that AC is really about the
AI worker's own behavior (`ai/management/commands/process_ai_operations.py`),
which is one of this unit's own "Implementation surfaces".
"""
import types
from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from content.models import ContentItem
from environments.tenancy import IsEnvironmentMember
from environments.tenancy_testing import PASSWORD, TenantTestCase

from .models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, Subscription
from .permissions import RequiresCapabilityBase

STATE_REC_URL = "/api/v1/ai/state-recommendations/"
QUIZ_URL = "/api/v1/student/quizzes/"
ASSISTANT_URL = "/api/v1/ai/operations/"
STUDENT_ASSISTANT_URL = "/api/v1/student/assistant/"


def grant_plan(environment, plan_key):
    """An ACTIVE Subscription on `plan_key`, with a SUCCEEDED attempt
    covering the current period — the exact shape `entitlements.decide`'s
    "paid" branch requires (billing/entitlements.py)."""
    plan = Plan.objects.get(key=plan_key)
    now = timezone.now()
    subscription = Subscription.objects.create(
        environment=environment, plan=plan, state=Subscription.State.ACTIVE,
        current_period_start=now - timedelta(days=1), current_period_end=now + timedelta(days=29),
    )
    period = BillingPeriod.objects.create(
        environment=environment, subscription=subscription,
        period_start=subscription.current_period_start, period_end=subscription.current_period_end,
    )
    AmountOwed.objects.create(
        environment=environment, billing_period=period, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=AmountOwed.Status.SATISFIED,
    )
    PaymentAttempt.objects.create(
        environment=environment, subscription=subscription, billing_period=period,
        merchant_order_id=f"ent-{subscription.pk}", amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=PaymentAttempt.Status.SUCCEEDED,
    )
    return subscription


def grant_trial(environment, *, expired=False):
    started = timezone.now() - timedelta(days=100) if expired else timezone.now()
    return Subscription.objects.create(environment=environment, trial_started_at=started)


class _StudentFixtureMixin:
    """Mirrors `studentarea.tests.Base.student` — a logged-in APIClient for
    a student enrolled in `env`."""

    def student_client(self, env, phone, name, grade, group=None):
        user = self.make_student_in(env, phone, name)
        user.is_active = True
        user.set_password(PASSWORD)
        user.save()
        enrollment = make_enrollment(env, user, grade, group)
        client = APIClient()
        tok = client.post("/api/v1/auth/student/login/", {"phone": "+" + phone, "password": PASSWORD}).data["access"]
        client.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return client, enrollment


class PlanGatedQuizAndStateRecommendationTests(_StudentFixtureMixin, TenantTestCase):
    """AC-BILL-011-1: Plan 1 grants `ai.quiz_from_video` (quiz submit
    allowed) but not `ai.performance_analysis` (state-recommendation
    submit refused with a stable code)."""

    def setUp(self):
        super().setUp()
        grant_plan(self.env_a, Plan.Key.PLAN_1)
        self.grade = Grade.objects.create(environment=self.env_a, name="g", fee_amount=1)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.enrollment = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201099911111", "s1"), self.grade, self.group)
        self.content = ContentItem.objects.create(
            environment=self.env_a, title="t", description="d" * 60, video_provider="youtube",
            video_ref="dQw4w9WgXcQ", published_at=timezone.now(),
        )
        self.content.target_grades.add(self.grade)
        self.student_cli, self.student_enrollment = self.student_client(self.env_a, "201099922222", "s2", self.grade, self.group)

    def test_quiz_submit_is_allowed_on_plan_1(self):
        r = self.student_cli.post(QUIZ_URL, {"content_id": self.content.id}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 202, r.content)

    def test_state_recommendation_submit_is_refused_on_plan_1(self):
        month = timezone.now().strftime("%Y-%m")
        r = self.client_a.post(
            STATE_REC_URL, {"enrollment_id": self.enrollment.id, "month": month}, format="json",
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 403, r.content)
        self.assertEqual(r.json()["code"], "capability_not_in_plan")


class TrialGrantsFullPlan3CapabilitySetTests(_StudentFixtureMixin, TenantTestCase):
    """AC-BILL-011-2: an unexpired trial can use every Plan 3 gated
    capability — both `ai.quiz_from_video` and `ai.performance_analysis`."""

    def setUp(self):
        super().setUp()
        grant_trial(self.env_a)
        self.grade = Grade.objects.create(environment=self.env_a, name="g", fee_amount=1)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.enrollment = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201099933333", "s3"), self.grade, self.group)
        self.content = ContentItem.objects.create(
            environment=self.env_a, title="t", description="d" * 60, video_provider="youtube",
            video_ref="dQw4w9WgXcQ", published_at=timezone.now(),
        )
        self.content.target_grades.add(self.grade)
        self.student_cli, _ = self.student_client(self.env_a, "201099944444", "s4", self.grade, self.group)

    def test_quiz_submit_is_allowed_on_trial(self):
        r = self.student_cli.post(QUIZ_URL, {"content_id": self.content.id}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 202, r.content)

    def test_state_recommendation_submit_is_allowed_on_trial(self):
        month = timezone.now().strftime("%Y-%m")
        r = self.client_a.post(
            STATE_REC_URL, {"enrollment_id": self.enrollment.id, "month": month}, format="json",
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 202, r.content)


class ExpiredTrialNoSubscriptionTests(_StudentFixtureMixin, TenantTestCase):
    """AC-BILL-011-3: an expired-trial/no-subscription Environment is
    refused gated AI submissions but can still GET existing AI results,
    log in, and reach always-permitted billing endpoints."""

    def setUp(self):
        super().setUp()
        grant_trial(self.env_a, expired=True)
        self.grade = Grade.objects.create(environment=self.env_a, name="g", fee_amount=1)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.enrollment = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201099955555", "s5"), self.grade, self.group)
        self.content = ContentItem.objects.create(
            environment=self.env_a, title="t", description="d" * 60, video_provider="youtube",
            video_ref="dQw4w9WgXcQ", published_at=timezone.now(),
        )
        self.content.target_grades.add(self.grade)
        self.student_cli, _ = self.student_client(self.env_a, "201099966666", "s6", self.grade, self.group)

    def test_quiz_submit_is_refused(self):
        r = self.student_cli.post(QUIZ_URL, {"content_id": self.content.id}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 403, r.content)
        self.assertEqual(r.json()["code"], "capability_not_in_plan")

    def test_state_recommendation_submit_is_refused(self):
        month = timezone.now().strftime("%Y-%m")
        r = self.client_a.post(
            STATE_REC_URL, {"enrollment_id": self.enrollment.id, "month": month}, format="json",
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 403, r.content)

    def test_can_still_poll_existing_quiz_results(self):
        r = self.student_cli.get(f"{QUIZ_URL}operations/999999/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 404)  # a read: reaches the view, just no such row

    def test_can_still_log_in_and_reach_billing(self):
        r = self.client_a.get("/api/v1/billing/plans/")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client_a.get("/api/v1/billing/subscription/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)


class CrossTenantPrecedesEntitlementTests(TenantTestCase):
    """AC-BILL-011-4: the tenant check precedes the entitlement check —
    Teacher B with Teacher A's header gets `environment_forbidden`, never
    an entitlement error, even though env_a has no plan at all (which
    would ALSO deny on entitlement grounds if reached)."""

    def test_state_recommendation_cross_tenant_is_environment_forbidden(self):
        self.assert_cross_tenant_denied(
            "post", STATE_REC_URL, body={"enrollment_id": 1, "month": "2024-01"}, expect_status=403,
            expect_code="environment_forbidden",
        )


class AssistantIsNotGatedTests(_StudentFixtureMixin, TenantTestCase):
    """AC-BILL-011-8: the `assistant` kind's gating status matches the
    recorded BILL-DEC-07 outcome — ungated until decided. No Subscription
    at all exists for env_a here, yet the teacher AND student assistant
    submit both still succeed."""

    def test_teacher_assistant_submit_succeeds_with_no_subscription(self):
        r = self.client_a.post(ASSISTANT_URL, {"prompt": "سؤال"}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 202, r.content)

    def test_student_assistant_submit_succeeds_with_no_subscription(self):
        grade = Grade.objects.create(environment=self.env_a, name="g", fee_amount=1)
        group = Group.objects.create(environment=self.env_a, grade=grade, name="G1")
        client, _ = self.student_client(self.env_a, "201099999999", "s9", grade, group)
        r = client.post(STUDENT_ASSISTANT_URL, {"prompt": "سؤال"}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 202, r.content)


class AuthenticationModuleUntouchedTests(SimpleTestCase):
    """AC-BILL-011-7: `accounts/authentication.py` has no `billing` import
    (AST, not substring — ignores prose that merely discusses this)."""

    def test_accounts_authentication_never_imports_billing(self):
        import ast
        import inspect

        import accounts.authentication as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.startswith("billing"), alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or "").startswith("billing"), node.module)


class PermissionOrderingTests(SimpleTestCase):
    """AC-BILL-011-5: every view that lists (statically or dynamically, via
    `get_permissions`) a `RequiresCapabilityBase`-derived permission lists
    `IsEnvironmentMember` (or a `for_role(...)` subclass of it) earlier in
    the resolved list, for every HTTP method the view defines. Walks the
    real URL resolver (same technique as
    `billing.test_webhooks.AllowAnyRouteEnumerationTests`), not a grep."""

    def _iter_view_classes(self, resolver):
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                yield from self._iter_view_classes(pattern)
            else:
                view_class = getattr(pattern.callback, "view_class", None)
                if view_class is not None:
                    yield view_class

    def test_requires_capability_is_never_listed_before_is_environment_member(self):
        from django.urls import get_resolver

        checked_any = False
        for view_class in self._iter_view_classes(get_resolver()):
            for method in ("GET", "POST", "PUT", "DELETE"):
                view = view_class()
                view.request = types.SimpleNamespace(method=method)
                try:
                    permissions = view.get_permissions()
                except Exception:
                    continue
                classes = [type(p) for p in permissions]
                cap_indexes = [i for i, c in enumerate(classes) if issubclass(c, RequiresCapabilityBase)]
                if not cap_indexes:
                    continue
                checked_any = True
                env_indexes = [i for i, c in enumerate(classes) if issubclass(c, IsEnvironmentMember)]
                self.assertTrue(
                    env_indexes,
                    f"{view_class.__module__}.{view_class.__qualname__} ({method}) has "
                    "RequiresCapability but no IsEnvironmentMember",
                )
                self.assertTrue(
                    all(ei < ci for ei in env_indexes for ci in cap_indexes),
                    f"{view_class.__module__}.{view_class.__qualname__} ({method}): "
                    "RequiresCapability listed before IsEnvironmentMember",
                )
        self.assertTrue(checked_any, "no decorated view was found at all — the test would pass vacuously")
