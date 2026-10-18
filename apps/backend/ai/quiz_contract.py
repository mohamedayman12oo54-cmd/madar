"""
The AI Quiz generation CONTRACT: what is requested, and what counts as a valid
answer from the model. No prompt text and no provider calls live here — the
prompt is `ai/quiz_prompt.py`, orchestration is `ai/quiz_generation.py`.

Relationship to the existing schema (`ai.providers.validate_questions`, stored
in `studentarea.Quiz.questions`, rendered by `studentarea.views`):

    {"q": str, "options": [str], "answer_index": int, "explanation": str}

That shape is reused as-is (same key names, 0-based `answer_index`, 2..6
options). Two keys are ADDED, both optional for legacy/stub questions and
ignored by every existing consumer:

    "type":       "mcq"
    "difficulty": "easy" | "medium" | "hard"

They exist because "exactly 3 easy / 3 medium / 4 hard" cannot be verified —
only requested — unless each question states its difficulty.

Everything checkable by code is checked here, deterministically. What code
cannot prove (source fidelity, distractor quality, whether a "hard" question is
really hard, dialect correctness) is NOT claimed: see `ai/quiz_evaluation.py`
for the human review criteria.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field

from django.conf import settings

# ------------------------------------------------------------- constants ----
QUESTION_TYPE_MCQ = "mcq"
SUPPORTED_QUESTION_TYPES = (QUESTION_TYPE_MCQ,)

EASY, MEDIUM, HARD = "easy", "medium", "hard"
DIFFICULTIES = (EASY, MEDIUM, HARD)

# Product requirement: 10 questions, 30% / 30% / 40%.
REQUIRED_QUESTION_COUNT = 10
REQUIRED_DIFFICULTY_COUNTS = {EASY: 3, MEDIUM: 3, HARD: 4}

# The persisted schema allows 2..6 options (validate_questions); generated MCQs
# use 4, the same width the existing rule-based generator produces.
DEFAULT_OPTION_COUNT = 4
SCHEMA_MIN_OPTIONS, SCHEMA_MAX_OPTIONS = 2, 6
MAX_EXPLANATION_CHARS = 500  # validate_questions cuts at 500; we refuse to be cut

# Quiz languages. There is NO product-level default (see QuizGenerationConfig).
LANG_AR_MSA, LANG_AR_EG, LANG_EN = "ar-msa", "ar-eg", "en"
SUPPORTED_LANGUAGES = (LANG_AR_MSA, LANG_AR_EG, LANG_EN)
_ARABIC_LANGUAGES = (LANG_AR_MSA, LANG_AR_EG)

NEAR_DUPLICATE_JACCARD = 0.8
MIN_ARABIC_SHARE = 0.6   # of letters in the prose fields (question + explanation)
MIN_LATIN_SHARE = 0.9
MAX_REPORTED_ERRORS = 12

INSUFFICIENT_SOURCE = "insufficient_source"


class QuizConfigError(ValueError):
    """The requested generation configuration violates the contract."""


# --------------------------------------------------------------- request ----
@dataclass(frozen=True)
class QuizGenerationConfig:
    """What is asked of the model. Validated on construction, so an invalid
    configuration cannot exist — and therefore can never reach the LLM client.

    `language` has no default on purpose: Madar defines no quiz-language policy
    (the lesson may be spoken in Egyptian Arabic, the quiz may need MSA), and
    silently choosing one would be a product decision made by code.
    """

    language: str
    question_count: int = REQUIRED_QUESTION_COUNT
    difficulty_counts: dict = field(default_factory=lambda: dict(REQUIRED_DIFFICULTY_COUNTS))
    question_types: tuple = SUPPORTED_QUESTION_TYPES
    option_count: int = DEFAULT_OPTION_COUNT

    def __post_init__(self):
        if not self.language:
            raise QuizConfigError(
                "No quiz language is configured. Set QUIZ_LANGUAGE to one of: "
                + ", ".join(SUPPORTED_LANGUAGES) + ".")
        if self.language not in SUPPORTED_LANGUAGES:
            raise QuizConfigError(
                f"Unsupported quiz language {self.language!r}. Supported: {', '.join(SUPPORTED_LANGUAGES)}.")
        if self.question_count != REQUIRED_QUESTION_COUNT:
            raise QuizConfigError(f"question_count must be exactly {REQUIRED_QUESTION_COUNT}, got {self.question_count!r}.")
        counts = self.difficulty_counts
        if not isinstance(counts, dict) or set(counts) != set(DIFFICULTIES):
            raise QuizConfigError(f"difficulty_counts must have exactly the keys {', '.join(DIFFICULTIES)}.")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in counts.values()):
            raise QuizConfigError("difficulty_counts values must be integers.")
        if sum(counts.values()) != self.question_count:
            raise QuizConfigError(
                f"difficulty_counts must sum to {self.question_count}, got {sum(counts.values())}.")
        if counts != REQUIRED_DIFFICULTY_COUNTS:
            raise QuizConfigError(f"difficulty_counts must be exactly {REQUIRED_DIFFICULTY_COUNTS}, got {counts}.")
        if tuple(self.question_types) != SUPPORTED_QUESTION_TYPES:
            raise QuizConfigError(
                f"Unsupported question type(s) {tuple(self.question_types)!r}; only {SUPPORTED_QUESTION_TYPES!r}.")
        if isinstance(self.option_count, bool) or not isinstance(self.option_count, int) \
                or not SCHEMA_MIN_OPTIONS <= self.option_count <= SCHEMA_MAX_OPTIONS:
            raise QuizConfigError(f"option_count must be an integer from {SCHEMA_MIN_OPTIONS} to {SCHEMA_MAX_OPTIONS}.")

    @classmethod
    def from_settings(cls):
        return cls(language=getattr(settings, "QUIZ_LANGUAGE", ""))

    def as_metadata(self):
        return {
            "question_type": QUESTION_TYPE_MCQ,
            "question_count": self.question_count,
            "difficulty_counts": dict(self.difficulty_counts),
            "option_count": self.option_count,
            "language": self.language,
        }


# ---------------------------------------------------------------- output ----
@dataclass
class QuizValidation:
    """Outcome of validating raw model output against a configuration."""
    questions: list | None = None
    errors: list = field(default_factory=list)
    insufficient_source: bool = False

    @property
    def ok(self):
        return self.questions is not None and not self.errors and not self.insufficient_source


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S | re.I)
_DIACRITICS = re.compile("[ً-ٰٟـ]")  # tashkeel, dagger alef, tatweel
_ALEF_YA = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})
_TA_MARBUTA = str.maketrans({"ة": "ه"})

# Whole-token colloquial (Egyptian) markers that do not occur in Modern
# Standard Arabic. Deliberately short and unambiguous: a partial check, not a
# dialect detector (Arabic prose in MSA can still be awkward or wrong).
_COLLOQUIAL_MARKERS = frozenset("ده دي دا ايه ازاي ليه مش عشان كده دلوقتي اللي بتاع بتاعه فين امتي".split())


def normalize_text(text):
    """Comparison form for duplicate detection: NFKC, case-folded, Arabic
    diacritics/tatweel removed, alef/ya/ta-marbuta variants folded, punctuation
    dropped, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", str(text)).casefold()
    t = _DIACRITICS.sub("", t).translate(_ALEF_YA).translate(_TA_MARBUTA)
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def _is_arabic_letter(ch):
    o = ord(ch)
    return 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def script_shares(text):
    letters = [c for c in text if unicodedata.category(c).startswith("L")]
    if not letters:
        return 0.0, 0.0
    arabic = sum(_is_arabic_letter(c) for c in letters)
    latin = sum(("LATIN" in unicodedata.name(c, "")) for c in letters)
    return arabic / len(letters), latin / len(letters)


