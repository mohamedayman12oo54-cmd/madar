from django.core.management.base import BaseCommand

from accounts.models import User
from environments.models import Environment, EnvironmentMembership

DEMO_PASSWORD = "Demo1234!"


class Command(BaseCommand):
    """Seeds a small, realistic demo dataset so every frontend screen can
    be exercised immediately without manually walking through signup:
      - a team account
      - a teacher with two environments
      - one already-claimed student, one pre-registered-but-unclaimed
        student (to try the '/auth/student/claim' flow with)
    Safe to re-run — it upserts rather than duplicating."""

    help = "Seed demo accounts for manual/frontend testing."

    def handle(self, *args, **options):
        team, _ = User.objects.update_or_create(
            username="team@madar",
            defaults=dict(role=User.Role.TEAM, name="Team Madar", is_active=True, is_verified=True),
        )
        team.set_password(DEMO_PASSWORD)
        team.save()

        teacher, _ = User.objects.update_or_create(
            email="ahmed@madar.test",
            defaults=dict(
                role=User.Role.TEACHER, name="أستاذ أحمد", phone="201001234567",
                is_active=True, is_verified=True,
            ),
        )
        teacher.set_password(DEMO_PASSWORD)
        teacher.save()

        env_a, _ = Environment.objects.get_or_create(
            owner=teacher, name="مجموعات الصف الثالث الثانوي", defaults={"subject_stage": "الرياضيات"}
        )
        env_b, _ = Environment.objects.get_or_create(
            owner=teacher, name="مجموعات الصف الثاني الثانوي", defaults={"subject_stage": "الرياضيات"}
        )
        EnvironmentMembership.objects.get_or_create(user=teacher, environment=env_a, defaults={"role": "owner"})
        EnvironmentMembership.objects.get_or_create(user=teacher, environment=env_b, defaults={"role": "owner"})

        claimed, _ = User.objects.update_or_create(
            phone="201119998888",
            defaults=dict(role=User.Role.STUDENT, name="طالب مفعّل", is_active=True, is_verified=True),
        )
        claimed.set_password(DEMO_PASSWORD)
        claimed.save()
        EnvironmentMembership.objects.get_or_create(user=claimed, environment=env_a, defaults={"role": "student"})

        unclaimed, _ = User.objects.update_or_create(
            phone="201117776666",
            defaults=dict(role=User.Role.STUDENT, name="طالب غير مفعّل", is_active=False, is_verified=False),
        )
        unclaimed.set_unusable_password()
        unclaimed.save()
        EnvironmentMembership.objects.get_or_create(user=unclaimed, environment=env_a, defaults={"role": "student"})

        self.stdout.write(self.style.SUCCESS("Demo data ready. Password for every seeded account: " + DEMO_PASSWORD))
        self.stdout.write("  Team login:    identifier=team@madar")
        self.stdout.write("  Teacher login: identifier=ahmed@madar.test  (or phone 201001234567)")
        self.stdout.write("  Student login (already claimed): phone=201119998888")
        self.stdout.write("  Student claim (try /auth/student/claim): phone=201117776666")
