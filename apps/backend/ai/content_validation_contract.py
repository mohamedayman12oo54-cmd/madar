"""
The Transcript Content Validation CONTRACT: what counts as a valid
classification response. Mirrors ai/quiz_contract.py's `parse_generated_quiz`,
but for the much smaller, fixed `is_educational` / `category` / `confidence` /
`reason` schema. No prompt text and no provider calls live here — the prompt
is ai/content_validation_prompt.py, orchestration is ai/quiz_generation.py.
"""
import json
import re
from dataclasses import dataclass, field

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S | re.I)
MAX_CATEGORY_CHARS = 100
MAX_REASON_CHARS = 500


@dataclass
class ContentValidationResult:
    """Outcome of validating the model's raw classification output.
    `is_educational` stays `None` until every field has checked out — so a
    malformed response can never be mistaken for a classification, in either
    direction."""
    is_educational: bool | None = None
    category: str = ""
    confidence: float | None = None
    reason: str = ""
    errors: list = field(default_factory=list)

    @property
    def ok(self):
        return self.is_educational is not None and not self.errors


def parse_validation_response(raw) -> ContentValidationResult:
    """Parse and validate the model's raw text. Never repairs content: output
    that violates the contract is reported, not fixed. (The only tolerance is
    a single surrounding ```json fence, which is packaging, not content.)"""
    out = ContentValidationResult()
    text = (raw or "").strip()
    fence = _FENCE.match(text)
    if fence:
        text = fence.group(1)
    if not text:
        out.errors.append("output is empty")
        return out
    try:
        data = json.loads(text)
    except ValueError:
        out.errors.append("output is not valid JSON")
        return out
    if not isinstance(data, dict):
        out.errors.append("output must be a JSON object")
        return out

    is_educational = data.get("is_educational")
    if not isinstance(is_educational, bool):
        out.errors.append('"is_educational" must be a boolean')
    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        out.errors.append('"confidence" must be a number from 0.0 to 1.0')
    category = data.get("category")
    if not isinstance(category, str) or not category.strip():
        out.errors.append('"category" must be a non-empty string')
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        out.errors.append('"reason" must be a non-empty string')

    if out.errors:
        return out
    out.is_educational = is_educational
    out.category = category.strip()[:MAX_CATEGORY_CHARS]
    out.confidence = float(confidence)
    out.reason = reason.strip()[:MAX_REASON_CHARS]
    return out
