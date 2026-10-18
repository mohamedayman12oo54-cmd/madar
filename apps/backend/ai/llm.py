"""
Madar-owned LLM client boundary (docs: ADR-002, ADR-009,
07-contracts/external-interfaces.md — "modules depend on the Madar contract,
not the provider API").

This is the LOW-LEVEL seam: "send text, get text back, plus honest metadata".
It deliberately knows nothing about quizzes, tutors or prompts — that is the
job of the domain-level `ai.providers.AIProvider` (which a later phase will
implement on top of an `LLMClient`). Nothing in the product calls this module
yet; it only establishes the integration foundation.

    domain provider (later)  ->  LLMClient.complete(LLMRequest)  ->  adapter  ->  vendor API
                                 \\_ retries, backoff, normalised errors live here

Guarantees every adapter inherits:
- ONE error family (`LLMError` and subclasses) with a stable `category`, so
  callers can react without parsing provider-specific messages.
- Bounded retries ONLY for transient failures (rate limit, timeout, network,
  5xx). Exponential backoff with jitter; a provider-supplied Retry-After wins
  and is never exceeded silently — if it is longer than the configured cap the
  call fails fast instead of parking a worker for minutes/hours.
- No secrets and no lesson/student content in logs or error messages.
- No silent truncation: a response cut short by the output limit is flagged
  (`LLMResponse.truncated`), never returned as if it were complete.

`LLMError` is intentionally NOT an `AIProviderError`: the worker shows the
message of an `AIProviderError` to the end user, and provider/network details
must never reach a student. The domain provider (next phase) decides what
user-safe message to raise.
"""
import logging
import random
import re
import time
from dataclasses import dataclass, replace

from django.conf import settings
from django.utils.module_loading import import_string

log = logging.getLogger(__name__)

# Defence in depth for error messages / logs: Google API keys have a fixed
# shape, so even a key we were never told about is masked if a provider echoes
# one back.
_GOOGLE_KEY_RE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")


def redact(text, *secrets):
    """Mask known secrets (and anything shaped like a Google API key)."""
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return _GOOGLE_KEY_RE.sub("[redacted]", text)


