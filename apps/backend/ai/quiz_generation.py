"""
LLM-backed quiz generation, plugged into the EXISTING operation lifecycle:

    studentarea quiz request  ->  AIOperation(pending, evidence = prepared source)
    process_ai_operations     ->  get_provider().generate_quiz_result(evidence)   <- this module
                              ->  validate_questions()  ->  Quiz + AIOperation(completed)
                                  or AIOperation(failed, error, metadata)

Select it with `AI_PROVIDER=llm`. It subclasses `StubTutorProvider` ONLY so the
Study Assistant and State Recommendation keep their existing behaviour while the
quiz uses the model; it overrides nothing but quiz generation.

Pipeline per operation (every step is its own module):
    1. configuration    quiz_contract.QuizGenerationConfig   (validated BEFORE any LLM call)
    2. source guard     evidence["text"] is already the complete prepared lesson
                        (quiz_source.py); too little material fails explicitly
    3. content check    content_validation_prompt + content_validation_contract:
                        one classification call, EDUCATIONAL vs NON_EDUCATIONAL
                        (QUIZ_CONTENT_VALIDATION_ENABLED; on by default). A
                        NON_EDUCATIONAL verdict, or a validation failure, stops
                        here — the quiz-generation steps below never run.
    4. prompt           quiz_prompt.build_quiz_prompt
    5. model call       ai.llm.LLMClient (never Gemini directly), JSON output mode
    6. validation       quiz_contract.parse_generated_quiz   (deterministic, whole result)
    7. bounded recovery at most QUIZ_MAX_ATTEMPTS model calls in total, each
                        retry carrying the validation errors; then fail

Failures never produce a partial quiz, and never leak provider detail: the
message shown to the student is chosen here from a fixed table; the category,
attempts and validation errors go to `AIOperation.metadata` and the log.
"""
import logging

from django.conf import settings

from .content_validation_contract import parse_validation_response
from .content_validation_prompt import PROMPT_VERSION as CONTENT_VALIDATION_PROMPT_VERSION
from .content_validation_prompt import build_content_validation_prompt
from .llm import LLMError, LLMRequest, get_llm_client
from .providers import AIProviderError, QuizResult, StubTutorProvider
from .quiz_contract import INSUFFICIENT_SOURCE, QuizConfigError, QuizGenerationConfig, parse_generated_quiz
from .quiz_prompt import PROMPT_VERSION, build_quiz_prompt

log = logging.getLogger(__name__)

MAX_ATTEMPTS_LIMIT = 3          # hard ceiling regardless of settings
DEFAULT_MAX_ATTEMPTS = 2        # 1 generation + 1 corrective regeneration
DEFAULT_MIN_SOURCE_CHARS = 400

_BUSY = "خدمة توليد الاختبارات مشغولة حاليًا. حاول مرة أخرى بعد قليل."
_INVALID = "تعذّر إنشاء اختبار صالح لهذا الدرس. حاول مرة أخرى."
_GENERIC = "تعذّر إنشاء الاختبار الآن."
NON_EDUCATIONAL = "non_educational"
CONTENT_VALIDATION_FAILED = "content_validation_failed"
_FAILURE_MESSAGES = {
    "config": "خدمة توليد الاختبارات غير مهيأة بعد. أخبر معلمك.",
    INSUFFICIENT_SOURCE: "مادة هذا الدرس لا تكفي لإنشاء اختبار كامل منها.",
    "rate_limit": _BUSY, "timeout": _BUSY, "network": _BUSY, "provider": _BUSY,
    "invalid_output": _INVALID, "truncated": _INVALID, "malformed_response": _INVALID, "blocked": _INVALID,
    NON_EDUCATIONAL: "لا يحتوي هذا الفيديو على محتوى تعليمي كافٍ لإنشاء اختبار ذي معنى منه.",
    CONTENT_VALIDATION_FAILED: "تعذّر التحقق من محتوى هذا الدرس. حاول مرة أخرى.",
}


class QuizGenerationError(AIProviderError):
    """An explicit, categorised failure. `str(exc)` is a fixed Arabic message
    that is safe to show to a student; `metadata` is for operators."""

    def __init__(self, category, metadata=None):
        super().__init__(_FAILURE_MESSAGES.get(category, _GENERIC))
        self.category = category
        self.metadata = {**(metadata or {}), "validation": "failed", "failure_category": category}


