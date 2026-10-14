"""Attendance / recitation marking (the Fast Session write path) and schedule
expansion. Each mark is ONE small atomic write; the notification event is
created in the same transaction (ADR-005) and delivered later by the worker."""
import datetime as dt

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from notifications.services import notify_absent, notify_not_studied

from academics.models import Enrollment
from .models import AttendanceRecord, GuestVisit, RecitationRecord, Schedule, SessionInstance

MAX_GENERATE_WEEKS = 8


def _guard(session, enrollment):
    # An open session whose time is over closes itself the moment anyone
    # touches it, so correctness never depends on the cron job having run.
    if session.is_overdue():
        session.close(auto=True)
        raise ValidationError(
            "انتهى وقت الجلسة وأُغلقت تلقائيًا وسُجّل غياب من لم يُسجَّل حضوره. أعد فتحها لتعديل التسجيل.")
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
                # A teacher touching an auto-recorded absence takes ownership
                # of it, whether they confirm it or change it.
                taken_over = not created and getattr(record, "auto_marked", False)
                if not created and (record.status != status or taken_over):
                    record.status = status
                    fields = ["status", "marked_at"]
                    if taken_over:
                        record.auto_marked = False
                        fields.append("auto_marked")
                    record.save(update_fields=fields)
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


def mark_unmarked_absent(session):
    """Closing rule: every ACTIVE member of the session's group with no
    attendance record becomes Absent (auto_marked), and the normal absence
    notification fires for each. Students already marked — present or absent —
    are never touched. Returns the enrollments that were auto-marked."""
    marked = set(AttendanceRecord.objects.filter(session=session).values_list("enrollment_id", flat=True))
    missing = list(
        Enrollment.objects.filter(environment_id=session.environment_id, is_active=True, groups=session.group_id)
        .exclude(pk__in=marked).select_related("student").distinct()
    )
    with transaction.atomic():
        for enrollment in missing:
            AttendanceRecord.objects.create(
                session=session, enrollment=enrollment, environment_id=session.environment_id,
                status=AttendanceRecord.Status.ABSENT, auto_marked=True)
            notify_absent(enrollment, session)
    return missing


def close_due_sessions(env=None, now=None):
    """Close every OPEN session whose end time has passed. Safe to call from
    anywhere, any number of times (cron every minute, or lazily when a teacher
    opens a screen). Returns how many sessions were closed."""
    now = now or timezone.now()
    qs = SessionInstance.objects.filter(status=SessionInstance.Status.OPEN, ends_at__isnull=False, ends_at__lte=now)
    if env is not None:
        qs = qs.filter(environment=env)
    closed = 0
    for session in qs.select_related("group"):
        if session.is_overdue(now):
            session.close(auto=True)
            closed += 1
    return closed


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
                ends = (timezone.make_aware(dt.datetime.combine(day, schedule.end_time), tz)
                        if schedule.end_time else None)
                created.append(SessionInstance.objects.create(
                    environment=env, group=schedule.group, scheduled_at=moment, ends_at=ends))
    return created


# ----------------------------------------------------------- guest visits ----
GUEST_WINDOW = dt.timedelta(days=14)  # how far ahead an un-targeted visit may be carried


def is_member(session, enrollment) -> bool:
    return enrollment.groups.filter(pk=session.group_id).exists()


def default_home_session(host, enrollment):
    """The student's own next session (planned or open) after the visit."""
    return (SessionInstance.objects
            .filter(environment_id=host.environment_id, group__in=enrollment.groups.all(),
                    status__in=[SessionInstance.Status.PLANNED, SessionInstance.Status.OPEN],
                    scheduled_at__gt=host.scheduled_at)
            .exclude(pk=host.pk).order_by("scheduled_at").first())


def _validate_home(host, enrollment, home):
    if home is None:
        return
    if home.environment_id != host.environment_id or not is_member(home, enrollment):
        raise ValidationError("هذه ليست جلسة من مجموعات الطالب.")
    if home.pk == host.pk:
        raise ValidationError("اختر جلسة مجموعته هو، وليس جلسة الضيافة.")
    if home.status == SessionInstance.Status.CLOSED:
        raise ValidationError("جلسة مجموعته مغلقة؛ أعد فتحها وسجّل له هناك مباشرة.")


