"""
Teacher-authored exams (a section of the educational content, next to videos / PDFs / summaries).

The teacher writes the questions, the choices and the correct choice, picks who receives the exam
(whole grades, groups, individual students) and a window in which it can be taken. A student gets ONE
attempt with a SERVER-SIDE clock: the deadline is fixed when the attempt starts, answers are saved as
they go, grading happens on the server, and the correct choices never leave the server until the
teacher's release rules allow it.

Integrity (honest scope): a web page cannot stop a screenshot or a photo of the screen. What the
server CAN do, and does here: fix the clock, show each student their own random order, record every
integrity signal the browser reports (leaving full screen, switching tab/window, copy / print / screenshot
keys), and submit the attempt automatically after the teacher's limit of violations.
"""
from datetime import timedelta

from django.db import models
from django.db.models import Exists, OuterRef, Q

from academics.models import Enrollment, Grade, Group
from environments.tenancy import TenantOwnedModel

MAX_QUESTIONS = 100
MIN_CHOICES, MAX_CHOICES = 2, 6


class Exam(TenantOwnedModel):
    class Release(models.TextChoices):
        IMMEDIATE = "immediate", "الدرجة فور التسليم"
        AFTER_CLOSE = "after_close", "الدرجة بعد انتهاء موعد الامتحان"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=2000)
    duration_minutes = models.PositiveSmallIntegerField()
    # Opens at publication when null. `closes_at` is mandatory: an exam that never closes is an exam
    # whose questions can be collected from the first student and handed to the rest.
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField()
    shuffle_questions = models.BooleanField(default=True)
    shuffle_choices = models.BooleanField(default=True)
    results_release = models.CharField(max_length=12, choices=Release.choices, default=Release.IMMEDIATE)
    # Show the student which choice was right (and theirs) - only after the window has closed, so a
    # student who finished early cannot pass the answers to one who has not started.
    reveal_answers = models.BooleanField(default=False)
    # Counted integrity violations after which the attempt is submitted automatically.
    max_violations = models.PositiveSmallIntegerField(default=3)

    target_grades = models.ManyToManyField(Grade, blank=True, related_name="exams")
    target_groups = models.ManyToManyField(Group, blank=True, related_name="exams")
    target_enrollments = models.ManyToManyField(Enrollment, blank=True, related_name="exams")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title

    def has_targets(self):
        return self.target_grades.exists() or self.target_groups.exists() or self.target_enrollments.exists()

    def effective_opens_at(self):
        return self.opens_at or self.published_at

    def audience(self):
        """ACTIVE enrollments who receive this exam. Same rule as content and broadcasts: grade and
        group NARROW (grade + group = that group within that grade), students picked by name are
        added on top, nobody else qualifies."""
        base = Enrollment.objects.filter(environment_id=self.environment_id, is_active=True)
        grade_ids = list(self.target_grades.values_list("pk", flat=True))
        group_ids = list(self.target_groups.values_list("pk", flat=True))
        direct_ids = list(self.target_enrollments.values_list("pk", flat=True))
        cond = Q(pk__in=direct_ids)
        if grade_ids or group_ids:
            narrowed = base
            if grade_ids:
                narrowed = narrowed.filter(grade_id__in=grade_ids)
            if group_ids:
                narrowed = narrowed.filter(groups__id__in=group_ids)
            cond |= Q(pk__in=narrowed.values("pk"))
        return base.filter(cond).distinct()

    @classmethod
    def visible_to(cls, enrollment):
        """PUBLISHED exams this one student receives - the mirror of `audience()`."""
        Grades, Groups, Direct = (cls.target_grades.through, cls.target_groups.through,
                                  cls.target_enrollments.through)
        has_grades = Exists(Grades.objects.filter(exam_id=OuterRef("pk")))
        has_groups = Exists(Groups.objects.filter(exam_id=OuterRef("pk")))
        grade_hit = Exists(Grades.objects.filter(exam_id=OuterRef("pk"), grade_id=enrollment.grade_id))
        group_hit = Exists(Groups.objects.filter(
            exam_id=OuterRef("pk"), group_id__in=[g.pk for g in enrollment.groups.all()]))
        direct_hit = Exists(Direct.objects.filter(exam_id=OuterRef("pk"), enrollment_id=enrollment.pk))
        narrowed = (Q(has_grades=True) | Q(has_groups=True)) & (Q(has_grades=False) | Q(grade_hit=True)) \
            & (Q(has_groups=False) | Q(group_hit=True))
        return (cls.objects
                .filter(environment_id=enrollment.environment_id, published_at__isnull=False)
                .annotate(has_grades=has_grades, has_groups=has_groups, grade_hit=grade_hit,
                          group_hit=group_hit, direct_hit=direct_hit)
                .filter(narrowed | Q(direct_hit=True)))


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveSmallIntegerField()
    text = models.TextField(max_length=1500)
    points = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "id"]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    position = models.PositiveSmallIntegerField()
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            # At most one correct choice per question, enforced by the database and not only by the
            # serializer (the serializer also requires exactly one before an exam can be saved).
            models.UniqueConstraint(fields=["question"], condition=Q(is_correct=True),
                                    name="exam_one_correct_choice_per_question"),
        ]


