"""Test helpers. Throttle counters live in the cache, which persists across
tests inside one process — clear it before every test so a rate-limit test
can never make an unrelated test fail (and vice-versa)."""
import itertools

from django.core.cache import cache
from django.test import TestCase as DjangoTestCase

_counter = itertools.count(1)


class TestCase(DjangoTestCase):
    def _pre_setup(self):
        cache.clear()
        super()._pre_setup()


def ensure_active_enrollment(student, env=None, grade=None, active=True):
    """Give `student` an Enrollment (active by default) so the activation rule
    ("a student needs at least one active teacher") is satisfied. Creates a
    throwaway teacher/environment/grade when none is supplied."""
    from academics.models import Enrollment, Grade
    from accounts.models import User
    from environments.models import Environment, EnvironmentMembership

    n = next(_counter)
    if env is None:
        owner = User.objects.create_user(
            role=User.Role.TEACHER, name=f"T{n}", email=f"auto{n}@example.com",
            phone=f"2010999{n:05d}", password="Str0ng!Pass", is_active=True,
        )
        env = Environment.objects.create(owner=owner, name=f"Auto {n}")
        EnvironmentMembership.objects.create(user=owner, environment=env, role="owner")
    grade = grade or Grade.objects.get_or_create(environment=env, name="Auto grade", defaults={"fee_amount": 100})[0]
    EnvironmentMembership.objects.get_or_create(user=student, environment=env, defaults={"role": "student"})
    return Enrollment.objects.create(
        environment=env, student=student, grade=grade, student_name=student.name or "", is_active=active,
    )


def make_enrollment(env, student, grade, group=None, **kw):
    """Create an Enrollment the way the API does (teacher-scoped name, groups
    through the M2M)."""
    from academics.models import Enrollment

    kw.setdefault("student_name", student.name or "")
    enrollment = Enrollment.objects.create(environment=env, student=student, grade=grade, **kw)
    if group is not None:
        enrollment.groups.add(group)
    return enrollment