def parse_generated_quiz(raw, config: QuizGenerationConfig) -> QuizValidation:
    """Parse and validate the model's raw text. Never repairs content: output
    that violates the contract is reported, not fixed. (The only tolerance is
    a single surrounding ```json fence, which is packaging, not content.)"""
    out = QuizValidation()
    text = (raw or "").strip()
    fence = _FENCE.match(text)
    if fence:
        text = fence.group(1)
    if not text:
        out.errors.append("output is empty")
        return out
    try:
        data = json.loads(text)
    except ValueError:
        out.errors.append("output is not valid JSON")
        return out
    if not isinstance(data, dict):
        out.errors.append("output must be a JSON object")
        return out
    if data.get("error") == INSUFFICIENT_SOURCE:
        out.insufficient_source = True
        return out
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list):
        out.errors.append('output must contain a "questions" list')
        return out
    if len(raw_questions) != config.question_count:
        out.errors.append(f"expected exactly {config.question_count} questions, got {len(raw_questions)}")

    questions, errs = [], out.errors
    for i, item in enumerate(raw_questions, 1):
        question = _validate_question(item, i, config, errs)
        if question is not None:
            questions.append(question)

    if len(questions) == len(raw_questions):
        _check_distribution(questions, config, errs)
        _check_duplicates(questions, errs)
        _check_language(questions, config, errs)

    if len(errs) > MAX_REPORTED_ERRORS:
        out.errors = errs[:MAX_REPORTED_ERRORS] + [f"... and {len(errs) - MAX_REPORTED_ERRORS} more"]
    if not out.errors:
        out.questions = questions
    return out