class Attempt(models.Model):
    class Reason(models.TextChoices):
        MANUAL = "manual", "سلّم الطالب"
        TIME = "time", "انتهى الوقت"
        VIOLATIONS = "violations", "تجاوز حد المخالفات"

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="exam_attempts")
    started_at = models.DateTimeField()
    # Fixed when the attempt starts: now + duration, never later than the exam's own closing time.
    deadline_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    submit_reason = models.CharField(max_length=12, choices=Reason.choices, blank=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    max_score = models.PositiveIntegerField(null=True, blank=True)
    violations = models.PositiveSmallIntegerField(default=0)
    # This student's own random order (ids), fixed at start so a reload shows the same paper.
    question_order = models.JSONField(default=list)
    choice_order = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["exam", "enrollment"], name="exam_one_attempt_per_student"),
        ]

    @property
    def submitted(self):
        return self.submitted_at is not None


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="exam_one_answer_per_question"),
        ]


class IntegrityEvent(models.Model):
    class Kind(models.TextChoices):
        FULLSCREEN_EXIT = "fullscreen_exit", "خرج من وضع ملء الشاشة"
        TAB_HIDDEN = "tab_hidden", "ترك تبويب الامتحان"
        WINDOW_BLUR = "window_blur", "انتقل إلى نافذة أخرى"
        PRINT_ATTEMPT = "print_attempt", "حاول الطباعة"
        SCREENSHOT_KEY = "screenshot_key", "ضغط مفتاح لقطة الشاشة"
        COPY_ATTEMPT = "copy_attempt", "حاول النسخ"
        PASTE_ATTEMPT = "paste_attempt", "حاول اللصق"
        CONTEXT_MENU = "context_menu", "حاول فتح القائمة"
        DEVTOOLS_KEY = "devtools_key", "حاول فتح أدوات المطوّر"
        RESUMED = "resumed", "عاد إلى الامتحان بعد إعادة تحميل الصفحة"

    # Only these move the violation counter. The rest are blocked in the page and recorded for the
    # teacher to read, but they do not by themselves end a student's exam.
    COUNTED = frozenset({"fullscreen_exit", "tab_hidden", "window_blur", "print_attempt", "screenshot_key"})
    # One real departure often raises several signals at once (blur + hidden + fullscreen exit).
    COUNT_DEBOUNCE = timedelta(seconds=3)
    MAX_PER_ATTEMPT = 300

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    counted = models.BooleanField(default=False)
    at = models.DateTimeField()

    class Meta:
        ordering = ["at", "id"]
