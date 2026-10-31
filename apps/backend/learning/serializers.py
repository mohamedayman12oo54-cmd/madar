from django.utils import timezone
from rest_framework import serializers

from academics.models import Enrollment, Grade, Group

from .models import Choice, Exam, Question

MAX_QUESTIONS = 100


class ChoiceIn(serializers.Serializer):
    text = serializers.CharField(max_length=400, trim_whitespace=True)
    is_correct = serializers.BooleanField(default=False)


class QuestionIn(serializers.Serializer):
    text = serializers.CharField(max_length=1500, trim_whitespace=True)
    points = serializers.IntegerField(min_value=1, max_value=100, default=1)
    choices = ChoiceIn(many=True)

    def validate_choices(self, v):
        if not 2 <= len(v) <= 6:
            raise serializers.ValidationError("كل سؤال يحتاج من 2 إلى 6 اختيارات.")
        if sum(1 for c in v if c["is_correct"]) != 1:
            raise serializers.ValidationError("حدّد إجابة صحيحة واحدة بالضبط.")
        return v


class ExamWriteSerializer(serializers.ModelSerializer):
    questions = QuestionIn(many=True)
    grade_ids = serializers.PrimaryKeyRelatedField(many=True, queryset=Grade.objects.all(), required=False)
    group_ids = serializers.PrimaryKeyRelatedField(many=True, queryset=Group.objects.all(), required=False)
    enrollment_ids = serializers.PrimaryKeyRelatedField(many=True, queryset=Enrollment.objects.all(), required=False)

    class Meta:
        model = Exam
        fields = ["title", "description", "duration_minutes", "shuffle_questions", "shuffle_choices",
                  "allow_back", "max_violations", "reveal_answers", "opens_at", "closes_at",
                  "questions", "grade_ids", "group_ids", "enrollment_ids"]
        extra_kwargs = {"duration_minutes": {"min_value": 1, "max_value": 300},
                        "max_violations": {"min_value": 1, "max_value": 10}}

    def validate_questions(self, v):
        if not v:
            raise serializers.ValidationError("أضف سؤالًا واحدًا على الأقل.")
        if len(v) > MAX_QUESTIONS:
            raise serializers.ValidationError(f"الحد الأقصى {MAX_QUESTIONS} سؤال.")
        return v

    def validate(self, attrs):
        env = self.context["request"].environment
        # Targets must belong to THIS teacher's environment (never trust ids from the client).
        for key, model in (("grade_ids", Grade), ("group_ids", Group), ("enrollment_ids", Enrollment)):
            bad = [o for o in attrs.get(key, []) if o.environment_id != env.id]
            if bad:
                raise serializers.ValidationError({key: "عنصر غير موجود."})
        o, c = attrs.get("opens_at"), attrs.get("closes_at")
        if o and c and c <= o:
            raise serializers.ValidationError({"closes_at": "وقت الإغلاق يجب أن يكون بعد وقت الفتح."})
        return attrs

    def _save_questions(self, exam, questions):
        exam.questions.all().delete()
        for qi, q in enumerate(questions):
            qq = Question.objects.create(exam=exam, order=qi, text=q["text"], points=q["points"])
            Choice.objects.bulk_create([Choice(question=qq, order=ci, text=c["text"], is_correct=c["is_correct"])
                                        for ci, c in enumerate(q["choices"])])

    def _save_targets(self, exam, data):
        if "grade_ids" in data:
            exam.target_grades.set(data["grade_ids"])
        if "group_ids" in data:
            exam.target_groups.set(data["group_ids"])
        if "enrollment_ids" in data:
            exam.target_enrollments.set(data["enrollment_ids"])

    def create(self, validated):
        questions = validated.pop("questions")
        targets = {k: validated.pop(k) for k in ("grade_ids", "group_ids", "enrollment_ids") if k in validated}
        exam = Exam.objects.create(environment=self.context["request"].environment, **validated)
        self._save_questions(exam, questions)
        self._save_targets(exam, targets)
        return exam

    def update(self, exam, validated):
        questions = validated.pop("questions", None)
        targets = {k: validated.pop(k) for k in ("grade_ids", "group_ids", "enrollment_ids") if k in validated}
        for k, v in validated.items():
            setattr(exam, k, v)
        exam.save()
        if questions is not None:
            self._save_questions(exam, questions)
        self._save_targets(exam, targets)
        return exam


def exam_read(exam, with_answers=True):
    """Teacher-facing representation (includes the answer key)."""
    return {
        "id": exam.pk, "title": exam.title, "description": exam.description,
        "duration_minutes": exam.duration_minutes, "shuffle_questions": exam.shuffle_questions,
        "shuffle_choices": exam.shuffle_choices, "allow_back": exam.allow_back,
        "max_violations": exam.max_violations, "reveal_answers": exam.reveal_answers,
        "opens_at": exam.opens_at, "closes_at": exam.closes_at, "published_at": exam.published_at,
        "created_at": exam.created_at,
        "grade_ids": [g.pk for g in exam.target_grades.all()],
        "group_ids": [g.pk for g in exam.target_groups.all()],
        "enrollment_ids": [e.pk for e in exam.target_enrollments.all()],
        "question_count": exam.questions.count(),
        "attempt_count": exam.attempts.count(),
        "questions": [
            {"id": q.pk, "text": q.text, "points": q.points,
             "choices": [{"id": c.pk, "text": c.text, "is_correct": c.is_correct} for c in q.choices.all()]}
            for q in exam.questions.prefetch_related("choices")
        ] if with_answers else [],
    }