def _validate_question(item, i, config, errs):
    where = f"question {i}"
    if not isinstance(item, dict):
        errs.append(f"{where}: must be an object")
        return None
    before = len(errs)

    qtype = item.get("type")
    if qtype not in config.question_types:
        errs.append(f"{where}: type must be one of {list(config.question_types)}, got {_brief(qtype)}")
    difficulty = item.get("difficulty")
    if difficulty not in DIFFICULTIES:
        errs.append(f"{where}: difficulty must be one of {list(DIFFICULTIES)}, got {_brief(difficulty)}")

    q = item.get("q")
    if not isinstance(q, str) or not q.strip():
        errs.append(f"{where}: q must be a non-empty string")
    explanation = item.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        errs.append(f"{where}: explanation must be a non-empty string")
    elif len(explanation.strip()) > MAX_EXPLANATION_CHARS:
        errs.append(f"{where}: explanation exceeds {MAX_EXPLANATION_CHARS} characters")

    options = item.get("options")
    if not isinstance(options, list) or len(options) != config.option_count:
        errs.append(f"{where}: options must be a list of exactly {config.option_count} strings")
    elif not all(isinstance(o, str) and o.strip() for o in options):
        errs.append(f"{where}: every option must be a non-empty string")
    else:
        normalized = [normalize_text(o) for o in options]
        if len(set(normalized)) != len(normalized):
            errs.append(f"{where}: options must be distinct")

    answer = item.get("answer_index")
    if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < config.option_count:
        errs.append(f"{where}: answer_index must be an integer from 0 to {config.option_count - 1}")

    if len(errs) > before:
        return None
    return {
        "q": q.strip(), "options": [o.strip() for o in options], "answer_index": answer,
        "explanation": explanation.strip(), "type": qtype, "difficulty": difficulty,
    }


def _brief(value):
    return repr(value)[:40]


def _check_distribution(questions, config, errs):
    got = {d: sum(q["difficulty"] == d for q in questions) for d in DIFFICULTIES}
    if got != config.difficulty_counts:
        errs.append(f"difficulty distribution must be {config.difficulty_counts}, got {got}")


def _check_duplicates(questions, errs):
    tokens = [set(normalize_text(q["q"]).split()) for q in questions]
    pairs = [
        (i + 1, j + 1)
        for i in range(len(questions)) for j in range(i + 1, len(questions))
        if tokens[i] == tokens[j] or (min(len(tokens[i]), len(tokens[j])) >= 3
                                      and _jaccard(tokens[i], tokens[j]) >= NEAR_DUPLICATE_JACCARD)
    ]
    for a, b in pairs[:3]:   # capped so a degenerate quiz cannot flood out every other error
        errs.append(f"questions {a} and {b} are duplicates or near-duplicates")
    if len(pairs) > 3:
        errs.append(f"... and {len(pairs) - 3} more duplicate pair(s)")


def _check_language(questions, config, errs):
    """Coarse, deterministic compliance check on the PROSE fields (question and
    explanation); options are excluded because they are often bare technical
    terms. It cannot establish correct grammar, register or dialect."""
    prose = " ".join(f"{q['q']} {q['explanation']}" for q in questions)
    arabic, latin = script_shares(prose)
    if config.language in _ARABIC_LANGUAGES and arabic < MIN_ARABIC_SHARE:
        errs.append(f"language {config.language}: Arabic script is {arabic:.0%} of letters in questions/explanations "
                    f"(minimum {MIN_ARABIC_SHARE:.0%})")
    if config.language == LANG_EN and latin < MIN_LATIN_SHARE:
        errs.append(f"language en: Latin script is {latin:.0%} of letters in questions/explanations "
                    f"(minimum {MIN_LATIN_SHARE:.0%})")
    if config.language == LANG_AR_MSA:
        words = set(_DIACRITICS.sub("", prose).translate(_ALEF_YA).split())
        # (ta marbuta is deliberately not folded here, so "آية" = verse never collides with "ايه")
        stripped = {w.strip("؟?.,،:؛!\"'()") for w in words}
        hits = sorted(stripped & _COLLOQUIAL_MARKERS)
        if hits:
            errs.append(f"language ar-msa: colloquial word(s) found: {', '.join(hits)}")
