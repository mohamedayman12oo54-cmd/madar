"""Automatic guardian warnings (opt-in, idempotent) and the lesson schedule in the guardian portal."""
from datetime import time, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from financials.models import MonthlyPayment
from scheduling.models import AttendanceRecord, Schedule, SessionInstance

from .guardian_alerts import run_all
from .models import GuardianAlertSettings, GuardianMessage
from .test_followup import make_exam, sit
from .tests import OVERVIEW, _Base

SETTINGS = "/api/v1/guardian-messages/settings/"


class _AlertBase(_Base):
    def turn_on(self, **over):
        return GuardianAlertSettings.objects.update_or_create(
            environment=self.env_a, defaults={"enabled": True, **over})[0]

    def absent(self, n):
        # Mid-month on purpose: "this month" must hold whatever day the suite runs on.
        base = timezone.now().replace(day=1, hour=12)
        for i in range(n):
            s = SessionInstance.objects.create(environment=self.env_a, group=self.group,
                                               scheduled_at=base + timedelta(hours=i))
            AttendanceRecord.objects.create(environment=self.env_a, session=s, enrollment=self.enr,
                                            status=AttendanceRecord.Status.ABSENT)

    def autos(self):
        return list(GuardianMessage.objects.exclude(auto_key="").order_by("auto_key"))


class AutoWarningTests(_AlertBase):
    def test_nothing_is_sent_until_the_teacher_turns_it_on(self):
        self.absent(5)
        self.assertEqual(run_all(), 0)
        GuardianAlertSettings.objects.create(environment=self.env_a, enabled=False)
        self.assertEqual(run_all(), 0)
        self.assertEqual(self.autos(), [])

    def test_absences_at_the_threshold_warn_once_per_month(self):
        self.turn_on(absence_threshold=3, unpaid_after_day=0, exam_percent_below=0)
        self.absent(2)
        self.assertEqual(run_all(), 0)
        self.absent(1)
        self.assertEqual(run_all(), 1)
        self.assertEqual(run_all(), 0, "running again repeats nothing")
        (m,) = self.autos()
        self.assertEqual((m.kind, m.title, m.sent_by), ("warning", "تنبيه غياب", None))
        self.assertIn("3 حصص", m.body)
        self.assertTrue(m.auto_key.startswith("absent:"))

    def test_a_threshold_of_zero_switches_that_warning_off(self):
        self.turn_on(absence_threshold=0, unpaid_after_day=0, exam_percent_below=0)
        self.absent(10)
        self.assertEqual(run_all(), 0)

    def test_unpaid_fee_warns_from_the_chosen_day_and_not_when_paid(self):
        self.turn_on(absence_threshold=0, exam_percent_below=0, unpaid_after_day=10)
        real = timezone.localdate()
        with mock.patch("parents.guardian_alerts.timezone.localdate") as today:
            today.return_value = real.replace(day=9)
            self.assertEqual(run_all(), 0, "too early in the month")
            today.return_value = real.replace(day=10)
            self.assertEqual(run_all(), 1)
            self.assertEqual(run_all(), 0)
        (m,) = self.autos()
        self.assertEqual(m.title, "تذكير بمصروفات الشهر")
        self.assertIn("200", m.body)  # the grade's fee, since no payment row exists yet

    def test_a_paid_month_is_never_warned_about(self):
        self.turn_on(absence_threshold=0, exam_percent_below=0, unpaid_after_day=1)
        MonthlyPayment.objects.create(
            environment=self.env_a, enrollment=self.enr, month=timezone.localdate().replace(day=1),
            status=MonthlyPayment.Status.PAID, amount=Decimal("200"), paid_at=timezone.now())
        self.assertEqual(run_all(), 0)

    def test_a_low_exam_score_warns_and_a_retake_that_passes_does_not(self):
        self.turn_on(absence_threshold=0, unpaid_after_day=0, exam_percent_below=50)
        weak = make_exam(self.env_a, self.enr, "ضعيف")
        sit(weak, self.enr, 1, 3)
        fixed = make_exam(self.env_a, self.enr, "اتصلح")
        sit(fixed, self.enr, 1, 3)
        sit(fixed, self.enr, 2, 8)  # the best sitting counts
        fine = make_exam(self.env_a, self.enr, "ممتاز")
        sit(fine, self.enr, 1, 10)
        self.assertEqual(run_all(), 1)
        (m,) = self.autos()
        self.assertEqual(m.auto_key, f"exam:{weak.pk}")
        self.assertIn("«ضعيف»", m.body)
        self.assertIn("30%", m.body)

    def test_one_teachers_rules_never_touch_another_teachers_students(self):
        self.turn_on(absence_threshold=1, unpaid_after_day=0, exam_percent_below=0)
        GuardianAlertSettings.objects.create(environment=self.env_b, enabled=True, absence_threshold=1)
        self.absent(2)
        self.assertEqual(run_all(), 1)
        self.assertEqual(GuardianMessage.objects.filter(environment=self.env_b).count(), 0)

    def test_a_child_without_a_guardian_phone_is_skipped(self):
        self.turn_on(absence_threshold=1, unpaid_after_day=0, exam_percent_below=0)
        self.enr.parent_phone = ""
        self.enr.save(update_fields=["parent_phone"])
        self.absent(2)
        self.assertEqual(run_all(), 0)

    def test_the_warning_reaches_the_portal_and_the_command_runs(self):
        self.turn_on(absence_threshold=1, unpaid_after_day=0, exam_percent_below=0)
        self.absent(1)
        call_command("process_guardian_alerts", stdout=mock.MagicMock())
        msgs = self.portal().get(OVERVIEW).json()["messages"]
        self.assertEqual([m["title"] for m in msgs], ["تنبيه غياب"])


