"""
LLM-backed quiz generation, plugged into the EXISTING operation lifecycle:

    studentarea quiz request  ->  AIOperation(pending, evidence = prepared source)
    process_ai_operations     ->  get_provider().generate_quiz_result(evidence)   <- this module
                              ->  validate_questions()  ->  Quiz + AIOperation(completed)
                                  or AIOperation(failed, error, metadata)

Select it with `AI_PROVIDER=llm`. It subclasses `StubTutorProvider` and overrides what the real model should do:
quiz generation and the Study Assistant's answers (`generate`, grounded in the Knowledge Base excerpts only). The
monthly State suggestion keeps the transparent counts rule, without the "test mode" label.

Pipeline per operation (every step is its own module):
    1. configuration    quiz_contract.QuizGenerationConfig   (validated BEFORE any LLM call)
    2. source guard     evidence["text"] is already the complete prepared lesson
                        (quiz_source.py); too little material fails explicitly
    3. content check    content_validation_prompt + content_validation_contract:
                        one classification call, EDUCATIONAL vs NON_EDUCATIONAL
                        (QUIZ_CONTENT_VALIDATION_ENABLED; on by default). A
                        NON_EDUCATIONAL verdict, or a validation failure, means
                        NO quiz: sequentially it stops before generation; with
                        QUIZ_VALIDATION_PARALLEL (default) it runs at the same time as
                        the first generation call, and its verdict is applied before
                        anything is returned — so the student waits for one model call,
                        not two, and still never receives a quiz for rejected content.
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
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from .content_validation_contract import parse_validation_response
from .content_validation_prompt import PROMPT_VERSION as CONTENT_VALIDATION_PROMPT_VERSION
from .content_validation_prompt import build_content_validation_prompt
from .llm import LLMError, LLMRequest, get_llm_client
from .providers import AIProviderError, QuizResult, StubTutorProvider, state_from_counts
from .quiz_contract import INSUFFICIENT_SOURCE, QuizConfigError, QuizGenerationConfig, parse_generated_quiz
from .quiz_prompt import PROMPT_VERSION, build_quiz_prompt
from .tutor_prompt import PROMPT_VERSION as TUTOR_PROMPT_VERSION
from .tutor_prompt import build_tutor_prompt

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


# The Study Assistant has its own wording: the student asked a question, not for a quiz.
_TUTOR_BUSY = "المساعد الدراسي مشغول حاليًا. حاول مرة أخرى بعد قليل."
_TUTOR_FAILURE_MESSAGES = {
    "config": "المساعد الدراسي غير مهيأ بعد. أخبر معلمك.",
    "rate_limit": _TUTOR_BUSY, "timeout": _TUTOR_BUSY, "network": _TUTOR_BUSY, "provider": _TUTOR_BUSY,
    "blocked": "لا أستطيع الإجابة عن هذا السؤال. جرّب صياغته بطريقة أخرى أو اسأل معلمك.",
    "malformed_response": "تعذّر تجهيز الإجابة. حاول مرة أخرى.",
}
TUTOR_MAX_OUTPUT_TOKENS = 2048   # a short answer; also bounds how long a student can be kept waiting


class TutorError(AIProviderError):
    """A categorised Study Assistant failure; `str(exc)` is safe to show to the student."""

    def __init__(self, category, metadata=None):
        super().__init__(_TUTOR_FAILURE_MESSAGES.get(category, "تعذّر الرد على سؤالك الآن."))
        self.category = category
        self.metadata = {**(metadata or {}), "validation": "failed", "failure_category": category}


class QuizGenerationError(AIProviderError):
    """An explicit, categorised failure. `str(exc)` is a fixed Arabic message
    that is safe to show to a student; `metadata` is for operators."""

    def __init__(self, category, metadata=None):
        super().__init__(_FAILURE_MESSAGES.get(category, _GENERIC))
        self.category = category
        self.metadata = {**(metadata or {}), "validation": "failed", "failure_category": category}


class LLMQuizProvider(StubTutorProvider):
    def __init__(self, *, client=None, config=None, max_attempts=DEFAULT_MAX_ATTEMPTS,
                 min_source_chars=DEFAULT_MIN_SOURCE_CHARS, validate_content=True,
                 parallel_validation=False, validation_sample_chars=0):
        if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
            raise QuizGenerationError("config", {"detail": f"QUIZ_MAX_ATTEMPTS must be 1..{MAX_ATTEMPTS_LIMIT}"})
        self._client = client
        self._config = config   # None => QuizGenerationConfig.from_settings() per operation
        self.max_attempts = max_attempts
        self.min_source_chars = min_source_chars
        self.validate_content = validate_content
        self.parallel_validation = parallel_validation
        self.validation_sample_chars = max(0, int(validation_sample_chars or 0))

    @classmethod
    def from_settings(cls):
        return cls(
            max_attempts=getattr(settings, "QUIZ_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
            min_source_chars=getattr(settings, "QUIZ_MIN_SOURCE_CHARS", DEFAULT_MIN_SOURCE_CHARS),
            validate_content=getattr(settings, "QUIZ_CONTENT_VALIDATION_ENABLED", True),
            parallel_validation=getattr(settings, "QUIZ_VALIDATION_PARALLEL", True),
            validation_sample_chars=getattr(settings, "QUIZ_VALIDATION_SAMPLE_CHARS", 0),
        )

    # ------------------------------------------------------------- tutor --
    def generate(self, prompt, context=""):
        """The Study Assistant. Grounded ONLY in the Knowledge Base excerpts: with none, there is nothing to
        answer from, so no model call is made at all (instant, free, and nothing can be invented)."""
        if not (context or "").strip():
            raise AIProviderError(
                "لا توجد مادة منشورة في قاعدة المعرفة تغطي هذا السؤال بعد. "
                "جرّب صياغة أخرى أو اسأل معلمك."
            )
        meta = {"prompt_version": TUTOR_PROMPT_VERSION}
        try:
            client = self._client or get_llm_client()
        except LLMError as exc:
            log.error("study assistant: LLM client unavailable (%s)", exc.category)
            raise TutorError(exc.category, meta) from exc
        built = build_tutor_prompt(prompt, context)
        try:
            response = client.complete(LLMRequest(
                prompt=built.user, system=built.system, max_output_tokens=TUTOR_MAX_OUTPUT_TOKENS, temperature=0.3))
        except LLMError as exc:
            log.warning("study assistant: LLM call failed category=%s", exc.category)
            raise TutorError(exc.category, {**meta, "provider_attempts": exc.attempts}) from exc
        answer = response.text.strip()
        if response.truncated:  # never present a cut-off sentence as a finished answer
            answer = answer.rstrip() + "…"
        log.info("study assistant ok latency_ms=%s tokens=%s", response.latency_ms,
                 response.usage.total_tokens if response.usage else None)
        return answer

    def recommend_state(self, evidence):
        """Advisory State from the counts — a transparent rule, not a model: instant, repeatable and explainable
        to a teacher. Same decision as the stub, worded for production (no "test mode" label)."""
        state, present, sessions, studied, recitations = state_from_counts(evidence)
        return state, (
            f"الحضور: {present} من {sessions} — التسميع: {studied} ذاكر من {recitations}. "
            "هذا اقتراح استشاري محسوب من أرقام الشهر، والقرار النهائي للمعلّم."
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

        # 3. content check — a NON_EDUCATIONAL verdict (or a failure to reach one) means no quiz. Sequential mode
        # runs it first; parallel mode runs it WHILE the first generation call is in flight and applies the
        # verdict before anything is returned (see the module docstring).
        started = time.monotonic()
        timings = {}
        check = None
        pool = None
        if self.validate_content:
            sample = self._classifier_sample(text)
            if len(sample) < len(text):
                meta["validation_sample_chars"] = len(sample)
            if self.parallel_validation:
                pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quiz-check")
                check = pool.submit(self._timed_check, client, title, sample, dict(meta), timings)
            else:
                meta["content_validation"] = self._timed_check(client, title, sample, meta, timings)
        try:
            result = self._generate_loop(client, config, title, text, meta, check, timings)
            if check is not None:
                meta["content_validation"] = check.result()      # raises on NON_EDUCATIONAL / failed check
            result.metadata["content_validation"] = meta.get("content_validation")
            if result.metadata["content_validation"] is None:
                result.metadata.pop("content_validation")
            timings["total"] = int((time.monotonic() - started) * 1000)
            result.metadata["timings_ms"] = dict(timings)
            return result
        except QuizGenerationError as exc:
            # If the content check has ALREADY condemned the lesson, that is the more useful answer than whatever
            # the generation side hit on the way. (Never wait for an unfinished check just to fail slower.)
            if check is not None and check.done():
                try:
                    check.result()
                except QuizGenerationError as verdict:
                    verdict.metadata["timings_ms"] = dict(timings)
                    if verdict is exc:
                        raise
                    raise verdict from exc
            exc.metadata["timings_ms"] = {**timings, "total": int((time.monotonic() - started) * 1000)}
            raise
        finally:
            if pool is not None:
                pool.shutdown(wait=False)

    def _classifier_sample(self, text):
        """What the content check reads: the whole transcript, or — above the configured size — its beginning,
        middle and end, which is enough to tell WHAT the lesson is without paying to send hours of it twice."""
        limit = self.validation_sample_chars
        if not limit or len(text) <= limit:
            return text
        third = limit // 3
        mid = (len(text) - third) // 2
        return "\n[…]\n".join((text[:third], text[mid:mid + third], text[-third:]))

    def _timed_check(self, client, title, sample, meta, timings):
        t0 = time.monotonic()
        try:
            return self._check_content(client, title, sample, meta)
        finally:
            timings["content_check"] = int((time.monotonic() - t0) * 1000)

    def _generate_loop(self, client, config, title, text, meta, check, timings):
        usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        errors, category = [], "invalid_output"
        t0 = time.monotonic()
        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1 and check is not None and check.done():
                check.result()   # already condemned (raises) — do not spend a corrective call on it
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
            timings["generation"] = int((time.monotonic() - t0) * 1000)
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
