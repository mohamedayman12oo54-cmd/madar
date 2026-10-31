"""
Exams (secure, timed, server-judged) and, later, downloadable study material.

Design rules for exams (the browser can never be trusted, so the SERVER owns everything that matters):
  * correct answers never leave the server while the exam is running — a question is sent with its
    choices only, and one question at a time, so there is no "all questions in the page" to copy;
  * the clock is the server's: `deadline_at` is fixed when the attempt starts, and an answer that
    arrives after it is refused and the attempt is closed;
  * one attempt per student unless the TEACHER re-opens the exam for that student (an `AttemptGrant`):
    then the student sits it again as attempt 2, 3 … and the BEST score is the one that counts. Question
    and choice ORDER is shuffled per attempt and stored, so a photographed question sheet is useless to a
    friend;
  * the browser reports suspicious events (leaving the page, exiting full screen, copy, print…); the
    server counts them and closes the attempt itself when the teacher's limit is reached.
"""
from django.db import models
from django.db.models import Exists, OuterRef, Q

from academics.models import Enrollment, Grade, Group
from environments.tenancy import TenantOwnedModel


class Targeted(TenantOwnedModel):
    """Audience = same narrowing rule as videos/broadcasts: grade + group narrows to that group, a grade
    alone is the whole grade, a group alone is that group; individually picked students are additions."""

    target_grades = models.ManyToManyField(Grade, blank=True, related_name="+")
    target_groups = models.ManyToManyField(Group, blank=True, related_name="+")
    target_enrollments = models.ManyToManyField(Enrollment, blank=True, related_name="+")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def has_targets(self):
        return self.target_grades.exists() or self.target_groups.exists() or self.target_enrollments.exists()

    def audience(self):
        base = Enrollment.objects.filter(environment_id=self.environment_id, is_active=True)
        grade_ids = list(self.target_grades.values_list("pk", flat=True))
        group_ids = list(self.target_groups.values_list("pk", flat=True))
        cond = Q(pk__in=list(self.target_enrollments.values_list("pk", flat=True)))
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
        """Published rows this ONE student is in the audience of (mirror of `audience()`)."""
        key = f"{cls._meta.model_name}_id"
        G, Gr, D = cls.target_grades.through, cls.target_groups.through, cls.target_enrollments.through
        has_grades = Exists(G.objects.filter(**{key: OuterRef("pk")}))
        has_groups = Exists(Gr.objects.filter(**{key: OuterRef("pk")}))
        grade_hit = Exists(G.objects.filter(**{key: OuterRef("pk"), "grade_id": enrollment.grade_id}))
        group_hit = Exists(Gr.objects.filter(**{key: OuterRef("pk"),
                                                "group_id__in": [g.pk for g in enrollment.groups.all()]}))
        direct_hit = Exists(D.objects.filter(**{key: OuterRef("pk"), "enrollment_id": enrollment.pk}))
        narrowed = (Q(has_grades=True) | Q(has_groups=True)) & (Q(has_grades=False) | Q(grade_hit=True)) \
            & (Q(has_groups=False) | Q(group_hit=True))
        return (cls.objects.filter(environment_id=enrollment.environment_id, published_at__isnull=False)
                .annotate(has_grades=has_grades, has_groups=has_groups, grade_hit=grade_hit,
                          group_hit=group_hit, direct_hit=direct_hit)
                .filter(narrowed | Q(direct_hit=True)))


class Exam(Targeted):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=2000)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    shuffle_questions = models.BooleanField(default=True)
    shuffle_choices = models.BooleanField(default=True)
    # False = forward only: once a question is answered the student cannot return to it.
    allow_back = models.BooleanField(default=False)
    # Attempt is closed automatically after this many suspicious events.
    max_violations = models.PositiveSmallIntegerField(default=3)
    # Student sees the correct answers after finishing (only if the teacher opts in).
    reveal_answers = models.BooleanField(default=False)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(default=0)
    text = models.TextField(max_length=1500)
    points = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    order = models.PositiveSmallIntegerField(default=0)
    text = models.CharField(max_length=400)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "id"]


class Attempt(models.Model):
    class End(models.TextChoices):
        SUBMITTED = "submitted", "سلّم الطالب"
        TIME = "time", "انتهى الوقت"
        VIOLATIONS = "violations", "مخالفات متكررة"

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="exam_attempts")
    number = models.PositiveSmallIntegerField(default=1)  # 1 = first sitting, 2+ = sittings the teacher allowed
    started_at = models.DateTimeField(auto_now_add=True)
    deadline_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=12, choices=End.choices, blank=True)
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(null=True, blank=True)
    current_index = models.PositiveSmallIntegerField(default=0)
    violations = models.PositiveSmallIntegerField(default=0)
    violation_log = models.JSONField(default=list, blank=True)
    question_order = models.JSONField(default=list)
    choice_orders = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "enrollment", "number"], name="one_attempt_per_number")]
        ordering = ["number"]

    @property
    def finished(self):
        return self.submitted_at is not None


class AttemptGrant(models.Model):
    """The teacher re-opened an exam for ONE student ("something went wrong"): one more sitting, allowed even
    after the exam's closing time. It is consumed (`used_by`) when the student starts that sitting, and at
    most one unused grant exists per student, so a double click cannot hand out two."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="grants")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="exam_grants")
    granted_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    used_by = models.OneToOneField(Attempt, on_delete=models.SET_NULL, null=True, blank=True, related_name="grant")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "enrollment"], condition=models.Q(used_by__isnull=True),
                                               name="one_open_grant_per_student")]


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")]
