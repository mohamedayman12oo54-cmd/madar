"""
BILL-WU-012 — student-cap enforcement on enrollment creation and
re-activation.
"""
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from accounts.testing import make_enrollment
from billing.entitlements import StudentCapReached
from billing.models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, Subscription
from environments.models import current_academic_year
from environments.tenancy_testing import TenantTestCase

from .access import count_for_cap
from .models import Enrollment, Grade
from .serializers import EnrollmentCreateSerializer, EnrollmentUpdateSerializer

ENROLL_URL = "/api/v1/academics/enrollments/"


def enrollment_url(pk):
    return f"{ENROLL_URL}{pk}/"


def grant_trial(environment, *, expired=False):
    started = timezone.now() - timedelta(days=100) if expired else timezone.now()
    return Subscription.objects.create(environment=environment, trial_started_at=started)


def grant_plan(environment, plan_key):
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
        merchant_order_id=f"cap-{subscription.pk}", amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=PaymentAttempt.Status.SUCCEEDED,
    )
    return subscription


def bulk_active_students(environment, grade, count, tag):
    """Direct bulk insert — not `create_user`/`Enrollment.save()` — purely
    to make a 250/400/800-row fixture fast; these rows are never logged
    into or otherwise exercised beyond being counted."""
    users = User.objects.bulk_create(
        [
            User(
                username=f"u_cap_{tag}_{i}", phone=f"20109{tag}{i:05d}", role=User.Role.STUDENT,
                name=f"s{i}", is_active=False, is_verified=False,
            )
            for i in range(count)
        ]
    )
    Enrollment.objects.bulk_create(
        [
            Enrollment(
                environment=environment, student=u, grade=grade, student_name=u.name,
                academic_year=current_academic_year(), is_active=True,
            )
            for u in users
        ]
    )


class _FakeRequest:
    def __init__(self, environment):
        self.environment = environment


def create_student(environment, *, name, phone, grade, is_active=True):
    request = _FakeRequest(environment)
    ser = EnrollmentCreateSerializer(
        data={"name": name, "phone": phone, "grade_id": grade.id, "parent_phone": "201199900000", "is_active": is_active},
        context={"request": request},
    )
    ser.is_valid(raise_exception=True)
    return ser.save()


class CapByPlanTests(TenantTestCase):
    """AC-BILL-012-1: trial 250 / Plan 1 400 / Plan 2 800 / Plan 3 none."""

    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="g")

    def test_trial_rejects_the_251st_active_student(self):
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, self.grade, 250, "tr")
        self.assertEqual(count_for_cap(self.env_a), 250)

        with self.assertRaises(StudentCapReached):
            create_student(self.env_a, name="جديد", phone="201090000001", grade=self.grade)

    def test_plan_1_rejects_the_401st_active_student(self):
        grant_plan(self.env_a, Plan.Key.PLAN_1)
        bulk_active_students(self.env_a, self.grade, 400, "p1")

        with self.assertRaises(StudentCapReached):
            create_student(self.env_a, name="جديد", phone="201090000002", grade=self.grade)

    def test_plan_2_rejects_the_801st_active_student(self):
        grant_plan(self.env_a, Plan.Key.PLAN_2)
        bulk_active_students(self.env_a, self.grade, 800, "p2")

        with self.assertRaises(StudentCapReached):
            create_student(self.env_a, name="جديد", phone="201090000003", grade=self.grade)

    def test_plan_3_accepts_beyond_800(self):
        grant_plan(self.env_a, Plan.Key.PLAN_3)
        bulk_active_students(self.env_a, self.grade, 800, "p3")

        enrollment, created = create_student(self.env_a, name="جديد", phone="201090000004", grade=self.grade)
        self.assertTrue(created)
        self.assertEqual(count_for_cap(self.env_a), 801)

    def test_under_cap_add_succeeds(self):
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, self.grade, 249, "under")

        enrollment, created = create_student(self.env_a, name="جديد", phone="201090000005", grade=self.grade)
        self.assertTrue(created)


