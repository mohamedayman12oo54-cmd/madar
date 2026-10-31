from django.db import transaction
from rest_framework import exceptions, serializers

from academics.models import Enrollment, Grade, Group

from .models import MAX_CHOICES, MAX_QUESTIONS, MIN_CHOICES, Choice, Exam, Question
from . import services

class ExamLocked(exceptions.APIException):
    status_code = 409
    default_code = "exam_locked"
    default_detail = "لا يمكن تعديل هذا بعد إرسال الامتحان للطلاب."


MAX_TARGETS = 500
MAX_DURATION = 600


# --- read (teacher) ------------------------------------------------------------------------------
class ChoiceReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ["id", "text", "is_correct"]


class QuestionReadSerializer(serializers.ModelSerializer):
    choices = ChoiceReadSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ["id", "text", "points", "choices"]


class ExamSerializer(serializers.ModelSerializer):
    """What the TEACHER sees: the whole exam, correct choices included. Students never use this."""

    questions = QuestionReadSerializer(many=True, read_only=True)
    targets = serializers.SerializerMethodField()
    published = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()
    total_points = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    started_count = serializers.SerializerMethodField()
    submitted_count = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ["id", "title", "description", "duration_minutes", "opens_at", "closes_at", "shuffle_questions",
                  "shuffle_choices", "results_release", "reveal_answers", "max_violations", "targets", "published",
                  "published_at", "created_at", "question_count", "total_points", "state", "started_count",
                  "submitted_count", "questions"]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if self.context.get("list"):  # a list row is a summary; the full paper comes from the detail view
            data.pop("questions", None)
        return data

    def get_targets(self, obj):
        return {
            "grades": [{"id": g.id, "name": g.name} for g in obj.target_grades.all()],
            "groups": [{"id": g.id, "name": g.name} for g in obj.target_groups.all()],
            "students": [{"id": e.id, "name": e.display_name} for e in obj.target_enrollments.all()],
        }

    def get_published(self, obj):
        return obj.published_at is not None

    def _qs(self, obj):
        return list(obj.questions.all())

    def get_question_count(self, obj):
        return len(self._qs(obj))

    def get_total_points(self, obj):
        return sum(q.points for q in self._qs(obj))

    def get_state(self, obj):
        return services.window_state(obj, services.now())

    def get_started_count(self, obj):
        return len(obj.attempts.all())

    def get_submitted_count(self, obj):
        return sum(1 for a in obj.attempts.all() if a.submitted_at)


# --- write (teacher) -----------------------------------------------------------------------------
class ChoiceWriteSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=300, trim_whitespace=True)
    is_correct = serializers.BooleanField(default=False)


class QuestionWriteSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1500, trim_whitespace=True)
    points = serializers.IntegerField(min_value=1, max_value=100, default=1)
    choices = ChoiceWriteSerializer(many=True)

    def validate_choices(self, value):
        if not MIN_CHOICES <= len(value) <= MAX_CHOICES:
            raise serializers.ValidationError(f"لكل سؤال من {MIN_CHOICES} إلى {MAX_CHOICES} اختيارات.")
        if sum(1 for c in value if c["is_correct"]) != 1:
            raise serializers.ValidationError("حدّد اختيارًا واحدًا فقط كإجابة صحيحة.")
        texts = [c["text"].strip().casefold() for c in value]
        if len(set(texts)) != len(texts):
            raise serializers.ValidationError("لا تكرّر نفس الاختيار في السؤال الواحد.")
        return value


# Fields that decide what a student sat. Once the exam is published they are frozen: changing them
# would make students' answers and scores mean different things.
LOCKED_AFTER_PUBLISH = ("questions", "duration_minutes", "opens_at", "shuffle_questions", "shuffle_choices",
                        "results_release", "max_violations", "grade_ids", "group_ids", "enrollment_ids")


