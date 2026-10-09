"""Monthly paid/unpaid tracking (docs: Payment = Enrollment x Calendar Month,
record-only, fee owned by the Grade)."""
from decimal import Decimal

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from config.months import current_month
from environments.tenancy_testing import TenantTestCase

from .models import MonthlyPayment

M = "/api/v1/financials/monthly/"


class PaymentTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.month = current_month().strftime("%Y-%m")
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=Decimal("250.00"))
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.s1 = self.make_student_in(self.env_a, "201011100001", name="أحمد")
        self.s2 = self.make_student_in(self.env_a, "201011100002", name="سارة")
        self.e1 = make_enrollment(self.env_a, self.s1, self.grade, self.group)
        self.e2 = make_enrollment(self.env_a, self.s2, self.grade, self.group)

    def put(self, enrollment, status, month=None, client=None, env=None, **extra):
        c = client or self.client_a
        return c.put(M, {"enrollment_id": enrollment.id, "month": month or self.month, "status": status, **extra},
                     format="json", **self.with_env((env or self.env_a).id))

    def sheet(self, qs=""):
        return self.client_a.get(f"{M}?month={self.month}{qs}", **self.with_env(self.env_a.id)).json()

    def test_sheet_lists_every_active_student_unpaid_by_default_with_grade_fee(self):
        body = self.sheet()
        self.assertEqual([r["status"] for r in body["rows"]], ["unpaid", "unpaid"])
        self.assertEqual(body["rows"][0]["amount"], "250.00")
        self.assertEqual(body["summary"]["expected_total"], "500.00")
        self.assertEqual(body["summary"]["outstanding_total"], "500.00")

    def test_mark_paid_then_unpaid_is_one_row_and_totals_follow(self):
        self.assertEqual(self.put(self.e1, "paid").status_code, 200)
        s = self.sheet()["summary"]
        self.assertEqual((s["paid"], s["unpaid"], s["collected_total"], s["outstanding_total"]), (1, 1, "250.00", "250.00"))
        self.assertEqual(self.put(self.e1, "unpaid").status_code, 200)
        self.assertEqual(MonthlyPayment.objects.count(), 1)
        self.assertIsNone(MonthlyPayment.objects.get().paid_at)

    def test_client_cannot_choose_the_amount(self):
        """No discounts / partial payments (docs): the amount is the grade fee."""
        self.put(self.e1, "paid", amount="1")
        self.assertEqual(MonthlyPayment.objects.get().amount, Decimal("250.00"))

    def test_changing_the_grade_fee_later_does_not_rewrite_recorded_months(self):
        self.put(self.e1, "paid")
        self.grade.fee_amount = Decimal("400.00")
        self.grade.save()
        self.assertEqual(MonthlyPayment.objects.get().amount, Decimal("250.00"))

    def test_second_group_in_same_grade_creates_no_extra_obligation(self):
        g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.e1.groups.add(g2)
        self.put(self.e1, "paid")
        self.assertEqual(self.sheet()["summary"]["expected_total"], "500.00")
        self.assertEqual(MonthlyPayment.objects.count(), 1)

    def test_inactive_students_are_not_on_the_sheet_and_cannot_be_charged(self):
        self.e2.is_active = False
        self.e2.save()
        self.assertEqual(len(self.sheet()["rows"]), 1)
        self.assertEqual(self.put(self.e2, "paid").status_code, 400)

    def test_filter_by_status(self):
        self.put(self.e1, "paid")
        self.assertEqual([r["name"] for r in self.sheet("&status=paid")["rows"]], ["أحمد"])
        self.assertEqual([r["name"] for r in self.sheet("&status=unpaid")["rows"]], ["سارة"])

    def test_bad_or_out_of_range_months_rejected(self):
        for m in ("2026-13", "26-01", "abc", "1999-01", "2099-01"):
            self.assertEqual(self.put(self.e1, "paid", month=m).status_code, 400, m)

    def test_other_status_values_rejected(self):
        self.assertEqual(self.put(self.e1, "partial").status_code, 400)

    def test_history_is_per_student(self):
        self.put(self.e1, "paid")
        r = self.client_a.get(f"/api/v1/financials/enrollments/{self.e1.id}/history/", **self.with_env(self.env_a.id))
        self.assertEqual([x["status"] for x in r.json()], ["paid"])

    def test_cross_tenant_isolation(self):
        self.assert_cross_tenant_denied("get", M)
        r = self.put(self.e1, "paid", client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 404)  # B's own env, A's enrollment id -> not found
        self.assertEqual(MonthlyPayment.objects.count(), 0)
        self.assertEqual(self.client_b.get(f"{M}?month={self.month}", **self.with_env(self.env_b.id)).json()["rows"], [])
