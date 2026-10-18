"""
Madar-owned AI provider interface (spec: "External providers must be
accessed through Madar-owned interfaces"; "the external LLM provider is
behind that interface").

IMPORTANT — WHAT IS AND ISN'T REAL HERE:
No LLM credentials exist anywhere in this project, and none are hardcoded or
invented. The only implementation is `StubTutorProvider`: it exercises the
entire real pipeline (async submit, worker, persisted result, polling,
failure handling) but its "answer" is a clearly-labelled placeholder, not a
model's output. The interface and lifecycle are production-shaped; connecting
a real model is one new class implementing `generate()` plus a settings
change (`AI_PROVIDER`), with no change to models, views, or the worker.
The stub's output says so in-band, so nobody can mistake it for real tutoring.
"""
from dataclasses import dataclass, field

from django.conf import settings

# The tutor's contract, kept next to the interface a real provider will
# receive it through. GENERAL educational tutor — never handed any student's
# records, because nothing in this app can even reference them.
TUTOR_SYSTEM_PROMPT = (
    "You are a general educational tutor for a student. Answer clearly and "
    "accurately in the language of the question, using ONLY the curated "
    "Knowledge Base excerpts provided to you. If they do not cover the "
    "question, say so plainly instead of answering from memory. You have no "
    "access to any student's personal records and must not ask for them."
)

MAX_PROMPT_CHARS = 2000


class AIProviderError(Exception):
    """A provider failed in a way that should mark the operation `failed`."""


@dataclass(frozen=True)
class QuizResult:
    """A provider's quiz plus what is worth persisting about how it was made
    (`AIOperation.metadata`: prompt version, configuration, attempts, token
    usage...). `metadata` must never contain secrets or lesson text."""
    questions: list
    metadata: dict = field(default_factory=dict)


class AIProvider:
    def generate(self, prompt: str, context: str = "") -> str:  # pragma: no cover - interface
        """`context` is the bounded Knowledge Base excerpt set selected for
        this question (knowledge/retrieval.py). An empty string means the KB
        had nothing relevant and the answer must say so."""
        raise NotImplementedError

    def recommend_state(self, evidence: dict):  # pragma: no cover - interface
        """-> (state_code, rationale). `evidence` holds aggregate counts only."""
        raise NotImplementedError

    def generate_quiz(self, title: str, text: str):  # pragma: no cover - interface
        """-> list of {"q", "options", "answer_index", "explanation"}. The input is
        ONLY teacher-provided lesson text — never any student data."""
        raise NotImplementedError

    def generate_quiz_result(self, evidence: dict) -> QuizResult:
        """What the worker calls. `evidence` is the operation's frozen input
        snapshot ({"title", "text", "source": {...}}). The default adapts the
        legacy `generate_quiz(title, text)` so existing providers keep working;
        a provider that needs more (the LLM one) overrides this."""
        return QuizResult(questions=self.generate_quiz(evidence.get("title", ""), evidence.get("text", "")))


