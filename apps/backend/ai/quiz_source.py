"""
Quiz source preparation — the boundary between stored lesson material and
quiz generation.

Before this module the quiz request copied `description + quiz_source` into the
operation's snapshot and sliced it to 6000 characters, and the stored
`content.Transcript` (the real text of the lesson) was never read at all.

Rules this boundary enforces:

* The COMPLETE material is returned. Nothing here slices, summarises or
  otherwise reduces it, and nothing writes to `Transcript`: what is returned is
  a derived, in-memory snapshot.
* An item whose video was uploaded to Madar (`ContentItem.source == "upload"`)
  is taught by that video, so its transcript is REQUIRED. A transcript that is
  pending/processing/failed/missing raises `QuizSourceError`; there is
  deliberately no silent fallback to the (possibly empty or partial) teacher
  text, because that would produce a quiz about a lesson nobody checked.
* Items that reference an external video have no transcript by construction
  (transcription only runs on uploads); their source is the teacher's text, as
  before, but complete.
* Whether a lesson fits ONE provider request is not decided here: that depends
  on the chosen model's context/output limits. `QuizSource.char_count` and
  `split_text` are the primitives the generation phase builds that decision on.
"""
import re
from dataclasses import dataclass

from content.models import ContentItem, Transcript

ORIGIN_TRANSCRIPT = "transcript"
ORIGIN_TEACHER_TEXT = "teacher_text"

NOT_READY = "transcript_not_ready"
UNAVAILABLE = "transcript_unavailable"


class QuizSourceError(Exception):
    """The lesson's material cannot be used right now. `code` is stable and
    machine-readable; `message` is safe to show to the student."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class QuizSource:
    title: str
    text: str                       # the COMPLETE material
    origin: str                     # ORIGIN_TRANSCRIPT | ORIGIN_TEACHER_TEXT
    transcript_id: int | None = None
    transcript_updated_at: str | None = None
    language: str = ""
    duration_seconds: int | None = None

    @property
    def char_count(self):
        return len(self.text)

    def as_evidence(self):
        """The frozen snapshot stored on `AIOperation.evidence`. `title`/`text`
        keep their existing meaning (the worker reads exactly those); `source`
        records where the text came from so a quiz can be traced back to it."""
        return {
            "title": self.title,
            "text": self.text,
            "source": {
                "origin": self.origin,
                "char_count": self.char_count,
                "transcript_id": self.transcript_id,
                "transcript_updated_at": self.transcript_updated_at,
                "language": self.language,
                "duration_seconds": self.duration_seconds,
            },
        }


def teacher_text(item):
    """What the teacher wrote for the lesson, complete. Same composition the
    quiz request used before (minus the slice)."""
    return f"{item.description}\n{item.quiz_source}".strip()


def prepare_quiz_source(item) -> QuizSource:
    """-> the complete source for a quiz about `item`, or `QuizSourceError`.

    `item` must already have passed the caller's authorisation (the student
    view only offers published, targeted items of the student's environment);
    this function adds no access to anything the caller could not already
    reach, and the transcript is looked up within the item's own environment.
    """
    notes = teacher_text(item)
    if item.source != ContentItem.Source.UPLOAD:
        return QuizSource(title=item.title, text=notes, origin=ORIGIN_TEACHER_TEXT)

    transcript = Transcript.objects.filter(item_id=item.pk, environment_id=item.environment_id).first()
    if transcript is None:
        raise QuizSourceError(UNAVAILABLE, _UNAVAILABLE_MESSAGE)
    if transcript.status in (Transcript.Status.PENDING, Transcript.Status.PROCESSING):
        raise QuizSourceError(NOT_READY, _NOT_READY_MESSAGE)
    text = (transcript.text or "").strip()
    if transcript.status != Transcript.Status.COMPLETED or not text:
        raise QuizSourceError(UNAVAILABLE, _UNAVAILABLE_MESSAGE)

    if notes:
        text = f"{text}\n\n{notes}"  # the teacher's own notes are lesson material too — never dropped
    return QuizSource(
        title=item.title, text=text, origin=ORIGIN_TRANSCRIPT,
        transcript_id=transcript.pk, transcript_updated_at=transcript.updated_at.isoformat(),
        language=transcript.language, duration_seconds=transcript.duration_seconds,
    )


_NOT_READY_MESSAGE = "ما زال نص هذا الدرس قيد التجهيز. حاول طلب الاختبار مرة أخرى بعد قليل."
_UNAVAILABLE_MESSAGE = "تعذّر تجهيز نص هذا الدرس، لذلك لا يمكن إنشاء اختبار له الآن. أخبر معلمك."


# --------------------------------------------------------------- splitting --
# A sentence is a run ending in terminal punctuation (Latin or Arabic) plus the
# whitespace after it, or the unterminated tail. Together these cover the whole
# string, which is what makes `split_text` lossless.
_SENTENCE = re.compile(r"[^.!?؟۔]*[.!?؟۔]+\s*|[^.!?؟۔]+\Z")


def split_text(text, max_chars):
    """Partition `text` into consecutive pieces of at most `max_chars`
    characters, preferring sentence boundaries, then spaces, then (only for an
    unbroken token longer than the limit) a hard cut.

    LOSSLESS by construction: `"".join(split_text(t, n)) == t`. It is a
    primitive, not a strategy — the limit itself (a function of the chosen
    model's context and output limits), any overlap, and how questions are
    spread across pieces are generation-phase decisions and are not made here.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    pieces, current = [], ""
    for sentence in _SENTENCE.findall(text):
        for part in (_hard_split(sentence, max_chars) if len(sentence) > max_chars else (sentence,)):
            if current and len(current) + len(part) > max_chars:
                pieces.append(current)
                current = ""
            current += part
    if current:
        pieces.append(current)
    return pieces


def _hard_split(sentence, max_chars):
    out = []
    while len(sentence) > max_chars:
        space = sentence.rfind(" ", 0, max_chars)
        cut = space + 1 if space > 0 else max_chars  # keep the space with the left piece
        out.append(sentence[:cut])
        sentence = sentence[cut:]
    if sentence:
        out.append(sentence)
    return out
