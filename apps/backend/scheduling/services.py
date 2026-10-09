"""Attendance / recitation marking (the Fast Session write path) and schedule
expansion. Each mark is ONE small atomic write; the notification event is
created in the same transaction (ADR-005) and delivered later by the worker."""
import datetime as dt

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from notifications.services import notify_absent, notify_not_studied

from .models import AttendanceRecord, RecitationRecord, Schedule, SessionInstance

MAX_GENERATE_WEEKS = 8


def _guard(session, enrollment):
    if session.status != SessionInstance.Status.OPEN:
        raise ValidationError("الجلسة غير مفتوحة. افتحها (أو أعد فتحها للتصحيح) قبل تسجيل أي بيانات.")
    if enrollment.environment_id != session.environment_id:
        raise ValidationError("الطالب لا ينتمي لهذه البيئة.")
    if not enrollment.is_active:
        raise ValidationError("الطالب غير نشط.")
    if not enrollment.groups.filter(pk=session.group_id).exists():
        raise ValidationError("الطالب لا ينتمي لمجموعة هذه الجلسة.")


def _upsert(model, session, enrollment, status):
    """Returns (record, previous_status or None)."""
    for _ in range(2):  # one retry if two taps race on the unique constraint
        try:
            with transaction.atomic():
                record, created = model.objects.select_for_update().get_or_create(
                    session=session, enrollment=enrollment, defaults={"environment_id": session.environment_id, "status": status},
                )
                previous = None if created else record.status
                if not created and record.status != status:
                    record.status = status
                    record.save(update_fields=["status", "marked_at"])
                return record, previous
        except IntegrityError:
            continue
    raise ValidationError("تعذّر حفظ التسجيل، حاول مرة أخرى.")


def mark_attendance(session, enrollment, status):
    if status not in AttendanceRecord.Status.values:
        raise ValidationError("حالة الحضور غير صحيحة.")
    _guard(session, enrollment)
    with transaction.atomic():
        record, previous = _upsert(AttendanceRecord, session, enrollment, status)
        # Fires when the outcome BECOMES absent (new mark, or a correction to
        # absent). Re-tapping absent on an already-absent student does not
        # spam a second notification.
        if status == AttendanceRecord.Status.ABSENT and previous != AttendanceRecord.Status.ABSENT:
            notify_absent(enrollment, session)
    return record


def mark_recitation(session, enrollment, status):
    if status not in RecitationRecord.Status.values:
        raise ValidationError("حالة التسميع غير صحيحة.")
    _guard(session, enrollment)
    with transaction.atomic():
        record, previous = _upsert(RecitationRecord, session, enrollment, status)
        if status == RecitationRecord.Status.NOT_STUDIED and previous != RecitationRecord.Status.NOT_STUDIED:
            notify_not_studied(enrollment, session)
    return record


def generate_planned_sessions(env, weeks, group=None, today=None):
    """Materialise PLANNED sessions from the environment's schedules for the
    next `weeks` weeks (today included). Idempotent: an existing session for
    the same group + moment is never duplicated. Returns the created rows."""
    weeks = max(1, min(int(weeks), MAX_GENERATE_WEEKS))
    tz = timezone.get_current_timezone()
    today = today or timezone.localdate()
    schedules = Schedule.objects.filter(environment=env).select_related("group")
    if group is not None:
        schedules = schedules.filter(group=group)
    created = []
    with transaction.atomic():
        for schedule in schedules:
            existing = set(
                SessionInstance.objects.filter(environment=env, group=schedule.group).values_list("scheduled_at", flat=True)
            )
            for offset in range(weeks * 7):
                day = today + dt.timedelta(days=offset)
                if day.weekday() != schedule.weekday:
                    continue
                moment = timezone.make_aware(dt.datetime.combine(day, schedule.start_time), tz)
                if moment in existing or moment < timezone.now():
                    continue
                created.append(SessionInstance.objects.create(environment=env, group=schedule.group, scheduled_at=moment))
    return created
