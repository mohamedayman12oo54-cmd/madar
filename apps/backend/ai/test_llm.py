"""LLM client foundation (ai/llm.py + ai/gemini.py + check_llm_provider).

Everything here runs against an injected fake transport: no external network,
no paid request, no free-tier quota consumed, and no database. (One regression
test starts two throw-away HTTP servers on 127.0.0.1 only.)"""
import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from . import gemini
from .gemini import GeminiClient
from .llm import (
    LLMAuthError, LLMBadRequestError, LLMBlockedError, LLMClient, LLMConfigError, LLMError,
    LLMNetworkError, LLMProviderError, LLMRateLimitError, LLMRequest, LLMResponseError,
    LLMSettings, LLMTimeoutError, get_llm_client, redact,
)

# Shaped like a real Google key on purpose, so the redaction tests are honest.
FAKE_KEY = "AIzaSyFAKE-KEY-FOR-TESTS-0123456789abcd"
MODEL = "test-model"


def ok(text="pong", *, finish="STOP", usage=True, parts=None, extra=None):
    body = {"candidates": [{
        "content": {"role": "model", "parts": parts if parts is not None else [{"text": text}]},
        "finishReason": finish,
    }]}
    if usage:
        body["usageMetadata"] = {"promptTokenCount": 7, "candidatesTokenCount": 2, "totalTokenCount": 9}
    body.update(extra or {})
    return 200, {}, json.dumps(body).encode()


def err(status, message="boom", *, status_str="", headers=None, details=None):
    body = {"error": {"code": status, "message": message, "status": status_str, "details": details or []}}
    return status, headers or {}, json.dumps(body).encode()