class StubTutorProvider(AIProvider):
    def generate(self, prompt: str, context: str = "") -> str:
        """Honest stub: the RETRIEVAL is real (the excerpts below come from
        actually published KB documents), only the generation is stubbed, and
        it says so in-band. It never answers beyond the supplied context."""
        preview = " ".join(prompt.split())[:120]
        if not context.strip():
            raise AIProviderError(
                "لا توجد مادة منشورة في قاعدة المعرفة تغطي هذا السؤال بعد. "
                "جرّب صياغة أخرى أو اسأل معلمك."
            )
        excerpt = " ".join(context.split())[:300]
        return (
            "[وضع تجريبي — لم يتم ربط نموذج ذكاء اصطناعي حقيقي بعد]\n"
            f"سؤالك: «{preview}».\n"
            "استُخرجت الإجابة من مواد قاعدة المعرفة المنشورة الموضّحة أدناه:\n"
            f"{excerpt}…"
        )


    def recommend_state(self, evidence: dict):
        present, absent = int(evidence.get("present", 0)), int(evidence.get("absent", 0))
        studied, not_studied = int(evidence.get("studied", 0)), int(evidence.get("not_studied", 0))
        sessions, recitations = present + absent, studied + not_studied
        if sessions + recitations == 0:
            raise AIProviderError("لا توجد بيانات كافية لهذا الشهر لاقتراح حالة.")
        attendance = present / sessions if sessions else 1.0
        study = studied / recitations if recitations else 1.0
        if attendance < 0.6 or study < 0.5:
            state = "at_risk"
        elif attendance < 0.8 or study < 0.75:
            state = "needs_follow_up"
        else:
            state = "good"
        return state, (
            "[وضع تجريبي — قاعدة حسابية بسيطة وليست نموذج ذكاء اصطناعي]\n"
            f"الحضور: {present} من {sessions} — التسميع: {studied} ذاكر من {recitations}. "
            "هذا اقتراح استشاري فقط، والقرار النهائي للمعلّم."
        )


    def generate_quiz(self, title: str, text: str):
        import re

        sentences = [x.strip() for x in re.split(r"[.!?؟\n]+", text or "") if len(x.split()) >= 5][:5]
        vocab = list(dict.fromkeys(w for w in re.findall(r"[\w\u0600-\u06FF]{4,}", text or "")))
        questions = []
        for sentence in sentences:
            words = [w for w in re.findall(r"[\w\u0600-\u06FF]{4,}", sentence)]
            if not words:
                continue
            key = max(words, key=len)
            distractors = [w for w in vocab if w != key][:3]
            if len(distractors) < 1:
                continue
            options = (distractors + [key])[:4]
            options.sort()  # deterministic order that does not always end with the answer
            questions.append({
                "q": "أكمل الجملة: " + sentence.replace(key, "_____", 1),
                "options": options, "answer_index": options.index(key),
                "explanation": f"الكلمة الصحيحة هي «{key}» كما وردت في الدرس. [وضع تجريبي — أسئلة مبنية على قاعدة بسيطة وليست نموذج ذكاء اصطناعي]",
            })
        if not questions:
            raise AIProviderError("نص الدرس قصير جدًا لتوليد اختبار. اطلب من معلمك إضافة ملخص أطول للدرس.")
        return questions


def validate_questions(questions):
    """A quiz is persisted ONLY if every question is well formed (no partial /
    invalid quiz — docs: ai-quiz.md)."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= 20:
        raise AIProviderError("تعذّر توليد اختبار صالح.")
    for q in questions:
        ok = (isinstance(q, dict) and isinstance(q.get("q"), str) and q["q"].strip()
              and isinstance(q.get("options"), list) and 2 <= len(q["options"]) <= 6
              and all(isinstance(o, str) and o.strip() for o in q["options"])
              and isinstance(q.get("answer_index"), int) and 0 <= q["answer_index"] < len(q["options"]))
        if not ok:
            raise AIProviderError("تعذّر توليد اختبار صالح.")
    # `type` / `difficulty` exist only on questions made by the LLM pipeline
    # (ai/quiz_contract.py); legacy and stub questions simply do not have them.
    return [{"q": q["q"].strip(), "options": [o.strip() for o in q["options"]], "answer_index": q["answer_index"],
             "explanation": str(q.get("explanation", ""))[:500],
             **{k: q[k] for k in ("type", "difficulty") if isinstance(q.get(k), str)}} for q in questions]


_PROVIDERS = {"stub": StubTutorProvider}


def get_provider() -> AIProvider:
    name = getattr(settings, "AI_PROVIDER", "stub")
    if name == "llm":
        # Imported lazily: ai.quiz_generation imports this module.
        from .quiz_generation import LLMQuizProvider
        return LLMQuizProvider.from_settings()
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise AIProviderError(f"Unknown AI_PROVIDER {name!r}")