class ExamWriteSerializer(serializers.ModelSerializer):
    grade_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    enrollment_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    questions = QuestionWriteSerializer(many=True, required=False, write_only=True)
    duration_minutes = serializers.IntegerField(min_value=1, max_value=MAX_DURATION)
    max_violations = serializers.IntegerField(min_value=1, max_value=10, required=False)

    class Meta:
        model = Exam
        fields = ["id", "title", "description", "duration_minutes", "opens_at", "closes_at", "shuffle_questions",
                  "shuffle_choices", "results_release", "reveal_answers", "max_violations", "grade_ids",
                  "group_ids", "enrollment_ids", "questions"]
        read_only_fields = ["id"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_questions(self, value):
        if len(value) > MAX_QUESTIONS:
            raise serializers.ValidationError(f"الحد الأقصى {MAX_QUESTIONS} سؤالًا.")
        return value

    def _targets(self, model, ids, field):
        ids = list(dict.fromkeys(ids))
        if len(ids) > MAX_TARGETS:
            raise serializers.ValidationError({field: "عدد كبير جدًا."})
        rows = list(model.objects.filter(environment=self.context["request"].environment, id__in=ids))
        if len(rows) != len(ids):
            raise serializers.ValidationError({field: "عنصر غير موجود."})
        return rows

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and inst.published_at:
            for field in LOCKED_AFTER_PUBLISH:
                if field in attrs:
                    raise ExamLocked()
            # The only change to timing after publishing is giving students MORE time to take it.
            if "closes_at" in attrs and attrs["closes_at"] < inst.closes_at:
                raise serializers.ValidationError({"closes_at": "يمكن تمديد موعد الإغلاق فقط."})
        opens = attrs.get("opens_at", getattr(inst, "opens_at", None))
        closes = attrs.get("closes_at", getattr(inst, "closes_at", None))
        if opens and closes and closes <= opens:
            raise serializers.ValidationError({"closes_at": "موعد الإغلاق يجب أن يكون بعد موعد الفتح."})
        if closes is not None and not (inst and inst.published_at) and closes <= services.now():
            raise serializers.ValidationError({"closes_at": "موعد الإغلاق يجب أن يكون في المستقبل."})
        if "grade_ids" in attrs:
            attrs["_grades"] = self._targets(Grade, attrs.pop("grade_ids"), "grade_ids")
        if "group_ids" in attrs:
            attrs["_groups"] = self._targets(Group, attrs.pop("group_ids"), "group_ids")
        if "enrollment_ids" in attrs:
            attrs["_enrollments"] = self._targets(Enrollment, attrs.pop("enrollment_ids"), "enrollment_ids")
        return attrs

    @staticmethod
    def _write_questions(exam, questions):
        exam.questions.all().delete()
        for qi, q in enumerate(questions):
            question = Question.objects.create(exam=exam, position=qi, text=q["text"], points=q["points"])
            Choice.objects.bulk_create([
                Choice(question=question, position=ci, text=c["text"], is_correct=c["is_correct"])
                for ci, c in enumerate(q["choices"])])

    def _apply(self, exam, extra, questions):
        for key, rel in (("_grades", exam.target_grades), ("_groups", exam.target_groups),
                         ("_enrollments", exam.target_enrollments)):
            if key in extra:
                rel.set(extra[key])
        if questions is not None:
            self._write_questions(exam, questions)

    @transaction.atomic
    def create(self, validated):
        extra = {k: validated.pop(k) for k in ("_grades", "_groups", "_enrollments") if k in validated}
        questions = validated.pop("questions", None)
        exam = super().create(validated)
        self._apply(exam, extra, questions)
        return exam

    @transaction.atomic
    def update(self, instance, validated):
        extra = {k: validated.pop(k) for k in ("_grades", "_groups", "_enrollments") if k in validated}
        questions = validated.pop("questions", None)
        exam = super().update(instance, validated)
        self._apply(exam, extra, questions)
        return exam

    def to_representation(self, instance):
        return ExamSerializer(instance, context=self.context).data
