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
from django.conf import settings

# The tutor's contract, kept next to the interface a real provider will
# receive it through. GENERAL educational tutor — never handed any student's
# records, because nothing in this app can even reference them.
TUTOR_SYSTEM_PROMPT = (
    "You are a general educational tutor helping a teacher. Answer clearly and "
    "accurately in the language of the question. You have no access to any "
    "student's personal records and must not ask for them."
)

MAX_PROMPT_CHARS = 2000


class AIProviderError(Exception):
    """A provider failed in a way that should mark the operation `failed`."""


class AIProvider:
    def generate(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class StubTutorProvider(AIProvider):
    def generate(self, prompt: str) -> str:
        preview = " ".join(prompt.split())[:120]
        return (
            "[وضع تجريبي — لم يتم ربط نموذج ذكاء اصطناعي حقيقي بعد]\n"
            f"استلمتُ سؤالك: «{preview}».\n"
            "هذه إجابة توضيحية لاختبار دورة العمل (إرسال ← معالجة ← نتيجة) فقط."
        )


_PROVIDERS = {"stub": StubTutorProvider}


def get_provider() -> AIProvider:
    name = getattr(settings, "AI_PROVIDER", "stub")
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise AIProviderError(f"Unknown AI_PROVIDER {name!r}")
