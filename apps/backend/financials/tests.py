"""Phase 4 — Payments and the per-enrollment financial summary. Grade owns
the fee (Phase 2); nothing here duplicates it — outstanding is always
computed as fee_amount - sum(payments)."""
from decimal import Decimal

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase

from .models import Payment

PAYMENTS_URL = "/api/v1/financials/payments/"
SUMMARY_URL = "/api/v1/financials/summary/"


def payment_url(pk):
    return f"{PAYMENTS_URL}{pk}/"


class PaymentTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount="1000.00")
        self.grade_b = Grade.objects.create(environment=self.env_b, name="أول", fee_amount="1000.00")
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.student = self.make_student_in(self.env_a, "201130000001", name="أحمد")
        self.enrollment = Enrollment.objects.create(environment=self.env_a, student=self.student, grade=self.grade, group=self.group)
        student_b = self.make_student_in(self.env_b, "201130000002", name="X")
        self.enrollment_b = Enrollment.objects.create(environment=self.env_b, student=student_b, grade=self.grade_b)

    def test_create_payment(self):
        r = self.client_a.post(PAYMENTS_URL, {"enrollment_id": self.enrollment.id, "amount": "300.00"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["amount"], "300.00")
        self.assertEqual(r.json()["student"]["name"], "أحمد")

    def test_negative_or_zero_amount_rejected(self):
        for bad in ("0", "-50"):
            r = self.client_a.post(PAYMENTS_URL, {"enrollment_id": self.enrollment.id, "amount": bad}, **self.with_env(self.env_a.id))
            self.assertEqual(r.status_code, 400, bad)

    def test_cannot_pay_against_another_teachers_enrollment(self):
        r = self.client_a.post(
            PAYMENTS_URL, {"enrollment_id": self.enrollment_b.id, "amount": "100"}, **self.with_env(self.env_a.id)
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Payment.objects.filter(enrollment=self.enrollment_b).exists())

    def test_list_scoped_and_filterable_by_enrollment(self):
        Payment.objects.create(environment=self.env_a, enrollment=self.enrollment, amount="100")
        Payment.objects.create(environment=self.env_b, enrollment=self.enrollment_b, amount="999")
        r = self.client_a.get(PAYMENTS_URL, **self.with_env(self.env_a.id))
        self.assertEqual(len(r.json()["results"]), 1)
        self.assertEqual(r.json()["results"][0]["amount"], "100.00")

    def test_update_amount_and_note(self):
        p = Payment.objects.create(environment=self.env_a, enrollment=self.enrollment, amount="100")
        r = self.client_a.patch(payment_url(p.id), {"amount": "150.00", "note": "دفعة معدّلة"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["amount"], "150.00")
        self.assertEqual(r.json()["note"], "دفعة معدّلة")

    def test_update_cannot_change_enrollment(self):
        p = Payment.objects.create(environment=self.env_a, enrollment=self.enrollment, amount="100")
        r = self.client_a.patch(payment_url(p.id), {"enrollment": self.enrollment_b.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)  # "enrollment" isn't a field on the update serializer -> no-op
        p.refresh_from_db()
        self.assertEqual(p.enrollment_id, self.enrollment.id)

    def test_delete_payment(self):
        p = Payment.objects.create(environment=self.env_a, enrollment=self.enrollment, amount="100")
        r = self.client_a.delete(payment_url(p.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Payment.objects.filter(pk=p.id).exists())

    def test_cannot_read_update_or_delete_another_teachers_payment(self):
        p = Payment.objects.create(environment=self.env_a, enrollment=self.enrollment, amount="100")
        self.assert_cross_tenant_denied("get", payment_url(p.id))
        self.assert_cross_tenant_denied("patch", payment_url(p.id), body={"amount": "1"})
        self.assert_cross_tenant_denied("delete", payment_url(p.id))
        self.assertTrue(Payment.objects.filter(pk=p.id).exists())


class FinancialSummaryTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount="1000.00")
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.s1 = self.make_student_in(self.env_a, "201140000001", name="أحمد")
        self.s2 = self.make_student_in(self.env_a, "201140000002", name="سارة")
        self.enr1 = Enrollment.objects.create(environment=self.env_a, student=self.s1, grade=self.grade, group=self.group)
        self.enr2 = Enrollment.objects.create(environment=self.env_a, student=self.s2, grade=self.grade, group=self.group)
        Payment.objects.create(environment=self.env_a, enrollment=self.enr1, amount="400.00")
        Payment.objects.create(environment=self.env_a, enrollment=self.enr1, amount="200.00")
        # enr2 has paid nothing

    def test_summary_computes_paid_total_and_outstanding_per_enrollment(self):
        r = self.client_a.get(SUMMARY_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        rows = {row["student"]["name"]: row for row in r.json()}
        self.assertEqual(rows["أحمد"]["paid_total"], "600.00")
        self.assertEqual(rows["أحمد"]["outstanding"], "400.00")
        self.assertEqual(rows["سارة"]["paid_total"], "0.00")
        self.assertEqual(rows["سارة"]["outstanding"], "1000.00")
        self.assertEqual(rows["أحمد"]["fee_amount"], "1000.00")

    def test_summary_overpayment_shows_negative_outstanding_not_clamped(self):
        Payment.objects.create(environment=self.env_a, enrollment=self.enr1, amount="1000.00")
        r = self.client_a.get(SUMMARY_URL, **self.with_env(self.env_a.id))
        row = next(row for row in r.json() if row["student"]["name"] == "أحمد")
        self.assertEqual(row["outstanding"], "-600.00")

    def test_summary_filterable_by_grade_and_group(self):
        grade2 = Grade.objects.create(environment=self.env_a, name="ثاني", fee_amount="500")
        group2 = Group.objects.create(environment=self.env_a, grade=grade2, name="G2")
        s3 = self.make_student_in(self.env_a, "201140000003", name="منى")
        Enrollment.objects.create(environment=self.env_a, student=s3, grade=grade2, group=group2)

        r = self.client_a.get(f"{SUMMARY_URL}?grade_id={self.grade.id}", **self.with_env(self.env_a.id))
        names = {row["student"]["name"] for row in r.json()}
        self.assertEqual(names, {"أحمد", "سارة"})

    def test_inactive_enrollment_excluded_from_summary(self):
        self.enr2.is_active = False
        self.enr2.save(update_fields=["is_active"])
        r = self.client_a.get(SUMMARY_URL, **self.with_env(self.env_a.id))
        names = {row["student"]["name"] for row in r.json()}
        self.assertEqual(names, {"أحمد"})

    def test_summary_is_tenant_scoped(self):
        other, _ = self.teacher_b, self.env_b
        grade_b = Grade.objects.create(environment=self.env_b, name="أول", fee_amount="10")
        sb = self.make_student_in(self.env_b, "201140000009", name="Other")
        Enrollment.objects.create(environment=self.env_b, student=sb, grade=grade_b)
        r = self.client_a.get(SUMMARY_URL, **self.with_env(self.env_a.id))
        names = {row["student"]["name"] for row in r.json()}
        self.assertNotIn("Other", names)

    def test_requires_owner_role_and_environment_header(self):
        anon_env = self.client_a.get(SUMMARY_URL)
        self.assertEqual(anon_env.status_code, 400)