class FakeTransport:
    """Plays back one outcome per call; an exception instance is raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        assert self.outcomes, "transport called more often than the test expected"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def last_body(self):
        return json.loads(self.calls[-1]["payload"].decode("utf-8"))


def make(*outcomes, **cfg):
    transport = FakeTransport(*outcomes)
    sleeps = []
    client = GeminiClient(
        api_key=FAKE_KEY, model=MODEL, llm_settings=LLMSettings(**cfg),
        transport=transport, sleep=sleeps.append, random_fn=lambda: 1.0,  # jitter off: full delay
    )
    return client, transport, sleeps


REQ = LLMRequest(prompt="hello")


class ConfigurationTests(SimpleTestCase):
    @override_settings(
        LLM_PROVIDER="gemini", GEMINI_API_KEY=FAKE_KEY, GEMINI_MODEL="models/some-model",
        LLM_TIMEOUT_SECONDS=15, LLM_MAX_OUTPUT_TOKENS=512, LLM_MAX_RETRIES=1,
        LLM_RETRY_BASE_SECONDS=2, LLM_RETRY_MAX_WAIT_SECONDS=9,
    )
    def test_configuration_loads_from_settings(self):
        client = get_llm_client()
        self.assertIsInstance(client, GeminiClient)
        self.assertEqual(client.model, "some-model")  # "models/" prefix is normalised
        self.assertEqual(client.llm_settings, LLMSettings(15, 512, 1, 2, 9))

    @override_settings(GEMINI_API_KEY=FAKE_KEY, GEMINI_MODEL="m", LLM_MAX_OUTPUT_TOKENS=0)
    def test_zero_max_output_tokens_means_provider_default(self):
        self.assertIsNone(LLMSettings.from_django().max_output_tokens)

    @override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="", GEMINI_MODEL="m")
    def test_missing_api_key_is_a_config_error_before_any_request(self):
        with mock.patch.object(urllib.request.OpenerDirector, "open") as opened:
            with self.assertRaises(LLMConfigError) as ctx:
                get_llm_client()
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))
        opened.assert_not_called()

    @override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY=FAKE_KEY, GEMINI_MODEL="")
    def test_model_has_no_hidden_default(self):
        with self.assertRaises(LLMConfigError) as ctx:
            get_llm_client()
        self.assertIn("GEMINI_MODEL", str(ctx.exception))
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_unknown_provider_fails_loudly(self):
        with override_settings(LLM_PROVIDER="nope"):
            with self.assertRaises(LLMConfigError):
                get_llm_client()

    def test_invalid_values_are_rejected(self):
        for kwargs in ({"timeout_seconds": 0}, {"max_retries": -1}, {"max_retries": 6},
                       {"retry_base_seconds": -1}, {"max_output_tokens": -5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(LLMConfigError):
                LLMSettings(**kwargs)

    def test_model_id_cannot_inject_into_the_url_path(self):
        for bad in ("a/b", "a?x=1", "a b", "../x", "a#b"):
            with self.subTest(model=bad), self.assertRaises(LLMConfigError):
                GeminiClient(api_key=FAKE_KEY, model=bad)

    def test_repr_never_contains_the_key(self):
        client, *_ = make(ok())
        self.assertNotIn(FAKE_KEY, repr(client))
        self.assertNotIn(FAKE_KEY, repr(client.llm_settings))


class RequestConstructionTests(SimpleTestCase):
    def test_url_headers_and_body(self):
        client, transport, _ = make(ok(), timeout_seconds=12)
        client.complete(LLMRequest(prompt="مرحبا hello", system="be brief", max_output_tokens=50, temperature=0.2))
        call = transport.calls[0]
        self.assertEqual(
            call["url"], f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent")
        self.assertEqual(call["headers"]["x-goog-api-key"], FAKE_KEY)
        self.assertEqual(call["timeout"], 12)
        self.assertEqual(transport.last_body, {
            "contents": [{"role": "user", "parts": [{"text": "مرحبا hello"}]}],
            "systemInstruction": {"parts": [{"text": "be brief"}]},
            "generationConfig": {"maxOutputTokens": 50, "temperature": 0.2},
        })

    def test_the_key_is_in_a_header_only_never_in_url_or_body(self):
        client, transport, _ = make(ok())
        client.complete(REQ)
        call = transport.calls[0]
        self.assertNotIn(FAKE_KEY, call["url"])
        self.assertNotIn(FAKE_KEY, call["payload"].decode("utf-8"))

    def test_optional_parts_are_omitted_when_unset(self):
        client, transport, _ = make(ok())
        client.complete(REQ)
        self.assertEqual(transport.last_body, {"contents": [{"role": "user", "parts": [{"text": "hello"}]}]})

    def test_configured_output_limit_is_the_default_and_the_request_overrides_it(self):
        client, transport, _ = make(ok(), ok(), max_output_tokens=100)
        client.complete(REQ)
        self.assertEqual(transport.last_body["generationConfig"], {"maxOutputTokens": 100})
        client.complete(LLMRequest(prompt="x", max_output_tokens=7))
        self.assertEqual(transport.last_body["generationConfig"], {"maxOutputTokens": 7})

    def test_invalid_requests_are_rejected_locally(self):
        for kwargs in ({"prompt": ""}, {"prompt": "   "}, {"prompt": "x", "max_output_tokens": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(LLMBadRequestError):
                LLMRequest(**kwargs)


class ResponseNormalisationTests(SimpleTestCase):
    def test_success_is_normalised(self):
        client, _, _ = make(ok("hello world"))
        r = client.complete(REQ)
        self.assertEqual((r.text, r.provider, r.model), ("hello world", "gemini", MODEL))
        self.assertEqual((r.finish_reason, r.truncated, r.attempts), ("STOP", False, 1))
        self.assertGreaterEqual(r.latency_ms, 0)

    def test_multiple_text_parts_are_joined_and_thought_parts_dropped(self):
        client, _, _ = make(ok(parts=[{"text": "secret reasoning", "thought": True}, {"text": "A"}, {"text": "B"}]))
        self.assertEqual(client.complete(REQ).text, "AB")

    def test_token_usage_is_preserved(self):
        usage = make(ok())[0].complete(REQ).usage
        self.assertEqual((usage.prompt_tokens, usage.output_tokens, usage.total_tokens), (7, 2, 9))
        self.assertIsNone(usage.thinking_tokens)

    def test_thinking_tokens_are_exposed_when_reported(self):
        body = {"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 10,
                                  "thoughtsTokenCount": 7}}
        usage = make((200, {}, json.dumps(body).encode()))[0].complete(REQ).usage
        self.assertEqual(usage.thinking_tokens, 7)

    def test_missing_usage_is_none_not_an_error(self):
        self.assertIsNone(make(ok(usage=False))[0].complete(REQ).usage)

    def test_output_cut_by_the_limit_is_flagged_not_silently_returned_as_complete(self):
        r = make(ok("partial", finish="MAX_TOKENS"))[0].complete(REQ)
        self.assertTrue(r.truncated)
        self.assertEqual(r.finish_reason, "MAX_TOKENS")


class MalformedResponseTests(SimpleTestCase):
    def assert_response_error(self, outcome, exc_type=LLMResponseError):
        client, transport, sleeps = make(outcome)
        with self.assertRaises(exc_type):
            client.complete(REQ)
        self.assertEqual((len(transport.calls), sleeps), (1, []))  # a bad answer is never retried

    def test_not_json(self):
        self.assert_response_error((200, {}, b"<html>oops</html>"))

    def test_invalid_utf8(self):
        self.assert_response_error((200, {}, b"\xff\xfe\x00"))

    def test_json_but_not_an_object(self):
        self.assert_response_error((200, {}, b"[1, 2, 3]"))

    def test_missing_or_empty_candidates(self):
        self.assert_response_error((200, {}, b"{}"))
        self.assert_response_error((200, {}, b'{"candidates": []}'))
        self.assert_response_error((200, {}, b'{"candidates": ["x"]}'))

    def test_empty_or_wrongly_typed_text(self):
        self.assert_response_error(ok(parts=[]))
        self.assert_response_error(ok(parts=[{"text": "   "}]))
        self.assert_response_error(ok(parts=[{"text": 123}]))
        self.assert_response_error(ok(parts="nope"))

    def test_max_tokens_with_no_text_explains_itself(self):
        client, *_ = make(ok(parts=[], finish="MAX_TOKENS"))
        with self.assertRaises(LLMResponseError) as ctx:
            client.complete(REQ)
        self.assertIn("LLM_MAX_OUTPUT_TOKENS", str(ctx.exception))

    def test_blocked_prompt(self):
        self.assert_response_error(
            (200, {}, json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}).encode()), LLMBlockedError)

    def test_generation_stopped_by_safety_is_not_treated_as_complete(self):
        self.assert_response_error(ok("half an answer", finish="SAFETY"), LLMBlockedError)

    def test_malformed_usage_does_not_crash(self):
        client, *_ = make(ok(extra={"usageMetadata": {"promptTokenCount": "many", "totalTokenCount": True}}))
        usage = client.complete(REQ).usage
        self.assertIsNone(usage.prompt_tokens)
        self.assertIsNone(usage.total_tokens)

    def test_unparseable_error_body_still_maps_by_status(self):
        client, *_ = make((400, {}, b"not json at all"))
        with self.assertRaises(LLMBadRequestError):
            client.complete(REQ)


class AuthenticationErrorTests(SimpleTestCase):
    def assert_auth_failure_not_retried(self, outcome):
        client, transport, sleeps = make(outcome, max_retries=3)
        with self.assertRaises(LLMAuthError) as ctx:
            client.complete(REQ)
        self.assertEqual((len(transport.calls), sleeps), (1, []))
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(ctx.exception.category, "auth")

    def test_401_and_403(self):
        self.assert_auth_failure_not_retried(err(401, "bad creds", status_str="UNAUTHENTICATED"))
        self.assert_auth_failure_not_retried(err(403, "no access", status_str="PERMISSION_DENIED"))

    def test_google_reports_an_invalid_key_as_400(self):
        self.assert_auth_failure_not_retried(err(
            400, "API key not valid. Please pass a valid API key.", status_str="INVALID_ARGUMENT",
            details=[{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]))

    def test_other_4xx_is_a_bad_request_not_auth_and_not_retried(self):
        for status in (400, 404):
            client, transport, sleeps = make(err(status, "model not found"), max_retries=3)
            with self.assertRaises(LLMBadRequestError):
                client.complete(REQ)
            self.assertEqual((len(transport.calls), sleeps), (1, []))


class RateLimitAndRetryTests(SimpleTestCase):
    def test_rate_limit_then_success_honours_retry_after_header(self):
        client, transport, sleeps = make(err(429, "slow down", headers={"retry-after": "7"}), ok())
        r = client.complete(REQ)
        self.assertEqual((r.text, r.attempts, len(transport.calls)), ("pong", 2, 2))
        self.assertEqual(sleeps, [7.0])

    def test_retry_after_http_date_is_understood(self):
        import time
        from email.utils import formatdate
        header = formatdate(time.time() + 20, usegmt=True)
        client, _, sleeps = make(err(429, headers={"retry-after": header}), ok(), retry_max_wait_seconds=60)
        client.complete(REQ)
        self.assertEqual(len(sleeps), 1)
        self.assertTrue(15 <= sleeps[0] <= 21, sleeps)

    def test_retry_info_in_the_body_is_used_when_there_is_no_header(self):
        details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "3s"}]
        client, _, sleeps = make(err(429, "quota", status_str="RESOURCE_EXHAUSTED", details=details), ok())
        client.complete(REQ)
        self.assertEqual(sleeps, [3.0])

    def test_retry_after_longer_than_the_cap_fails_fast_without_sleeping(self):
        client, transport, sleeps = make(err(429, headers={"retry-after": "3600"}), retry_max_wait_seconds=30)
        with self.assertRaises(LLMRateLimitError) as ctx:
            client.complete(REQ)
        self.assertEqual((len(transport.calls), sleeps), (1, []))
        self.assertEqual(ctx.exception.retry_after, 3600.0)  # the caller can still see what was asked

    def test_retries_are_bounded(self):
        client, transport, sleeps = make(err(429), err(429), err(429), err(429), max_retries=2)
        with self.assertRaises(LLMRateLimitError) as ctx:
            client.complete(REQ)
        self.assertEqual(len(transport.calls), 3)  # 1 try + 2 retries, never more
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertEqual(len(sleeps), 2)

    def test_max_retries_zero_means_a_single_attempt(self):
        client, transport, sleeps = make(err(503), max_retries=0)
        with self.assertRaises(LLMProviderError):
            client.complete(REQ)
        self.assertEqual((len(transport.calls), sleeps), (1, []))

    def test_backoff_is_exponential_and_capped(self):
        client, _, sleeps = make(err(503), err(503), err(503), err(503), ok(),
                                 max_retries=4, retry_base_seconds=1, retry_max_wait_seconds=3)
        client.complete(REQ)
        self.assertEqual(sleeps, [1.0, 2.0, 3.0, 3.0])  # 1, 2, 4->capped 3, 8->capped 3

    def test_jitter_stays_within_half_to_full_delay(self):
        transport = FakeTransport(err(503), ok())
        sleeps = []
        client = GeminiClient(api_key=FAKE_KEY, model=MODEL, llm_settings=LLMSettings(retry_base_seconds=4),
                              transport=transport, sleep=sleeps.append, random_fn=lambda: 0.0)
        client.complete(REQ)
        self.assertEqual(sleeps, [2.0])

    def test_5xx_and_408_are_retried(self):
        for status in (500, 503, 504, 408):
            with self.subTest(status=status):
                client, transport, _ = make(err(status), ok())
                self.assertEqual(client.complete(REQ).attempts, 2)

    def test_unexpected_status_is_not_retried(self):
        client, transport, _ = make((302, {}, b""))
        with self.assertRaises(LLMProviderError):
            client.complete(REQ)
        self.assertEqual(len(transport.calls), 1)


class TransportFailureTests(SimpleTestCase):
    def test_timeout_then_success(self):
        client, _, sleeps = make(LLMTimeoutError("t"), ok())
        self.assertEqual(client.complete(REQ).attempts, 2)
        self.assertEqual(len(sleeps), 1)

    def test_persistent_network_failure_surfaces_a_normalised_error(self):
        client, transport, _ = make(LLMNetworkError("n"), LLMNetworkError("n"), LLMNetworkError("n"), max_retries=2)
        with self.assertRaises(LLMNetworkError) as ctx:
            client.complete(REQ)
        self.assertEqual((len(transport.calls), ctx.exception.category), (3, "network"))

    def test_default_transport_maps_socket_timeout(self):
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=socket.timeout("timed out")):
            with self.assertRaises(LLMTimeoutError):
                gemini._urllib_transport("https://x", {}, b"{}", 1)

    def test_default_transport_maps_wrapped_timeout_and_connection_errors(self):
        with mock.patch.object(urllib.request.OpenerDirector, "open",
                               side_effect=urllib.error.URLError(socket.timeout("timed out"))):
            with self.assertRaises(LLMTimeoutError):
                gemini._urllib_transport("https://x", {}, b"{}", 1)
        with mock.patch.object(urllib.request.OpenerDirector, "open",
                               side_effect=urllib.error.URLError(ConnectionRefusedError())):
            with self.assertRaises(LLMNetworkError):
                gemini._urllib_transport("https://x", {}, b"{}", 1)
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=ConnectionResetError()):
            with self.assertRaises(LLMNetworkError):
                gemini._urllib_transport("https://x", {}, b"{}", 1)

    def test_default_transport_returns_http_errors_as_data(self):
        http_error = urllib.error.HTTPError(
            "https://x", 429, "Too Many", {"Retry-After": "5"}, StringIO('{"error": {}}'))
        http_error.read = lambda: b'{"error": {}}'
        with mock.patch.object(urllib.request.OpenerDirector, "open", side_effect=http_error):
            status, headers, body = gemini._urllib_transport("https://x", {}, b"{}", 1)
        self.assertEqual((status, headers["retry-after"], body), (429, "5", b'{"error": {}}'))


class ReviewRegressionTests(SimpleTestCase):
    """Defects found when the foundation was independently reviewed."""

    def test_redirect_never_forwards_the_api_key_to_another_host(self):
        seen = {}

        class Target(BaseHTTPRequestHandler):
            def _record(self):
                seen["key"] = self.headers.get("x-goog-api-key")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            do_GET = do_POST = _record

            def log_message(self, *args):
                pass

        target = HTTPServer(("127.0.0.1", 0), Target)

        class Redirector(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("content-length", 0)))
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/elsewhere")
                self.end_headers()

            def log_message(self, *args):
                pass

        redirector = HTTPServer(("127.0.0.1", 0), Redirector)
        for server in (target, redirector):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

        status, _, _ = gemini._urllib_transport(
            f"http://127.0.0.1:{redirector.server_port}/", {"x-goog-api-key": FAKE_KEY}, b"{}", 5)
        self.assertEqual(status, 302)          # surfaced, not followed
        self.assertNotIn("key", seen)          # the redirect target was never contacted

    def test_a_redirect_is_an_unretried_provider_error(self):
        client, transport, sleeps = make((302, {}, b""), max_retries=3)
        with self.assertRaises(LLMProviderError):
            client.complete(REQ)
        self.assertEqual((len(transport.calls), sleeps), (1, []))

    def test_malformed_error_details_do_not_crash(self):
        for details in (5, "x", {"a": 1}, [1, "x", None]):
            with self.subTest(details=details):
                body = json.dumps({"error": {"message": "m", "details": details}}).encode()
                client, *_ = make((400, {}, body))
                with self.assertRaises(LLMBadRequestError):
                    client.complete(REQ)

    def test_unencodable_prompt_is_a_normalised_error_and_nothing_is_sent(self):
        client, transport, _ = make(ok())
        with self.assertRaises(LLMBadRequestError):
            client.complete(LLMRequest(prompt="broken \ud800 text"))
        self.assertEqual(transport.calls, [])


class SecretHandlingTests(SimpleTestCase):
    def test_a_provider_that_echoes_the_key_never_leaks_it(self):
        client, *_ = make(err(400, f"invalid argument for key {FAKE_KEY}"))
        with self.assertLogs("ai", level="DEBUG") as logs:
            with self.assertRaises(LLMError) as ctx:
                client.complete(REQ)
        everything = str(ctx.exception) + repr(ctx.exception) + "\n".join(logs.output)
        self.assertNotIn(FAKE_KEY, everything)
        self.assertIn("[redacted]", str(ctx.exception))

    def test_a_key_we_were_not_told_about_is_masked_by_shape(self):
        self.assertNotIn("AIzaSyOTHER-KEY-0123456789abcdefgh", redact("x AIzaSyOTHER-KEY-0123456789abcdefgh y"))

    def test_provider_message_length_is_bounded(self):
        client, *_ = make(err(400, "x" * 5000))
        with self.assertRaises(LLMBadRequestError) as ctx:
            client.complete(REQ)
        self.assertLess(len(str(ctx.exception)), 300)

    def test_logs_carry_metadata_only_not_prompt_or_response_text(self):
        client, *_ = make(err(503), ok("THE-MODEL-ANSWER"))
        with self.assertLogs("ai", level="DEBUG") as logs:
            client.complete(LLMRequest(prompt="THE-STUDENT-LESSON-TEXT"))
        joined = "\n".join(logs.output)
        self.assertNotIn("THE-STUDENT-LESSON-TEXT", joined)
        self.assertNotIn("THE-MODEL-ANSWER", joined)
        self.assertNotIn(FAKE_KEY, joined)
        self.assertIn("attempts=2", joined)


class AdapterContractTests(SimpleTestCase):
    def test_base_client_is_an_interface(self):
        with self.assertRaises(NotImplementedError):
            LLMClient(LLMSettings(), model="m").complete(REQ)

    def test_llm_errors_are_not_ai_provider_errors(self):
        """The worker shows AIProviderError messages to end users; provider and
        network details must never take that path."""
        from .providers import AIProviderError
        self.assertFalse(issubclass(LLMError, AIProviderError))


@override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY=FAKE_KEY, GEMINI_MODEL=MODEL)
class CheckCommandTests(SimpleTestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("check_llm_provider", *args, stdout=out)
        return out.getvalue()

    def test_config_only_makes_no_request_and_hides_the_key(self):
        with mock.patch.object(urllib.request.OpenerDirector, "open") as opened:
            out = self.run_command("--config-only")
        opened.assert_not_called()
        self.assertIn(MODEL, out)
        self.assertIn("No request was sent", out)
        self.assertNotIn(FAKE_KEY, out)

    def test_success_reports_tokens_and_hides_the_key(self):
        client, transport, _ = make(ok("pong"))
        with mock.patch("ai.management.commands.check_llm_provider.get_llm_client", return_value=client):
            out = self.run_command()
        self.assertIn("Connectivity OK", out)
        self.assertIn("prompt=7 output=2 total=9", out)
        self.assertNotIn(FAKE_KEY, out)
        self.assertEqual(transport.last_body["contents"][0]["parts"][0]["text"], "Reply with the single word: pong")

    def test_failure_is_a_clear_command_error_without_the_key(self):
        client, *_ = make(err(403, f"denied for {FAKE_KEY}"))
        with mock.patch("ai.management.commands.check_llm_provider.get_llm_client", return_value=client):
            with self.assertRaises(CommandError) as ctx:
                self.run_command()
        self.assertIn("FAILED [auth]", str(ctx.exception))
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    @override_settings(GEMINI_API_KEY="")
    def test_missing_configuration_fails_clearly(self):
        with self.assertRaises(CommandError) as ctx:
            self.run_command()
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))
