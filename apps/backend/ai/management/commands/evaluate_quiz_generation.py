"""
Opt-in evaluation harness: run the REAL quiz-generation pipeline on a lesson
text file you provide, and produce (a) deterministic metrics and (b) a blank
human review sheet. It is not part of the product and not part of the test
suite.

    python manage.py evaluate_quiz_generation --source-file lesson.txt --language ar-msa
        -> DRY RUN: validates the configuration, builds the prompt, reports its
           size. Sends NOTHING.

    python manage.py evaluate_quiz_generation --source-file lesson.txt --language ar-msa \
            --send --runs 3 --output report.json
        -> sends the file's text to the configured LLM provider (GEMINI_API_KEY,
           GEMINI_MODEL) and records every run.

Only use text you are allowed to send: on a free tier the provider may retain and
review it. The file's content is never printed; --output holds the questions.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.llm import LLMError
from ai.providers import AIProviderError
from ai.quiz_contract import QuizConfigError, QuizGenerationConfig
from ai.quiz_evaluation import REVIEW_CRITERIA, REVIEW_SCALE, deterministic_metrics, review_sheet
from ai.quiz_generation import LLMQuizProvider
from ai.quiz_prompt import PROMPT_VERSION, build_quiz_prompt

MAX_RUNS = 5


class Command(BaseCommand):
    help = "Dry-run (default) or send a lesson text through the real quiz pipeline and report metrics + a review sheet."

    def add_arguments(self, parser):
        parser.add_argument("--source-file", required=True, help="UTF-8 text file with the lesson material.")
        parser.add_argument("--title", default="", help="Lesson title (default: the file name).")
        parser.add_argument("--language", default="", help="ar-msa | ar-eg | en (default: QUIZ_LANGUAGE).")
        parser.add_argument("--runs", type=int, default=1, help=f"Generations to run with --send (1-{MAX_RUNS}).")
        parser.add_argument("--send", action="store_true", help="Actually call the provider. Without it, nothing is sent.")
        parser.add_argument("--output", default="", help="Write the full JSON report (questions + review sheet) here.")

    def handle(self, *args, **options):
        path = Path(options["source_file"])
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CommandError(f"Cannot read --source-file as UTF-8 text: {type(exc).__name__}") from None
        if not 1 <= options["runs"] <= MAX_RUNS:
            raise CommandError(f"--runs must be between 1 and {MAX_RUNS}.")
        try:
            config = (QuizGenerationConfig(language=options["language"]) if options["language"]
                      else QuizGenerationConfig.from_settings())
        except QuizConfigError as exc:
            raise CommandError(str(exc)) from None
        title = options["title"] or path.stem

        prompt = build_quiz_prompt(config, title, text)
        self.stdout.write(f"Prompt version : {PROMPT_VERSION}")
        self.stdout.write(f"Configuration  : {json.dumps(config.as_metadata(), ensure_ascii=False)}")
        self.stdout.write(f"Source         : {len(text)} characters")
        self.stdout.write(f"Prompt         : {len(prompt.system) + len(prompt.user)} characters")
        if not options["send"]:
            self.stdout.write(self.style.WARNING("DRY RUN: nothing was sent. Re-run with --send to call the provider."))
            return

        provider = LLMQuizProvider(config=config)
        runs = []
        for n in range(1, options["runs"] + 1):
            run = {"run": n}
            try:
                result = provider.generate_quiz_result({"title": title, "text": text})
            except AIProviderError as exc:
                run.update(status="failed", category=getattr(exc, "category", "unexpected"),
                           metadata=getattr(exc, "metadata", {}))
                self.stdout.write(f"run {n}: FAILED [{run['category']}]")
            except LLMError as exc:  # defensive: the provider converts these
                raise CommandError(f"[{exc.category}] {exc}") from None
            else:
                run.update(status="ok", metadata=result.metadata, questions=result.questions,
                           metrics=deterministic_metrics(result.questions, config),
                           review=review_sheet(result.questions))
                usage = result.metadata.get("usage", {})
                self.stdout.write(
                    f"run {n}: OK attempts={result.metadata.get('attempts')} tokens={usage.get('total_tokens')} "
                    f"metrics={json.dumps(run['metrics'], ensure_ascii=False)}")
            runs.append(run)

        if options["output"]:
            report = {"prompt_version": PROMPT_VERSION, "config": config.as_metadata(), "source_chars": len(text),
                      "review_scale": REVIEW_SCALE, "review_criteria": REVIEW_CRITERIA, "runs": runs}
            Path(options["output"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"Report written to {options['output']}")
        passed = sum(r["status"] == "ok" for r in runs)
        self.stdout.write(self.style.SUCCESS(f"{passed}/{len(runs)} runs passed deterministic validation. "
                                             "Semantic quality still needs human review (see review_criteria)."))
