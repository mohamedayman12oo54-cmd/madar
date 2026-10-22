"""BILL-WU-003 / 006 — INV-9: one Teacher Account owns exactly one Environment, enforced by the DB."""
import io
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from accounts.models import User
from environments.management.commands.check_environment_cardinality import duplicate_owner_report
from environments.models import Environment, EnvironmentMembership


def teacher(n):
    return User.objects.create_user(role=User.Role.TEACHER, name=f"PII-name-{n}", email=f"pii{n}@example.com",
                                    phone=f"2010999{n:04d}", password="x", is_active=True)


def run():
    out = io.StringIO()
    try:
        call_command("check_environment_cardinality", stdout=out)
        return 0, out.getvalue()
    except CommandError as exc:
        return 1, out.getvalue() + str(exc)


class OneEnvironmentPerTeacherTests(TestCase):
    def test_a_second_environment_for_the_same_owner_is_rejected_by_the_database(self):
        t = teacher(1)
        Environment.objects.create(owner=t, name="one")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Environment.objects.create(owner=t, name="two")

    def test_the_unique_index_really_exists_in_postgres(self):
        with connection.cursor() as cur:
            cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'environments_environment'")
            defs = " ".join(r[0] for r in cur.fetchall()).lower()
        self.assertIn("unique", defs)
        self.assertIn("owner_id", defs)

    def test_reverse_accessor_is_a_single_object(self):
        t = teacher(2)
        env = Environment.objects.create(owner=t, name="e")
        self.assertEqual(t.owned_environment, env)

    def test_teachers_each_get_their_own(self):
        a, b = teacher(3), teacher(4)
        Environment.objects.create(owner=a, name="a")
        Environment.objects.create(owner=b, name="b")
        self.assertEqual(Environment.objects.count(), 2)

    def test_teacher_environment_list_still_returns_a_list(self):
        from rest_framework.test import APIClient
        t = teacher(5)
        env = Environment.objects.create(owner=t, name="e")
        EnvironmentMembership.objects.create(user=t, environment=env, role="owner")
        t.set_password("Str0ng!Pass-1"); t.save()
        c = APIClient()
        tok = c.post("/api/v1/auth/teacher/login/", {"identifier": t.email, "password": "Str0ng!Pass-1"}).json()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok['access']}")
        r = c.get("/api/v1/environments/teacher/")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        self.assertEqual(len(r.json()), 1)


class CardinalityCheckCommandTests(TestCase):
    def test_clean_database_passes(self):
        t = teacher(10)
        env = Environment.objects.create(owner=t, name="e")
        EnvironmentMembership.objects.create(user=t, environment=env, role="owner")
        code, out = run()
        self.assertEqual(code, 0, out)
        self.assertIn("owners_with_multiple_environments=0", out)

    def test_owner_without_membership_is_reported_and_fails(self):
        t = teacher(11)
        env = Environment.objects.create(owner=t, name="e")
        code, out = run()
        self.assertEqual(code, 1)
        self.assertIn(f"({env.id}, {t.id})", out)

    def test_it_reports_duplicates_if_the_constraint_is_absent(self):
        """Simulates a not-yet-migrated database: drop the unique index, create a duplicate."""
        t = teacher(12)
        e1 = Environment.objects.create(owner=t, name="first")
        with connection.cursor() as cur:
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute("SELECT conname FROM pg_constraint WHERE conrelid = 'environments_environment'::regclass AND contype = 'u'")
            names = [r[0] for r in cur.fetchall()]
            for n in names:
                cur.execute(f'ALTER TABLE environments_environment DROP CONSTRAINT "{n}"')
            e2 = Environment.objects.create(owner=t, name="second")
            report = duplicate_owner_report()
            self.assertEqual([r["owner_id"] for r in report], [t.id])
            self.assertEqual({e["id"] for e in report[0]["environments"]}, {e1.id, e2.id})
            code, out = run()
        self.assertEqual(code, 1)
        self.assertIn("INV-9 check FAILED", out)

    def test_the_report_contains_no_personal_data(self):
        t = teacher(13)
        env = Environment.objects.create(owner=t, name="SECRET-ENV-NAME")
        EnvironmentMembership.objects.create(user=t, environment=env, role="owner")
        _, out = run()
        for needle in ("PII-name", "pii13@example.com", "2010999", "SECRET-ENV-NAME"):
            self.assertNotIn(needle, out)

    def test_the_command_performs_no_writes(self):
        t = teacher(14)
        Environment.objects.create(owner=t, name="e")
        before = (Environment.objects.count(), EnvironmentMembership.objects.count(), User.objects.count())
        run()
        self.assertEqual(before, (Environment.objects.count(), EnvironmentMembership.objects.count(), User.objects.count()))


class SeedDemoTests(TestCase):
    def test_seed_demo_leaves_every_teacher_with_one_environment_even_when_run_twice(self):
        call_command("seed_demo", stdout=io.StringIO())
        call_command("seed_demo", stdout=io.StringIO())
        code, out = run()
        self.assertEqual(code, 0, out)
