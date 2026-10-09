"""
Phase 2 / Educational Foundation.

Domain rules enforced here (from the product spec, not invented):
- Grade OWNS the fee (`Grade.fee_amount`) — never move fee ownership onto
  Student/Enrollment/Group/Session.
- Group belongs to a Teacher Environment AND a Grade; a Group's students are
  reached through Enrollment, not a direct Group<->Student relation.
- Enrollment is the ownership boundary between a (globally-identified)
  Student and one Teacher Environment. Its `grade` and `academic_year` are
  immutable once set — enforced here (defense in depth) and in
  academics/serializers.py (the actual enforcement point for the API: PATCH
  simply never exposes these fields).
- Student identity stays global (accounts.User, role=student) — nothing here
  duplicates it per environment; only the relationship (Enrollment) and the
  membership row (environments.EnvironmentMembership, unchanged from Phase 0)
  are tenant-scoped.

All three models subclass TenantOwnedModel (environments/tenancy.py), so
`environment` is set exactly once, from `request.environment`
(IsEnvironmentMember), by TenantScopedQuerySetMixin.perform_create — never
from client input.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
import secrets

from django.db import models

from environments.models import current_academic_year
from environments.tenancy import TenantOwnedModel


class Grade(TenantOwnedModel):
    name = models.CharField(max_length=100)
    # GRADE OWNS THE FEE — see module docstring. Never referenced by Group,
    # Session, or Student; Enrollment reads it through `enrollment.grade.fee_amount`.
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order = models.PositiveIntegerField(default=0, help_text="Display ordering only.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["environment", "name"], name="unique_grade_name_per_environment"),
        ]

    def __str__(self):
        return f"{self.name} ({self.environment})"


class Group(TenantOwnedModel):
    """GROUP OWNS SESSIONS (Phase 3 will add Session Instance with a FK
    here). A Group's students are reached through Enrollment.group, not a
    direct M2M — see module docstring."""

    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="groups")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["environment", "grade", "name"], name="unique_group_name_per_grade"),
        ]

    def clean(self):
        if self.grade_id and self.environment_id and self.grade.environment_id != self.environment_id:
            raise ValidationError("المجموعة يجب أن تنتمي لنفس بيئة الصف.")

    def __str__(self):
        return f"{self.name} — {self.grade}"


# Unambiguous alphabet: no 0/O, no 1/I/L. A teacher reads a badge aloud or
# types it in, so look-alike characters would cause real misreads.
BADGE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
BADGE_LENGTH = 6


def new_qr_token():
    """A short, human-readable badge code: 6 characters from a 31-symbol
    unambiguous alphabet (~8.9e8 combinations).

    Short enough to read off a badge or type by hand, and safe because it is
    never the only control: resolution is tenant-scoped (a code only means
    anything inside the teacher's own environment), the scan endpoints are
    rate limited, and the teacher can rotate a code instantly. `unique=True`
    turns the rare collision into a retry.
    """
    return "".join(secrets.choice(BADGE_ALPHABET) for _ in range(BADGE_LENGTH))


class Enrollment(TenantOwnedModel):
    """The Student <-> Teacher Environment relationship boundary.
    `student` is a global identity (accounts.User); everything else here is
    scoped to one `environment`. `grade` and `academic_year` are immutable
    after creation (INV-3, see module docstring); `groups` (INV-4: a student
    may attend several groups, all inside the enrollment's grade) and
    `is_active` are not.

    Teacher-scoped identity data lives HERE, not on the global User:
      - `student_name`: what THIS teacher calls the student. Renaming it never
        touches the global account, so one teacher can neither see nor change
        what another teacher typed (INV-7 — isolation of records, not identity).
      - `parent_name` / `parent_phone`: parent contact is Enrollment-owned
        data; it creates no parent account or access right.
    `is_active` is the teacher's switch: a student with NO active enrollment
    anywhere cannot claim an account or log in (academics/access.py)."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments",
        limit_choices_to={"role": "student"},
    )
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="enrollments")
    groups = models.ManyToManyField(Group, blank=True, related_name="member_enrollments")
    student_name = models.CharField(max_length=150, blank=True)
    # --- student QR badge -------------------------------------------------
    # An OPAQUE, unguessable handle printed on the student's badge. It is
    # deliberately NOT the enrollment id and carries no personal data, so a
    # photographed code reveals nothing and ids cannot be enumerated. It is
    # rotatable: `rotate_qr_token()` instantly invalidates a lost/shared badge.
    # Resolution is always server-side AND tenant-scoped, so a badge from
    # another teacher's environment simply does not resolve.
    qr_token = models.CharField(max_length=BADGE_LENGTH, unique=True, default=new_qr_token, editable=False)

    parent_name = models.CharField(max_length=150, blank=True)
    parent_phone = models.CharField(max_length=20, blank=True)
    academic_year = models.CharField(max_length=20, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["environment", "student"], name="unique_enrollment_per_environment"),
        ]

    @property
    def display_name(self) -> str:
        return self.student_name or self.student.name

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Captured on load (and after every save) so `save()` can detect an
        # attempt to change grade/academic_year on an EXISTING row. Never
        # true for a brand-new instance (both are None until first save).
        self._original_grade_id = self.grade_id
        self._original_academic_year = self.academic_year

    def save(self, *args, **kwargs):
        if not self.academic_year:
            self.academic_year = current_academic_year()
        if self.pk and (self.grade_id != self._original_grade_id or self.academic_year != self._original_academic_year):
            raise ValidationError("لا يمكن تعديل الصف أو العام الدراسي بعد إنشاء التسجيل.")
        if self.pk is None:
            # A 6-character code can collide; retry with a fresh one instead of
            # failing the enrolment.
            from django.db import IntegrityError, transaction

            for attempt in range(8):
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    if attempt == 7:
                        raise
                    self.qr_token = new_qr_token()
            self._original_grade_id = self.grade_id
            self._original_academic_year = self.academic_year
            return
        super().save(*args, **kwargs)
        self._original_grade_id = self.grade_id
        self._original_academic_year = self.academic_year

    def rotate_qr_token(self):
        """Issue a new badge code; the previous one stops resolving at once.
        Retries on the (rare) collision rather than surfacing an error."""
        from django.db import IntegrityError, transaction

        for _ in range(8):
            candidate = new_qr_token()
            try:
                with transaction.atomic():
                    self.qr_token = candidate
                    self.save(update_fields=["qr_token"])
                return self.qr_token
            except IntegrityError:
                continue
        raise IntegrityError("تعذّر توليد رمز فريد للطالب. حاول مرة أخرى.")

    def __str__(self):
        return f"{self.student} @ {self.environment} ({self.grade}, {self.academic_year})"