class LLMQuizProvider(StubTutorProvider):
    def __init__(self, *, client=None, config=None, max_attempts=DEFAULT_MAX_ATTEMPTS,
                 min_source_chars=DEFAULT_MIN_SOURCE_CHARS, validate_content=True):
        if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
            raise QuizGenerationError("config", {"detail": f"QUIZ_MAX_ATTEMPTS must be 1..{MAX_ATTEMPTS_LIMIT}"})
        self._client = client
        self._config = config   # None => QuizGenerationConfig.from_settings() per operation
        self.max_attempts = max_attempts
        self.min_source_chars = min_source_chars
        self.validate_content = validate_content

    @classmethod
    def from_settings(cls):
        return cls(
            max_attempts=getattr(settings, "QUIZ_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
            min_source_chars=getattr(settings, "QUIZ_MIN_SOURCE_CHARS", DEFAULT_MIN_SOURCE_CHARS),
            validate_content=getattr(settings, "QUIZ_CONTENT_VALIDATION_ENABLED", True),
        )

    def generate_quiz(self, title, text):
        return self.generate_quiz_result({"title": title, "text": text}).questions

    def generate_quiz_result(self, evidence) -> QuizResult:
        title = str(evidence.get("title") or "")
        text = evidence.get("text") or ""
        meta = {"prompt_version": PROMPT_VERSION, "max_attempts": self.max_attempts, "source_chars": len(text),
                "source_origin": (evidence.get("source") or {}).get("origin")}

        # 1. configuration — an invalid one never reaches the client.
        try:
            config = self._config or QuizGenerationConfig.from_settings()
        except QuizConfigError as exc:
            log.error("quiz generation is misconfigured: %s", exc)  # names the setting, never a value
            raise QuizGenerationError("config", meta) from exc
        meta.update(config.as_metadata())

        # 2. source guard — nothing is sliced; too little material is a failure.
        if len(text.strip()) < self.min_source_chars:
            raise QuizGenerationError(INSUFFICIENT_SOURCE, {**meta, "min_source_chars": self.min_source_chars})

        try:
            client = self._client or get_llm_client()
        except LLMError as exc:
            log.error("quiz generation: LLM client unavailable (%s)", exc.category)
            raise QuizGenerationError(exc.category, meta) from exc

        # 3. content check — a NON_EDUCATIONAL verdict (or a failure to reach
        # one) stops here; the generation loop below never sees this text.
        if self.validate_content:
            meta["content_validation"] = self._check_content(client, title, text, meta)

        usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        errors, category = [], "invalid_output"
        for attempt in range(1, self.max_attempts + 1):
            prompt = build_quiz_prompt(config, title, text, correction_errors=errors or None)
            try:
                response = client.complete(LLMRequest(prompt=prompt.user, system=prompt.system, json_output=True))
            except LLMError as exc:
                # Transient errors were already retried (bounded) inside the client.
                # Anything that survives is final here: no second layer of retries.
                log.warning("quiz generation: LLM call failed category=%s attempt=%d", exc.category, attempt)
                raise QuizGenerationError(
                    exc.category, {**meta, "attempts": attempt, "provider_attempts": exc.attempts, "usage": usage}
                ) from exc
            meta.update({"provider": response.provider, "model": response.model})
            for key, value in (("prompt_tokens", response.usage and response.usage.prompt_tokens),
                               ("output_tokens", response.usage and response.usage.output_tokens),
                               ("total_tokens", response.usage and response.usage.total_tokens)):
                usage[key] += value or 0

            if response.truncated:
                category, errors = "truncated", ["the output was cut off at the output limit; the JSON was incomplete"]
                log.warning("quiz generation: truncated output attempt=%d", attempt)
                continue
            outcome = parse_generated_quiz(response.text, config)
            if outcome.insufficient_source:
                raise QuizGenerationError(INSUFFICIENT_SOURCE, {**meta, "attempts": attempt, "usage": usage})
            if outcome.ok:
                log.info("quiz generation ok prompt=%s attempts=%d", PROMPT_VERSION, attempt)
                return QuizResult(outcome.questions, {**meta, "attempts": attempt, "usage": usage, "validation": "passed"})
            category, errors = "invalid_output", outcome.errors
            log.warning("quiz generation: invalid output attempt=%d errors=%d", attempt, len(errors))

        raise QuizGenerationError(category, {
            **meta, "attempts": self.max_attempts, "usage": usage, "validation_errors": errors[:5]})

    def _check_content(self, client, title, text, meta):
        """One classification call (no corrective regeneration — see
        content_validation_prompt.build_content_validation_prompt). Returns
        the metadata to record on success; raises `QuizGenerationError`
        (NON_EDUCATIONAL, or CONTENT_VALIDATION_FAILED for anything that
        stopped us from reaching a verdict) otherwise — the generation loop
        is never reached in that case."""
        prompt = build_content_validation_prompt(title, text)
        try:
            response = client.complete(LLMRequest(prompt=prompt.user, system=prompt.system, json_output=True))
        except LLMError as exc:
            log.warning("content validation: LLM call failed category=%s", exc.category)
            raise QuizGenerationError(exc.category, {**meta, "step": "content_validation"}) from exc

        if response.truncated:
            log.warning("content validation: truncated output")
            raise QuizGenerationError(CONTENT_VALIDATION_FAILED, {**meta, "step": "content_validation"})

        outcome = parse_validation_response(response.text)
        if not outcome.ok:
            log.warning("content validation: invalid output errors=%d", len(outcome.errors))
            raise QuizGenerationError(CONTENT_VALIDATION_FAILED,
                                       {**meta, "step": "content_validation", "validation_errors": outcome.errors[:5]})

        log.info("content validation ok prompt=%s is_educational=%s category=%s confidence=%.2f",
                  CONTENT_VALIDATION_PROMPT_VERSION, outcome.is_educational, outcome.category, outcome.confidence)
        if not outcome.is_educational:
            raise QuizGenerationError(NON_EDUCATIONAL, {
                **meta, "step": "content_validation", "content_category": outcome.category,
                "confidence": outcome.confidence, "reason": outcome.reason,
            })
        return {
            "prompt_version": CONTENT_VALIDATION_PROMPT_VERSION, "is_educational": True,
            "category": outcome.category, "confidence": outcome.confidence,
        }
