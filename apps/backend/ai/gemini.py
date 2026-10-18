"""
Gemini adapter for `ai.llm.LLMClient` — the initial DEVELOPMENT provider.

It is an implementation detail behind the Madar-owned interface (ADR-009): it
is not a vendor decision for production (external-interfaces.md keeps vendor
selection deferred), and replacing it means writing another `LLMClient`, not
touching the callers.

Talks to the public REST endpoint `models.generateContent` with the standard
library only — no SDK dependency — so the retry/timeout behaviour is exactly the
one in `ai.llm` and nothing retries behind our back. The API key is sent in the
`x-goog-api-key` header, never in the URL (URLs end up in proxy/server logs).

Unverified against a live account in this phase (no credentials exist in the
repo): the response/error parsing follows Google's published reference and is
covered by mock tests only. See the README section "AI / LLM provider
foundation" for the manual live check.
"""
import email.utils
import http.client
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from django.conf import settings

from .llm import (
    LLMAuthError, LLMBadRequestError, LLMBlockedError, LLMClient, LLMConfigError, LLMNetworkError,
    LLMProviderError, LLMRateLimitError, LLMRequest, LLMResponse, LLMResponseError, LLMSettings,
    LLMTimeoutError, TokenUsage, redact,
)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# The model id is interpolated into the URL path, so only plain id characters
# are accepted (no "/", "?", "#", whitespace ...).
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RETRY_DELAY_RE = re.compile(r"^(\d+(?:\.\d+)?)s$")  # google.rpc.RetryInfo, e.g. "35s"
_MAX_ERROR_CHARS = 200


