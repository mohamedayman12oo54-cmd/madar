from django.conf import settings
from django.db import models
from django.utils import timezone


def current_academic_year() -> str:
    """Egypt-style academic year runs roughly Sept -> Aug.
    In Jan-Aug we're still in the year that started the previous September."""
    today = timezone.localdate()
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start} / {start + 1}"


class Environment(models.Model):
    """One teacher's teaching space ("بيئة تعليمية"). INV-9 / ADR-013: one Teacher Account owns
    exactly ONE Environment, permanently — enforced by the database (OneToOne => unique index on
    owner_id), because Billing's "one Subscription per Environment" is only "one per account" if this
    holds. Students are linked to the environment via EnvironmentMembership."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_environment",
        limit_choices_to={"role": "teacher"},
    )
    name = models.CharField(max_length=150)
    subject_stage = models.CharField(max_length=150, blank=True)
    academic_year = models.CharField(max_length=20, blank=True)
    initials = models.CharField(max_length=4, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.academic_year:
            self.academic_year = current_academic_year()
        if not self.initials:
            self.initials = (self.name.strip()[:1] or "؟")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner})"


class EnvironmentMembership(models.Model):
    """Who can enter which environment, and when they last did.
    role='owner' rows are created automatically when a teacher creates an
    Environment; role='student' rows are created when a teacher
    pre-registers a student into their environment."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        STUDENT = "student", "Student"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "environment"], name="unique_membership_per_env"),
        ]
        ordering = ["-last_accessed_at", "-joined_at"]

    def __str__(self):
        return f"{self.user} in {self.environment} ({self.role})"
