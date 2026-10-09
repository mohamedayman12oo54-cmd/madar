"""AI Quiz persistence (docs: ai-quiz.md / consistency.md): a generated quiz is
persisted BEFORE the student answers; answers and the auto-scored result are
persisted as educational records the student can see. The LLM is never the
source of truth, and a quiz exists only if generation fully succeeded.

One attempt per quiz: after submitting, the correct answers are revealed, so a
second attempt on the same questions would measure nothing. Another attempt =
generate a new quiz (rate-limited)."""
from django.db import models

from environments.tenancy import TenantOwnedModel


class Quiz(TenantOwnedModel):
    enrollment = models.ForeignKey("academics.Enrollment", on_delete=models.CASCADE, related_name="quizzes")
    content = models.ForeignKey("content.ContentItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    content_title = models.CharField(max_length=200, blank=True)  # survives the teacher deleting the content
    operation = models.OneToOneField("ai.AIOperation", on_delete=models.SET_NULL, null=True, blank=True, related_name="quiz")
    # [{"q": str, "options": [str], "answer_index": int, "explanation": str}] — answers stay server-side until submitted
    questions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class QuizAttempt(TenantOwnedModel):
    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name="attempt")
    answers = models.JSONField(default=list)  # chosen option index per question, or null (skipped)
    score = models.PositiveSmallIntegerField()
    total = models.PositiveSmallIntegerField()
    submitted_at = models.DateTimeField(auto_now_add=True)
