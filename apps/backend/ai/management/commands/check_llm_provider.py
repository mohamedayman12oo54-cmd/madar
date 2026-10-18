"""
Connectivity / configuration check for the configured LLM provider (ai/llm.py).

    python manage.py check_llm_provider                 # one tiny live request
    python manage.py check_llm_provider --config-only   # validate settings, no network

This is NOT quiz generation and touches no database content: the only text it
ever sends is the fixed, harmless probe below — never a lesson, transcript or
anything about a student. It makes at most `1 + LLM_MAX_RETRIES` requests, so on
a free tier it costs a handful of tokens. It never prints the API key.
"""
from django.core.management.base import BaseCommand, CommandError

from ai.llm import LLMError, LLMRequest, get_llm_client

PROBE_PROMPT = "Reply with the single word: pong"


class Command(BaseCommand):
    help = "Verifies the LLM provider configuration and (unless --config-only) that it can be reached."

    def add_arguments(self, parser):
        parser.add_argument(
            "--config-only", action="store_true",
            help="Only validate configuration; make no network request.",
        )

    def handle(self, *args, **options):
        try:
            client = get_llm_client()
        except LLMError as exc:
            raise CommandError(f"[{exc.category}] {exc}") from None

        cfg = client.llm_settings
        self.stdout.write(f"Provider : {client.name}")
        self.stdout.write(f"Model    : {client.model}")
        self.stdout.write("API key  : configured (value not shown)")
        self.stdout.write(
            f"Timeout  : {cfg.timeout_seconds}s per request, up to {cfg.max_retries} retries "
            f"(max wait {cfg.retry_max_wait_seconds}s)"
        )
        self.stdout.write(f"Max output tokens: {cfg.max_output_tokens or 'provider default'}")

        if options["config_only"]:
            self.stdout.write(self.style.SUCCESS("Configuration is valid. No request was sent (--config-only)."))
            return

        self.stdout.write("Sending a harmless connectivity probe (no lesson or student data)...")
        try:
            response = client.complete(LLMRequest(prompt=PROBE_PROMPT))
        except LLMError as exc:
            suffix = f" (after {exc.attempts} attempts)" if exc.attempts > 1 else ""
            raise CommandError(f"Connectivity check FAILED [{exc.category}]{suffix}: {exc}") from None

        usage = response.usage
        tokens = (
            f"prompt={usage.prompt_tokens} output={usage.output_tokens} total={usage.total_tokens}"
            + (f" thinking={usage.thinking_tokens}" if usage.thinking_tokens is not None else "")
            if usage else "not reported by the provider"
        )
        reply = " ".join(response.text.split())[:80]
        self.stdout.write(self.style.SUCCESS(
            f"Connectivity OK — {response.latency_ms} ms, {response.attempts} attempt(s), "
            f"finish={response.finish_reason or 'n/a'}."
        ))
        self.stdout.write(f"Tokens   : {tokens}")
        self.stdout.write(f"Reply    : {reply!r}")