def add_guest(host, enrollment, home_session=None):
    """Register `enrollment` as a guest of `host` (an OPEN session)."""
    if host.status != SessionInstance.Status.OPEN:
        raise ValidationError("الجلسة غير مفتوحة. افتحها قبل إضافة ضيف.")
    if enrollment.environment_id != host.environment_id:
        raise ValidationError("الطالب لا ينتمي لهذه البيئة.")
    if not enrollment.is_active:
        raise ValidationError("الطالب غير نشط.")
    if is_member(host, enrollment):
        raise ValidationError("الطالب من مجموعة هذه الجلسة أصلًا.")
    _validate_home(host, enrollment, home_session)
    visit, _ = GuestVisit.objects.get_or_create(
        session=host, enrollment=enrollment,
        defaults={"environment_id": host.environment_id,
                  "home_session": home_session or default_home_session(host, enrollment)})
    if home_session is not None and visit.home_session_id != home_session.pk:
        set_home_session(visit, home_session)
    return visit


def _editable(visit):
    if visit.session.status != SessionInstance.Status.OPEN:
        raise ValidationError("الجلسة غير مفتوحة. افتحها (أو أعد فتحها للتصحيح) قبل تسجيل أي بيانات.")
    home = visit.home_session
    if visit.applied_at and (home is None or home.status == SessionInstance.Status.CLOSED):
        raise ValidationError("تم ترحيل هذا الحضور إلى جلسة مجموعته وأُغلقت؛ عدّله من هناك.")


def set_home_session(visit, home):
    _editable(visit)
    _validate_home(visit.session, visit.enrollment, home)
    visit.home_session = home
    visit.applied_at = None
    visit.save(update_fields=["home_session", "applied_at"])
    _sync_if_home_open(visit)
    return visit


def mark_guest(host, enrollment, kind, status, home_session=None):
    """kind: 'attendance' | 'recitation'. Creates the visit on first mark."""
    model = AttendanceRecord if kind == "attendance" else RecitationRecord
    if status not in model.Status.values:
        raise ValidationError("الحالة غير صحيحة.")
    visit = add_guest(host, enrollment, home_session)
    _editable(visit)
    setattr(visit, kind, status)
    visit.save(update_fields=[kind])
    _sync_if_home_open(visit)
    return visit


def remove_guest(visit):
    _editable(visit)
    if visit.applied_at:
        raise ValidationError("تم ترحيل هذا الحضور بالفعل إلى جلسة مجموعته؛ لا يمكن إلغاؤه من هنا.")
    visit.delete()


def _carry(visit, home, overwrite):
    """Write the visit's marks into `home` through the SAME services the
    manual screens use, so absence / not-studied notifications behave alike."""
    for kind, fn, model in (("attendance", mark_attendance, AttendanceRecord),
                            ("recitation", mark_recitation, RecitationRecord)):
        status = getattr(visit, kind)
        if not status:
            continue
        if not overwrite and model.objects.filter(session=home, enrollment=visit.enrollment).exists():
            continue  # never override what the teacher already marked there
        fn(home, visit.enrollment, status)
    visit.home_session = home
    visit.applied_at = timezone.now()
    visit.save(update_fields=["home_session", "applied_at"])


def _sync_if_home_open(visit):
    home = visit.home_session
    if home is not None and home.status == SessionInstance.Status.OPEN:
        _carry(visit, home, overwrite=True)


def apply_guest_visits(session):
    """Called when `session` opens: carry in every pending visit by one of its
    members - either aimed at this very session, or un-aimed and recent."""
    visits = (GuestVisit.objects
              .filter(environment_id=session.environment_id, applied_at__isnull=True,
                      enrollment__is_active=True, enrollment__groups=session.group_id)
              .exclude(session=session)
              .filter(Q(home_session=session) | Q(
                  home_session__isnull=True,
                  session__scheduled_at__lte=session.scheduled_at,
                  session__scheduled_at__gte=session.scheduled_at - GUEST_WINDOW))
              .exclude(attendance="", recitation="")
              .select_related("enrollment", "session").order_by("session__scheduled_at", "id").distinct())
    for visit in visits:
        _carry(visit, session, overwrite=False)
