"""Getting the audio to the transcription service: where ffmpeg comes from, what happens to a big video when there
is none, and how a long lecture is sent in pieces. The real-ffmpeg tests run only when an ffmpeg is available."""
import json
import os
import subprocess
import tempfile
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import transcription
from .models import Transcript
from .test_video import _Base
from .transcription import ExternalSTTError, GroqWhisperTranscriber, Transcriber, run_transcription

HAVE_FFMPEG = bool(transcription._ffmpeg_path())


def _ok(text, duration, segments=()):
    body = {"text": text, "language": "ar", "duration": duration,
            "segments": [{"start": s, "end": e, "text": t} for s, e, t in segments]}
    return 200, {}, json.dumps(body).encode()


class FindingFfmpegTests(SimpleTestCase):
    @override_settings(FFMPEG_BINARY="")
    def test_a_system_ffmpeg_is_preferred_over_the_bundled_one(self):
        with mock.patch.object(transcription.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(transcription._ffmpeg_path(), "/usr/bin/ffmpeg")

    @override_settings(FFMPEG_BINARY="")
    def test_the_bundled_ffmpeg_is_used_when_the_machine_has_none(self):
        fake = mock.Mock(get_ffmpeg_exe=mock.Mock(return_value=__file__))  # any existing file stands in for the exe
        with mock.patch.object(transcription.shutil, "which", return_value=None), \
                mock.patch.dict("sys.modules", {"imageio_ffmpeg": fake}):
            self.assertEqual(transcription._ffmpeg_path(), __file__)

    @override_settings(FFMPEG_BINARY="")
    def test_no_ffmpeg_anywhere_is_none_not_a_crash(self):
        with mock.patch.object(transcription.shutil, "which", return_value=None), \
                mock.patch.dict("sys.modules", {"imageio_ffmpeg": None}):  # import fails
            self.assertIsNone(transcription._ffmpeg_path())

    def test_the_configured_path_wins(self):
        with override_settings(FFMPEG_BINARY=__file__), \
                mock.patch.object(transcription.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(transcription._ffmpeg_path(), __file__)


class BigVideoWithoutFfmpegTests(SimpleTestCase):
    def _transcribe(self, ffmpeg):
        client = GroqWhisperTranscriber(api_key="gsk_test", max_upload_mb=1,
                                        transport=mock.Mock(side_effect=AssertionError("must not call the API")))
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/video.mp4", False)), \
                mock.patch.object(transcription, "_ffmpeg_path", return_value=ffmpeg), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"x" * (1024 * 1024 + 1))):
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe("/tmp/video.mp4")
        return ctx.exception

    def test_a_big_video_with_no_ffmpeg_says_so(self):
        err = self._transcribe(ffmpeg=None)
        self.assertEqual((err.category, err.hint), ("too_large", "no_ffmpeg"))

    def test_a_big_video_whose_extraction_failed_is_plainly_too_large(self):
        err = self._transcribe(ffmpeg="/usr/bin/ffmpeg")
        self.assertEqual((err.category, err.hint), ("too_large", None))


class NoFfmpegMessageTests(_Base):
    @override_settings(TRANSCRIPTION_BACKGROUND="worker")
    def test_the_teacher_is_told_the_server_lacks_ffmpeg_not_that_the_video_is_too_big(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)

        class NoFfmpeg(Transcriber):
            name = "groq_whisper_api"

            def transcribe(self, path, language=""):
                raise ExternalSTTError("big", category="too_large", hint="no_ffmpeg")

        with mock.patch.dict(transcription._TRANSCRIBERS, {"groq_whisper_api": NoFfmpeg}):
            run_transcription(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.error, transcription._STT_NO_FFMPEG)
        self.assertIn("ffmpeg", row.error)
        self.assertNotEqual(row.error, transcription._STT_FAILURE_MESSAGES["too_large"])


class LongLectureInPiecesTests(SimpleTestCase):
    """The audio alone is over the limit, so it goes out in several pieces that are stitched back together."""

    def test_pieces_are_sent_in_order_and_times_are_moved_to_where_each_piece_sits(self):
        sent = []

        def transport(url, headers, fields, filename, data, timeout):
            sent.append(data)
            n = len(sent)
            return _ok(f"جزء {n}", 100.0, [(0.0, 4.0, f"بداية {n}"), (4.0, 9.0, f"نهاية {n}")])

        client = GroqWhisperTranscriber(api_key="gsk_test", max_upload_mb=1, transport=transport)
        big = b"a" * (1024 * 1024 + 1)  # the extracted audio is over the limit -> split
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/a.mp3", True)), \
                mock.patch.object(transcription, "_split_audio",
                                  return_value=[("/tmp/p1.mp3", 0), ("/tmp/p2.mp3", 1500)]) as split, \
                mock.patch.object(transcription, "_remove_files") as cleanup, \
                mock.patch("builtins.open", mock.mock_open(read_data=big)) as op:
            op.return_value.read.side_effect = [big, b"p1", b"p2"]
            result = client.transcribe("/tmp/v.mp4", "ar")
        split.assert_called_once()
        self.assertEqual(sent, [b"p1", b"p2"])
        self.assertEqual(result["text"], "جزء 1 جزء 2")
        starts = [s["start"] for s in result["segments"]]
        self.assertEqual(starts, [0.0, 4.0, 1500.0, 1504.0], "the second piece starts 1500 s into the lecture")
        self.assertEqual(result["duration"], 1600.0)
        self.assertEqual(result["parts"], 2)
        self.assertEqual(set(cleanup.call_args[0][0]), {"/tmp/a.mp3", "/tmp/p1.mp3", "/tmp/p2.mp3"})

    def test_a_failing_piece_fails_the_whole_lecture_and_still_cleans_up(self):
        calls = []

        def transport(url, headers, fields, filename, data, timeout):
            calls.append(1)
            return (200, {}, b"{}") if False else (429, {}, b'{"error":{"message":"slow down"}}')

        client = GroqWhisperTranscriber(api_key="gsk_test", max_upload_mb=1, transport=transport)
        big = b"a" * (1024 * 1024 + 1)
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/a.mp3", True)), \
                mock.patch.object(transcription, "_split_audio", return_value=[("/tmp/p1.mp3", 0), ("/tmp/p2.mp3", 9)]), \
                mock.patch.object(transcription, "_remove_files") as cleanup, \
                mock.patch("builtins.open", mock.mock_open(read_data=big)) as op:
            op.return_value.read.side_effect = [big, b"p1", b"p2"]
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe("/tmp/v.mp4")
        self.assertEqual(ctx.exception.category, "rate_limit")
        self.assertEqual(len(calls), 1, "stops at the first failed piece")
        cleanup.assert_called_once()


def _make_video(path, seconds):
    subprocess.run(
        [transcription._ffmpeg_path(), "-nostdin", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=5",
         "-t", str(seconds), "-shortest", "-c:v", "mpeg4", "-c:a", "aac", path], check=True, capture_output=True)


@mock.patch.object(transcription, "_ffmpeg_path", transcription._ffmpeg_path)  # real lookup, whatever the machine has
class RealFfmpegTests(SimpleTestCase):
    def setUp(self):
        if not HAVE_FFMPEG:
            self.skipTest("no ffmpeg available (system or imageio-ffmpeg)")
        self.dir = tempfile.mkdtemp(prefix="stt-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def test_the_audio_is_pulled_out_of_a_video_as_a_small_mp3(self):
        video = os.path.join(self.dir, "lesson.mp4")
        _make_video(video, 6)
        out, is_temp = transcription._extract_audio(video)
        self.addCleanup(lambda: is_temp and os.path.exists(out) and os.remove(out))
        self.assertTrue(is_temp)
        self.assertTrue(out.endswith(".mp3"))
        self.assertTrue(0 < os.path.getsize(out) < os.path.getsize(video) * 2)

    def test_a_long_recording_is_cut_into_pieces_that_each_fit_the_limit(self):
        video = os.path.join(self.dir, "lesson.mp4")
        _make_video(video, 40)
        audio, is_temp = transcription._extract_audio(video)
        self.assertTrue(is_temp)
        limit = 100_000  # bytes: far below the ~320 KB the 40 s of audio takes, so it must be split
        pieces = transcription._split_audio(audio, limit)
        self.addCleanup(lambda: transcription._remove_files([audio] + [p for p, _ in pieces]))
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(os.path.getsize(p) <= limit for p, _ in pieces))
        offsets = [o for _, o in pieces]
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(len(set(offsets)), len(offsets))

    def test_end_to_end_a_long_video_reaches_the_service_as_pieces_under_the_limit(self):
        video = os.path.join(self.dir, "lesson.mp4")
        _make_video(video, 40)
        sizes = []

        def transport(url, headers, fields, filename, data, timeout):
            sizes.append(len(data))
            return _ok("نص", 10.0, [(0.0, 2.0, "نص")])

        # 0.1 MB limit: the extracted audio (about 320 KB) is over it, so the real splitter has to run
        client = GroqWhisperTranscriber(api_key="gsk_test", transport=transport)
        client._max_upload_bytes = 100_000
        result = client.transcribe(video, "ar")
        self.assertGreater(len(sizes), 1)
        self.assertTrue(all(s <= 100_000 for s in sizes))
        self.assertEqual(result["parts"], len(sizes))
        self.assertEqual(sum(1 for _ in os.listdir(tempfile.gettempdir()) if _.startswith("stt-parts-")), 0,
                         "temporary pieces are removed")
