"""The transcription key (a Gemini API key): it is read from the environment variable `api_for_transcript` and
nowhere else, it is what authenticates the request (in the `x-goog-api-key` header only), and no real key is written
anywhere in the source. No test here contacts the
transcription service: the transport is a fake, and the settings checks run in a throw-away interpreter."""
import json
import os
import re
import secrets
import string
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from . import transcription
from .transcription import ExternalSTTError, GeminiTranscriber

BACKEND = Path(settings.BASE_DIR)
DUMMY = "dummy-value-used-only-by-this-test-0123456789"
MODEL = "unit-test-model"


def _resolved_setting(**env_vars):
    """What `settings.TRANSCRIPT_API_KEY` resolves to in a fresh interpreter whose environment is exactly: this process's,
    minus both variable names, plus `env_vars`. The project's real .env is still loaded by settings, but a variable
    that is already in the environment (even a blank one) wins over it, so the developer's key never leaks in."""
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ("api_for_transcript", "groq_api_key", "grok_api_key")}
    env.update({"DJANGO_SETTINGS_MODULE": "config.settings", "DJANGO_DEBUG": "True", "DB_USER": "u",
                "DB_PASSWORD": "p", "DB_HOST": "localhost", "api_for_transcript": "", "GROQ_API_KEY": "",
                "GROK_API_KEY": ""})
    env.update(env_vars)
    done = subprocess.run(
        [sys.executable, "-c", "import json; from django.conf import settings; print(json.dumps(settings.TRANSCRIPT_API_KEY))"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-400:]
    return json.loads(done.stdout.strip().splitlines()[-1])


class KeyComesFromTheEnvironmentTests(SimpleTestCase):
    def test_api_for_transcript_is_the_key(self):
        self.assertEqual(_resolved_setting(api_for_transcript=DUMMY), DUMMY)

    def test_the_old_variable_names_are_no_longer_read(self):
        self.assertEqual(_resolved_setting(GROQ_API_KEY="old-name-that-must-be-ignored-0123456789"), "")
        self.assertEqual(_resolved_setting(GROK_API_KEY="old-name-that-must-be-ignored-0123456789"), "")

    def test_the_old_provider_setting_no_longer_exists(self):
        self.assertFalse(hasattr(settings, "GROQ_API_KEY"))
        self.assertEqual(settings.TRANSCRIPTION_PROVIDER, "gemini_audio")

    def test_a_blank_value_means_not_configured(self):
        self.assertEqual(_resolved_setting(api_for_transcript="   "), "")

    def test_the_example_env_documents_the_new_name_and_not_the_old_one(self):
        text = (BACKEND / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^#\s*api_for_transcript=")
        self.assertNotRegex(text, r"(?m)^\s*#?\s*GROQ_API_KEY=")


@override_settings(GEMINI_TRANSCRIBE_MODEL=MODEL, LLM_MAX_RETRIES=0)
class KeyAuthenticatesTheRequestTests(SimpleTestCase):
    def _run(self, transport):
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.write(fd, b"fake-audio-bytes" * 10)
        os.close(fd)
        self.addCleanup(os.remove, path)
        with mock.patch.object(transcription, "_extract_audio", return_value=(path, False)):
            return GeminiTranscriber(transport=transport).transcribe("/tmp/video.mp4", "en")  # key from settings

    @override_settings(TRANSCRIPT_API_KEY=DUMMY)
    def test_the_configured_key_is_the_google_api_key_header_and_goes_nowhere_else(self):
        seen = {}

        def transport(url, headers, payload, timeout):
            seen.update(url=url, headers=headers, payload=payload)
            text = json.dumps({"language": "en", "segments": []})
            body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
            return 200, {}, json.dumps(body).encode()

        self.assertTrue(GeminiTranscriber.is_configured())
        self._run(transport)
        self.assertEqual(seen["headers"]["x-goog-api-key"], DUMMY)
        self.assertEqual(seen["url"], f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent")
        elsewhere = json.dumps([seen["url"], seen["payload"].decode("utf-8"),
                                {k: v for k, v in seen["headers"].items() if k != "x-goog-api-key"}])
        self.assertNotIn(DUMMY, elsewhere, "the key is in the x-goog-api-key header only: not the URL, not the body")

    @override_settings(TRANSCRIPT_API_KEY="")
    def test_without_the_key_nothing_is_sent_and_the_error_names_the_variable(self):
        client = GeminiTranscriber(transport=mock.Mock(side_effect=AssertionError("must not call the service")))
        self.assertFalse(GeminiTranscriber.is_configured())
        with self.assertRaises(ExternalSTTError) as ctx:
            client.transcribe("/tmp/video.mp4")
        self.assertEqual(ctx.exception.category, "config")
        self.assertIn("api_for_transcript", str(ctx.exception))

    @override_settings(TRANSCRIPT_API_KEY=DUMMY)
    def test_the_key_never_reaches_an_error_even_if_the_provider_echoes_it(self):
        def transport(url, headers, payload, timeout):
            body = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": f"API key not valid {DUMMY}",
                              "details": [{"reason": "API_KEY_INVALID"}]}}
            return 400, {}, json.dumps(body).encode()

        with self.assertRaises(ExternalSTTError) as ctx:
            self._run(transport)
        self.assertEqual(ctx.exception.category, "auth")
        self.assertNotIn(DUMMY, str(ctx.exception))


class NoKeyIsWrittenInTheSourceTests(SimpleTestCase):
    """Real keys live in .env (git-ignored) only. Scans everything that could be committed except .env itself."""

    KEY_SHAPES = re.compile(r"AQ\.[A-Za-z0-9_\-]{30,}|gsk_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_\-]{30,}|xai-[A-Za-z0-9]{30,}")
    SKIP = {"venv", "node_modules", "dist", "private-media", "__pycache__", ".git", "media-e2e"}
    EXTENSIONS = {".py", ".js", ".jsx", ".mjs", ".json", ".md", ".txt", ".example", ".yml", ".yaml", ".conf", ".html", ".css"}

    # Test fixtures such as FAKE_KEY = "AIzaSy...abcdefghij..." are obviously made up: they run through the alphabet.
    # A genuine key is random, so six consecutive alphabet letters or digits mark a stand-in, never a real credential.
    RUNS = (string.ascii_lowercase, string.ascii_uppercase, string.digits * 2)

    @classmethod
    def _is_stand_in(cls, text):
        return any(text[i:i + 6] in run for i in range(len(text) - 5) for run in cls.RUNS)

    def test_the_stand_in_filter_never_excuses_a_random_key(self):
        alphabet = string.ascii_letters + string.digits
        for _ in range(2000):
            self.assertFalse(self._is_stand_in("AQ." + "".join(secrets.choice(alphabet) for _ in range(50))))
        self.assertTrue(self._is_stand_in("AIzaSyFAKEKEYabcdefghijklmnopqrstuvwxyz0123456"))

    def test_no_api_key_shaped_text_in_the_project_files(self):
        found = []
        for root, dirs, files in os.walk(BACKEND.parent):  # apps/ : backend + web
            dirs[:] = [d for d in dirs if d not in self.SKIP]
            for name in files:
                path = Path(root, name)
                if name == ".env" or path.suffix not in self.EXTENSIONS or path.stat().st_size > 2_000_000:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if any(not self._is_stand_in(m.group(0)) for m in self.KEY_SHAPES.finditer(text)):
                    found.append(str(path.relative_to(BACKEND.parent)))
        self.assertEqual(found, [], "an API-key-shaped string is written in a source file")
