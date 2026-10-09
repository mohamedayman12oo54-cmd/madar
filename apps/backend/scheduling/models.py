"""
Sessions, Schedules, Attendance and Recitation (per the System Documentation).

Domain rules (docs: domain-model, invariants INV-4/INV-8, lifecycles, functional):
- GROUP OWNS SESSIONS: SessionInstance.group is required and fixed forever.
- SessionInstance lifecycle: planned -> open -> closed -> (reopen) -> open ...
  Reopening re-opens the SAME row (never a new session); `reopened_count` is
  the only trace. A session may come from a Schedule or be ad-hoc (make-up).
- Schedule = the recurring EXPECTED slot of a Group (e.g. Monday 18:00). It
  never prevents recording an off-schedule session.
- Attendance is binary Present/Absent per (session, enrollment). Records are
  created ONLY when the teacher marks a student — never pre-filled — so an
  "Absent" always means the teacher said so (Absent fires a notification).
- Recitation: Studied / Not-Studied persist; "Skip" records nothing.
- A student may belong to several groups of their grade (INV-4), so the
  roster of a session is `group.member_enrollments` (active only).
- Records can only be written while the session is OPEN (docs: lifecycles);
  corrections go through reopen -> edit -> close.
"""
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from academics.models import Enrollment, Group
from environments.tenancy import TenantOwnedModel


class Schedule(TenantOwnedModel):
    WEEKDAYS = [
        (5, "السبت"), (6, "الأحد"), (0, "الاثنين"), (1, "الثلاثاء"),
        (2, "الأربعاء"), (3, "الخميس"), (4, "الجمعة"),
    ]  # Python weekday numbers (Monday=0); listed Saturday-first for Egypt.

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="schedules")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS, validators=[MaxValueValidator(6)])
    start_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group_id", "weekday", "start_time"]
        constraints = [
            models.UniqueConstraint(fields=["group", "weekday", "start_time"], name="unique_schedule_slot"),
        ]

    def clean(self):
        if self.group_id and self.environment_id and self.group.environment_id != self.environment_id:
            raise ValidationError("الموعد يجب أن ينتمي لنفس بيئة المجموعة.")


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
    reopened_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_at"]

    def clean(self):
        if self.group_id and self.environment_id and self.group.environment_id != self.environment_id:
            raise ValidationError("الجلسة يجب أن تنتمي لنفس بيئة المجموعة.")

    def open(self):
        if self.status != self.Status.PLANNED:
            raise ValidationError("لا يمكن فتح الجلسة إلا وهي في حالة (مخطط لها).")
        self.status = self.Status.OPEN
        self.opened_at = timezone.now()
        self.save(update_fields=["status", "opened_at"])

    def close(self):
        if self.status != self.Status.OPEN:
            raise ValidationError("لا يمكن إغلاق الجلسة إلا وهي مفتوحة.")
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at"])

    def reopen(self):
        """Reopens THIS SAME SessionInstance — never creates a new one.
        Notifications already fired are NOT retracted (docs: fired-and-forgotten)."""
        if self.status != self.Status.CLOSED:
            raise ValidationError("لا يمكن إعادة فتح إلا جلسة مغلقة.")
        self.status = self.Status.OPEN
        self.opened_at = timezone.now()
        self.reopened_count += 1
        self.save(update_fields=["status", "opened_at", "reopened_count"])

    def __str__(self):
        return f"{self.group} @ {self.scheduled_at:%Y-%m-%d %H:%M} ({self.status})"


class _SessionRecord(TenantOwnedModel):
    """Shared integrity rules for per-(session, enrollment) records (INV-8)."""

    session = models.ForeignKey(SessionInstance, on_delete=models.CASCADE, related_name="+")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="+")
    marked_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def clean(self):
        if self.session_id and self.session.environment_id != self.environment_id:
            raise ValidationError("السجل يجب أن ينتمي لنفس بيئة الجلسة.")
        if self.enrollment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("السجل يجب أن ينتمي لنفس بيئة تسجيل الطالب.")
        if self.session_id and self.enrollment_id and not self.enrollment.groups.filter(
            pk=self.session.group_id
        ).exists():
            raise ValidationError("الطالب لا ينتمي لمجموعة هذه الجلسة.")


class AttendanceRecord(_SessionRecord):
    class Status(models.TextChoices):
        PRESENT = "present", "حاضر"
        ABSENT = "absent", "غائب"

    session = models.ForeignKey(SessionInstance, on_delete=models.CASCADE, related_name="attendance_records")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance_records")
    status = models.CharField(max_length=10, choices=Status.choices)

    class Meta:
        ordering = ["enrollment__student_name"]
        constraints = [
            models.UniqueConstraint(fields=["session", "enrollment"], name="unique_attendance_per_session_enrollment"),
        ]


class RecitationRecord(_SessionRecord):
    class Status(models.TextChoices):
        STUDIED = "studied", "ذاكر"
        NOT_STUDIED = "not_studied", "لم يذاكر"

    session = models.ForeignKey(SessionInstance, on_delete=models.CASCADE, related_name="recitation_records")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="recitation_records")
    status = models.CharField(max_length=12, choices=Status.choices)

    class Meta:
        ordering = ["enrollment__student_name"]
        constraints = [
            models.UniqueConstraint(fields=["session", "enrollment"], name="unique_recitation_per_session_enrollment"),
        ]
