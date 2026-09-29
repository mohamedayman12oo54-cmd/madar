"""
Phase 3 / Sessions + Attendance.

Domain rules enforced here (from the spec, not invented):
- GROUP OWNS SESSIONS: SessionInstance.group is required and fixed forever
  (no serializer ever exposes changing it — see serializers.py).
- SessionInstance is a first-class entity with an explicit lifecycle:
  planned -> open -> closed -> (reopen) -> open -> closed -> ...
  Reopening transitions the SAME row back to `open` — it never creates a new
  SessionInstance. `reopened_count` is the only trace of "this has happened
  before"; there is no separate "reopened" status (a reopened session is,
  functionally, open again).
- Attendance is scoped to a SessionInstance AND an Enrollment (never a bare
  "student" — the enrollment is what ties a student to a specific
  environment/group, per Phase 2). One record per (session, enrollment).
- Attendance rows are not hand-created by the teacher one at a time — they
  are generated for every currently-active Enrollment in the session's group
  at the moment the session is opened (or reopened, to pick up anyone
  enrolled since), defaulting to "absent". The teacher's job is then only to
  flip the ones who showed up — see `open()`/`reopen()`/`_sync_roster()`.
"""
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from academics.models import Enrollment, Group
from environments.tenancy import TenantOwnedModel


class SessionInstance(TenantOwnedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "مخطط لها"
        OPEN = "open", "مفتوحة"
        CLOSED = "closed", "مغلقة"

    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="sessions")
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # The only trace that a reopen ever happened — see module docstring.
    # Never resets; incremented, never decremented.
    reopened_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_at"]

    def clean(self):
        if self.group_id and self.environment_id and self.group.environment_id != self.environment_id:
            raise ValidationError("الجلسة يجب أن تنتمي لنفس بيئة المجموعة.")

    def _sync_roster(self):
        """Create an ABSENT AttendanceRecord for every currently-active
        Enrollment in this session's group that doesn't already have one.
        Never touches an existing record's status — a student already marked
        present before a reopen stays present."""
        existing = set(self.attendance_records.values_list("enrollment_id", flat=True))
        roster = Enrollment.objects.filter(environment_id=self.environment_id, group_id=self.group_id, is_active=True)
        AttendanceRecord.objects.bulk_create(
            [
                AttendanceRecord(environment_id=self.environment_id, session=self, enrollment=e)
                for e in roster if e.id not in existing
            ]
        )

    def open(self):
        if self.status != self.Status.PLANNED:
            raise ValidationError("لا يمكن فتح الجلسة إلا وهي في حالة (مخطط لها).")
        # Deferred import: avoids a circular import at module-load time
        # (notifications.models imports SessionInstance for its FK).
        from notifications.services import notify_session_event
        from notifications.models import Notification

        with transaction.atomic():
            self.status = self.Status.OPEN
            self.opened_at = timezone.now()
            self.save(update_fields=["status", "opened_at"])
            self._sync_roster()
            notify_session_event(self, Notification.Type.SESSION_OPENED)

    def close(self):
        if self.status != self.Status.OPEN:
            raise ValidationError("لا يمكن إغلاق الجلسة إلا وهي مفتوحة.")
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at"])

    def reopen(self):
        """Reopens THIS SAME SessionInstance — never creates a new one."""
        if self.status != self.Status.CLOSED:
            raise ValidationError("لا يمكن إعادة فتح إلا جلسة مغلقة.")
        from notifications.services import notify_session_event
        from notifications.models import Notification

        with transaction.atomic():
            self.status = self.Status.OPEN
            self.opened_at = timezone.now()
            self.reopened_count += 1
            self.save(update_fields=["status", "opened_at", "reopened_count"])
            self._sync_roster()
            # A fresh, independent notification — never touches/retracts
            # whatever notification the original open() created (spec:
            # reopening does not retroactively retract an already-fired
            # notification).
            notify_session_event(self, Notification.Type.SESSION_REOPENED)

    def __str__(self):
        return f"{self.group} @ {self.scheduled_at:%Y-%m-%d %H:%M} ({self.status})"


class AttendanceRecord(TenantOwnedModel):
    class Status(models.TextChoices):
        PRESENT = "present", "حاضر"
        ABSENT = "absent", "غائب"

    session = models.ForeignKey(SessionInstance, on_delete=models.CASCADE, related_name="attendance_records")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance_records")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABSENT)
    marked_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["enrollment__student__name"]
        constraints = [
            models.UniqueConstraint(fields=["session", "enrollment"], name="unique_attendance_per_session_enrollment"),
        ]

    def clean(self):
        if self.session_id and self.session.environment_id != self.environment_id:
            raise ValidationError("سجل الحضور يجب أن ينتمي لنفس بيئة الجلسة.")
        if self.enrollment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("سجل الحضور يجب أن ينتمي لنفس بيئة تسجيل الطالب.")
        if self.session_id and self.enrollment_id and self.session.group_id != self.enrollment.group_id:
            raise ValidationError("لا يمكن تسجيل حضور طالب لا ينتمي لمجموعة هذه الجلسة.")

    def __str__(self):
        return f"{self.enrollment} @ {self.session} = {self.status}"
