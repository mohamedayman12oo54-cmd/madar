"""Cross-app access helper kept tiny and import-free at module level so that
accounts/ (lower layer) can call it lazily without an import cycle."""


def student_has_active_enrollment(user) -> bool:
    """True while at least one teacher keeps this student ACTIVE.

    This is the single rule behind "inactive students cannot claim or log in
    unless another teacher activates them" (see accounts/serializers.py,
    accounts/authentication.py, environments/tenancy.py)."""
    from .models import Enrollment

    return Enrollment.objects.filter(student_id=user.id, is_active=True).exists()


def count_for_cap(environment) -> int:
    """BILL-WU-012's counted-student definition for student-cap enforcement
    — this unit's own TRACKED OPEN ITEM (a BILL-DEC-07 sub-item):
    commercial-model decides the CAP NUMBERS (trial 250 / Plan 1 400 /
    Plan 2 800 / Plan 3 none) but never states which enrollments count
    toward them. Candidates considered and NOT silently ruled out: active
    Enrollments scoped to the Environment's CURRENT Academic Year only;
    student EnvironmentMemberships instead of Enrollments. PROPOSED here,
    as the simplest reading until decided otherwise: every ACTIVE
    Enrollment in this Environment, regardless of Academic Year. Whichever
    the eventual decision names, only this one function needs to change —
    every caller (`academics/serializers.py`'s create/re-activate guards)
    goes through it rather than re-deriving the count."""
    from .models import Enrollment

    return Enrollment.objects.filter(environment=environment, is_active=True).count()