class AlertSettingsEndpointTests(_AlertBase):
    def put(self, client=None, env=None, **body):
        data = {"enabled": True, "absence_threshold": 4, "exam_percent_below": 60, "unpaid_after_day": 12, **body}
        return (client or self.client_a).put(SETTINGS, data, format="json", **self.with_env((env or self.env_a).id))

    def test_defaults_are_off(self):
        r = self.client_a.get(SETTINGS, **self.with_env(self.env_a.id))
        self.assertEqual(r.json(), {"enabled": False, "absence_threshold": 3, "exam_percent_below": 50,
                                    "unpaid_after_day": 10, "show_rank": False})

    def test_a_teacher_saves_their_own_limits_only(self):
        self.assertEqual(self.put().status_code, 200)
        cfg = GuardianAlertSettings.objects.get(environment=self.env_a)
        self.assertEqual((cfg.enabled, cfg.absence_threshold, cfg.exam_percent_below, cfg.unpaid_after_day),
                         (True, 4, 60, 12))
        self.assertFalse(GuardianAlertSettings.objects.filter(environment=self.env_b, enabled=True).exists())

    def test_out_of_range_values_are_refused(self):
        for bad in ({"exam_percent_below": 101}, {"unpaid_after_day": 29}, {"absence_threshold": -1},
                    {"absence_threshold": 32}):
            self.assertEqual(self.put(**bad).status_code, 400, bad)

    def test_another_teacher_cannot_use_my_environment(self):
        self.assert_cross_tenant_denied("put", SETTINGS, body={"enabled": True, "absence_threshold": 1,
                                                                "exam_percent_below": 1, "unpaid_after_day": 1})
        self.assertFalse(GuardianAlertSettings.objects.filter(environment=self.env_a, enabled=True).exists())

    def test_the_teachers_history_marks_automatic_messages(self):
        self.turn_on(absence_threshold=1, unpaid_after_day=0, exam_percent_below=0)
        self.absent(1)
        run_all()
        r = self.client_a.get("/api/v1/guardian-messages/", {"enrollment": self.enr.id}, **self.with_env(self.env_a.id))
        self.assertEqual([m["automatic"] for m in r.json()["results"]], [True])


class ScheduleTests(_Base):
    def schedule(self):
        r = self.portal().get(OVERVIEW)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["schedule"]

    def test_the_guardian_sees_the_weekly_slots_of_the_childs_groups_saturday_first(self):
        Schedule.objects.create(environment=self.env_a, group=self.group, weekday=2, start_time=time(17, 0))
        Schedule.objects.create(environment=self.env_a, group=self.group, weekday=5, start_time=time(18, 0),
                                end_time=time(19, 30))
        weekly = self.schedule()["weekly"]
        self.assertEqual([(w["weekday_label"], w["start_time"], w["end_time"]) for w in weekly],
                         [("السبت", "18:00", "19:30"), ("الأربعاء", "17:00", None)])

    def test_only_upcoming_sessions_of_my_childs_groups_are_listed_in_order(self):
        from academics.models import Group

        other = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        now = timezone.now()
        mk = lambda g, delta, status=SessionInstance.Status.PLANNED: SessionInstance.objects.create(  # noqa: E731
            environment=self.env_a, group=g, scheduled_at=now + delta, status=status)
        later, sooner = mk(self.group, timedelta(days=3)), mk(self.group, timedelta(days=1))
        mk(self.group, -timedelta(days=2))                                  # past
        mk(self.group, timedelta(days=2), SessionInstance.Status.CLOSED)    # closed
        mk(other, timedelta(days=1))                                        # a group the child is not in
        got = self.schedule()["upcoming"]
        self.assertEqual([x["group"] for x in got], ["G1", "G1"])
        self.assertEqual([x["scheduled_at"][:10] for x in got],
                         [(now + timedelta(days=d)).astimezone(dt_timezone.utc).date().isoformat() for d in (1, 3)])
        self.assertTrue(sooner.pk and later.pk)

    def test_no_groups_no_schedule(self):
        self.enr.groups.clear()
        self.assertEqual(self.schedule(), {"weekly": [], "upcoming": []})