class ReactivationCapTests(TenantTestCase):
    """AC-BILL-012-2: re-activating at cap is rejected; deactivating is
    always allowed."""

    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="g")
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, self.grade, 250, "react")
        student = self.make_student_in(self.env_a, "201090000006", "x")
        self.inactive_enrollment = make_enrollment(self.env_a, student, self.grade)
        self.inactive_enrollment.is_active = False
        self.inactive_enrollment.save(update_fields=["is_active"])

    def test_reactivating_at_cap_is_rejected(self):
        request = _FakeRequest(self.env_a)
        ser = EnrollmentUpdateSerializer(
            self.inactive_enrollment, data={"is_active": True}, partial=True, context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        with self.assertRaises(StudentCapReached):
            ser.save()
        self.inactive_enrollment.refresh_from_db()
        self.assertFalse(self.inactive_enrollment.is_active)

    def test_deactivating_an_active_enrollment_is_always_allowed(self):
        active = Enrollment.objects.filter(environment=self.env_a, is_active=True).first()
        request = _FakeRequest(self.env_a)
        ser = EnrollmentUpdateSerializer(active, data={"is_active": False}, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        active.refresh_from_db()
        self.assertFalse(active.is_active)


class OverCapRosterUntouchedTests(TenantTestCase):
    """AC-BILL-012-4: an existing over-cap roster is never deactivated."""

    def test_adding_a_student_that_is_rejected_deactivates_nobody(self):
        grade = Grade.objects.create(environment=self.env_a, name="g")
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, grade, 260, "over")  # already over cap

        with self.assertRaises(StudentCapReached):
            create_student(self.env_a, name="جديد", phone="201090000007", grade=grade)

        self.assertEqual(count_for_cap(self.env_a), 260)  # untouched, none deactivated


class CountDefinitionTests(TenantTestCase):
    """AC-BILL-012-5: a single counting function with a docstring citing
    the open item."""

    def test_count_for_cap_is_one_function_whose_docstring_cites_the_open_item(self):
        self.assertIsNotNone(count_for_cap.__doc__)
        self.assertIn("BILL-WU-012", count_for_cap.__doc__)
        self.assertIn("open", count_for_cap.__doc__.lower())

    def test_an_inactive_new_enrollment_is_never_counted_or_blocked(self):
        grade = Grade.objects.create(environment=self.env_a, name="g")
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, grade, 250, "inact")

        enrollment, created = create_student(self.env_a, name="جديد", phone="201090000008", grade=grade, is_active=False)
        self.assertTrue(created)
        self.assertEqual(count_for_cap(self.env_a), 250)  # the new row is inactive — never counted

    def test_an_idempotent_reenroll_of_an_existing_student_is_never_blocked_by_the_cap(self):
        grade = Grade.objects.create(environment=self.env_a, name="g")
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, grade, 250, "idem")
        existing_student = self.make_student_in(self.env_a, "201090000009", "موجود")
        make_enrollment(self.env_a, existing_student, grade)

        enrollment, created = create_student(self.env_a, name="موجود", phone="201090000009", grade=grade)
        self.assertFalse(created)  # same (environment, student) — the get_or_create path


class ConcurrentEnrollmentAtCapTests(TenantTestCase):
    """AC-BILL-012-3: two concurrent adds at cap - 1 result in exactly one
    success. Both calls take the SAME first lock (the Subscription row,
    via `student_cap_locked`) before counting, so the realistic race is
    exercised sequentially — same convention as
    `billing.test_process_billing_renewals.ConcurrentClaimTests` — via two
    calls to `EnrollmentCreateSerializer.save()`, each with its own inner
    `transaction.atomic()`. Deliberately `TenantTestCase`, not
    `TransactionTestCase`: the logic under test (the second call's count
    must see the first call's insert) only needs savepoint-level
    visibility within one connection, which `TestCase`'s outer atomic
    wrapper already gives; a real `TransactionTestCase` here would flush
    the migration-seeded `Plan` catalog (`academics` precedes `billing` in
    `INSTALLED_APPS`, so this app's own `TransactionTestCase` would always
    run before `billing.test_checkout`'s, breaking that unrelated,
    already-VERIFIED test — avoided by not needing a real `flush()` here
    rather than by touching that file)."""

    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="g")
        grant_trial(self.env_a)
        bulk_active_students(self.env_a, self.grade, 249, "race")  # exactly cap - 1

    def test_two_concurrent_adds_at_cap_minus_one_yield_exactly_one_success(self):
        enrollment_a, created_a = create_student(self.env_a, name="أحمد", phone="201090000010", grade=self.grade)
        self.assertTrue(created_a)

        with self.assertRaises(StudentCapReached):
            create_student(self.env_a, name="باسم", phone="201090000011", grade=self.grade)

        self.assertEqual(count_for_cap(self.env_a), 250)
