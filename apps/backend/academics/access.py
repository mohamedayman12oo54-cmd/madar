"""Cross-app access helper kept tiny and import-free at module level so that
accounts/ (lower layer) can call it lazily without an import cycle."""


def student_has_active_enrollment(user) -> bool:
    """True while at least one teacher keeps this student ACTIVE.

    This is the single rule behind "inactive students cannot claim or log in
    unless another teacher activates them" (see accounts/serializers.py,
    accounts/authentication.py, environments/tenancy.py)."""
    from .models import Enrollment

    return Enrollment.objects.filter(student_id=user.id, is_active=True).exists()
