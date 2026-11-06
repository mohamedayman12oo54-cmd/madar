"""Getting the audio ready for Gemini: where ffmpeg comes from, what happens when it is missing or fails, how a long
recording is cut into pieces, and that nothing is left on disk. No test here calls Gemini: the transport is always a
fake. The tests that run a real ffmpeg are skipped on a machine that has none. (The pieces-and-stitching behaviour of
the transcriber itself is in test_gemini_transcriber.)"""
import os
import subprocess
import tempfile
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import transcription
from .transcription import ExternalSTTError, GeminiTranscriber

HAVE_FFMPEG = bool(transcription._ffmpeg_path())
NO_NETWORK_CALL = mock.Mock(side_effect=AssertionError("the transcription service must not be called"))


def _leftovers():
    """Temp files/folders this module's code creates; a test compares before and after."""
    return {n for n in os.listdir(tempfile.gettempdir()) if n.startswith("stt-")}


def _private_tempdir(case):
    """Make this test's temp folder its own, so the "nothing left behind" checks cannot be fooled by other tests
    (or other test processes) writing `stt-*` files to the shared system temp folder at the same time."""
    folder = tempfile.mkdtemp(prefix="stt-isolated-")
    previous = tempfile.tempdir
    tempfile.tempdir = folder

    def restore():
        tempfile.tempdir = previous
        __import__("shutil").rmtree(folder, ignore_errors=True)

    case.addCleanup(restore)


# ------------------------------------------------------------------------------------- finding ffmpeg
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


# ------------------------------------------------------------------------------------- extraction (mocked ffmpeg)
@override_settings(TRANSCRIPT_API_KEY="", GEMINI_MODEL="unit-test-model")
class ExtractionFailureTests(SimpleTestCase):
    """The original video is NEVER used as a stand-in for audio that could not be extracted."""

    def setUp(self):
        _private_tempdir(self)

    def _video(self):
        folder = tempfile.mkdtemp(prefix="secret-folder-")
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        path = os.path.join(folder, "lesson.mp4")
        open(path, "wb").write(b"not really a video")
        return path

    def test_missing_ffmpeg_is_a_specific_error_and_nothing_is_sent(self):
        client = GeminiTranscriber(api_key="unit-test-key", model="unit-test-model", transport=NO_NETWORK_CALL)
        with mock.patch.object(transcription, "_ffmpeg_path", return_value=None):
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe(self._video())
        self.assertEqual(ctx.exception.category, "no_ffmpeg")

    def test_failed_extraction_is_extract_failed_with_a_sanitised_diagnostic(self):
        video = self._video()
        stderr = (f"{video}: Invalid data found when processing input\n"
                  f"Error opening input file {video}.\nError opening input files: Invalid data").encode()
        before = _leftovers()
        client = GeminiTranscriber(api_key="unit-test-key", model="unit-test-model", transport=NO_NETWORK_CALL)
        with mock.patch.object(transcription, "_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(transcription.subprocess, "run",
                                  return_value=subprocess.CompletedProcess([], 1, b"", stderr)):
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe(video)
        err = ctx.exception
        self.assertEqual(err.category, "extract_failed")
        self.assertIn("Invalid data found", str(err))                        # the useful part is kept
        self.assertIn("<input>", str(err))                                    # the location is replaced
        self.assertNotIn("secret-folder", str(err))
        self.assertNotIn("\n", str(err))
        self.assertEqual(_leftovers(), before, "the half-made mp3 is removed")

    def test_the_diagnostic_is_short_even_when_ffmpeg_is_chatty(self):
        text = transcription._ffmpeg_diagnostic(b"x" * 5000 + b"\nreal problem", "/a/b/in.mp4", "/a/b/out.mp3")
        self.assertLessEqual(len(text), 300)
        self.assertTrue(text.endswith("real problem"))

    def test_a_timeout_and_an_unstartable_ffmpeg_are_both_extract_failed(self):
        for failure, wording in ((subprocess.TimeoutExpired("ffmpeg", 600), "stopped"), (OSError("boom"), "could not be started")):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(transcription, "_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
                        mock.patch.object(transcription.subprocess, "run", side_effect=failure):
                    with self.assertRaises(ExternalSTTError) as ctx:
                        transcription._extract_audio(self._video())
                self.assertEqual(ctx.exception.category, "extract_failed")
                self.assertIn(wording, str(ctx.exception))

    def test_ffmpeg_that_exits_cleanly_but_wrote_nothing_is_extract_failed(self):
        before = _leftovers()
        with mock.patch.object(transcription, "_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(transcription.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")):
            with self.assertRaises(ExternalSTTError) as ctx:
                transcription._extract_audio(self._video())
        self.assertEqual(ctx.exception.category, "extract_failed")
        self.assertEqual(_leftovers(), before)

    def test_splitting_without_ffmpeg_says_so(self):
        with mock.patch.object(transcription, "_ffmpeg_path", return_value=None):
            with self.assertRaises(ExternalSTTError) as ctx:
                transcription._split_audio("/tmp/a.mp3", 60, 1000)
        self.assertEqual(ctx.exception.category, "no_ffmpeg")

    def test_a_failed_split_is_split_failed_and_leaves_no_folder(self):
        before = _leftovers()
        with mock.patch.object(transcription, "_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(transcription.subprocess, "run",
                                  return_value=subprocess.CompletedProcess([], 1, b"", b"Invalid data found")):
            with self.assertRaises(ExternalSTTError) as ctx:
                transcription._split_audio("/tmp/a.mp3", 60, 1000)
        self.assertEqual(ctx.exception.category, "split_failed")
        self.assertEqual(_leftovers(), before)