# ------------------------------------------------------------------ errors --
class LLMError(Exception):
    """Base of every failure surfaced by an LLM client.

    `category` is stable and machine-readable (log it, branch on it).
    `retryable` says whether repeating the SAME request can plausibly succeed.
    `retry_after` is the provider's requested wait in seconds, when it gave one.
    """

    category = "error"
    retryable = False

    def __init__(self, message, *, status=None, retry_after=None, retryable=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.attempts = 1
        if retryable is not None:
            self.retryable = retryable


class LLMConfigError(LLMError):
    """Missing/invalid configuration. Raised before any network call."""
    category = "config"


class LLMAuthError(LLMError):
    """Credentials missing, invalid, or without access. Never retried."""
    category = "auth"


class LLMRateLimitError(LLMError):
    """Provider rate/quota limit hit (HTTP 429)."""
    category = "rate_limit"
    retryable = True


class LLMTimeoutError(LLMError):
    category = "timeout"
    retryable = True


class LLMNetworkError(LLMError):
    category = "network"
    retryable = True


class LLMProviderError(LLMError):
    """Provider-side failure (5xx). Retryable only when the adapter says so."""
    category = "provider"


class LLMBadRequestError(LLMError):
    """The provider rejected the request (4xx other than auth/rate limit),
    e.g. an unknown model or invalid parameters. Retrying cannot help."""
    category = "bad_request"


class LLMBlockedError(LLMError):
    """The provider refused or stopped generation (safety filters etc.)."""
    category = "blocked"


class LLMResponseError(LLMError):
    """The provider answered, but not in a shape we can use."""
    category = "malformed_response"


# ------------------------------------------------------------ request/response --
@dataclass(frozen=True)
class LLMRequest:
    """One text-completion request. `None` settings mean "use the configured
    default, or the provider's own default if none is configured"."""
    prompt: str
    system: str = ""
    max_output_tokens: int | None = None
    temperature: float | None = None
    # Ask the provider for a JSON document (not prose). This only constrains
    # the MIME type; callers must still parse and validate the result.
    json_output: bool = False

    def __post_init__(self):
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise LLMBadRequestError("prompt must be a non-empty string.")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise LLMBadRequestError("max_output_tokens must be positive.")


@dataclass(frozen=True)
class TokenUsage:
    """As reported by the provider; any field the provider omitted is None.
    `thinking_tokens` is billed/limited separately on some models."""
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    thinking_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    # Provider's raw stop reason (e.g. "STOP", "MAX_TOKENS"), kept for diagnosis.
    finish_reason: str = ""
    # True when generation stopped at the output limit: `text` is incomplete.
    truncated: bool = False
    usage: TokenUsage | None = None
    latency_ms: int = 0
    attempts: int = 1


# ---------------------------------------------------------------- settings --
@dataclass(frozen=True)
class LLMSettings:
    """Provider-independent knobs (env: LLM_*). Credentials and the model id
    are provider-specific and belong to the adapter, not here."""
    timeout_seconds: float = 60
    max_output_tokens: int | None = None
    max_retries: int = 2
    retry_base_seconds: float = 1
    retry_max_wait_seconds: float = 30

    def __post_init__(self):
        if self.timeout_seconds <= 0:
            raise LLMConfigError("LLM_TIMEOUT_SECONDS must be greater than 0.")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise LLMConfigError("LLM_MAX_OUTPUT_TOKENS must be greater than 0 (or 0/unset for the provider default).")
        if not 0 <= self.max_retries <= 5:
            raise LLMConfigError("LLM_MAX_RETRIES must be between 0 and 5.")
        if self.retry_base_seconds < 0 or self.retry_max_wait_seconds < 0:
            raise LLMConfigError("LLM_RETRY_BASE_SECONDS / LLM_RETRY_MAX_WAIT_SECONDS must not be negative.")

    @classmethod
    def from_django(cls):
        return cls(
            timeout_seconds=getattr(settings, "LLM_TIMEOUT_SECONDS", 60),
            max_output_tokens=getattr(settings, "LLM_MAX_OUTPUT_TOKENS", 0) or None,
            max_retries=getattr(settings, "LLM_MAX_RETRIES", 2),
            retry_base_seconds=getattr(settings, "LLM_RETRY_BASE_SECONDS", 1),
            retry_max_wait_seconds=getattr(settings, "LLM_RETRY_MAX_WAIT_SECONDS", 30),
        )


# ------------------------------------------------------------------ client --
class LLMClient:
    """Interface + the one retry loop. Adapters implement `_complete_once`
    (a single HTTP attempt that raises a normalised `LLMError` on failure) and
    never retry on their own, so retries can never be hidden or compounded."""

    name = ""

    def __init__(self, llm_settings: LLMSettings, *, model: str, sleep=time.sleep, random_fn=random.random):
        self.llm_settings = llm_settings
        self.model = model
        self._sleep = sleep          # injectable so tests never really sleep
        self._random = random_fn     # injectable so backoff is deterministic in tests

    def _complete_once(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover - interface
        raise NotImplementedError

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send one request. Raises an `LLMError` subclass on failure."""
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._complete_once(request)
            except LLMError as exc:
                exc.attempts = attempt
                wait = None
                if exc.retryable and attempt <= self.llm_settings.max_retries:
                    wait = self._wait_for(attempt, exc.retry_after)
                if wait is None:
                    # Metadata only — never the prompt, response text or key.
                    log.warning(
                        "llm call failed provider=%s model=%s category=%s status=%s attempts=%d",
                        self.name, self.model, exc.category, exc.status, attempt,
                    )
                    raise
                log.warning(
                    "llm call retrying provider=%s model=%s category=%s status=%s attempt=%d wait=%.1fs",
                    self.name, self.model, exc.category, exc.status, attempt, wait,
                )
                self._sleep(wait)
                continue
            latency_ms = int((time.monotonic() - started) * 1000)
            usage = response.usage
            log.info(
                "llm call ok provider=%s model=%s latency_ms=%d attempts=%d prompt_tokens=%s output_tokens=%s truncated=%s",
                self.name, self.model, latency_ms, attempt,
                usage.prompt_tokens if usage else None, usage.output_tokens if usage else None, response.truncated,
            )
            return replace(response, attempts=attempt, latency_ms=latency_ms)

    def _wait_for(self, attempt, retry_after):
        """Seconds to sleep before the next attempt, or None to give up now."""
        cfg = self.llm_settings
        if retry_after is not None:
            # The provider said when to come back. Honour it exactly — or, if
            # that is longer than we are willing to block, do not retry at all.
            return retry_after if retry_after <= cfg.retry_max_wait_seconds else None
        delay = min(cfg.retry_max_wait_seconds, cfg.retry_base_seconds * (2 ** (attempt - 1)))
        return delay * (0.5 + 0.5 * self._random())  # jitter in [50%, 100%] of the delay


# --------------------------------------------------------------- factory ----
# Same convention as ai.providers._PROVIDERS / content.transcription._TRANSCRIBERS,
# but by dotted path so importing this module never imports an adapter.
_CLIENTS = {"gemini": "ai.gemini.GeminiClient"}


def get_llm_client() -> LLMClient:
    """The client selected by LLM_PROVIDER, fully configured from settings.
    Raises `LLMConfigError` (before any network call) if it cannot be built."""
    name = getattr(settings, "LLM_PROVIDER", "gemini")
    try:
        path = _CLIENTS[name]
    except KeyError:
        raise LLMConfigError(f"Unknown LLM_PROVIDER {name!r}. Supported: {', '.join(sorted(_CLIENTS))}.") from None
    return import_string(path).from_settings()