# --------------------------------------------------------------- transport --
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib follows 301/302/303 by default and re-sends every request header
    — including `x-goog-api-key` — to wherever `Location` points. An API
    endpoint never legitimately redirects, so a redirect is surfaced as an
    error and the key is never sent anywhere else."""

    def redirect_request(self, *args, **kwargs):
        return None


def _urllib_transport(url, headers, payload, timeout):
    """One POST. Returns (status, lower-cased headers, body bytes) for ANY HTTP
    status; raises only for transport-level failures (timeout / network)."""
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, _lower(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:  # non-2xx: still a perfectly good answer
        try:
            body = exc.read()
        except OSError:
            body = b""
        finally:
            exc.close()
        return exc.code, _lower(exc.headers or {}), body
    except TimeoutError as exc:  # socket.timeout is TimeoutError on Python >= 3.10
        raise LLMTimeoutError("The request to the LLM provider timed out.") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise LLMTimeoutError("The request to the LLM provider timed out.") from exc
        raise LLMNetworkError(f"Could not reach the LLM provider ({type(exc.reason).__name__}).") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise LLMNetworkError(f"Connection to the LLM provider failed ({type(exc).__name__}).") from exc


def _lower(headers):
    return {k.lower(): v for k, v in headers.items()}


# ----------------------------------------------------------------- parsing --
def _parse_retry_after(value):
    """Retry-After is delta-seconds or an HTTP-date. -> seconds or None."""
    if value is None:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _parse_error_body(raw):
    """-> (message, status_string, reasons, retry_delay_seconds). Tolerant: an
    error body that is not the expected JSON just yields empty values."""
    try:
        err = json.loads(raw.decode("utf-8", "replace")).get("error", {})
        if not isinstance(err, dict):
            return "", "", set(), None
    except (ValueError, AttributeError):
        return "", "", set(), None
    reasons, retry_delay = set(), None
    details = err.get("details")
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        if isinstance(detail.get("reason"), str):
            reasons.add(detail["reason"])
        match = _RETRY_DELAY_RE.match(str(detail.get("retryDelay", "")))
        if match:
            retry_delay = float(match.group(1))
    message = err.get("message") if isinstance(err.get("message"), str) else ""
    status = err.get("status") if isinstance(err.get("status"), str) else ""
    return message, status, reasons, retry_delay


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class GeminiClient(LLMClient):
    name = "gemini"

    def __init__(self, *, api_key, model, llm_settings=None, transport=None, **kwargs):
        if not (api_key or "").strip():
            raise LLMConfigError("GEMINI_API_KEY is not set.")
        model = (model or "").strip()
        if model.startswith("models/"):
            model = model[len("models/"):]
        if not model:
            raise LLMConfigError(
                "GEMINI_MODEL is not set. Choose a model id from Google's current model list; "
                "none is assumed by default because available models change."
            )
        if not _MODEL_RE.match(model):
            raise LLMConfigError("GEMINI_MODEL contains invalid characters.")
        super().__init__(llm_settings or LLMSettings(), model=model, **kwargs)
        self._api_key = api_key.strip()
        # (url, headers, payload, timeout) -> (status, headers, body). Injected in tests.
        self._transport = transport or _urllib_transport

    @classmethod
    def from_settings(cls):
        return cls(
            api_key=getattr(settings, "GEMINI_API_KEY", ""),
            model=getattr(settings, "GEMINI_MODEL", ""),
            llm_settings=LLMSettings.from_django(),
        )

    def __repr__(self):  # never include the key
        return f"GeminiClient(model={self.model!r})"

    # -------------------------------------------------------------- request --
    def _build_body(self, request: LLMRequest) -> dict:
        body = {"contents": [{"role": "user", "parts": [{"text": request.prompt}]}]}
        if request.system.strip():
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        config = {}
        max_tokens = request.max_output_tokens or self.llm_settings.max_output_tokens
        if max_tokens:
            config["maxOutputTokens"] = max_tokens
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.json_output:
            config["responseMimeType"] = "application/json"
        if config:
            body["generationConfig"] = config
        return body

    def _complete_once(self, request: LLMRequest) -> LLMResponse:
        url = f"{API_BASE}/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}
        try:
            payload = json.dumps(self._build_body(request), ensure_ascii=False).encode("utf-8")
        except (ValueError, TypeError) as exc:  # e.g. a lone surrogate in stored text
            raise LLMBadRequestError("The prompt could not be encoded as UTF-8 text.") from exc
        status, resp_headers, raw = self._transport(url, headers, payload, self.llm_settings.timeout_seconds)
        if status != 200:
            raise self._error_for(status, resp_headers, raw)
        return self._parse(raw)

    # --------------------------------------------------------------- errors --
    def _error_for(self, status, headers, raw):
        message, status_str, reasons, retry_delay = _parse_error_body(raw)
        safe = redact(message, self._api_key)[:_MAX_ERROR_CHARS]
        detail = f"Gemini HTTP {status}" + (f" {status_str}" if status_str else "") + (f": {safe}" if safe else "")

        # Google reports a bad key as 400 + reason API_KEY_INVALID (not 401).
        bad_key = "API_KEY_INVALID" in reasons or "api key not valid" in message.lower()
        if status in (401, 403) or (status == 400 and bad_key):
            return LLMAuthError(detail, status=status)
        if status == 429:
            retry_after = _parse_retry_after(headers.get("retry-after"))
            if retry_after is None:
                retry_after = retry_delay
            return LLMRateLimitError(detail, status=status, retry_after=retry_after)
        if status == 408 or status >= 500:
            return LLMProviderError(detail, status=status, retryable=True)
        if 400 <= status < 500:
            return LLMBadRequestError(detail, status=status)
        return LLMProviderError(detail, status=status)  # 1xx/3xx: unexpected, not retried

    # ------------------------------------------------------------- response --
    def _parse(self, raw) -> LLMResponse:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise LLMResponseError("The LLM provider returned a response that is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise LLMResponseError("The LLM provider returned an unexpected response shape.")

        feedback = data.get("promptFeedback")
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise LLMBlockedError(f"The prompt was blocked by the provider ({feedback['blockReason']}).")

        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            raise LLMResponseError("The LLM provider returned no candidates.")
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        finish = finish if isinstance(finish, str) else ""

        # STOP / MAX_TOKENS are the only normal endings. Anything else (SAFETY,
        # RECITATION, ...) means the output must not be treated as complete.
        if finish not in ("", "STOP", "MAX_TOKENS", "FINISH_REASON_UNSPECIFIED"):
            raise LLMBlockedError(f"The provider stopped generation ({finish}).")

        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        texts = [
            p["text"] for p in (parts if isinstance(parts, list) else [])
            if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")
        ]
        text = "".join(texts)
        if not text.strip():
            if finish == "MAX_TOKENS":
                raise LLMResponseError(
                    "The output limit was reached before any text was produced "
                    "(on some models, thinking tokens count toward the limit). Raise LLM_MAX_OUTPUT_TOKENS."
                )
            raise LLMResponseError("The LLM provider returned an empty response.")

        return LLMResponse(
            text=text, provider=self.name, model=self.model, finish_reason=finish,
            truncated=finish == "MAX_TOKENS", usage=self._usage(data.get("usageMetadata")),
        )

    @staticmethod
    def _usage(meta):
        if not isinstance(meta, dict):
            return None
        return TokenUsage(
            prompt_tokens=_int_or_none(meta.get("promptTokenCount")),
            output_tokens=_int_or_none(meta.get("candidatesTokenCount")),
            total_tokens=_int_or_none(meta.get("totalTokenCount")),
            thinking_tokens=_int_or_none(meta.get("thoughtsTokenCount")),
        )
