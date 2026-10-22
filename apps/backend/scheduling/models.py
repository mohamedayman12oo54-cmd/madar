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
  created when the teacher marks a student, with ONE exception: when a session
  CLOSES (the teacher closes it, or its end time passes) every active member
  nobody marked is recorded Absent with `auto_marked=True`, and the usual
  absence notification fires. A teacher who reopens the session and marks the
  student overrides it (`auto_marked` goes back to False).
- Recitation: Studied / Not-Studied persist; "Skip" records nothing.
- A student may belong to several groups of their grade (INV-4), so the
  roster of a session is `group.member_enrollments` (active only).
- Records can only be written while the session is OPEN (docs: lifecycles);
  corrections go through reopen -> edit -> close.
"""
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models, transaction
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
    # When the lesson ends (same day). Sessions generated from this slot get
    # `ends_at` from it and close themselves at that time. Empty = no auto-close.
    end_time = models.TimeField(null=True, blank=True)
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
    # End of the lesson. While OPEN, the session closes itself at this moment
    # (see auto_close_at) and records Absent for every unmarked member.
    # Empty = it only closes when the teacher closes it.
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reopened_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_at"]

    # A session opened late (or reopened to fix a record) must not close again
    # the instant it opens just because its end time already passed.
    FIRST_OPEN_GRACE = timedelta(minutes=15)
    REOPEN_WINDOW = timedelta(hours=2)

    def clean(self):
        if self.group_id and self.environment_id and self.group.environment_id != self.environment_id:
            raise ValidationError("الجلسة يجب أن تنتمي لنفس بيئة المجموعة.")
        if self.ends_at and self.scheduled_at and self.ends_at <= self.scheduled_at:
            raise ValidationError("وقت الانتهاء يجب أن يكون بعد وقت البداية.")

    @property
    def auto_close_at(self):
        """When this OPEN session closes by itself (None = never)."""
        if self.status != self.Status.OPEN or not self.ends_at:
            return None
        opened = self.opened_at or self.ends_at
        grace = self.REOPEN_WINDOW if self.reopened_count else self.FIRST_OPEN_GRACE
        return max(self.ends_at, opened + grace)

    def is_overdue(self, now=None):
        due = self.auto_close_at
        return due is not None and due <= (now or timezone.now())

    def open(self):
        if self.status != self.Status.PLANNED:
            raise ValidationError("لا يمكن فتح الجلسة إلا وهي في حالة (مخطط لها).")
        from .services import apply_guest_visits

        with transaction.atomic():
            self.status = self.Status.OPEN
            self.opened_at = timezone.now()
            self.save(update_fields=["status", "opened_at"])
            # Students who visited ANOTHER group's session instead of this one
            # are recorded here automatically (see GuestVisit).
            apply_guest_visits(self)

    def close(self, auto=False):
        """Close the session and record Absent for every active member nobody
        marked. Returns the enrollments auto-marked. `auto=True` (end time /
        cron) silently does nothing if someone else already closed it."""
        from .services import mark_unmarked_absent

        with transaction.atomic():
            locked = SessionInstance.objects.select_for_update().get(pk=self.pk)
            if locked.status != self.Status.OPEN:
                self.status = locked.status
                if auto:
                    return []
                raise ValidationError("لا يمكن إغلاق الجلسة إلا وهي مفتوحة.")
            self.status = self.Status.CLOSED
            self.closed_at = timezone.now()
            self.save(update_fields=["status", "closed_at"])
            return mark_unmarked_absent(self)

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
    # True = recorded by the system when the session closed (nobody marked
    # this student). Cleared as soon as the teacher marks the student.
    auto_marked = models.BooleanField(default=False)

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


class GuestVisit(TenantOwnedModel):
    """A student of ANOTHER group attended this session as a guest.

    Why a separate record instead of an AttendanceRecord on the host session:
      * INV-8 stays intact - attendance/recitation rows exist only for members
        of the session's own group, so no report or total is polluted;
      * nothing is counted twice - the student's real attendance lives in HIS
        group's session, where it is written automatically when that session
        opens (`apply_guest_visits`), exactly as if it had been taken there;
      * until then the visit is just a note on the host session.

    `home_session` is the student's own session this visit stands in for. Left
    empty, it resolves to the first session of any of his groups that opens
    after the visit (within two weeks). Payment is monthly and not tied to a
    session, so it is recorded through the normal payment screens.
    """

    session = models.ForeignKey(SessionInstance, on_delete=models.CASCADE, related_name="guest_visits")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="guest_visits")
    home_session = models.ForeignKey(
        SessionInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name="carried_visits")
    attendance = models.CharField(max_length=10, choices=AttendanceRecord.Status.choices, blank=True)
    recitation = models.CharField(max_length=12, choices=RecitationRecord.Status.choices, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "enrollment"], name="unique_guest_per_session_enrollment"),
        ]

    def clean(self):
        if self.session_id and self.session.environment_id != self.environment_id:
            raise ValidationError("الزيارة يجب أن تنتمي لنفس بيئة الجلسة.")
        if self.enrollment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("الزيارة يجب أن تنتمي لنفس بيئة تسجيل الطالب.")
        if self.session_id and self.enrollment_id and self.enrollment.groups.filter(pk=self.session.group_id).exists():
            raise ValidationError("الطالب من مجموعة هذه الجلسة أصلًا، وليس ضيفًا.")


def new_checkin_token():
    """Opaque, unguessable handle carried by the QR (128 bits)."""
    return secrets.token_urlsafe(16)


def new_checkin_code():
    """The short code the teacher tells the class (NOT part of the QR)."""
    return f"{secrets.randbelow(10 ** 6):06d}"


class CheckinLink(TenantOwnedModel):
    """A teacher-generated self check-in for ONE open session.

    Two secrets are needed to use it, and they travel by different routes:
      * `token`  - inside the QR (a link). Anyone who can see the screen has it.
      * `code`   - six digits the teacher says out loud / writes on the board.
    A photo of the QR alone therefore cannot mark anyone present.

    What it can do is deliberately tiny: mark an ACTIVE member of THIS
    session's group present, while the session is open and the link unexpired.
    Nothing else (no absence, no recitation, no payment, no data is read).
    Generating a new link revokes the previous one for the session.
    """

    session = models.ForeignKey(SessionInstance, on_delete=models.CASCADE, related_name="checkin_links")
    token = models.CharField(max_length=32, unique=True, default=new_checkin_token, editable=False)
    code = models.CharField(max_length=6, default=new_checkin_code, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    checked_in_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    VALID_FOR = timedelta(hours=3)

    class Meta:
        ordering = ["-created_at"]

    def is_usable(self, now=None):
        now = now or timezone.now()
        return self.revoked_at is None and self.expires_at > now and self.session.status == SessionInstance.Status.OPEN
