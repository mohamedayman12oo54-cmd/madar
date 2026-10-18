"""Quiz source preparation (ai/quiz_source.py): complete material, explicit
failure, no mutation of the stored transcript, lossless splitting."""
import random

from django.test import SimpleTestCase
from django.utils import timezone

from content.models import ContentItem, Transcript
from environments.tenancy_testing import TenantTestCase

from .quiz_source import (
    NOT_READY, ORIGIN_TEACHER_TEXT, ORIGIN_TRANSCRIPT, UNAVAILABLE, QuizSourceError,
    prepare_quiz_source, split_text,
)


def long_transcript(chars=100_000):
    """A ~2 hour lesson: numbered Arabic sentences, so any lost/reordered part is detectable."""
    parts, n = [], 0
    while sum(len(p) for p in parts) < chars:
        n += 1
        parts.append(f"الجملة رقم {n} من شرح الدرس عن الخلية والبناء الضوئي. ")
    return "".join(parts).strip(), n


class PrepareTests(TenantTestCase):
    def item(self, **kw):
        defaults = dict(environment=self.env_a, title="درس الخلية", description="وصف", published_at=timezone.now())
        defaults.update(kw)
        return ContentItem.objects.create(**defaults)

    def uploaded(self, status=Transcript.Status.COMPLETED, text="", **kw):
        item = self.item(source=ContentItem.Source.UPLOAD, **kw)
        Transcript.objects.create(environment=self.env_a, item=item, status=status, text=text,
                                  segments=[{"start": 0.0, "end": 1.0, "text": text}] if text else [],
                                  language="ar", duration_seconds=7200, provider="faster_whisper")
        return item

    def test_long_transcript_is_returned_complete_not_a_prefix(self):
        text, n = long_transcript()
        source = prepare_quiz_source(self.uploaded(text=text, description=""))
        self.assertEqual(source.origin, ORIGIN_TRANSCRIPT)
        self.assertEqual(source.text, text)
        self.assertGreater(source.char_count, 60_000)              # nothing near the old 6000 cap
        self.assertIn(f"الجملة رقم {n} ", source.text)             # the END of the lesson is present
        self.assertIn("الجملة رقم 1 ", source.text)

    def test_teacher_notes_are_appended_not_dropped(self):
        source = prepare_quiz_source(self.uploaded(text="نص التفريغ.", description="ملخص المعلم", quiz_source="نقاط مهمة"))
        self.assertTrue(source.text.startswith("نص التفريغ."))
        self.assertIn("ملخص المعلم", source.text)
        self.assertIn("نقاط مهمة", source.text)

    def test_provenance_is_recorded_in_the_evidence_snapshot(self):
        item = self.uploaded(text="نص التفريغ.", description="")
        evidence = prepare_quiz_source(item).as_evidence()
        transcript = Transcript.objects.get(item=item)
        self.assertEqual((evidence["title"], evidence["text"]), ("درس الخلية", "نص التفريغ."))
        self.assertEqual(evidence["source"], {
            "origin": ORIGIN_TRANSCRIPT, "char_count": len("نص التفريغ."), "transcript_id": transcript.pk,
            "transcript_updated_at": transcript.updated_at.isoformat(), "language": "ar", "duration_seconds": 7200,
        })

    def test_the_stored_transcript_is_never_modified(self):
        text, _ = long_transcript(20_000)
        item = self.uploaded(text=text, description="ملخص")
        before = Transcript.objects.values().get(item=item)
        prepare_quiz_source(item)
        self.assertEqual(Transcript.objects.values().get(item=item), before)

    def test_external_video_uses_the_complete_teacher_text(self):
        body = "جملة طويلة من المعلم. " * 2000   # 44k chars, far over the old 6000 cut
        source = prepare_quiz_source(self.item(description=body, quiz_source="ملخص"))
        self.assertEqual(source.origin, ORIGIN_TEACHER_TEXT)
        self.assertEqual(source.text, f"{body}\nملخص".strip())
        self.assertIsNone(source.transcript_id)

    def test_uploaded_video_without_a_usable_transcript_fails_explicitly(self):
        cases = [
            (Transcript.Status.PENDING, "", NOT_READY),
            (Transcript.Status.PROCESSING, "", NOT_READY),
            (Transcript.Status.FAILED, "", UNAVAILABLE),
            (Transcript.Status.COMPLETED, "   ", UNAVAILABLE),
        ]
        for status, text, code in cases:
            with self.subTest(status=status, text=text):
                # a perfectly good teacher summary must NOT silently stand in for the lesson
                item = self.uploaded(status=status, text=text, description="ملخص طويل بما يكفي للدرس كله", quiz_source="نقاط")
                with self.assertRaises(QuizSourceError) as ctx:
                    prepare_quiz_source(item)
                self.assertEqual(ctx.exception.code, code)
                self.assertTrue(ctx.exception.message)

    def test_uploaded_video_with_no_transcript_row_fails_explicitly(self):
        with self.assertRaises(QuizSourceError) as ctx:
            prepare_quiz_source(self.item(source=ContentItem.Source.UPLOAD, quiz_source="ملخص"))
        self.assertEqual(ctx.exception.code, UNAVAILABLE)

    def test_a_transcript_from_another_environment_is_never_used(self):
        item = self.item(source=ContentItem.Source.UPLOAD)
        Transcript.objects.create(environment=self.env_b, item=item, status=Transcript.Status.COMPLETED, text="سري")
        with self.assertRaises(QuizSourceError):
            prepare_quiz_source(item)


class SplitTextTests(SimpleTestCase):
    def assert_lossless(self, text, limit):
        pieces = split_text(text, limit)
        self.assertEqual("".join(pieces), text)
        self.assertTrue(all(0 < len(p) <= limit for p in pieces), [len(p) for p in pieces if len(p) > limit])
        return pieces

    def test_a_long_transcript_is_partitioned_with_nothing_lost(self):
        text, _ = long_transcript(100_000)
        pieces = self.assert_lossless(text, 8_000)
        self.assertGreaterEqual(len(pieces), 12)

    def test_pieces_break_on_sentence_boundaries_when_possible(self):
        text, _ = long_transcript(30_000)
        for piece in split_text(text, 5_000)[:-1]:
            self.assertTrue(piece.rstrip().endswith("."), piece[-30:])

    def test_text_that_fits_is_one_piece(self):
        self.assertEqual(split_text("جملة واحدة. وأخرى؟", 1000), ["جملة واحدة. وأخرى؟"])
        self.assertEqual(split_text("", 10), [])

    def test_arabic_and_latin_terminators(self):
        text = "ما هي الخلية؟ هي وحدة البناء. What is DNA? A molecule! ختام"
        self.assert_lossless(text, 15)

    def test_oversized_sentence_without_punctuation_is_cut_on_spaces_then_hard(self):
        self.assert_lossless("كلمة " * 500, 37)
        self.assert_lossless("ا" * 1000, 64)   # one unbroken token

    def test_random_inputs_are_always_lossless(self):
        rng = random.Random(7)
        alphabet = "ابتث جحخ .؟!?\n\t abc"
        for _ in range(200):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
            self.assert_lossless(text, rng.randint(1, 60)) if text else self.assertEqual(split_text(text, 5), [])

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            split_text("x", 0)