# ------------------------------------------------------------------------------------- real ffmpeg
def _make_video(path, seconds, audio=True):
    cmd = [transcription._ffmpeg_path(), "-nostdin", "-y", "-v", "error"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000"]
    cmd += ["-f", "lavfi", "-i", "color=c=blue:s=64x64:r=5", "-t", str(seconds)]
    cmd += (["-shortest", "-c:v", "mpeg4", "-c:a", "aac"] if audio else ["-c:v", "mpeg4"]) + [path]
    subprocess.run(cmd, check=True, capture_output=True)


@override_settings(TRANSCRIPT_API_KEY="", GEMINI_MODEL="unit-test-model")
class RealFfmpegTests(SimpleTestCase):
    def setUp(self):
        if not HAVE_FFMPEG:
            self.skipTest("no ffmpeg available (system or imageio-ffmpeg)")
        _private_tempdir(self)
        self.dir = tempfile.mkdtemp(prefix="stt-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.before = _leftovers() - {os.path.basename(self.dir)}

    def _file(self, name, content=None):
        path = os.path.join(self.dir, name)
        if content is not None:
            open(path, "wb").write(content)
        return path

    def _no_new_leftovers(self):
        self.assertEqual(_leftovers() - {os.path.basename(self.dir)}, self.before, "temp files were left behind")

    # --- extraction
    def test_short_valid_video_becomes_one_small_mp3(self):
        video = self._file("lesson.mp4")
        _make_video(video, 6)
        audio, is_temp = transcription._extract_audio(video)
        self.addCleanup(lambda: os.path.exists(audio) and os.remove(audio))
        data = open(audio, "rb").read()
        self.assertTrue(is_temp)
        self.assertTrue(data[:3] == b"ID3" or data[0] == 0xFF, "an mp3, not the video")
        self.assertLess(len(data), transcription._MAX_PIECE_BYTES)

    def test_the_audio_settings_are_mono_16khz_and_compressed(self):
        video = self._file("lesson.mp4")
        _make_video(video, 4)
        audio, is_temp = transcription._extract_audio(video)
        self.addCleanup(lambda: os.path.exists(audio) and os.remove(audio))
        self.assertTrue(is_temp and audio.endswith(".mp3"))
        info = subprocess.run([transcription._ffmpeg_path(), "-i", audio], capture_output=True, text=True).stderr
        self.assertIn("mono", info)
        self.assertIn("16000 Hz", info)
        self.assertIn("64 kb/s", info)

    def test_corrupt_unsupported_and_silent_media_are_extract_failed_and_leave_nothing(self):
        silent = self._file("silent.mp4")
        _make_video(silent, 2, audio=False)
        cases = {
            "corrupted video": self._file("broken.mp4", os.urandom(4096)),
            "not media at all": self._file("notes.txt", b"hello, this is not a video"),
            "video with no audio track": silent,
        }
        for label, path in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ExternalSTTError) as ctx:
                    GeminiTranscriber(api_key="unit-test-key", model="unit-test-model", transport=NO_NETWORK_CALL).transcribe(path)
                self.assertEqual(ctx.exception.category, "extract_failed")
                self.assertNotIn(self.dir, str(ctx.exception), "no server path in the diagnostic")
        self._no_new_leftovers()

    # --- splitting
    def test_a_long_recording_is_cut_into_ordered_pieces_of_the_requested_length(self):
        video = self._file("lesson.mp4")
        _make_video(video, 40)
        audio, _ = transcription._extract_audio(video)
        pieces = transcription._split_audio(audio, 15, 10_000_000)
        self.addCleanup(lambda: transcription._remove_files([audio] + [p for p, _ in pieces]))
        self.assertEqual([o for _, o in pieces], [0, 15, 30], "40 s cut every 15 s -> 3 pieces at their real offsets")
        sizes = [os.path.getsize(p) for p, _ in pieces]
        self.assertTrue(all(s > 0 for s in sizes))
        self.assertLessEqual(sum(sizes), os.path.getsize(audio) * 1.05, "stream copy: no re-encoding, nothing duplicated")

    def test_a_piece_that_cannot_fit_is_split_failed_and_leaves_nothing(self):
        video = self._file("lesson.mp4")
        _make_video(video, 6)
        audio, _ = transcription._extract_audio(video)
        self.addCleanup(lambda: os.path.exists(audio) and os.remove(audio))
        before = _leftovers()
        with self.assertRaises(ExternalSTTError) as ctx:
            transcription._split_audio(audio, 3, 1)  # no piece can be under 1 byte
        self.assertEqual(ctx.exception.category, "split_failed")
        self.assertEqual(_leftovers(), before)
