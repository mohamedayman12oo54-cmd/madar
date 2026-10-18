"""
Evaluation of REAL model output — the part of quality that unit tests with a
mocked model cannot establish.

Two layers, deliberately kept apart:

* `deterministic_metrics` — facts a program can compute about a quiz (counts,
  answer-position spread, length bias, script share). Cheap, repeatable.
* `REVIEW_CRITERIA` / `review_sheet` — what only a human reviewer (ideally the
  lesson's teacher) can judge. The harness never scores these itself.

Run via `manage.py evaluate_quiz_generation`; nothing here is used on the
request path.
"""
from collections import Counter

from .quiz_contract import DIFFICULTIES, script_shares

REVIEW_SCALE = "0 = fails, 1 = acceptable with edits, 2 = good as is"

REVIEW_CRITERIA = [
    {"id": "source_fidelity",
     "check": "The question and its correct answer are stated or directly implied by the lesson text; nothing is "
              "imported from outside it; the explanation adds no new facts."},
    {"id": "question_clarity",
     "check": "The question is unambiguous and answerable without guessing what the writer meant; exactly one "
              "option is defensible."},
    {"id": "distractor_quality",
     "check": "Wrong options are plausible to a student who half-understood the lesson, do not overlap, and give "
              "no clue through length, grammar or wording."},
    {"id": "duplication",
     "check": "The question tests a different idea from every other question in the quiz."},
    {"id": "difficulty_appropriateness",
     "check": "The labelled difficulty matches the reasoning needed (easy = recall, medium = interpretation or "
              "application, hard = multi-step reasoning or synthesis), judged against the lesson."},
    {"id": "language_style",
     "check": "Language, register and dialect match the configured quiz language throughout; technical terms are "
              "used as in the lesson; no mixed or inconsistent wording."},
]


def deterministic_metrics(questions, config):
    n = len(questions)
    correct_is_longest = sum(
        1 for q in questions
        if len(q["options"][q["answer_index"]]) == max(len(o) for o in q["options"])
        and sum(len(o) == len(q["options"][q["answer_index"]]) for o in q["options"]) == 1
    )
    positions = Counter(q["answer_index"] for q in questions)
    prose = " ".join(f"{q['q']} {q['explanation']}" for q in questions)
    arabic, latin = script_shares(prose)
    return {
        "question_count": n,
        "difficulty_counts": {d: sum(q["difficulty"] == d for q in questions) for d in DIFFICULTIES},
        "answer_position_counts": {str(i): positions.get(i, 0) for i in range(config.option_count)},
        # A model that makes the right answer the unique longest option is
        # easy to game; a value far above 1/option_count is a warning sign.
        "correct_option_unique_longest_share": round(correct_is_longest / n, 2) if n else 0.0,
        "arabic_letter_share": round(arabic, 2),
        "latin_letter_share": round(latin, 2),
    }


def review_sheet(questions):
    """One blank review row per question, for a human to fill in."""
    return [
        {"number": i, "difficulty": q["difficulty"], "q": q["q"], "options": q["options"],
         "answer_index": q["answer_index"], "explanation": q["explanation"],
         "scores": {c["id"]: None for c in REVIEW_CRITERIA}, "notes": ""}
        for i, q in enumerate(questions, 1)
    ]
